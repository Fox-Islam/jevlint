"""The bare minimum that reads `--name=value`, `--flag` and positionals."""
from __future__ import annotations

import math
import re

from ..errors import JevLintError
from ..text import Text

_NUMERIC = re.compile(r'^\s*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\s*$')


class Args:
    def __init__(
        self,
        positional: list[str],
        options: dict[str, str | bool],
        malformed: list[str] | None = None,
        repeated: list[str] | None = None,
    ) -> None:
        self.positional = positional
        self._options = options
        # options written with one dash
        self.malformed = malformed or []
        # options given more than once
        self.repeated = repeated or []

    @staticmethod
    def parse(argv: list[str]) -> Args:
        positional: list[str] = []
        options: dict[str, str | bool] = {}
        malformed: list[str] = []
        repeated: list[str] = []

        for argument in argv:
            if not argument.startswith('--'):
                # `-static-only`, written with one dash, parsed as a positional,
                # so the option guard never saw it and the run paid for the calls
                # the caller believed they had switched off.
                if argument.startswith('-') and len(argument) > 1:
                    malformed.append(argument)

                    continue

                positional.append(argument)

                continue

            body = argument[2:]
            name, separator, value = body.partition('=')

            if separator == '':
                name, value = body, True

            if name in options and name not in repeated:
                repeated.append(name)

            options[name] = value

        return Args(positional, options, malformed, repeated)

    def has(self, name: str) -> bool:
        return name in self._options

    def flag(self, name: str) -> bool:
        value = self._options.get(name)

        if value is None:
            return False

        # `--strict=false` read as true, which is the opposite of what anybody
        # typing it means. A switch takes no value.
        if value is not True and value != '':
            raise JevLintError.of(
                JevLintError.USAGE,
                Text.of('args.switch_takes_no_value', {'option': name}),
            )

        return True

    def value(self, name: str, fallback: str | None = None) -> str | None:
        value = self._options.get(name)

        return value if isinstance(value, str) else fallback

    def int(self, name: str, fallback: int, most: int = 20) -> int:
        """
        A count, with a ceiling.

        Every count here multiplies calls, and a typed `--repeats=50` is a bill
        nobody meant to run. The limit is refused out loud, naming what the most
        is.
        """
        value = self.value(name)

        if value is None:
            return fallback

        # Falling back to the default here runs a threshold the caller believes
        # they raised, and says nothing about it.
        if _NUMERIC.match(value) is None:
            raise JevLintError.of(
                JevLintError.USAGE,
                Text.of('args.not_a_number', {'option': name, 'given': value}),
            )

        whole = math.trunc(float(value))

        # `1.9` truncates to 1 and a huge value saturates, both in silence, so the
        # threshold that runs is not the one the caller wrote.
        if str(whole) != re.sub(r'^\+', '', value):
            raise JevLintError.of(
                JevLintError.USAGE,
                Text.of('args.not_a_whole_number', {'option': name, 'given': value}),
            )

        if whole < 1:
            raise JevLintError.of(
                JevLintError.USAGE,
                Text.of('args.not_a_count', {'option': name, 'given': value}),
            )

        if whole > most:
            raise JevLintError.of(
                JevLintError.USAGE,
                Text.of('args.above_the_most', {'option': name, 'given': value, 'most': most}),
            )

        return whole

    def seconds(self, name: str, fallback: float) -> float:
        """
        A duration in seconds, which can carry a fraction.

        The count reader calls `--timeout=0.5` "not a count", which is a message
        about the wrong kind of number.
        """
        value = self.value(name)

        if value is None:
            return fallback

        if _NUMERIC.match(value) is None or float(value) <= 0:
            raise JevLintError.of(
                JevLintError.USAGE,
                Text.of('args.not_seconds', {'option': name, 'given': value}),
            )

        return float(value)

    def argument(self, index: int) -> str | None:
        return self.positional[index] if index < len(self.positional) else None

    def unknown(self, known: list[str]) -> list[str]:
        """
        Options the caller did not list.

        A mistyped flag is otherwise indistinguishable from one left out, so
        `--static-onlyy` spends money on a run the caller takes for free.
        """
        return [name for name in self._options if name not in known]
