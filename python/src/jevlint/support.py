"""
Reading files, writing JSON, and the two facts about the environment the rest of
the package needs: where a key comes from, and why a call did not come back.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from .errors import JevLintError
from .text import Text
from .typesafe.errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
    TypeSafeError,
    UnprocessableEntityError,
)


class Json:
    @staticmethod
    def contents(path: str) -> str:
        """
        The file's text, or an error naming why it could not be read.

        A directory is named as one. Reading it otherwise fails deeper in with a
        message about the file's contents, which is a file nobody wrote.
        """
        if Path(path).is_dir():
            raise JevLintError.of(JevLintError.NOT_FOUND, Text.of('file.is_a_directory', {'path': path}))

        try:
            return Path(path).read_text(encoding='utf-8')
        except OSError:
            raise JevLintError.of(JevLintError.NOT_FOUND, Text.of('file.unreadable', {'path': path})) from None

    @staticmethod
    def read_file(path: str) -> dict[str, Any]:
        return Json.decode(Json.contents(path), path)

    @staticmethod
    def decode(contents: str, what: str = 'input') -> dict[str, Any]:
        try:
            decoded = json.loads(contents)
        except ValueError as error:
            raise JevLintError.of(JevLintError.INVALID_JSON, Text.of('json.invalid', {
                'what': what,
                'detail': str(error),
            })) from None

        if not isinstance(decoded, (dict, list)):
            raise JevLintError.of(JevLintError.INVALID_JSON, Text.of('json.not_an_object', {'what': what}))

        return decoded

    @staticmethod
    def is_list(contents: str) -> bool:
        """
        Whether the text was written as a JSON array.

        `{"0":"a"}` and `["a"]` decode to different things here, but the check is
        on the text in all three implementations so they agree about what a file
        holds however their parsers differ.
        """
        return re.match(r'\s*\[', contents) is not None

    @staticmethod
    def encode(value: Any) -> str:
        try:
            return _write(value, 4, '')
        except (TypeError, ValueError) as error:
            raise JevLintError.of(
                JevLintError.INVALID_JSON,
                Text.of('json.report_unencodable', {'detail': str(error)}),
            ) from None

    @staticmethod
    def encode_safely(value: Any) -> str:
        """
        The same, for the error document.

        The handler cannot fail: a raise here leaves the run with no output at
        all, and `command` is required by spec/error.schema.json, so the one
        document written without going through the encoder carries it too.
        """
        try:
            return Json.encode(value)
        except JevLintError:
            return '{"error":{"kind":"internal","message":"The error could not be written as JSON.","command":"check"}}'

    @staticmethod
    def inline(value: Any) -> str:
        """A stable, readable rendering of a state or criteria value."""
        if isinstance(value, str):
            return value

        return _write(value, 0, '')


def _number(value: int | float) -> str:
    """
    A number as the report writes one.

    A whole float is written without its fraction, because the other two
    implementations do: a probability that lands on 1.0 reads `1` in all three,
    and a report is compared between them as one document.
    """
    if isinstance(value, int):
        return str(value)

    if value != value or value in (float('inf'), float('-inf')):
        return 'null'

    return str(int(value)) if value.is_integer() and abs(value) < 1e21 else repr(value)


def _write(value: Any, indent: int, prefix: str) -> str:
    if value is None:
        return 'null'

    if isinstance(value, bool):
        return 'true' if value else 'false'

    if isinstance(value, (int, float)):
        return _number(value)

    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)

    inner = prefix + ' ' * indent
    opening = '' if indent == 0 else '\n' + inner
    closing = '' if indent == 0 else '\n' + prefix
    between = ',' if indent == 0 else ',\n' + inner
    colon = ':' if indent == 0 else ': '

    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return '[]'

        written = between.join(_write(item, indent, inner) for item in value)

        return '[' + opening + written + closing + ']'

    if isinstance(value, dict):
        if len(value) == 0:
            return '{}'

        written = between.join(
            json.dumps(str(key), ensure_ascii=False) + colon + _write(item, indent, inner)
            for key, item in value.items()
        )

        return '{' + opening + written + closing + '}'

    raise TypeError(f'{type(value).__name__} is not a value this can write as JSON')


_PHP_ESCAPES = {
    '"': '\\"',
    '\\': '\\\\',
    '/': '\\/',
    '\b': '\\b',
    '\f': '\\f',
    '\n': '\\n',
    '\r': '\\r',
    '\t': '\\t',
}


def encode_like_php(value: Any) -> str:
    """
    JSON as PHP's `json_encode` writes it with no flags.

    One digest in the report is a hash over this text, and the implementations
    have to agree on it or two runs of the same catalogue compare as different
    catalogues. PHP escapes `/` and every character above ASCII.
    """
    if value is None:
        return 'null'

    if isinstance(value, bool):
        return 'true' if value else 'false'

    if isinstance(value, (int, float)):
        return _php_number(value)

    if isinstance(value, str):
        return _php_quote(value)

    if isinstance(value, list):
        return '[' + ','.join(encode_like_php(item) for item in value) + ']'

    if isinstance(value, dict):
        return '{' + ','.join(
            f'{_php_quote(str(key))}:{encode_like_php(item)}' for key, item in value.items()
        ) + '}'

    return 'null'


def _php_number(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)

    if value != value or value in (float('inf'), float('-inf')):
        return '0'

    return repr(value)


def _php_quote(text: str) -> str:
    out = ['"']

    for character in text:
        escaped = _PHP_ESCAPES.get(character)

        if escaped is not None:
            out.append(escaped)

            continue

        code = ord(character)

        if code < 0x20:
            out.append(f'\\u{code:04x}')
        elif code < 0x80:
            out.append(character)
        else:
            # Above ASCII, PHP writes the UTF-16 code units, so a character
            # outside the basic plane comes out as its surrogate pair.
            units = character.encode('utf-16-be')
            out += [f'\\u{(units[i] << 8 | units[i + 1]):04x}' for i in range(0, len(units), 2)]

    return ''.join(out) + '"'


class Env:
    """
    Reads a key from the environment, falling back to a `.env` in the working
    directory or the one `--env-file` names. The client reads the environment
    itself; this exists so a `.env` in the directory you run from is enough.
    """

    _loaded: dict[str, str] | None = None

    _named: str | None = None

    @classmethod
    def get(cls, name: str) -> str | None:
        # A named file is where the key comes from, whether or not it holds one.
        # Falling back to the shell sent a run whose caller had pointed at one
        # account to whichever account the environment happened to carry.
        if cls._named is not None:
            return cls._from_file().get(name)

        value = os.environ.get(name)

        if value:
            return value

        return cls._from_file().get(name)

    @classmethod
    def file(cls) -> str | None:
        """The file `--env-file` named, for an error message that can say so."""
        return cls._named

    @classmethod
    def hydrate(cls) -> None:
        """Put what a `.env` holds into the environment, without overwriting it."""
        for name, value in cls._from_file().items():
            # The client reads the environment, so a named file has to reach it
            # there or the call goes out with whatever the shell held.
            if cls._named is not None or name not in os.environ:
                os.environ[name] = value

    @classmethod
    def use_file(cls, path: str | None) -> None:
        cls._loaded = None
        cls._named = None

        if path is None:
            return

        # Somebody who passed --env-file wants that file. Falling back to the
        # ambient environment sends them looking for a variable when what they
        # mistyped is a path.
        if not Path(path).exists():
            raise JevLintError.of(JevLintError.NOT_FOUND, Text.of('env.no_such_file', {'path': path}))

        if not Path(path).is_file():
            raise JevLintError.of(JevLintError.NOT_FOUND, Text.of('env.not_a_file', {'path': path}))

        try:
            contents = Path(path).read_text(encoding='utf-8')
        except OSError:
            raise JevLintError.of(JevLintError.NOT_FOUND, Text.of('env.unreadable', {'path': path})) from None

        cls._named = path
        cls._loaded = _read_env(contents)

    @classmethod
    def reset(cls) -> None:
        """Forget what is loaded, so a test can point at another file inside one process."""
        cls._loaded = None
        cls._named = None

    @classmethod
    def _from_file(cls) -> dict[str, str]:
        if cls._loaded is not None:
            return cls._loaded

        path = Path.cwd() / '.env'
        cls._loaded = _read_env(path.read_text(encoding='utf-8')) if path.is_file() else {}

        return cls._loaded


def _read_env(contents: str) -> dict[str, str]:
    values: dict[str, str] = {}

    for raw in contents.splitlines():
        line = raw.strip()

        if line == '' or line.startswith('#') or '=' not in line:
            continue

        name, _, value = line.partition('=')
        values[name.strip()] = value.strip().lstrip('"\'').rstrip('"\'')

    return values


class Cause:
    """
    Why a call did not come back, as a word.

    A caller deciding whether to retry has to tell a wrong key from a dropped
    connection, and the message is English written for a person.
    """

    # Nothing failed; the answer that came back was unusable
    ANSWER = 'answer'

    @staticmethod
    def is_settled(error: TypeSafeError) -> bool:
        """
        Whether a second call would fail the same way.

        A wrong key or a denied account answers every call identically, so a run
        that keeps going spends the rest of its calls learning what the first one
        already said.
        """
        return isinstance(error, (AuthenticationError, PermissionDeniedError))

    @staticmethod
    def of(error: TypeSafeError) -> str:
        for kind, word in (
            (AuthenticationError, 'auth'),
            (PermissionDeniedError, 'permission'),
            (RateLimitError, 'rate-limit'),
            (APITimeoutError, 'timeout'),
            (APIConnectionError, 'connection'),
            ((BadRequestError, UnprocessableEntityError), 'request'),
            (InternalServerError, 'server'),
            (APIError, 'api'),
        ):
            if isinstance(error, kind):
                return word

        return 'api'


def is_letter_or_number(character: str) -> bool:
    """Whether a character is a letter or a digit in any script, as `\\p{L}\\p{N}` matches one."""
    return unicodedata.category(character)[0] in ('L', 'N')


def has_letter(text: str) -> bool:
    """Whether anything in the text is a letter in any script."""
    return any(unicodedata.category(character).startswith('L') for character in text)


def is_invisible(character: str) -> bool:
    """
    Whether a character carries no word.

    `strip()` knows a handful of ASCII characters. A non-breaking space, a
    zero-width space or an ideographic space is an instruction carrying no words,
    and the model answers a blank question instead of yours.
    """
    return character.isspace() or unicodedata.category(character)[0] in ('Z', 'C')


def bytes_of(text: str) -> int:
    """The length of the text in bytes."""
    return len(text.encode('utf-8'))
