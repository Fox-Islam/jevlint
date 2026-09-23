"""
What a repository has decided about its own findings.

The acceptances live beside the query and not inside it: the API rejects an
unknown key at the top of a request, and a query file that cannot be sent is no
longer the thing being checked.

An absent file is an empty config. A repository that has never accepted anything
should not have to say so.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import JevLintError
from .support import Json
from .text import Text


class Acceptance:
    """One finding somebody has read and decided to live with."""

    def __init__(self, check: str, question: str | None, reason: str) -> None:
        self.check = check
        self.question = question
        self.reason = reason

    def covers(self, check: str, target: str) -> bool:
        if self.check != check:
            return False

        return self.question is None or self.question == '*' or self.question == target


class Config:
    FILE = '.jevlint.json'

    def __init__(self, accept: list[Acceptance], source: str | None, jev: str | None = None) -> None:
        self.accept = accept
        self.source = source
        self.jev = jev

    @staticmethod
    def empty() -> Config:
        return Config([], None)

    @staticmethod
    def discover(explicit: str | None, query_path: str) -> Config:
        """Find the config beside the query, then in the working directory."""
        if explicit is not None:
            if not Path(explicit).is_file():
                raise JevLintError.of(JevLintError.CONFIG, Text.of('config.not_found', {'path': explicit}))

            return Config.load(explicit)

        for candidate in (Path(query_path).parent / Config.FILE, Path.cwd() / Config.FILE):
            if candidate.is_file():
                return Config.load(str(candidate))

        return Config.empty()

    @staticmethod
    def load(path: str) -> Config:
        data = Json.read_file(path)

        # A misspelled `accept` leaves the whole block covering nothing, which is
        # the failure this file exists to make visible.
        unknown = [key for key in data if key not in ('accept', 'jev')]

        if len(unknown) > 0:
            raise JevLintError.of(JevLintError.CONFIG, Text.of('config.unknown_setting', {
                'path': path,
                'names': '", "'.join(unknown),
            }))

        accept = data.get('accept')

        if accept is None:
            accept = []

        if not isinstance(accept, (list, dict)):
            raise JevLintError.of(JevLintError.CONFIG, Text.of('config.accept_not_a_list', {'path': path}))

        accepted: list[Acceptance] = []
        entries = accept.items() if isinstance(accept, dict) else enumerate(accept)

        for index, entry in entries:
            if not isinstance(entry, dict):
                raise JevLintError.of(JevLintError.CONFIG, Text.of('config.entry_not_an_object', {
                    'path': path,
                    'entry': index,
                }))

            check = entry.get('check')
            reason = entry.get('reason')
            question = entry.get('question')

            if not isinstance(check, str) or check == '':
                raise JevLintError.of(JevLintError.CONFIG, Text.of('config.entry_names_no_check', {
                    'path': path,
                    'entry': index,
                }))

            # An acceptance is a judgement somebody made. Recording why is what
            # separates it from switching the check off.
            if not isinstance(reason, str) or reason.strip() == '':
                raise JevLintError.of(JevLintError.CONFIG, Text.of('config.acceptance_needs_a_reason', {
                    'path': path,
                    'check': check,
                }))

            accepted.append(Acceptance(check, question if isinstance(question, str) else None, reason))

        return Config(accepted, path, _jev_of(data, path))

    def reason_for(self, check: str, target: str) -> str | None:
        return next(
            (acceptance.reason for acceptance in self.accept if acceptance.covers(check, target)),
            None,
        )

    def unknown(self, known: list[str]) -> list[str]:
        """Check ids named in the config that the catalogue does not hold."""
        return list(dict.fromkeys(
            acceptance.check for acceptance in self.accept if acceptance.check not in known
        ))


def _jev_of(data: dict[str, Any], path: str) -> str | None:
    """
    The Jev version this repository writes its queries for.

    A query file carries no record of the build it will be sent to, so the
    version a run checks against comes from here.
    """
    jev = data.get('jev')

    if jev is None:
        return None

    if not isinstance(jev, str) or jev == '':
        raise JevLintError.of(JevLintError.CONFIG, Text.of('config.jev_not_a_version', {'path': path}))

    return jev
