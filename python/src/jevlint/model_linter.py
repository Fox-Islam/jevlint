"""
The half that asks Jev about the query.

Every check for one reviewed question goes in a single call, because a call costs
its round trip and not its question count. The question under review is the
state; the checks are the questions. State-scoped checks need the real state in
front of them, so they are a second call.

A check may be asked several ways at once. The wordings are meant to mean the
same thing, so their mean is the answer and their spread is the error bar.

Jev's answers about prompts are not calibrated against human judgement, so every
model finding carries the probability that produced it, and `jevlint self-test`
measures whether each check separates a clean question from a broken one.
"""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as _field
from typing import Any

from .catalogue import Catalogue, Check, Wording
from .query import Query, ReviewedQuestion
from .report import Finding, Patch, Report, Severity
from .support import Cause, Json
from .text import Text
from .typesafe import Choice, Client, Noul, SystemOne, SystemOneResponse
from .typesafe.errors import TypeSafeError


@dataclass
class Asked:
    """One check put on a call, with the keys its answers come back under."""

    check: Check

    field: str | None

    keys: list[str]

    # answer key to the element it is about
    locator: dict[str, str] = _field(default_factory=dict)


class ModelLinter:
    # Beyond this many questions the pairs outgrow one call
    MOST_QUESTIONS = 12

    # How close to its trigger a probability has to be before the finding is a coin flip
    NEAR = 0.05

    # How close to its trigger a cleared reading has to be to be worth printing
    # without `--all`.
    #
    # `--all` costs nothing extra in calls but a whole second run to ask for, and
    # a check sitting just under its trigger is the reading a reader is most
    # likely to want. This is the band the corpus tables count as shaky.
    WORTH_SEEING = 0.1

    def __init__(
        self,
        catalogue: Catalogue,
        client: Client,
        check_state: bool = True,
        repeat_count: int = 1,
        only: list[str] | None = None,
        report_all: bool = False,
        narrowed: bool = False,
    ) -> None:
        self._catalogue = catalogue
        self._client = client
        self._check_state = check_state
        self._repeat_count = repeat_count
        # check ids to run, or all of them when empty
        self._only = only or []
        self._report_all = report_all
        self._narrowed = narrowed
        # check id to field to question id to probability
        self._fields: dict[str, dict[str, dict[str, float]]] = {}
        # How many questions the query under review holds
        self._question_count = 0
        # Set when a call failed in a way every later call would repeat
        self._stopped = False

    def _wanted(self, check: Check) -> bool:
        return len(self._only) == 0 or check.id in self._only

    def run(self, query: Query, report: Report) -> None:
        self._fields = {}
        self._stopped = False
        self._question_count = len(query.questions)
        asked: list[str] = []
        unreadable: list[str] = []

        for question in query.questions:
            # Nothing here can read a question whose type is not one Jev answers
            # or whose instruction is blank. Skipping it in silence left a report
            # that could not be told from one where every check ran.
            if not question.is_known_type() or question.instructions_text().strip() == '':
                unreadable.append(question.id)

                continue

            asked.append(question.id)
            self._ask_about_question(question, report)

            if self._check_state and query.has_state():
                self._ask_about_state(query, question, report)

        if len(unreadable) > 0:
            report.skipped(Text.of('skipped.unreadable_questions', {
                'ids': ', '.join(unreadable),
                'count': len(unreadable),
            }), len(self._catalogue.model_checks('question')) * len(unreadable))

        # A check that asks whether a field serves the query cannot answer it from
        # some of the questions. Narrowed, it reads a field the hidden questions
        # use as one nothing reads, which is a wrong answer rather than a partial
        # one, so it is not asked.
        if self._narrowed and len(self._fields) > 0:
            field_checks = len(self._catalogue.model_checks('state-field'))

            report.skipped(Text.of('skipped.state_field_needs_whole_query', {'count': field_checks}), field_checks)

            self._fields = {}

        self._report_fields(asked, report)

        if self._check_state and query.has_state():
            self._ask_about_state_alone(query, report)
        elif self._check_state:
            # A query with no state leaves every state-scoped check out. The only
            # other sign is a `state/missing` finding, which `--min=warning`
            # filters away.
            state_scoped = [
                check for scope in ('state', 'state-field', 'state-once')
                for check in self._catalogue.model_checks(scope) if self._wanted(check)
            ]

            if len(state_scoped) > 0:
                report.skipped(Text.of('skipped.no_state', {'count': len(state_scoped)}), len(state_scoped))

        self._ask_about_query(query, report)

        # Last, once every call has been made: anything that went into a call and
        # never came back with a verdict is a loss, whichever path lost it.
        report.reconcile()

    def _ask_about_query(self, query: Query, report: Report) -> None:
        """
        One call for the checks that read the question set.

        Every check but these sees one question at a time, so two questions that
        ask the same thing in different words are invisible to all of them. The
        pairs go in a single call, which is why this is affordable at all.
        """
        checks = [check for check in self._catalogue.model_checks('query') if self._wanted(check)]
        questions = [
            question for question in query.questions
            if question.is_known_type() and question.instructions_text().strip() != ''
        ]

        if len(checks) == 0:
            return

        # Not `unreachable`: nothing failed, and this check was never going to run
        # on a query this size. It is a note because the alternative is a report
        # that silently omits a check the caller may have asked for by name.
        if len(questions) > ModelLinter.MOST_QUESTIONS:
            report.skipped(Text.of('skipped.too_many_questions', {
                'questions': len(questions),
                'most': ModelLinter.MOST_QUESTIONS,
            }), len(checks))

            return

        # One question makes no pairs. Returning bare left these checks out of a
        # report that then read as a full run.
        if len(questions) < 2:
            report.skipped(Text.of('skipped.too_few_questions', {'questions': len(questions)}), len(checks))

            return

        report.asked(len(checks))
        request = self._client.system_one().state({
            'questions': [question.instructions_text() for question in questions],
        })
        pairs: dict[str, tuple[Check, ReviewedQuestion, ReviewedQuestion]] = {}

        for check in checks:
            for index, first in enumerate(questions):
                for second in questions[index + 1:]:
                    key = f'{check.answer_key()}__{_slug(first.id)}__{_slug(second.id)}'
                    pairs[key] = (check, first, second)
                    request.ask(key, self.build(check.wordings[0]).instructions(
                        check.instructions().replace(
                            '{pair}',
                            f'"{first.instructions_text()}" and "{second.instructions_text()}"',
                        ),
                    ))

        if len(pairs) == 0:
            return

        for check, _, second in pairs.values():
            report.expecting(check.id, second.id)

        response = self._send(request, 'query', report)

        if response is None or not self._answered(list(pairs), response, 'query', report):
            return

        for key, (check, first, second) in pairs.items():
            if not response.has(key):
                continue

            report.reached(check.id, second.id)
            probability = _reading(response, key)

            if probability is None:
                report.unreachable(second.id, Text.of('report.no_usable_reading', {'key': key}))

                continue

            fired = probability > check.trigger

            if not fired and not self._report_all:
                continue

            report.add(Finding(
                check_id=check.id,
                title=Text.of('finding.pair_title', {
                    'title': check.title,
                    'first': first.id,
                    'second': second.id,
                }),
                severity=Severity.from_name(check.severity),
                target=second.id,
                message=check.message or check.title,
                hint=check.hint,
                suggest=check.suggest,
                advice=check.advice,
                mode=check.mode,
                action=check.action,
                path=f'/questions/{Check.escape(second.id)}',
                trigger=check.trigger,
                near_trigger=abs(probability - check.trigger) <= ModelLinter.NEAR,
                docs=check.docs,
                probability=probability,
                fired=fired,
                evidence=Text.of('evidence.both_ask', {
                    'first': _shorten(first.instructions_text(), 70),
                    'second': _shorten(second.instructions_text(), 70),
                }),
                paths=[
                    f'/questions/{Check.escape(first.id)}',
                    f'/questions/{Check.escape(second.id)}',
                ],
            ))

    def _answered(self, keys: list[str], response: SystemOneResponse, target: str, report: Report) -> bool:
        """
        Every question put on a call came back with an answer.

        A transport failure raises and is already handled. A 200 carrying none of
        the keys that were asked for - an answer-key skew, a truncated payload, a
        proxy answering on the endpoint's behalf - does not, and every check would
        then be skipped one at a time by `has()` with nothing recorded. The run
        would report a clean query it never looked at.
        """
        missing = [key for key in keys if not response.has(key)]

        if len(missing) == 0:
            return True

        report.unreachable(target, Text.of('report.partial_answer', {
            'answered': len(keys) - len(missing),
            'asked': len(keys),
            'missing': f'`{missing[0]}`' if len(missing) == 1 else f'`{missing[0]}` and {len(missing) - 1} more',
        }))

        # Some answers are still answers. Only a call that came back with none of
        # what it was asked has nothing to record.
        return len(missing) < len(keys)

    def _send(self, request: SystemOne, target: str, report: Report) -> SystemOneResponse | None:
        """
        Send one call and record what it cost.

        A call that fails is a note on the report and a None here. One set of
        checks that could not be asked is not a reason to abandon the rest.
        """
        if self._stopped:
            return None

        try:
            response = request.send()
        except TypeSafeError as error:
            # Counted: it left the machine and was paid for, and the client
            # retries before giving up, so one failed call is several requests.
            report.record_call(None)
            report.unreachable(target, str(error), Cause.of(error))

            # A wrong key answers every call the same way, so the rest of the run
            # is spent buying the same refusal again.
            if Cause.is_settled(error):
                self._stopped = True

            return None

        report.record_call(response.usage.total_tokens())
        report.answered_by(response.model)

        return response

    def _ask_about_state_alone(self, query: Query, report: Report) -> None:
        """
        One call for the checks that read the material and nothing else.

        Asking them once per question asked the same question of the same state as
        many times as the query had questions.
        """
        request = self._client.system_one().state({'state': query.state})
        asked: list[Asked] = []
        parts = self._state_parts(query)

        for check in self._catalogue.model_checks('state-once'):
            if self._wanted(check):
                asked.append(self._ask(request, check, None, parts))

        report.asked(len(asked))

        if len(asked) == 0:
            return

        keys = _answer_keys(asked)

        for entry in asked:
            report.expecting(entry.check.id, 'state')

        response = self._send(request, 'state', report)

        if response is None or not self._answered(keys, response, 'state', report):
            return

        for entry in asked:
            self._record(entry.check, entry.keys, None, [response], 'state', report, None, entry.locator)

    def _state_parts(self, query: Query) -> dict[str, str]:
        """The state's own parts, as something to choose between."""
        parts: dict[str, str] = {}

        for path in query.state_leaves():
            value = Json.inline(query.state_at(path))
            parts[path] = _shorten(path if value == '' else value, 120)

        return parts

    def _report_fields(self, asked: list[str], report: Report) -> None:
        """One finding per state field, however many questions were asked about it."""
        for check in self._catalogue.model_checks('state-field'):
            self._report_field(check, self._fields.get(check.id, {}), asked, report)

    def _report_field(
        self,
        check: Check,
        fields: dict[str, dict[str, float]],
        asked: list[str],
        report: Report,
    ) -> None:
        """One finding per state field, for one check asked about every field."""
        for field, by_question in fields.items():
            if len(by_question) == 0:
                continue

            readings = list(by_question.values())
            unused = [probability for probability in readings if probability > check.trigger]

            fired = len(unused) == len(asked) and len(asked) > 0

            # The verdict is that *every* question ignored the field, so the
            # statistic behind it is the weakest reading, not the average of them.
            # Publishing the mean printed 0.86 beside a cleared verdict against a
            # 0.75 trigger, which is a number arguing with itself.
            decided = min(readings)

            if not fired and not self._report_all:
                continue

            read = {'asked': asked[0] if len(asked) == 1 else ', '.join(asked), 'field': field}
            evidence = (
                Text.of('evidence.field_unread', read) if fired
                else Text.of('evidence.field_read', read)
            )

            report.add(Finding(
                check_id=check.id,
                title=check.title.replace('{field}', field),
                severity=Severity.from_name(check.severity),
                target='state',
                message=(check.message or check.title).replace('{field}', field),
                hint=check.hint,
                suggest=check.suggest.replace('{field}', field),
                advice=check.advice,
                mode=check.mode,
                action=check.action,
                path=check.path('state', field),
                trigger=check.trigger,
                near_trigger=abs(decided - check.trigger) <= ModelLinter.NEAR,
                supersedes=check.supersedes,
                docs=check.docs,
                probability=decided,
                readings=readings if len(readings) > 1 else [],
                readings_of=Text.of('evidence.question_count', {'count': len(readings)}) if len(readings) > 1 else None,
                spread=max(readings) - min(readings) if len(readings) > 1 else None,
                fired=fired,
                patch=self._removal(check, 'state', field),
                evidence=evidence,
            ))

    def _ask_about_question(self, question: ReviewedQuestion, report: Report) -> None:
        """One call: every question-scoped check, with the question as the state."""
        request = self._client.system_one().state(question.as_state())
        asked: list[Asked] = []
        elements = self._elements(question)

        for check in self._catalogue.model_checks('question', question.type):
            if not self._wanted(check):
                continue

            if check.requires == 'criteria' and not question.has_criteria():
                continue

            asked.append(self._ask(request, check, None, elements))

        report.asked(len(asked))
        self._collect(asked, request, question, question.id, report, question.as_state())

    def _ask_about_state(self, query: Query, question: ReviewedQuestion, report: Report) -> None:
        """One call: the state-scoped checks, with the real state in front of them."""
        request = self._client.system_one().state(query.state_with(question))
        asked: list[Asked] = []

        for check in self._catalogue.model_checks('state', question.type):
            if self._wanted(check):
                asked.append(self._ask(request, check))

        for check in self._catalogue.model_checks('state-field', question.type):
            if not self._wanted(check):
                continue

            leaves = query.state_leaves()

            # A state that is a string or a list has no named fields, so a check
            # asked once per field is asked zero times. Saying nothing left that
            # looking like a state whose every field was needed.
            if len(leaves) == 0:
                report.skipped(Text.of('skipped.no_fields_to_name', {'id': check.id}), 1)

                continue

            for field in leaves:
                asked.append(self._ask(request, check, field))

        report.asked(len(asked))
        self._collect(asked, request, question, question.id, report, query.state_with(question))

    def _ask(
        self,
        request: SystemOne,
        check: Check,
        field: str | None = None,
        options: dict[str, str] | None = None,
    ) -> Asked:
        """Put every wording of one check on the request."""
        options = options or {}
        keys: list[str] = []
        suffix = '' if field is None else f'__{_slug(field)}'

        for index, wording in enumerate(check.wordings):
            key = check.answer_key() + suffix + (f'__w{index}' if check.is_composite() else '')
            keys.append(key)
            request.ask(key, self.build(wording, field or ''))

        locator: dict[str, str] = {}

        if check.locate is not None and len(options) > 1:
            if check.locate_mode == 'each':
                for label, text in options.items():
                    key = f'{check.answer_key()}__where__{_slug(label)}'
                    locator[key] = label
                    request.ask(key, Noul.ask(check.locate.replace('{element}', f'"{text}"')))
            else:
                key = f'{check.answer_key()}__where'
                locator[key] = ''
                request.ask(key, Choice.ask(check.locate).options(dict(options)))

        return Asked(check, field, keys, locator)

    def _elements(self, question: ReviewedQuestion) -> dict[str, str]:
        """The reviewed question's own levels or options, as something to choose from."""
        options: dict[str, str] = {}

        if question.criteria is None or not question.has_criteria():
            return options

        for key, value in question.entries():
            label = f'level_{key}' if question.criteria_is_list() else key
            text = value if isinstance(value, str) else Json.inline(value)
            options[label] = label if text == '' else text

        return options

    def build(self, wording: Wording, field: str = '') -> Noul | Choice:
        """Turn one wording into the question that asks it."""
        criteria = wording.criteria if wording.criteria is not None else {}

        if wording.type == 'choice':
            options = {
                label: (description if isinstance(description, str) else None)
                for label, description in (criteria.items() if isinstance(criteria, dict) else [])
            }

            return Choice.ask(wording.instructions(field)).options(options)

        noul = Noul.ask(wording.instructions(field))

        if isinstance(criteria, dict):
            if isinstance(criteria.get('true'), str):
                noul.yes(criteria['true'])

            if isinstance(criteria.get('false'), str):
                noul.no(criteria['false'])

        return noul

    def _collect(
        self,
        asked: list[Asked],
        request: SystemOne,
        question: ReviewedQuestion,
        target: str,
        report: Report,
        state: dict[str, Any],
    ) -> None:
        """`state` is the state the first call used."""
        if len(asked) == 0:
            return

        for entry in asked:
            report.expecting(entry.check.id, target)

        responses: list[SystemOneResponse] = []

        for _ in range(max(1, self._repeat_count)):
            response = self._send(request, target, report)

            if response is not None:
                responses.append(response)

        if len(responses) == 0:
            return

        keys = _answer_keys(asked)

        # Every response, not the first: a repeat can answer 200 with the answer
        # keys missing, and a verdict resting on the calls that did answer is not
        # the verdict the caller asked for.
        for response in responses:
            if not self._answered(keys, response, target, report):
                return

        extra = self._settle(asked, responses, question, report, state)

        # The re-ask is a call like any other: if it answers nothing, the
        # borderline verdict it was asked to settle is still unsettled.
        for check_id, settled in extra.items():
            for response in settled:
                self._answered(_keys_for(asked, check_id), response, target, report)

        for entry in asked:
            if entry.check.compare == 'type':
                self._record_type_comparison(
                    entry.check, entry.keys[0] if entry.keys else '', responses[0], question, target, report,
                )

                continue

            self._record(
                entry.check,
                entry.keys,
                entry.field,
                [*responses, *extra.get(entry.check.id, [])],
                target,
                report,
                question,
                entry.locator,
            )

    def _settle(
        self,
        asked: list[Asked],
        responses: list[SystemOneResponse],
        question: ReviewedQuestion,
        report: Report,
        state: dict[str, Any],
    ) -> dict[str, list[SystemOneResponse]]:
        """
        Ask again, once, about every check whose first answer sat on its trigger.

        The repeats ride in a single call and only for the checks that need them,
        so settling a borderline verdict costs one round trip however many are
        borderline.
        """
        out: dict[str, list[SystemOneResponse]] = {}

        if len(responses) == 0 or self._repeat_count > 1:
            return out

        borderline: list[Asked] = []

        for entry in asked:
            if entry.check.compare == 'type' or entry.check.scope == 'state-field':
                continue

            values = [
                value for response in responses for key in entry.keys
                if (value := _reading(response, key)) is not None
            ]

            if len(values) > 0 and abs(_mean(values) - entry.check.trigger) <= ModelLinter.NEAR:
                borderline.append(entry)

        if len(borderline) == 0:
            return out

        # The same state the first call used. Rebuilding it from the question
        # alone showed a state-scoped check `{instructions, criteria}` when its
        # wording asks about `question` and `state`, so the re-ask answered a
        # question that was not on the page and was averaged in regardless.
        request = self._client.system_one().state(state)

        for entry in borderline:
            for index, wording in enumerate(entry.check.wordings):
                key = entry.keys[index] if index < len(entry.keys) else f'{entry.check.answer_key()}__w{index}'
                request.ask(key, self.build(wording))

        try:
            again = request.send()
        except TypeSafeError as error:
            # The first readings still stand, but the borderline ones were not
            # settled, and a run that swallows that reads like one that settled
            # them.
            report.unreachable(
                question.id,
                Text.of('report.resettle_failed', {'detail': str(error)}),
                Cause.of(error),
            )

            return out

        report.record_call(again.usage.total_tokens())

        for entry in borderline:
            out[entry.check.id] = [again]

        return out

    def _record(
        self,
        check: Check,
        keys: list[str],
        field: str | None,
        responses: list[SystemOneResponse],
        target: str,
        report: Report,
        question: ReviewedQuestion | None = None,
        locator: dict[str, str] | None = None,
    ) -> None:
        locator = locator or {}
        probabilities: list[float] = []
        # Per call as well as pooled. Two wordings that disagree the same way
        # every run are an error bar on one verdict, not a verdict that moves.
        per_call: list[float] = []

        for response in responses:
            this_call: list[float] = []

            for key in keys:
                value = _reading(response, key)

                if value is not None:
                    probabilities.append(value)
                    this_call.append(value)

            if len(this_call) > 0:
                per_call.append(_mean(this_call))

        # No reading survived: every one was missing or outside 0..1. The check
        # reached no verdict, so it is a loss and not a clear.
        if len(probabilities) == 0:
            report.unreachable(target, Text.of('report.no_reading_from', {
                'id': check.id,
                'questions': len(keys),
            }))

            return

        average = _mean(probabilities)
        report.reached(check.id, target)

        if check.scope == 'state-field' and field is not None:
            self._fields.setdefault(check.id, {}).setdefault(field, {})[target] = average

            return

        fired = average > check.trigger
        # Across calls, not across wordings: `undecided` says another run might
        # answer differently, so what has to straddle the trigger is what a run
        # produces, which is the mean of its wordings. The spread over the
        # wordings is reported either way.
        unstable = len(per_call) > 1 and min(per_call) <= check.trigger < max(per_call)

        # A cleared check within touching distance of its trigger is kept even
        # without `--all`, because the reading is already paid for and it is the
        # one a reader would otherwise re-run the whole query to see.
        worth_seeing = abs(average - check.trigger) <= ModelLinter.WORTH_SEEING

        # An `inconclusive` check is reported either way: dropping it when it
        # clears would say the defect is absent, which is the one thing its
        # reading cannot tell you.
        if not fired and not unstable and not worth_seeing and not check.inconclusive and not self._report_all:
            return

        elements = _locate(locator, responses[0]) if fired and len(locator) > 0 else []
        element = elements[0] if len(elements) == 1 else None

        if element is not None:
            title = Text.of('finding.title_with_detail', {
                'title': check.title,
                'detail': _describe(element, question),
            })
        elif len(elements) > 0:
            title = Text.of('finding.title_with_detail', {
                'title': check.title,
                'detail': ', '.join(_describe(found, question) for found in elements),
            })
        elif field is not None:
            title = Text.of('finding.title_with_field', {'title': check.title, 'field': field})
        else:
            title = check.title

        report.add(Finding(
            check_id=check.id,
            title=title,
            severity=Severity.from_name(check.severity),
            target=target,
            message=(check.message or check.title).replace('{field}', field or ''),
            hint=check.hint,
            suggest=check.suggest.replace('{target}', target).replace('{field}', field or ''),
            advice=check.advice,
            mode=check.mode,
            action=check.action,
            path=check.path(target, field) + ('' if element is None else f'/{_pointer_for(check, element)}'),
            paths=[f'{check.path(target, field)}/{_pointer_for(check, found)}' for found in elements],
            trigger=check.trigger,
            spread=max(probabilities) - min(probabilities) if len(probabilities) > 1 else None,
            near_trigger=abs(average - check.trigger) <= ModelLinter.NEAR,
            supersedes=check.supersedes,
            docs=check.docs,
            probability=average,
            fired=fired,
            unstable=unstable,
            patch=self._removal(check, target, field),
            evidence=_evidence_for(field, check, question, element),
            readings=probabilities if len(probabilities) > 1 else [],
            readings_of=_readings_of(len(keys), len(responses), self._repeat_count)
            if len(probabilities) > 1 else None,
        ))

    def _removal(self, check: Check, target: str, field: str | None) -> Patch | None:
        """
        The node a finding says to delete, where deleting one node is the fix.

        Rewording a question that asks Jev for arithmetic leaves the arithmetic
        with Jev. The fix is to take the question out and do the work in code.
        """
        if check.removes == 'question':
            # Taking the last question out leaves a query that asks nothing, which
            # this tool reports as an error of its own. The suggestion still
            # stands - the work belongs in code - but it is not a change anything
            # can apply on its own, so no patch is offered.
            return Patch(
                'remove', f'/questions/{Check.escape(target)}', None, Patch.DESTRUCTIVE,
            ) if self._question_count > 1 else None

        if check.removes == 'field':
            return None if field is None else Patch(
                'remove', check.path('state', field), None, Patch.DESTRUCTIVE,
            )

        return None

    def _record_type_comparison(
        self,
        check: Check,
        key: str,
        response: SystemOneResponse,
        question: ReviewedQuestion,
        target: str,
        report: Report,
    ) -> None:
        """
        The type check asks how the options in `criteria` relate to each other, and
        picks the primitive that fits. The finding is the disagreement with what
        the query declared.
        """
        report.reached(check.id, target)

        if not response.has(key):
            return

        answer = response.choice(key)
        picked = answer.choice()

        # How strongly the declared type is read as the wrong one. Defined the
        # same way whichever type the check picks, so a run that agrees with the
        # query still produces a reading, and `--all` can report it. Taking the
        # picked type's own probability instead left the check with no reading at
        # all wherever it agreed, and a firing rate whose denominator was the
        # questions it had already disagreed about.
        probability = 1.0 - (answer.probability_of(question.type) or 0.0)

        set_aside = picked != question.type and self._suppressed(check, picked, question)
        agrees = picked == question.type or set_aside

        fired = not agrees and probability > check.trigger

        if not fired and not self._report_all:
            return

        if agrees:
            message = Text.of('type.agrees', {'declared': question.type})
        elif picked == 'other':
            message = Text.of('type.none_fits', {'declared': question.type})
        else:
            message = Text.of('type.looks_like', {'picked': picked, 'declared': question.type})

        report.add(Finding(
            check_id=check.id,
            title=check.title,
            severity=Severity.from_name(check.severity),
            target=target,
            message=message,
            hint=check.hint,
            suggest=check.suggest,
            advice=check.advice,
            mode=check.mode,
            action=check.action,
            path=check.path(target),
            cleared_because=Text.of('type.suppressed_catch_all', {'picked': picked}) if set_aside else '',
            trigger=check.trigger,
            near_trigger=abs(probability - check.trigger) <= ModelLinter.NEAR,
            supersedes=check.supersedes,
            suggested_type=None if agrees or picked == 'other' else picked,
            docs=check.docs,
            # Not a probability that anything is wrong, and not the weight on the
            # primitive this picked either: one minus the weight on the primitive
            # the question declares, so it covers every other primitive at once.
            # `evidence` carries the picked one's own weight.
            measure='weight',
            probability=probability,
            fired=fired,
            evidence=Text.of('type.evidence', {
                'picked': picked,
                'picked_weight': answer.probability_of(picked) or 0.0,
                'declared': question.type,
                'declared_weight': answer.probability_of(question.type) or 0.0,
            }),
        ))

    def _suppressed(self, check: Check, answer: str, question: ReviewedQuestion) -> bool:
        """
        Whether the catalogue says this answer does not count as a finding.

        The conditions live in `suppress` and not here, so an implementation in
        another language reads the same rule out of the same file.
        """
        for rule in check.suppress:
            if rule['answer'] != answer:
                continue

            if rule['when'] == 'question_has_fallback_option' and question.has_fallback_option():
                return True

        return False


