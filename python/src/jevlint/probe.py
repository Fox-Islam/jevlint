"""
Runs the query, then runs rewrites of it that mean the same thing, and reports
how far each one moved the answer.

The linter reports that a question is vague. This reports that your question,
against your state, answers 0.72 one way round and 0.31 the other.

Movement is measured against the spread of the unchanged query repeated, so a
variant that moves less than the model's own jitter is reported as moving
nothing.
"""
from __future__ import annotations

import math
from typing import Any

from .errors import JevLintError
from .query import Query, ReviewedQuestion
from .report import Note
from .support import Cause
from .text import Text
from .typesafe import Choice, ChoiceAnswer, Client, Noul, Question, Score, SystemOneResponse
from .typesafe.errors import TypeSafeError
from .variants import (
    Baseline,
    CriteriaStripped,
    KeysHidden,
    LevelsReversed,
    NoulAsChoice,
    OptionsReversed,
    Reworded,
    Unchanged,
    Variant,
)


class QuestionBuilder:
    """Turns a question from the file under test back into one that can be sent."""

    @staticmethod
    def build(question: ReviewedQuestion) -> Question:
        if question.type == 'noul':
            return _noul(question)

        if question.type == 'choice':
            return Choice.ask(question.instructions).options(_options(question))

        if question.type == 'score':
            return Score.ask(question.instructions).levels([value for _, value in question.entries()])

        raise JevLintError(Text.of('probe.question_has_no_type', {'id': question.id}))


def _noul(question: ReviewedQuestion) -> Noul:
    built = Noul.ask(question.instructions)
    criteria = question.criteria if isinstance(question.criteria, dict) else {}

    if 'true' in criteria:
        built.yes(_content(criteria['true']))

    if 'false' in criteria:
        built.no(_content(criteria['false']))

    return built


def _options(question: ReviewedQuestion) -> dict[str, Any]:
    return {label: _content(description) for label, description in question.entries()}


def _content(value: Any) -> Any:
    return value if isinstance(value, (str, dict, list)) else None


class Reading:
    """What one variant did to one question."""

    def __init__(self, variant: str, describe: str, value: float | None, error: str | None = None) -> None:
        self.variant = variant
        self.describe = describe
        self.value = value
        self.error = error


class QuestionProbe:
    """Every reading taken of one question, and what they add up to."""

    # Movement smaller than this could not cross a threshold anybody sets
    NEGLIGIBLE = 0.05

    # How near the middle a yes/no answer sits before the threshold reading it
    # decides the outcome.
    #
    # A Noul answers with the probability of yes, and a caller turns that into a
    # decision at a threshold of their own. This band is a judgement and not a
    # measured figure: no corpus run sets it, and the probe reports what it covers
    # without gating on it.
    UNDECIDED = 0.15

    def __init__(self, question: ReviewedQuestion) -> None:
        self.question = question
        self.repeats: list[float] = []
        self.readings: list[Reading] = []
        # The label a Choice's probability belongs to, where the question is one
        self.reading: str | None = None

    def moved(self, reading: Reading) -> bool:
        """
        Whether a rewrite moved the answer.

        The rule lives here so the table and the JSON cannot disagree about it:
        movement counts when it clears both three times the repeat spread and a
        size any threshold would notice.
        """
        delta = self.delta(reading)

        return delta is not None and abs(delta) > 3 * self.floor() and abs(delta) >= QuestionProbe.NEGLIGIBLE

    def undecided(self) -> bool:
        """
        Whether the query as written failed to decide this question.

        Only a Noul has a middle. A Choice reports the winning label's own
        probability and a Score a position on its scale, and neither is undecided
        for sitting halfway.
        """
        baseline = self.baseline()

        return (
            self.question.type == 'noul'
            and baseline is not None
            and abs(baseline - 0.5) <= QuestionProbe.UNDECIDED
        )

    def flips(self) -> bool:
        """
        Whether the repeats of the unchanged query fell on both sides of the
        middle, so the answer did not hold still from one send to the next.
        """
        if self.question.type != 'noul' or len(self.repeats) < 2:
            return False

        return min(self.repeats) <= 0.5 < max(self.repeats)

    def baseline(self) -> float | None:
        if len(self.repeats) == 0:
            return None

        return sum(self.repeats) / len(self.repeats)

    def noise(self) -> float | None:
        """
        The spread of the unchanged query across its repeats.

        These repeats are sent back to back. Requests spread out over time vary
        more than clustered ones, and nothing here sends them that way, so this is
        a floor.
        """
        count = len(self.repeats)

        if count < 2:
            return None

        mean = sum(self.repeats) / count

        return math.sqrt(sum((value - mean) ** 2 for value in self.repeats) / (count - 1))

    def floor(self) -> float:
        """The noise floor to compare against: the measured one, or the published one."""
        return max(self.noise() or 0.0, Probe.PUBLISHED_NOISE)

    def delta(self, reading: Reading) -> float | None:
        baseline = self.baseline()

        if baseline is None or reading.value is None:
            return None

        return reading.value - baseline

    def ratio(self, reading: Reading) -> float | None:
        """How far a variant moved the answer, in multiples of the noise floor."""
        delta = self.delta(reading)

        return None if delta is None else abs(delta) / self.floor()


