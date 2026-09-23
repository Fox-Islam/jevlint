"""The four things the command line does, each from arguments to an exit code."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..catalogue import Catalogue, Check
from ..config import Config
from ..errors import JevLintError
from ..formatting import pad
from ..linter import ClientFactory, Linter
from ..probe import Probe, QuestionProbe
from ..probe_formatter import ProbeFormatter
from ..query import Query
from ..report import Severity
from ..self_test_formatter import SelfTestFormatter
from ..selftest import SelfTest
from ..support import Json
from ..text import Text
from ..text_formatter import TextFormatter
from .args import Args
from .output import Output


class CheckCommand:
    """`jevlint check <query.json>` - the linter."""

    def run(self, args: Args, output: Output) -> int:
        path = args.argument(1)

        if path is None:
            raise JevLintError(Text.of('check.no_query_file'))

        whole = Query.from_file(path)
        wanted = _list(args.value('question'), 'question')
        missing = [
            question_id for question_id in wanted
            if not any(question.id == question_id for question in whole.questions)
        ]

        if len(missing) > 0:
            raise JevLintError(Text.of('query.no_such_question', {
                'path': path,
                'ids': ', '.join(missing),
            }))

        query = whole.only(wanted)
        config = Config.discover(args.value('config'), path)
        catalogue = Catalogue.for_run(args.value('jev'), config)
        only = _list(args.value('only'), 'only')

        if args.flag('static-only'):
            linter = Linter.rules_only(catalogue, config)
        else:
            linter = Linter.from_environment(
                model=args.value('model'),
                open_router=args.flag('openrouter'),
                timeout=args.seconds('timeout', 10.0) if args.has('timeout') else None,
                catalogue=catalogue,
                config=config,
            )

        linter = (
            linter
            .only(only)
            .repeats(args.int('repeats', 1))
            .max_state_chars(args.int('max-state', 20000, 2 ** 53 - 1))
        )

        if args.flag('no-state'):
            linter = linter.without_state()

        if args.flag('all'):
            linter = linter.reporting_cleared()

        report = linter.check(query, whole)

        floor = Severity.from_name(args.value('min', 'advice') or 'advice')

        # The counts stay whole while the list is filtered, so a reader who sees
        # `4 advice` and no advice rows is owed the reason.
        hidden = len(report.findings()) - len(report.findings(floor))

        if hidden > 0:
            report.note(Text.of('note.below_the_floor', {'floor': floor.value, 'count': hidden}), hidden)

        if args.value('format') == 'json':
            output.line(Json.encode(report.to_dict(floor)))
        else:
            output.write(TextFormatter(
                output.colour(),
                args.flag('brief'),
                args.flag('show-accepted'),
                args.flag('all'),
            ).format(report, floor))

        # Checks that could not be asked did not pass. Reporting 0 here would tell
        # a caller gating on the exit code that a query nobody checked is fine.
        if not report.is_complete():
            return 2

        # A run can leave nothing to do - a narrowing that names a state check on a
        # query with no state - and every reason is recorded as a skipped note.
        # Reporting that as a pass is the same lie as reporting a failed call as
        # one.
        if report.asked_count() == 0:
            return 2

        if report.has_errors():
            return 1

        if args.flag('strict') and not report.is_empty(floor):
            return 1

        # A run that could not decide is not a run that passed.
        return 0 if len(report.unstable()) == 0 else 3


class ProbeCommand:
    """`jevlint probe <query.json>` - how far a rewrite moves the answer."""

    def run(self, args: Args, output: Output) -> int:
        path = args.argument(1)

        if path is None:
            raise JevLintError(Text.of('probe.no_query_file'))

        # The same load `check` does, so a file that is not a query is named as
        # one here too. Reading it straight into an object let a JSON list through
        # to be reported as a missing state, or as a missing key.
        query = Query.from_file(path)
        state_path = args.value('state')

        if state_path is not None:
            query = query.with_state(Json.read_file(state_path))

        # Probing costs a call per variant per question, so narrowing to the one
        # question being iterated on is the difference between a run you make once
        # and a run you make while editing.
        named = args.value('question')
        wanted = [] if named is None else [
            question_id.strip() for question_id in named.split(',') if question_id.strip() != ''
        ]

        if named is not None and len(wanted) == 0:
            raise JevLintError.of(JevLintError.USAGE, Text.of('narrow.no_question_named'))

        missing = [
            question_id for question_id in wanted
            if not any(question.id == question_id for question in query.questions)
        ]

        if len(missing) > 0:
            raise JevLintError.of(JevLintError.USAGE, Text.of('query.no_such_question', {
                'path': path,
                'ids': ', '.join(missing),
            }))

        whole = query
        query = query.only(wanted)
        repeats = args.int('repeats', 5)

        extra = []
        rewordings = args.value('variants')

        if rewordings is not None:
            extra = Probe.rewordings(Json.read_file(rewordings))

            # A rewording keyed by a question id that is not in the file applies to
            # nothing, and the run then reads as a query nothing moved.
            for variant in extra:
                if any(variant.applies(question) for question in whole.questions):
                    continue

                raise JevLintError.of(JevLintError.USAGE, Text.of('probe.variant_names_no_question', {
                    'variant': variant.name(),
                    'path': path,
                    'ids': ', '.join(question.id for question in whole.questions),
                }))

        # The client is built after the variants are read, so a mistyped path is
        # reported as a mistyped path instead of as a missing key.
        probe = Probe(ClientFactory.make(args.value('model'), args.flag('openrouter')))

        probes = probe.run(query, repeats, extra)

        if args.value('format') == 'json':
            output.line(Json.encode(_probe_to_dict(probes, path, repeats, probe, args.value('model'))))
        else:
            output.write(ProbeFormatter(output.colour()).format(
                probes,
                path,
                repeats,
                probe.calls(),
                probe.tokens(),
                probe.notes(),
            ))

        # A probe that could not send is not a probe that found no movement, and
        # exit 1 is what `--strict` returns when it does find some.
        if not probe.is_complete():
            return 2

        moved = any(
            any(question.moved(reading) for reading in question.readings)
            for question in probes.values()
        )

        return 1 if args.flag('strict') and moved else 0


def _probe_to_dict(
    probes: dict[str, QuestionProbe],
    source: str,
    repeats: int,
    probe: Probe,
    asked_through: str | None,
) -> dict[str, Any]:
    questions: dict[str, Any] = {}

    for question_id, question in probes.items():
        questions[question_id] = {
            'type': question.question.type,
            'reading': question.reading,
            'moved': any(question.moved(reading) for reading in question.readings),
            'undecided': question.undecided(),
            'flips': question.flips(),
            'baseline': question.baseline(),
            'repeats': question.repeats,
            'noise': question.noise(),
            'floor': question.floor(),
            'readings': [{
                'variant': reading.variant,
                'describes': reading.describe,
                'value': reading.value,
                'delta': question.delta(reading),
                'noise_multiples': question.ratio(reading),
                'moved': question.moved(reading),
                'error': reading.error,
            } for reading in question.readings],
        }

    moved = [question_id for question_id, row in questions.items() if row['moved']]
    undecided = [question_id for question_id, row in questions.items() if row['undecided']]

    return {
        'source': source,
        'asked_through': asked_through,
        'repeats': repeats,
        'calls': probe.calls(),
        'tokens': probe.tokens(),
        'notes': [note.to_dict() for note in probe.notes()],
        'summary': {
            'questions': len(questions),
            'moved': len(moved),
            'moved_questions': moved,
            'undecided': len(undecided),
            'undecided_questions': undecided,
            'unreachable': probe.unreachable(),
            'complete': probe.is_complete(),
            'rule': Text.of('probe.moved_definition', {'floor': QuestionProbe.NEGLIGIBLE}),
            'undecided_rule': Text.of('probe.undecided_definition', {'band': QuestionProbe.UNDECIDED}),
            'floor': Text.of('probe.floor_definition', {'noise': Probe.PUBLISHED_NOISE}),
        },
        'questions': questions,
    }


class SelfTestCommand:
    """`jevlint self-test` - does each check separate its own two examples?"""

    def run(self, args: Args, output: Output) -> int:
        config = Config.discover(args.value('config'), '.')
        catalogue = Catalogue.for_run(args.value('jev'), config)
        only = [
            check_id.strip() for check_id in (args.value('check', '') or '').split(',')
            if check_id.strip() != ''
        ]

        if args.has('check') and len(only) == 0:
            raise JevLintError.of(JevLintError.USAGE, Text.of('narrow.no_check_named'))

        # A check id the catalogue does not hold is a typo or a rename. Scoring
        # nothing and exiting 0 leaves a pinned CI job green for ever.
        ids = [check.id for check in catalogue.written()]
        unknown = [check_id for check_id in only if check_id not in ids]

        if len(unknown) > 0:
            raise JevLintError(Text.of('catalogue.no_such_check', {'ids': ', '.join(unknown)}))

        withheld = [check_id for check_id in only if catalogue.find(check_id) is None]

        if len(withheld) > 0:
            raise JevLintError(Text.of('self_test.withheld_for_version', {
                'ids': ', '.join(withheld),
                'count': len(withheld),
                'jev': catalogue.jev,
            }))

        static_checks = [
            check_id for check_id in only
            if catalogue.find(check_id) is not None and catalogue.find(check_id).is_static()
        ]

        if len(static_checks) > 0:
            raise JevLintError(Text.of('self_test.static_has_nothing_to_score', {
                'ids': ', '.join(static_checks),
                'count': len(static_checks),
            }))

        scores = SelfTest(catalogue, ClientFactory.make(
            args.value('model'),
            args.flag('openrouter'),
        )).run(only)

        if args.value('format') == 'json':
            output.line(Json.encode([score.to_dict() for score in scores]))
        else:
            output.write(SelfTestFormatter(output.colour()).format(scores))

        # A model check with no fixture is scored by nothing and would leave the
        # run reporting `0 of 0 checks separate their own examples`, which a
        # pinned CI job reads as a pass for ever.
        scored = [score.check.id for score in scores]
        unscored = [
            check for check in catalogue.all()
            if check.is_model()
            and (len(only) == 0 or check.id in only)
            and check.id not in scored
        ]

        if len(unscored) > 0:
            output.error(Text.of('self_test.no_examples', {
                'ids': ', '.join(check.id for check in unscored),
                'count': len(unscored),
                'file': Path(Catalogue.locate('fixtures.json')).name,
            }))

            return 1

        # A check that could not be asked has not failed its examples; the run did
        # not happen. Exit 1 is for a catalogue that is wrong, exit 2 for a run
        # that could not tell.
        if any(score.errored() for score in scores):
            return 2

        if any(not score.passed() for score in scores):
            return 1

        return 0


class ChecksCommand:
    """`jevlint checks` - what the catalogue holds."""

    def run(self, args: Args, output: Output) -> int:
        config = Config.discover(args.value('config'), '.')
        catalogue = Catalogue.for_run(args.value('jev'), config)
        wanted = args.argument(1)

        # The README says a check id is how you look one up. Printing all of them
        # instead answers a question nobody asked.
        if wanted is not None:
            check = catalogue.find(wanted)

            if check is None:
                written = catalogue.find_written(wanted)
                message = Text.of('catalogue.check_not_for_version', {
                    'id': wanted,
                    'jev': catalogue.jev,
                    'versions': ', '.join(catalogue.versions),
                }) if written is not None else Text.of('catalogue.no_such_check', {'ids': wanted})

                raise JevLintError.of(JevLintError.USAGE, message)

            if args.value('format') == 'json':
                output.line(Json.encode(_describe(check)))

                return 0

            for key, value in _describe(check).items():
                written = Json.inline(value) if isinstance(value, (dict, list)) else _scalar(value)
                output.line(pad(key, 12) + ' ' + written)

            return 0

        if args.value('format') == 'json':
            output.line(Json.encode([_describe(check) for check in catalogue.all()]))

            return 0

        output.line(Text.of('catalogue.header', {
            'version': catalogue.version,
            'model': catalogue.model,
            'withheld': catalogue.withheld(),
        }))
        output.line()

        for mode in ('static', 'model'):
            output.line(mode.upper())

            for check in catalogue.all():
                if check.mode != mode:
                    continue

                output.line(
                    '  ' + pad(check.severity, 8) + ' ' + pad(check.id, 34) + ' '
                    + pad(','.join(check.applies_to), 12) + ' ' + check.title,
                )

            output.line()

        return 0


def _describe(check: Check) -> dict[str, Any]:
    return _present({
        'id': check.id,
        'title': check.title,
        'mode': check.mode,
        'scope': check.scope,
        'applies_to': check.applies_to,
        'severity': check.severity,
        # Which builds the check is a rule for, where it is not all of them
        'since': check.since,
        'until': check.until,
        'reads': check.reads,
        'action': check.action,
        'message': check.message,
        'hint': check.hint,
        'suggest': check.suggest,
        'docs': check.docs,
        'removes': check.removes,
        # What a static check tests, and which findings it puts out of date. A
        # consumer that reads `superseded_by` in a report had nowhere to look the
        # relationship up.
        'rule': check.rule,
        'supersedes': None if len(check.supersedes) == 0 else check.supersedes,
        # A model check is a judgement against a threshold, and a caller that
        # cannot see the threshold cannot say what it gated on.
        'trigger': check.trigger if check.is_model() else None,
        'questions': [_wording(wording) for wording in check.wordings] if check.is_model() else None,
    })


def _wording(one: Any) -> dict[str, Any]:
    return {key: value for key, value in {
        'type': one.type,
        # Keep the placeholder: the catalogue's own text is what a reader is being
        # shown, and blanking it prints a hole.
        'instructions': one.instructions('{field}'),
        'criteria': one.criteria,
    }.items() if value is not None}


def _present(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value is not None and value != ''}


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value)


def _list(value: str | None, option: str = '') -> list[str]:
    if value is None:
        return []

    named = [item.strip() for item in value.split(',') if item.strip() != '']

    # `--only=$CHECKS` with the variable unset read as no narrowing at all, so a
    # run meant to carry one check carried the catalogue and paid for it.
    if len(named) == 0:
        raise JevLintError.of(JevLintError.USAGE, Text.of('narrow.nothing_named', {'option': option}))

    return named
