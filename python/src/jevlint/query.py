"""A Jev query as it would be sent, and the questions inside it."""
from __future__ import annotations

from typing import Any

from .errors import JevLintError
from .support import Json
from .text import Text

# The primitives Jev takes. The catalogue is checked against this list, so a
# check narrowed to a primitive that does not exist is refused at load.
PRIMITIVES = ('noul', 'choice', 'score')


class ReviewedQuestion:
    """One question from the query under review."""

    def __init__(
        self,
        question_id: str,
        type: str,
        instructions: Any,
        criteria: dict[str, Any] | list[Any] | None,
        raw: dict[str, Any],
    ) -> None:
        self.id = question_id
        self.type = type
        self.instructions = instructions
        self.criteria = criteria
        self.raw = raw

    def with_criteria(self, criteria: dict[str, Any] | list[Any] | None) -> ReviewedQuestion:
        """The same question with other criteria, for a probe variant."""
        return ReviewedQuestion(self.id, self.type, self.instructions, criteria, self.raw)

    def with_instructions(self, instructions: str) -> ReviewedQuestion:
        """The same question asked in other words."""
        return ReviewedQuestion(self.id, self.type, instructions, self.criteria, self.raw)

    @staticmethod
    def from_dict(question_id: str, data: dict[str, Any]) -> ReviewedQuestion:
        type = data.get('type')
        instructions = data.get('instructions')
        criteria = data.get('criteria')

        return ReviewedQuestion(
            question_id,
            type.lower() if isinstance(type, str) else '',
            instructions if isinstance(instructions, (str, dict, list)) else None,
            criteria if isinstance(criteria, (dict, list)) else None,
            data,
        )

    def criteria_is_list(self) -> bool:
        """Whether `criteria` was written as a JSON array."""
        return isinstance(self.criteria, list)

    def entries(self) -> list[tuple[str, Any]]:
        """The criteria entries in order, as label and value pairs."""
        if self.criteria is None:
            return []

        if isinstance(self.criteria, list):
            return [(str(index), value) for index, value in enumerate(self.criteria)]

        return list(self.criteria.items())

    def instructions_text(self) -> str:
        """The instructions as one string, whatever structure they were given in."""
        if self.instructions is None:
            return ''

        return self.instructions if isinstance(self.instructions, str) else Json.inline(self.instructions)

    def has_criteria(self) -> bool:
        return self.criteria is not None and len(self.entries()) > 0

    def has_fallback_option(self) -> bool:
        """
        Whether a Choice carries an option for what the others do not cover.

        A Score's levels are steps along one quality and cannot hold one, so this
        is evidence the question is a Choice whatever else it looks like.
        """
        if self.type != 'choice' or self.criteria is None:
            return False

        labels = [label.lower() for label, _ in self.entries()]

        if any(label in Text.list('words.fallback_labels') for label in labels):
            return True

        # A catch-all can be called anything. Matching only a list of labels
        # missed one named `misc` and offered to add a second one beside it,
        # which splits the mass the catch-all exists to collect. What makes an
        # option a catch-all is what its description says it holds.
        phrases = Text.list('words.catch_all_phrases')

        for _, description in self.entries():
            if not isinstance(description, str):
                continue

            text = description.lower()

            if any(phrase in text for phrase in phrases):
                return True

        return False

    def is_known_type(self) -> bool:
        return self.type in PRIMITIVES

    def as_state(self) -> dict[str, Any]:
        """
        What a question-scoped check is shown.

        The id is left out: Jev never sees it when the query runs, so the checker
        should not see it either, or a well-named id papers over an instruction
        that says nothing. The declared type is left out for a second reason -
        `question/type-mismatch` works out which primitive fits the answer, and
        naming the declared one in the state hands it what it is meant to decide.
        Which checks apply to which type is settled in code before the call.
        """
        state: dict[str, Any] = {'instructions': self.instructions if self.instructions is not None else ''}

        if self.has_criteria():
            state['criteria'] = self.criteria

        return state