class Probe:
    # The floor used when a run is too short to measure its own spread.
    #
    # TypeSafe's consistency cookbook publishes 0.0102 as the mean per-question
    # probability deviation over 15 repeats per condition, which is the nearest
    # published figure; where this one came from is not recorded here.
    PUBLISHED_NOISE = 0.0085

    def __init__(self, client: Client) -> None:
        self._client = client
        self._calls = 0
        self._tokens = 0
        self._notes: list[Note] = []
        # Calls that failed or came back without answering
        self._unreachable = 0

    def run(self, query: Query, repeats: int = 5, extra: list[Variant] | None = None) -> dict[str, QuestionProbe]:
        if not query.has_state():
            raise JevLintError(Text.of('probe.needs_state'))

        probes: dict[str, QuestionProbe] = {}
        unsendable: list[str] = []

        for question in query.questions:
            if question.is_known_type():
                probes[question.id] = QuestionProbe(question)

                continue

            unsendable.append(question.id)

        if len(probes) == 0:
            raise JevLintError(Text.of('probe.nothing_sendable'))

        # A question of a type this cannot send is left out of every reading, so a
        # report that does not name it says nothing moved on a question it never
        # asked. `check` reports the same query as an error.
        if len(unsendable) > 0:
            self._notes.append(Note(Text.of('probe.unsendable_questions', {
                'ids': ', '.join(unsendable),
                'count': len(unsendable),
            }), 'skipped'))

        baseline = self._baseline(query, probes, repeats)

        for variant in [*Probe.variants(), *(extra or [])]:
            self._variant(query, probes, variant, baseline)

        return probes

    @staticmethod
    def variants() -> list[Variant]:
        return [CriteriaStripped(), NoulAsChoice(), OptionsReversed(), KeysHidden(), LevelsReversed()]

    @staticmethod
    def rewordings(rewordings: dict[str, Any]) -> list[Variant]:
        """`rewordings` maps a variant name to a map of question id to its rewording."""
        variants: list[Variant] = []

        # The built-ins and the baseline. Two rows under one name share a legend
        # line, and the footer's note about which rewrites are expected to move
        # would speak about the wrong one.
        taken = ['unchanged', *[variant.name() for variant in Probe.variants()]]

        for name, instructions in rewordings.items():
            if name in taken:
                raise JevLintError.of(JevLintError.USAGE, Text.of('probe.variant_name_taken', {
                    'name': name,
                    'taken': ', '.join(taken),
                }))

            # A file written as {"question_id": "text"} names no variant, and the
            # one input written by hand is the one that has to fail loudly.
            if not isinstance(instructions, dict) or len(instructions) == 0:
                raise JevLintError.of(
                    JevLintError.USAGE,
                    Text.of('probe.variant_not_a_map', {'name': name}),
                )

            strings: dict[str, str] = {}

            for question_id, text in instructions.items():
                if not isinstance(text, str):
                    raise JevLintError.of(JevLintError.USAGE, Text.of('probe.variant_not_text', {
                        'name': name,
                        'id': question_id,
                        'type': _php_type(text),
                    }))

                strings[question_id] = text

            variants.append(Reworded(name, strings))

        return variants

    def _baseline(
        self,
        query: Query,
        probes: dict[str, QuestionProbe],
        repeats: int,
    ) -> dict[str, Baseline]:
        """
        Send the query unchanged, several times. The mean is what everything is
        compared with; the spread is what counts as movement.
        """
        unchanged = Unchanged()
        meta: dict[str, Baseline] = {
            question_id: {'levels': len(probe.question.entries()) or 2}
            for question_id, probe in probes.items()
        }

        for run in range(max(1, repeats)):
            questions = {question_id: probe.question for question_id, probe in probes.items()}
            response = self._send(query, questions)

            if response is None:
                continue

            for question_id, probe in probes.items():
                about = meta.get(question_id, {})

                if run == 0 and response.has(question_id):
                    answer = response.answer(question_id)

                    if isinstance(answer, ChoiceAnswer):
                        about['winner'] = answer.choice()
                        probe.reading = Text.of('probe.reading_choice', {'label': answer.choice()})

                    if probe.question.type == 'score':
                        probe.reading = Text.of('probe.reading_score', {'levels': about.get('levels', 2)})

                    if probe.question.type == 'noul':
                        probe.reading = Text.of('probe.reading_yes')

                    meta[question_id] = about

                value = unchanged.read(response, probe.question, about)

                if value is not None:
                    probe.repeats.append(value)

        return meta

    def _variant(
        self,
        query: Query,
        probes: dict[str, QuestionProbe],
        variant: Variant,
        meta: dict[str, Baseline],
    ) -> None:
        questions = {
            question_id: variant.apply(probe.question)
            for question_id, probe in probes.items()
            if variant.applies(probe.question)
        }

        if len(questions) == 0:
            return

        response = self._send(query, questions)

        for question_id, question in questions.items():
            probes[question_id].readings.append(Reading(
                variant.name(),
                variant.describe(),
                None if response is None else variant.read(response, question, meta.get(question_id, {})),
                Text.of('probe.call_failed') if response is None else None,
            ))

    def _send(self, query: Query, questions: dict[str, ReviewedQuestion]) -> SystemOneResponse | None:
        request = self._client.system_one().state(query.state)

        for question_id, question in questions.items():
            request.ask(question_id, QuestionBuilder.build(question))

        try:
            response = request.send()
        except TypeSafeError as error:
            self._notes.append(Note(str(error), 'unreachable', None, None, Cause.of(error)))
            self._unreachable += 1

            return None

        missing = [question_id for question_id in questions if not response.has(question_id)]

        if len(missing) > 0:
            self._notes.append(Note(Text.of('probe.partial_answer', {
                'answered': len(questions) - len(missing),
                'asked': len(questions),
                'missing': missing[0],
            }), 'unreachable', missing[0], None, Cause.ANSWER))
            self._unreachable += 1

        self._calls += 1
        self._tokens += response.usage.total_tokens() or 0

        return response

    def calls(self) -> int:
        return self._calls

    def unreachable(self) -> int:
        return self._unreachable

    def is_complete(self) -> bool:
        """Whether every call this probe made came back with what it asked for."""
        return self._unreachable == 0

    def tokens(self) -> int:
        return self._tokens

    def notes(self) -> list[Note]:
        return self._notes


def _php_type(value: Any) -> str:
    """`gettype`, which is what the message about a rewording's value names."""
    if value is None:
        return 'NULL'

    if isinstance(value, bool):
        return 'boolean'

    if isinstance(value, int):
        return 'integer'

    if isinstance(value, float):
        return 'double'

    if isinstance(value, (list, dict)):
        return 'array'

    return type(value).__name__
