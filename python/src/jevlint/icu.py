"""
The subset of ICU MessageFormat the message files use.

Babel supplies the CLDR categories and number patterns, so every locale it has
data for brings its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from babel import Locale, UnknownLocaleError
from babel.numbers import format_decimal

Values = dict[str, Any]


class PatternError(Exception):
    """A pattern that will not parse, so the caller can print it unformatted."""


@dataclass(frozen=True)
class NumberStyle:
    """`integer`, or a skeleton naming how many fraction digits to print."""

    kind: str

    digits: int = 0


@dataclass
class Node:
    kind: str

    text: str = ''

    name: str = ''

    style: NumberStyle | None = None

    branches: dict[str, list[Node]] = field(default_factory=dict)

    exact: dict[float, list[Node]] = field(default_factory=dict)


_parsed: dict[str, list[Node]] = {}


def format(locale: str, pattern: str, values: Values | None = None) -> str:
    """
    One pattern, with its arguments filled in.

    Raises PatternError where the pattern is not MessageFormat this can read.
    """
    nodes = _parsed.get(pattern)

    if nodes is None:
        nodes = parse(pattern)
        _parsed[pattern] = nodes

    return _render(nodes, locale, values or {}, None)


def parses(pattern: str) -> bool:
    """Whether a pattern parses at all, for the test that holds the file to its job."""
    try:
        parse(pattern)
    except PatternError:
        return False

    return True


def arguments_of(pattern: str) -> list[str]:
    """
    Every argument name a pattern reads, so a caller can tell a missing value
    from a pattern that never wanted one.
    """
    names: list[str] = []

    def walk(nodes: list[Node]) -> None:
        for node in nodes:
            if node.kind in ('argument', 'plural', 'select') and node.name not in names:
                names.append(node.name)

            for branch in list(node.exact.values()) + list(node.branches.values()):
                walk(branch)

    walk(parse(pattern))

    return names


class _Reader:
    def __init__(self, source: str) -> None:
        self.source = source
        self.at = 0

    def peek(self, offset: int = 0) -> str:
        position = self.at + offset

        return self.source[position] if 0 <= position < len(self.source) else ''

    def done(self) -> bool:
        return self.at >= len(self.source)


def parse(pattern: str) -> list[Node]:
    reader = _Reader(pattern)
    nodes = _read_message(reader, False)

    if not reader.done():
        raise PatternError(f'Unexpected "{reader.peek()}" at {reader.at}.')

    return nodes


def _read_message(reader: _Reader, nested: bool) -> list[Node]:
    """
    Text up to the end of the pattern, or to the `}` that closes the branch this
    is inside. `#` is an argument only inside a plural branch.
    """
    nodes: list[Node] = []
    text = ''

    def flush() -> None:
        nonlocal text

        if text != '':
            nodes.append(Node('text', text=text))
            text = ''

    while not reader.done():
        char = reader.peek()

        if char == '}' and nested:
            break

        if char == '{':
            flush()
            nodes.append(_read_argument(reader))

            continue

        if char == '#' and nested:
            flush()
            nodes.append(Node('hash'))
            reader.at += 1

            continue

        if char == "'":
            text += _read_quoted(reader)

            continue

        text += char
        reader.at += 1

    flush()

    return nodes


def _read_quoted(reader: _Reader) -> str:
    """
    The ICU apostrophe rules, which are what a translator gets wrong first.

    `''` is one apostrophe. A lone `'` opens a quoted run only where it stands in
    front of a `{`, `}`, `#` or `|`, so `the SDK's` needs no escaping. Inside an
    open quote `''` is again one apostrophe and does not close it, which is why a
    run of braces has to be quoted together as `'}}'` and not as `'}''}'`.
    """
    if reader.peek(1) == "'":
        reader.at += 2

        return "'"

    if reader.peek(1) not in ('{', '}', '#', '|'):
        reader.at += 1

        return "'"

    reader.at += 1
    text = ''

    while not reader.done():
        if reader.peek() == "'":
            if reader.peek(1) == "'":
                text += "'"
                reader.at += 2

                continue

            reader.at += 1

            return text

        text += reader.peek()
        reader.at += 1

    # An unterminated quote runs to the end of the pattern, which is what ICU does.
    return text


def _read_argument(reader: _Reader) -> Node:
    reader.at += 1
    _skip_space(reader)
    name = _read_name(reader)
    _skip_space(reader)

    if reader.peek() == '}':
        reader.at += 1

        return Node('argument', name=name)

    _expect(reader, ',')
    _skip_space(reader)
    kind = _read_name(reader)
    _skip_space(reader)

    if kind == 'plural':
        _expect(reader, ',')

        return _read_plural(reader, name)

    if kind == 'select':
        _expect(reader, ',')

        return _read_select(reader, name)

    if kind != 'number':
        raise PatternError(f'"{kind}" is not an argument type this reads.')

    if reader.peek() == '}':
        reader.at += 1

        return Node('argument', name=name)

    _expect(reader, ',')
    _skip_space(reader)
    style = _read_style(reader)
    _skip_space(reader)
    _expect(reader, '}')

    return Node('argument', name=name, style=style)


def _read_style(reader: _Reader) -> NumberStyle:
    """
    `integer`, or the fraction-digit part of a number skeleton.

    `::.00` is two places, `::.` is none. The rest of the skeleton syntax is not
    read, because a pattern using it would format differently here from the
    implementation it was written against.
    """
    raw = ''

    while not reader.done() and reader.peek() != '}':
        raw += reader.peek()
        reader.at += 1

    raw = raw.strip()

    if raw == 'integer':
        return NumberStyle('integer')

    if raw.startswith('::'):
        skeleton = raw[2:].strip()

        if skeleton.startswith('.') and set(skeleton[1:]) <= {'0'}:
            return NumberStyle('fraction', len(skeleton) - 1)

    raise PatternError(f'"{raw}" is not a number style this reads.')


def _read_plural(reader: _Reader, name: str) -> Node:
    node = Node('plural', name=name)

    while True:
        _skip_space(reader)

        if reader.peek() == '}':
            reader.at += 1

            break

        if reader.done():
            raise PatternError(f'The plural on "{name}" is not closed.')

        if reader.peek() == '=':
            reader.at += 1
            digits = _read_name(reader)
            _skip_space(reader)
            node.exact[float(digits)] = _read_branch(reader)

            continue

        keyword = _read_name(reader)
        _skip_space(reader)
        node.branches[keyword] = _read_branch(reader)

    if 'other' not in node.branches:
        raise PatternError(f'The plural on "{name}" has no "other" branch.')

    return node


def _read_select(reader: _Reader, name: str) -> Node:
    node = Node('select', name=name)

    while True:
        _skip_space(reader)

        if reader.peek() == '}':
            reader.at += 1

            break

        if reader.done():
            raise PatternError(f'The select on "{name}" is not closed.')

        keyword = _read_name(reader)
        _skip_space(reader)
        node.branches[keyword] = _read_branch(reader)

    if 'other' not in node.branches:
        raise PatternError(f'The select on "{name}" has no "other" branch.')

    return node


def _read_branch(reader: _Reader) -> list[Node]:
    _expect(reader, '{')
    nodes = _read_message(reader, True)
    _expect(reader, '}')

    return nodes


def _read_name(reader: _Reader) -> str:
    name = ''

    while not reader.done() and not reader.peek().isspace() and reader.peek() not in ('{', '}', ','):
        name += reader.peek()
        reader.at += 1

    if name == '':
        raise PatternError(f'Expected a name at {reader.at}.')

    return name


def _skip_space(reader: _Reader) -> None:
    while not reader.done() and reader.peek().isspace():
        reader.at += 1


def _expect(reader: _Reader, char: str) -> None:
    if reader.peek() != char:
        raise PatternError(f'Expected "{char}" at {reader.at}, found "{reader.peek()}".')

    reader.at += 1


def _render(nodes: list[Node], locale: str, values: Values, hash_value: float | None) -> str:
    """`hash_value` is the plural argument the branch belongs to, where it is inside one."""
    return ''.join(_render_node(node, locale, values, hash_value) for node in nodes)


def _render_node(node: Node, locale: str, values: Values, hash_value: float | None) -> str:
    if node.kind == 'text':
        return node.text

    if node.kind == 'hash':
        # The plural's own value, through the locale's default number format, so
        # a count in the thousands is grouped.
        return '#' if hash_value is None else _number(locale, hash_value, None)

    if node.kind == 'argument':
        if node.name not in values:
            return '{' + node.name + '}'

        return _argument(locale, values[node.name], node.style)

    if node.kind == 'plural':
        if node.name not in values:
            return '{' + node.name + '}'

        value = _as_number(values[node.name])
        branch = node.exact.get(value)

        if branch is None:
            branch = node.branches.get(_category(locale, value), node.branches.get('other', []))

        return _render(branch, locale, values, value)

    if node.name not in values:
        return '{' + node.name + '}'

    chosen = '' if values[node.name] is None else str(values[node.name])
    branch = node.branches.get(chosen, node.branches.get('other', []))

    return _render(branch, locale, values, hash_value)


def _argument(locale: str, value: Any, style: NumberStyle | None) -> str:
    if value is None:
        return ''

    if style is not None:
        return _number(locale, _as_number(value), style)

    # An argument with no type is printed, not formatted: `{tokens}` arrives
    # already grouped by its caller, and putting it through a number format again
    # would group it a second time or round its fraction away.
    if isinstance(value, bool):
        return '1' if value else ''

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value)


def _as_number(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0

    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


_locales: dict[str, Locale] = {}


def _locale(locale: str) -> Locale:
    """
    A locale as the message files name it, as CLDR names it.

    A tag Babel has no data for falls back to English, because raising here would
    take a report down over the language it was going to be printed in.
    """
    found = _locales.get(locale)

    if found is None:
        try:
            found = Locale.parse(locale.replace('-', '_'))
        except (UnknownLocaleError, ValueError, TypeError):
            found = Locale.parse('en')

        _locales[locale] = found

    return found


def _number(locale: str, value: float, style: NumberStyle | None) -> str:
    """
    CLDR's own number format, which rounds half to even.

    The two modes disagree on every exact half: a 0.715 reading prints 0.72 under
    both, and 0.725 prints 0.72 here and 0.73 under half away from zero.
    """
    if style is None:
        pattern = '#,##0.###'
    elif style.kind == 'integer':
        pattern = '#,##0'
    else:
        pattern = '#,##0.' + '0' * style.digits if style.digits > 0 else '#,##0'

    return format_decimal(Decimal(repr(value)), format=pattern, locale=_locale(locale))


def _category(locale: str, value: float) -> str:
    return _locale(locale).plural_form(int(value) if float(value).is_integer() else value)