class Query:
    """
    A Jev query as it would be sent: one state and the questions asked about it.

    The file format is the request body, so what you already send is what you
    check. A `model` key is read if present and otherwise ignored.
    """

    def __init__(
        self,
        state: Any,
        questions: list[ReviewedQuestion],
        model: str | None,
        source: str,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.state = state
        self.questions = questions
        self.model = model
        self.source = source
        # the request as it was written
        self.raw = raw if raw is not None else {}

    def with_state(self, state: dict[str, Any]) -> Query:
        """The same query against state from somewhere else, for `probe --state`."""
        return Query(state, self.questions, self.model, self.source, {**self.raw, 'state': state})

    @staticmethod
    def from_file(path: str) -> Query:
        return Query.from_json(Json.contents(path), path)

    @staticmethod
    def from_json(json_text: str, source: str = 'query') -> Query:
        """
        A query from the request body as it was written.

        `criteria` written as a JSON object and as a JSON array are different
        requests, and this is the entry point that cannot get the two confused.
        """
        # `[]` decodes to something the checks can walk, so a JSON list reached
        # them and came back as `query/no-questions` instead of a shape error.
        if Json.is_list(json_text):
            raise JevLintError.of(JevLintError.QUERY, Text.of('query.is_a_list', {'source': source}))

        return Query.from_dict(Json.decode(json_text, source), source)

    @staticmethod
    def from_dict(data: dict[str, Any], source: str = 'query') -> Query:
        questions = data.get('questions')

        if questions is not None and not isinstance(questions, dict):
            raise JevLintError.of(JevLintError.QUERY, Text.of('query.questions_is_a_list', {'source': source}))

        reviewed: list[ReviewedQuestion] = []

        for question_id, question in (questions or {}).items():
            if not isinstance(question, dict):
                raise JevLintError.of(JevLintError.QUERY, Text.of('query.question_not_an_object', {
                    'source': source,
                    'id': question_id,
                }))

            reviewed.append(ReviewedQuestion.from_dict(question_id, question))

        state = data.get('state')

        # A number or a boolean here is a request the API rejects. Coercing it to
        # nothing reported the query as carrying no state, which is a different
        # defect and one the caller can exit 0 on.
        if state is not None and not isinstance(state, (str, dict, list)):
            raise JevLintError.of(JevLintError.QUERY, Text.of('query.state_wrong_type', {
                'source': source,
                'holds': Text.of('query.state_a_boolean') if isinstance(state, bool)
                else Text.of('query.state_a_number') if isinstance(state, (int, float))
                else f'a {type(state).__name__}',
            }))

        model = data.get('model')

        return Query(state, reviewed, model if isinstance(model, str) else None, source, data)

    def has_state(self) -> bool:
        if self.state is None or self.state == '':
            return False

        # An empty object is as much "no state" as an empty list: the request
        # goes out with nothing for the questions to read.
        if isinstance(self.state, (dict, list)):
            return len(self.state) > 0

        return True

    def state_fields(self) -> dict[str, Any] | None:
        """State as a JSON object, or None when it is a bare string or a list."""
        return self.state if isinstance(self.state, dict) else None

    def state_leaves(self, depth: int = 2) -> list[str]:
        """
        The removable parts of the state, by dotted path.

        A state is commonly one object holding everything, so stopping at the top
        level would ask whether that object is needed and never get a useful
        answer. Nesting is followed to `depth` levels, however wide each one is: a
        width limit would blind the field checks on exactly the states they exist
        for.
        """
        fields = self.state_fields()

        return [] if fields is None else _walk(fields, '', depth)

    @staticmethod
    def quote(segment: str) -> str:
        """
        A key with the separator in it, made safe to join with.

        A state key can hold a `.`, so joining it into a dotted path unescaped is
        indistinguishable from nesting: the field `a.b` reads as `a` containing
        `b`, and addresses a node that is not there.
        """
        return segment.replace('\\', '\\\\').replace('.', '\\.')

    @staticmethod
    def segments(path: str) -> list[str]:
        """A dotted path back into the keys it was built from."""
        parts: list[str] = []
        current = ''
        escaped = False

        for char in path:
            if escaped:
                current += char
                escaped = False

                continue

            if char == '\\':
                escaped = True
            elif char == '.':
                parts.append(current)
                current = ''
            else:
                current += char

        parts.append(current)

        return parts

    def state_at(self, path: str) -> Any:
        node: Any = self.state_fields()

        for part in Query.segments(path):
            if not isinstance(node, dict) or part not in node:
                return None

            node = node[part]

        return node

    def state_size(self) -> int:
        """
        The state's size, in characters.

        The threshold is described in characters, so this counts code points and
        not the bytes a multi-byte state takes on the wire.
        """
        return len(Json.inline(self.state if self.state is not None else ''))

    def state_with(self, question: ReviewedQuestion) -> dict[str, Any]:
        """
        The state a state-scoped check is shown: the question it is about, and the
        material itself, each under a name the check can point at.

        The question goes in whole. Its `criteria` decide as much about whether a
        query is any good as its instruction does, and a check shown the
        instruction alone cannot tell a query that settles an edge case from one
        that leaves it open.
        """
        return {'question': question.as_state(), 'state': self.state}

    def only(self, ids: list[str]) -> Query:
        """The same query narrowed to some of its questions, for a cheap re-check."""
        if len(ids) == 0:
            return self

        return Query(
            self.state,
            [question for question in self.questions if question.id in ids],
            self.model,
            self.source,
            self.raw,
        )

    def question(self, question_id: str) -> ReviewedQuestion | None:
        return next((question for question in self.questions if question.id == question_id), None)


def _walk(node: dict[str, Any], prefix: str, depth: int) -> list[str]:
    paths: list[str] = []

    for key, value in node.items():
        path = Query.quote(key) if prefix == '' else f'{prefix}.{Query.quote(key)}'

        # Descend on size, not in spite of it. A width limit blinds the field
        # checks on exactly the states they exist for: the bigger the object, the
        # fewer fields they see, and a fifteen-field object reads as one field
        # nobody reads.
        if depth > 1 and isinstance(value, dict):
            paths += _walk(value, path, depth - 1)

            continue

        paths.append(path)

    return paths
