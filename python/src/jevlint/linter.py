"""
One run of the linter, from a query to a report.

The two linters are separately usable, and this puts them in the order a run
needs, stamps the report with the catalogue that produced it, validates the
narrowing against the catalogue, and records what the run left out. The console
commands go through here, so a caller in Python gets the report the CLI prints.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from .catalogue import Catalogue, Check
from .config import Config
from .errors import JevLintError
from .model_linter import ModelLinter
from .query import Query
from .report import Report
from .static_linter import StaticLinter
from .support import Env
from .text import Text
from .typesafe import Client

_PINNED_BUILD = re.compile(r'^jev-(\d+(?:\.\d+)*)$')


class ClientFactory:
    """
    Builds the client the checks are asked through.

    The client reads the environment itself; this adds a `.env` in the working
    directory and turns a missing key into an error at startup instead of at the
    first call, so a run either costs nothing or completes.
    """

    @staticmethod
    def make(
        model: str | None = None,
        open_router: bool = False,
        timeout: float | None = None,
        rules_run_alone: bool = False,
    ) -> Client:
        Env.hydrate()

        name = 'OPENROUTER_API_KEY' if open_router else 'TYPESAFE_API_KEY'
        key = Env.get(name)

        if key is None:
            # Only `check` has a path that needs no key. Offering it to `probe`
            # sent a reader to a mode probe does not have.
            raise JevLintError.of(JevLintError.AUTH, Text.of('auth.no_key', {
                'name': name,
                'where': Env.file() or Text.of('auth.env_default'),
                'rules_alone': 'yes' if rules_run_alone else 'no',
            }))

        return Client(
            api_key=key,
            provider='openrouter' if open_router else 'typesafe',
            default_model=model,
            timeout=timeout,
        )


@dataclass(frozen=True)
class _Settings:
    catalogue: Catalogue

    # built when the run reaches a check that needs it, so a run of only rules needs no key
    client: Callable[[], Client] | None

    config: Config

    # check ids this run includes, or all of them when empty
    only: tuple[str, ...] = ()

    check_state: bool = True

    repeats: int = 1

    report_cleared: bool = False

    max_state_chars: int = 20000

    asked_through: str | None = None


class Linter:
    def __init__(self, settings: _Settings) -> None:
        self._settings = settings

    @staticmethod
    def make(client: Client, catalogue: Catalogue | None = None, config: Config | None = None) -> Linter:
        """
        A linter that asks its model checks through `client`.

        Any client will do, including one given a fake transport, which is how the
        tests here run the model path without calling anything.
        """
        return Linter(_Settings(
            catalogue=catalogue or Catalogue.load(),
            client=lambda: client,
            config=config or Config.empty(),
        ))

    @staticmethod
    def from_environment(
        model: str | None = None,
        open_router: bool = False,
        timeout: float | None = None,
        catalogue: Catalogue | None = None,
        config: Config | None = None,
    ) -> Linter:
        """
        A linter that reads a key from the environment, or a `.env` in the working
        directory, and builds its own client.
        """
        return Linter(_Settings(
            catalogue=catalogue or Catalogue.load(),
            client=lambda: ClientFactory.make(model, open_router, timeout, True),
            config=config or Config.empty(),
            asked_through=model,
        ))

    @staticmethod
    def rules_only(catalogue: Catalogue | None = None, config: Config | None = None) -> Linter:
        """A linter that runs the rules and makes no calls, so it needs no key."""
        return Linter(_Settings(
            catalogue=catalogue or Catalogue.load(),
            client=None,
            config=config or Config.empty(),
        ))

    def for_jev(self, version: str) -> Linter:
        """
        The rules for one Jev version.

        A query is sent to one build, and a build has the defects it has. Without
        this the run uses the newest version the catalogue covers.
        """
        return Linter(replace(self._settings, catalogue=self._settings.catalogue.for_jev(version)))

    def accepting(self, config: Config) -> Linter:
        """The acceptances a report reads to set findings aside."""
        return Linter(replace(self._settings, config=config))

    def only(self, check_ids: list[str]) -> Linter:
        """
        Narrow the run to these checks.

        An id the catalogue does not hold is an error instead of a narrowing that
        silently runs nothing.
        """
        ids = [check.id for check in self._settings.catalogue.written()]
        unknown = [check_id for check_id in check_ids if check_id not in ids]

        if len(unknown) > 0:
            raise JevLintError(Text.of('catalogue.no_such_check', {'ids': ', '.join(unknown)}))

        withheld = [check_id for check_id in check_ids if self._settings.catalogue.find(check_id) is None]

        if len(withheld) > 0:
            raise JevLintError(Text.of('narrow.withheld_for_version', {
                'ids': ', '.join(withheld),
                'count': len(withheld),
                'jev': self._settings.catalogue.jev,
            }))

        return Linter(replace(self._settings, only=tuple(check_ids)))

    def without_state(self) -> Linter:
        """Leave out the checks that read the query's state."""
        return Linter(replace(self._settings, check_state=False))

    def repeats(self, repeats: int) -> Linter:
        """Ask each model check this many times, so the report has the spread."""
        return Linter(replace(self._settings, repeats=repeats))

    def reporting_cleared(self) -> Linter:
        """
        Carry every model check that ran and cleared, not only the readings near a
        trigger. Without this a check that cleared and a check that never applied
        are indistinguishable.
        """
        return Linter(replace(self._settings, report_cleared=True))

    def max_state_chars(self, chars: int) -> Linter:
        """Where a state stops being state and starts being a document."""
        return Linter(replace(self._settings, max_state_chars=chars))

    def asked_through(self, model: str | None) -> Linter:
        """Record in the report which build the run asked for."""
        return Linter(replace(self._settings, asked_through=model))

    def catalogue(self) -> Catalogue:
        return self._settings.catalogue

    def check_file(self, path: str) -> Report:
        return self.check(Query.from_file(path))

    def check(self, query: Query, whole: Query | None = None) -> Report:
        """
        Run the catalogue over a query.

        `whole` is the query before any narrowing, where the caller narrowed it
        with `Query.only()`. The checks that judge a state field against the whole
        query cannot answer from part of it, so they are left out and said to be
        left out.
        """
        catalogue = self._settings.catalogue
        config = self._settings.config
        client = self._settings.client
        unknown = config.unknown([check.id for check in catalogue.written()])

        # A config naming a check that is not in the catalogue is accepting
        # nothing, which is worse than accepting the wrong thing.
        if len(unknown) > 0:
            raise JevLintError.of(JevLintError.CONFIG, Text.of('config.accepts_unknown_check', {
                'source': config.source or Config.FILE,
                'ids': ', '.join(unknown),
            }))

        left = 0 if whole is None else len(whole.questions) - len(query.questions)

        report = Report(
            source=query.source,
            catalogue_version=catalogue.version,
            model=catalogue.model,
            fingerprint=catalogue.fingerprint,
            question_print=catalogue.asked,
            asked_through=self._settings.asked_through,
        )

        report.order_by([question.id for question in query.questions])
        report.accept_from(config)
        self._note_version(whole or query, report)

        StaticLinter(catalogue, self._settings.max_state_chars, list(self._settings.only)).run(query, report)

        self._note_what_was_left_out(report, left)

        if client is not None and self._asks_jev():
            ModelLinter(
                catalogue,
                client(),
                self._settings.check_state,
                self._settings.repeats,
                list(self._settings.only),
                self._settings.report_cleared,
                left > 0,
            ).run(query, report)

        return report

    def _asks_jev(self) -> bool:
        """Whether anything in this run needs a call at all."""
        return len(self._model_checks()) > 0

    def _model_checks(self) -> list[Check]:
        return [
            check for check in self._settings.catalogue.all()
            if check.is_model() and (len(self._settings.only) == 0 or check.id in self._settings.only)
        ]

    def _note_version(self, query: Query, report: Report) -> None:
        """
        A query file may pin the build it will be sent to. Where that is a Jev
        version and the run resolved another one, the findings are the rules for a
        build this query never reaches.
        """
        named = None if query.model is None else _PINNED_BUILD.match(query.model)

        if named is None or named.group(1) == self._settings.catalogue.jev:
            return

        # `--jev` only takes a version the catalogue covers, and a build id
        # carrying a patch number - `jev-1.13.0` is what the API answers for
        # `jev-latest` - is not one, so telling every reader to pass it sent half
        # of them to a flag that refuses the value they would pass.
        covered = named.group(1) in self._settings.catalogue.versions

        about = {
            'source': query.source,
            'model': query.model or '',
            'jev': self._settings.catalogue.jev,
            'named': named.group(1),
        }

        report.note(
            Text.of('note.version_covered', about) if covered
            else Text.of('note.version_not_covered', about),
        )

    def _note_what_was_left_out(self, report: Report, questions_left_out: int) -> None:
        """
        Say what this run left out. A narrowed run that matched nothing, or a run
        with the model half switched off, produces the same empty report as a query
        with nothing wrong with it.
        """
        catalogue = self._settings.catalogue
        client = self._settings.client
        only = self._settings.only

        if questions_left_out > 0:
            report.skipped(Text.of('skipped.questions_left_out', {'count': questions_left_out}))

        if client is None:
            model = self._model_checks()

            if len(model) > 0:
                report.skipped(Text.of('skipped.jev_not_asked', {'count': len(model)}), len(model))
        elif not self._settings.check_state:
            state_scoped = [
                check for check in catalogue.all()
                if check.is_model() and check.scope in ('state', 'state-field', 'state-once')
            ]

            report.skipped(
                Text.of('skipped.state_not_checked', {'count': len(state_scoped)}),
                len(state_scoped),
            )

        if len(only) > 0:
            report.skipped(Text.of('skipped.narrowed_to', {
                'count': len(only),
                'total': len(catalogue.all()),
            }), len(catalogue.all()) - len(only))

        if catalogue.withheld() > 0:
            report.skipped(Text.of('skipped.written_for_another_version', {
                'jev': catalogue.jev,
                'count': catalogue.withheld(),
            }), catalogue.withheld())
