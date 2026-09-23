"""
The questions a call carries, built up a call at a time.

The SDK takes plain dictionaries. These builders exist because a check and a
reviewed question are both assembled piece by piece from data, and because the
request body is compared against the other two implementations byte for byte,
so what goes in it is written here and not inferred.
"""
from __future__ import annotations

from typing import Any

from .errors import TypeSafeError

# Instructions, and every criterion description: text, a JSON-ready value, or nothing
Content = Any


class Question:
    """One question put to the model."""

    def __init__(self) -> None:
        self._instructions: Content = None

    def instructions(self, instructions: Content) -> Question:
        """Set the question itself: text, a JSON-ready value, or nothing."""
        self._instructions = instructions

        return self

    def get_instructions(self) -> Content:
        return self._instructions

    def type(self) -> str:
        """The discriminator the API uses to pick an answer shape."""
        raise NotImplementedError

    def validate(self, name: str) -> None:
        """Reject a question the API would refuse, naming it as the caller keyed it."""
        raise NotImplementedError

    def _payload(self) -> dict[str, Any]:
        """The criteria half of the request body."""
        raise NotImplementedError

    def to_json(self) -> dict[str, Any]:
        return {'type': self.type(), 'instructions': self._instructions, **self._payload()}


class Noul(Question):
    """
    A yes/no question, answered with the probability of yes.

    https://docs.typesafe.ai/primitives/noul
    """

    def __init__(self) -> None:
        super().__init__()
        self._yes: Content = None
        self._no: Content = None
        self._described = False

    @staticmethod
    def ask(instructions: Content = None) -> Noul:
        built = Noul()
        built.instructions(instructions)

        return built

    def yes(self, description: Content) -> Noul:
        """Describe what a yes answer means."""
        self._yes = description
        self._described = True

        return self

    def no(self, description: Content) -> Noul:
        """Describe what a no answer means."""
        self._no = description
        self._described = True

        return self

    def type(self) -> str:
        return 'noul'

    def validate(self, name: str) -> None:
        """Both outcomes are optional: a noul question with no criteria is valid."""

    def _payload(self) -> dict[str, Any]:
        if not self._described:
            return {}

        return {'criteria': {'true': self._yes, 'false': self._no}}


class Choice(Question):
    """
    A question answered with one of several named labels.

    https://docs.typesafe.ai/primitives/choice
    """

    def __init__(self) -> None:
        super().__init__()
        self._criteria: dict[str, Content] = {}

    @staticmethod
    def ask(instructions: Content = None) -> Choice:
        built = Choice()
        built.instructions(instructions)

        return built

    @staticmethod
    def between(options: list[str] | dict[str, Content]) -> Choice:
        """Start from a set of labels, as a list of names or a map of name to description."""
        return Choice().options(options)

    def option(self, label: str, description: Content = None) -> Choice:
        """Add one label, with an optional description of when it applies."""
        self._criteria[label] = description

        return self

    def options(self, options: list[str] | dict[str, Content]) -> Choice:
        """Add several labels, as a list of names or a map of name to description."""
        if isinstance(options, list):
            for label in options:
                if not isinstance(label, str):
                    raise TypeSafeError('Choice options given as a list must be label strings.')

                self.option(label)

            return self

        for label, description in options.items():
            self.option(label, description)

        return self

    def get_options(self) -> dict[str, Content]:
        return dict(self._criteria)

    def type(self) -> str:
        return 'choice'

    def validate(self, name: str) -> None:
        if len(self._criteria) == 0:
            raise TypeSafeError(f'Choice question "{name}" has no options; at least one label is required.')

    def _payload(self) -> dict[str, Any]:
        return {'criteria': dict(self._criteria)}


class Score(Question):
    """
    A question answered with a level on an ordered rubric, scored from zero.

    https://docs.typesafe.ai/primitives/score
    """

    def __init__(self) -> None:
        super().__init__()
        self._criteria: list[Content] = []

    @staticmethod
    def ask(instructions: Content = None) -> Score:
        built = Score()
        built.instructions(instructions)

        return built

    @staticmethod
    def rubric(levels: list[Content]) -> Score:
        """Start from a rubric: descriptions in order, indexed by score from zero."""
        return Score().levels(levels)

    def level(self, description: Content) -> Score:
        """Append the next level of the rubric. The first call describes score 0."""
        self._criteria.append(description)

        return self

    def levels(self, levels: list[Content]) -> Score:
        for description in levels:
            self.level(description)

        return self

    def get_levels(self) -> list[Content]:
        return list(self._criteria)

    def type(self) -> str:
        return 'score'

    def validate(self, name: str) -> None:
        if len(self._criteria) < 2:
            raise TypeSafeError(
                f'Score question "{name}" has {len(self._criteria)} level(s); a rubric needs at least two.',
            )

    def _payload(self) -> dict[str, Any]:
        return {'criteria': list(self._criteria)}
