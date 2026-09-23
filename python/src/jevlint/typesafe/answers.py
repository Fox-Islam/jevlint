"""
One question's answer.

The SDK hands back typed models; these wrap the payload so a caller can ask what
kind of answer it is, and so an answer type a later API adds is left out instead
of taking the response down with it.
"""
from __future__ import annotations

from typing import Any

from .errors import TypeSafeError


class Answer:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def type(self) -> str:
        """The discriminator the API sent."""
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        return self._data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Answer | None:
        """The answer class matching the payload's `type`, or None for one not modelled here."""
        return {
            'noul': NoulAnswer,
            'choice': ChoiceAnswer,
            'score': ScoreAnswer,
        }.get(data.get('type'), lambda _: None)(data)

    def _number(self, key: str) -> float:
        value = self._data.get(key)

        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeSafeError(f'Expected a number for "{key}" in a {self.type()} answer.')

        return float(value)

    def _number_map(self, key: str) -> dict[str, float]:
        values = self._data.get(key) or {}

        if not isinstance(values, dict):
            raise TypeSafeError(f'Expected a map for "{key}" in a {self.type()} answer.')

        found: dict[str, float] = {}

        for name, value in values.items():
            try:
                found[str(name)] = float(value)
            except (TypeError, ValueError):
                found[str(name)] = 0.0

        return found


class NoulAnswer(Answer):
    """A yes/no answer."""

    def type(self) -> str:
        return 'noul'

    def noul(self) -> float:
        """Probability of a yes answer, from zero to one."""
        return self._number('noul')


class ChoiceAnswer(Answer):
    """The label the model selected, with its probability across every label."""

    def type(self) -> str:
        return 'choice'

    def choice(self) -> str:
        choice = self._data.get('choice')

        return choice if isinstance(choice, str) else ''

    def confidence(self) -> float:
        return self._number('confidence')

    def probabilities(self) -> dict[str, float]:
        return self._number_map('probabilities')

    def probability_of(self, label: str) -> float | None:
        """The probability of one label, or None where the model did not report it."""
        return self.probabilities().get(label)


class ScoreAnswer(Answer):
    """An expected score with the rubric it was drawn from."""

    def type(self) -> str:
        return 'score'

    def score(self) -> float:
        """Expected score, which may fall between the integer rubric levels."""
        return self._number('score')

    def nearest_level(self) -> int:
        return round(self.score())

    def confidence(self) -> float:
        return self._number('confidence')

    def legend(self) -> dict[int, Any]:
        legend = self._data.get('legend') or {}

        if not isinstance(legend, dict):
            return {}

        return {int(score): description for score, description in legend.items()}


class Usage:
    """
    Token counts for a request, when the API reports them.

    A provider that reports none is not a call that cost nothing, so the two are
    kept apart and the report says how many calls it could not price.
    """

    def __init__(self, input_tokens: int | None, output_tokens: int | None) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    @staticmethod
    def from_dict(data: dict[str, Any] | None) -> Usage:
        data = data or {}

        return Usage(_as_number(data.get('input_tokens')), _as_number(data.get('output_tokens')))

    def total_tokens(self) -> int | None:
        """Input and output tokens combined, or None where neither was reported."""
        if self.input_tokens is None and self.output_tokens is None:
            return None

        return (self.input_tokens or 0) + (self.output_tokens or 0)


def _as_number(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None

    return int(value)


class SystemOneResponse:
    """Answers keyed by question name, with the model that produced them and the tokens they cost."""

    def __init__(self, model: str, answers: dict[str, Answer], usage: Usage) -> None:
        self.model = model
        self.usage = usage
        self._answers = answers

    @staticmethod
    def from_dict(data: dict[str, Any]) -> SystemOneResponse:
        answers: dict[str, Answer] = {}
        raw = data.get('answers')

        if isinstance(raw, dict):
            for name, answer in raw.items():
                if not isinstance(answer, dict):
                    continue

                # An answer type a later API adds is left out rather than fatal.
                built = Answer.from_dict(answer)

                if built is not None:
                    answers[str(name)] = built

        model = data.get('model')
        usage = data.get('usage')

        return SystemOneResponse(
            model if isinstance(model, str) else '',
            answers,
            Usage.from_dict(usage if isinstance(usage, dict) else None),
        )

    def answers(self) -> dict[str, Answer]:
        return self._answers

    def answer(self, name: str) -> Answer:
        found = self._answers.get(name)

        if found is None:
            got = ', '.join(self._answers) if self._answers else 'none'

            raise TypeSafeError(f'No answer named "{name}" in the response; got: {got}.')

        return found

    def has(self, name: str) -> bool:
        return name in self._answers

    def noul(self, name: str) -> NoulAnswer:
        return self._expect(name, NoulAnswer, 'noul')

    def choice(self, name: str) -> ChoiceAnswer:
        return self._expect(name, ChoiceAnswer, 'choice')

    def score(self, name: str) -> ScoreAnswer:
        return self._expect(name, ScoreAnswer, 'score')

    def _expect(self, name: str, expected: type, wanted: str) -> Any:
        answer = self.answer(name)

        if not isinstance(answer, expected):
            raise TypeSafeError(f'Answer "{name}" is a {answer.type()} answer, not {wanted}.')

        return answer
