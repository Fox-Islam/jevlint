"""
One meaning-preserving rewrite of a query, and how to read its answers back onto
the same scale as the original's.

Every variant here is mechanical. A generated paraphrase would move both the
wording and whatever the generator took the question to mean, leaving the spread
attributable to neither.
"""
from __future__ import annotations

from typing import Any

from .query import ReviewedQuestion
from .typesafe import ChoiceAnswer, NoulAnswer, ScoreAnswer, SystemOneResponse

# What the unchanged run recorded about one question, so a rewrite's answer can be
# read back onto the same scale
Baseline = dict[str, Any]


class Variant:
    def name(self) -> str:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError

    def applies(self, question: ReviewedQuestion) -> bool:
        """Whether this variant changes anything about this question."""
        return True

    def apply(self, question: ReviewedQuestion) -> ReviewedQuestion:
        return question

    def read(
        self,
        response: SystemOneResponse,
        question: ReviewedQuestion,
        baseline: Baseline,
    ) -> float | None:
        """The answer as one number on [0, 1], comparable with the original's."""
        if not response.has(question.id):
            return None

        answer = response.answer(question.id)

        if isinstance(answer, NoulAnswer):
            return answer.noul()

        if isinstance(answer, ChoiceAnswer):
            return answer.probability_of(baseline.get('winner') or answer.choice())

        if isinstance(answer, ScoreAnswer):
            return answer.score() / max(1, (baseline.get('levels') or 2) - 1)

        return None


class Unchanged(Variant):
    """
    The query exactly as written. Sent several times, it gives the spread every
    other variant's movement is measured against.
    """

    def name(self) -> str:
        return 'unchanged'

    def describe(self) -> str:
        return 'the query as written'


class CriteriaStripped(Variant):
    """
    The same instructions with the criteria removed.

    This variant changes the question, which the others do not. The gap it opens
    is how much of the answer the criteria are carrying.
    """

    def name(self) -> str:
        return 'criteria-stripped'

    def describe(self) -> str:
        return (
            'the instructions alone, with the criteria removed - the one rewrite here '
            'that changes the question'
        )

    def applies(self, question: ReviewedQuestion) -> bool:
        # The criteria that reach the request, not the ones in the file. A Noul is
        # sent with `true` and `false` and nothing else, so criteria under any
        # other key never leave, and stripping them would send the baseline again
        # under the name of a rewrite.
        criteria = question.criteria if isinstance(question.criteria, dict) else {}

        return question.type == 'noul' and ('true' in criteria or 'false' in criteria)

    def apply(self, question: ReviewedQuestion) -> ReviewedQuestion:
        return question.with_criteria(None)


class NoulAsChoice(Variant):
    """
    The same yes/no question asked as a two-option Choice.

    The documented example has a Noul at 0.22 and the same question as a Choice at
    0.01 on the same ticket. Nothing guarantees the two agree, so a threshold
    tuned on one does not carry to the other, and this measures the gap on your
    question.
    """

    def name(self) -> str:
        return 'asked-as-choice'

    def describe(self) -> str:
        return 'the same yes/no question asked as a two-option Choice'

    def applies(self, question: ReviewedQuestion) -> bool:
        return question.type == 'noul'

    def apply(self, question: ReviewedQuestion) -> ReviewedQuestion:
        criteria = question.criteria if isinstance(question.criteria, dict) else {}

        # A criterion written as a list of bullets is a shape the request takes.
        # Requiring a string here would replace it with a placeholder, and the row
        # would measure the criteria going missing as well as the primitive
        # changing.
        def describes(value: Any, fallback: str) -> Any:
            return value if isinstance(value, (str, dict, list)) else fallback

        return ReviewedQuestion(question.id, 'choice', question.instructions, {
            'yes': describes(criteria.get('true'), 'The answer to the question is yes.'),
            'no': describes(criteria.get('false'), 'The answer to the question is no.'),
        }, question.raw)

    def read(
        self,
        response: SystemOneResponse,
        question: ReviewedQuestion,
        baseline: Baseline,
    ) -> float | None:
        answer = response.answer(question.id) if response.has(question.id) else None

        if not isinstance(answer, ChoiceAnswer):
            return None

        return answer.probability_of('yes')


class OptionsReversed(Variant):
    """
    The same Choice with its options listed back to front.

    Nothing about the question changes, so any movement comes from the order the
    options were listed in, which the calling code has no way to see.
    """

    def name(self) -> str:
        return 'options-reversed'

    def describe(self) -> str:
        return 'the same options in the opposite order'

    def applies(self, question: ReviewedQuestion) -> bool:
        return question.type == 'choice' and len(question.entries()) > 1

    def apply(self, question: ReviewedQuestion) -> ReviewedQuestion:
        return question.with_criteria(dict(reversed(question.entries())))


class LevelsReversed(Variant):
    """
    The same rubric with its levels in the opposite order, read back flipped.

    The rubric describes the same situations either way, and each level is
    evaluated on its own, so the flipped reading should fall where the original
    did. Where it does not, the scale is being read as an ordering instead of as
    the descriptions it is made of.
    """

    def name(self) -> str:
        return 'levels-reversed'

    def describe(self) -> str:
        return 'the same levels in the opposite order, with the reading flipped back'

    def applies(self, question: ReviewedQuestion) -> bool:
        return question.type == 'score' and len(question.entries()) > 1

    def apply(self, question: ReviewedQuestion) -> ReviewedQuestion:
        return question.with_criteria([value for _, value in reversed(question.entries())])

    def read(
        self,
        response: SystemOneResponse,
        question: ReviewedQuestion,
        baseline: Baseline,
    ) -> float | None:
        answer = response.answer(question.id) if response.has(question.id) else None

        if not isinstance(answer, ScoreAnswer):
            return None

        return 1.0 - (answer.score() / max(1, (baseline.get('levels') or 2) - 1))


class Reworded(Variant):
    """
    A rewording you wrote yourself, read from `--variants`.

    A paraphrase belongs here, where you have judged it to mean the same thing.
    When the answer then moves, the disagreement is between you and the model,
    with no generator in between.
    """

    def __init__(self, name: str, instructions: dict[str, str]) -> None:
        self._name = name
        # question id to its rewording
        self._instructions = instructions

    def name(self) -> str:
        return self._name

    def describe(self) -> str:
        return 'your rewording'

    def applies(self, question: ReviewedQuestion) -> bool:
        return question.id in self._instructions

    def apply(self, question: ReviewedQuestion) -> ReviewedQuestion:
        # `applies()` has already found the id, so there is nothing to fall back to.
        return question.with_instructions(self._instructions.get(question.id, ''))
