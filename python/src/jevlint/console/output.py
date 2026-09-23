"""Writes to stdout and stderr, and knows whether a terminal is reading."""
from __future__ import annotations

import os
import sys
from contextlib import suppress


class Output:
    def __init__(self, coloured: bool) -> None:
        self._coloured = coloured

    @staticmethod
    def make(force_off: bool = False) -> Output:
        return Output(not force_off and sys.stdout.isatty() and os.environ.get('NO_COLOR') is None)

    def colour(self) -> bool:
        return self._coloured

    def write(self, text: str) -> None:
        """A stream already torn down raises here; a pipe closing is handled by the binary."""
        # Nothing to do about either: the reader has gone.
        with suppress(BrokenPipeError, ValueError, OSError):
            sys.stdout.write(text)

    def line(self, text: str = '') -> None:
        self.write(f'{text}\n')

    def error(self, text: str) -> None:
        painted = '\u001b[31m' + text + '\u001b[0m' if self._coloured else text
        sys.stderr.write(painted + '\n')