def _slug(text: str) -> str:
    """
    An id as an answer key, without losing which id it was.

    Collapsing every run of punctuation to `_` made `a.b`, `a-b` and `a_b` the
    same key, so one of them silently replaced the others on the request and the
    reading that came back was reported against whichever name was asked last.
    Each byte that cannot appear in a key becomes its own escape, so two different
    ids cannot produce one key.
    """
    return ''.join(
        chr(byte) if chr(byte).isascii() and chr(byte).isalnum() else f'_{byte:02x}'
        for byte in text.encode('utf-8')
    )


def _reading(response: SystemOneResponse, key: str) -> float | None:
    """
    One reading, or None if it is not a probability.

    A calibrated answer is between 0 and 1. A response carrying anything else is
    not a reading this can compare against a trigger, and reporting it verbatim
    produced findings at 1.50 on a query with nothing wrong with it.
    """
    if not response.has(key):
        return None

    value = response.noul(key).noul()

    return value if 0.0 <= value <= 1.0 else None


def _answer_keys(asked: list[Asked]) -> list[str]:
    """Every answer key a call carries, the locators among them."""
    return [key for entry in asked for key in [*entry.keys, *entry.locator]]


def _keys_for(asked: list[Asked], check_id: str) -> list[str]:
    """The answer keys one check was asked under."""
    return next((entry.keys for entry in asked if entry.check.id == check_id), [])


def _evidence_for(
    field: str | None,
    check: Check,
    question: ReviewedQuestion | None,
    element: str | None,
) -> str | None:
    parts: list[str] = []

    if element is not None and question is not None:
        key = element[6:] if element.startswith('level_') else element
        found = next((value for label, value in question.entries() if label == key), None)
        parts.append(Text.of('evidence.read', {
            'what': f'"{_shorten(found)}"' if isinstance(found, str) else element,
        }))
    elif field is not None:
        parts.append(Text.of('evidence.field', {'field': field}))
    elif question is not None:
        read = _quote(check, question)

        if read is not None:
            parts.append(read)

    return None if len(parts) == 0 else ' '.join(parts)


def _readings_of(wordings: int, calls: int, asked: int) -> str:
    """
    What the readings behind a probability are.

    `calls` counts the answers; `asked` is what the caller asked for. A borderline
    check is re-asked without `--repeats`, so a run of one can end with two
    answers, and calling those "2 repeats" names a flag nobody passed.
    """
    settled = asked < 2 and calls > 1

    if wordings > 1 and settled:
        return Text.of('readings.wordings_resettled', {'wordings': wordings})

    if settled:
        return Text.of('readings.one_and_a_resettle')

    if wordings > 1 and calls > 1:
        return Text.of('readings.wordings_over_repeats', {'wordings': wordings, 'repeats': calls})

    if wordings > 1:
        return Text.of('readings.wordings', {'wordings': wordings})

    return Text.of('readings.repeats', {'repeats': calls})


def _locate(locator: dict[str, str], response: SystemOneResponse) -> list[str]:
    """
    Every level or option the check fires on.

    Reporting one of three broken levels sends a literal reader round the loop
    twice more, so each is asked about and all of them are named.
    """
    found: list[str] = []

    for key, label in locator.items():
        if not response.has(key):
            continue

        # An empty label marks the Choice form, which names one element.
        if label == '':
            answer = response.choice(key)

            if (answer.probability_of(answer.choice()) or 0.0) >= 0.5:
                found.append(answer.choice())

            continue

        if (_reading(response, key) or 0.0) >= 0.6:
            found.append(label)

    return found


def _describe(element: str, question: ReviewedQuestion | None) -> str:
    """
    An element as a reader of their own query would name it.

    `level_2` is this module's own addressing, zero-based, and printing it at
    somebody whose rubric starts at 1 names a different level from the one that is
    wrong. A Choice option is already the label they wrote.
    """
    if not element.startswith('level_'):
        return f'`{element}`'

    index = int(element[6:])
    entries = question.entries() if question is not None else []
    levels = len(entries)
    found = next((value for label, value in entries if label == str(index)), None)
    quoted = Text.of('evidence.level_quoted', {
        'text': _shorten(found, 60),
    }) if isinstance(found, str) and found != '' else ''

    if levels > 0:
        return Text.of('evidence.level_of', {'index': index + 1, 'levels': levels, 'quoted': quoted})

    return Text.of('evidence.level', {'index': index + 1, 'quoted': quoted})


def _pointer_for(check: Check, element: str) -> str:
    """
    The pointer tail for one element a check located.

    `level_2` addresses index 2. A state field is a dotted path and splits into
    segments, so `ticket.body` is `/ticket/body`. An option label is a key
    somebody chose, so the `.` in `billing.invoices` belongs to the label, and
    splitting it addresses a node that is not there or one that is the wrong one.
    """
    if element.startswith('level_'):
        return element[6:]

    if check.reads == 'field':
        return '/'.join(Check.escape(segment) for segment in Query.segments(element))

    return Check.escape(element)


def _quote(check: Check, question: ReviewedQuestion) -> str | None:
    """What the check was looking at, quoted back from the query."""
    criteria = Json.inline(question.criteria) if question.has_criteria() else None

    if check.reads == 'instructions':
        return Text.of('evidence.read_quoted', {'what': _shorten(question.instructions_text())})

    if check.reads == 'criteria':
        return None if criteria is None else Text.of('evidence.read', {'what': _shorten(criteria)})

    if check.reads in ('question', 'type'):
        if criteria is None:
            return Text.of('evidence.read_quoted', {'what': _shorten(question.instructions_text())})

        return Text.of('evidence.read_with', {
            'instructions': _shorten(question.instructions_text(), 80),
            'criteria': _shorten(criteria, 80),
        })

    return None


def _shorten(text: str, limit: int = 150) -> str:
    """
    The text a check was shown, short enough to print.

    Cut from the middle, not the tail. A question that weighs several factors or
    asks two things usually carries the second at the end, and a quote that stops
    before it shows the reader everything except the reason.
    """
    if len(text) <= limit:
        return text

    head = (limit - 3) * 6 // 10

    return f'{text[:head]} … {text[len(text) - (limit - 3 - head):]}'


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)
