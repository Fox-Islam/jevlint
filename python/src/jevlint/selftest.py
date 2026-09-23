"""
Does each model check separate a clean question from a broken one?

Every check ships one example it should fire on and one it should not. This asks
both and reports the span between them. A check whose span is small is not
measuring what its title claims, whatever it reports about your query.
"""
from __future__ import annotations

from typing import Any

from .catalogue import Catalogue, Check
from .errors import JevLintError
from .model_linter import ModelLinter
from .query import ReviewedQuestion
from .support import Json
from .text import Text
from .typesafe import Client
from .typesafe.errors import TypeSafeError


class CheckScore:
    """What one check scored against its own clean and broken examples."""

    def __init__(
        self,
        check: Check,
        clean: float | None,
        broken: float | None,
        fixed: float | None = None,
        domain: str = '',
        offers_fixed: bool = False,
    ) -> None:
        self.check = check
        self.clean = clean
        self.broken = broken
        self.fixed = fixed
        self.domain = domain
        # Whether the fixture shipped a `fixed` example at all. Without it, a
        # `fixed` call that failed and a check that ships no rewrite are both
        # None, and only the second is a pass.
        self.offers_fixed = offers_fixed

    def span(self) -> float | None:
        if self.clean is None or self.broken is None:
            return None

        return self.broken - self.clean

    def verdict(self) -> str:
        """
        `flat` and `inverted` mean the check is not measuring what it claims.
        `fires-on-clean` and `misses-broken` mean it is, but the trigger is in the
        wrong place.
        """
        span = self.span()

        # Before anything about the readings: a run that lost a call did not
        # measure this check, and reporting a catalogue as wrong on the strength
        # of a call that never came back sends the reader to the wrong file.
        if span is None or (self.offers_fixed and self.fixed is None):
            return 'errored'

        # A suggestion that leaves the check firing sends the reader in a circle
        if self.fixed is not None and self.fixed > self.check.trigger:
            return 'suggestion-fails'

        if span < 0:
            return 'inverted'

        if span < SelfTest.FLAT:
            return 'flat'

        if self.clean is not None and self.clean > self.check.trigger:
            return 'fires-on-clean'

        if self.broken is not None and self.broken <= self.check.trigger:
            return 'misses-broken'

        return 'weak' if span < SelfTest.WEAK else 'ok'

    def passed(self) -> bool:
        return self.verdict() in ('ok', 'weak')

    def errored(self) -> bool:
        """The check was never scored, because the call carrying it did not come back."""
        return self.verdict() == 'errored'

    def to_dict(self) -> dict[str, Any]:
        return {
            'check': self.check.id,
            'domain': None if self.domain == '' else self.domain,
            'trigger': self.check.trigger,
            'clean': self.clean,
            'broken': self.broken,
            'fixed': self.fixed,
            'span': self.span(),
            'verdict': self.verdict(),
        }


class SelfTest:
    # Below this, a check is not telling clean and broken apart
    FLAT = 0.15

    # Below this, it separates them, but not by much
    WEAK = 0.30

    def __init__(self, catalogue: Catalogue, client: Client) -> None:
        self._catalogue = catalogue
        self._client = client

    def run(self, only: list[str] | None = None) -> list[CheckScore]:
        only = only or []
        path = Catalogue.locate('fixtures.json')
        data = Json.read_file(path)
        results: list[CheckScore] = []
        fixtures = data['fixtures'] if isinstance(data.get('fixtures'), list) else []

        for raw in fixtures:
            fixture = raw if isinstance(raw, dict) else {}
            check_id = fixture['check'] if isinstance(fixture.get('check'), str) else ''
            check = self._catalogue.find(check_id)

            # A fixture naming a check that is not there is a typo in a file
            # nobody reads twice, and skipping it quietly took a check's second
            # domain out of the run while the summary still said it separated. The
            # same typo on the command line is refused loudly.
            if check is None and self._catalogue.find_written(check_id) is None:
                raise JevLintError.of(JevLintError.CATALOGUE, Text.of('self_test.fixture_unknown_check', {
                    'path': path,
                    'id': check_id,
                }))

            if check is None or (len(only) > 0 and check_id not in only):
                continue

            results.append(self._score(check, fixture))

        return results

    def _score(self, check: Check, fixture: dict[str, Any]) -> CheckScore:
        clean = self._probability(check, fixture.get('clean'))
        broken = self._probability(check, fixture.get('broken'))
        offers_fixed = 'fixed' in fixture
        fixed = self._probability(check, fixture['fixed']) if offers_fixed else None

        return CheckScore(
            check,
            clean,
            broken,
            fixed,
            fixture['domain'] if isinstance(fixture.get('domain'), str) else '',
            offers_fixed,
        )

    def _probability(self, check: Check, example: Any) -> float | None:
        """The probability this check puts on its own defect being present."""
        if not isinstance(example, dict):
            raise JevLintError.of(
                JevLintError.CATALOGUE,
                Text.of('self_test.fixture_missing_example', {'id': check.id}),
            )

        field = example['field'] if isinstance(example.get('field'), str) else ''
        linter = ModelLinter(self._catalogue, self._client)
        request = self._client.system_one().state(_state(check, example))
        keys: list[str] = []

        pair = example['pair'] if isinstance(example.get('pair'), list) else None

        for index, wording in enumerate(check.wordings):
            keys.append(f'{check.answer_key()}__w{index}')
            question = linter.build(wording, field)

            if pair is not None and len(pair) == 2:
                question.instructions(wording.instructions().replace(
                    '{pair}', f'"{pair[0]}" and "{pair[1]}"',
                ))

            request.ask(keys[index], question)

        try:
            response = request.send()
        except TypeSafeError:
            return None

        if check.compare == 'type':
            declared = example['type'] if isinstance(example.get('type'), str) else ''

            return 1.0 - (response.choice(keys[0]).probability_of(declared) or 0.0)

        # The wordings mean the same thing, so the check's answer is their mean
        probabilities = [response.noul(key).noul() for key in keys]

        return sum(probabilities) / len(probabilities)


def _state(check: Check, example: dict[str, Any]) -> dict[str, Any]:
    if check.scope == 'question':
        return ReviewedQuestion.from_dict('fixture', example).as_state()

    # A query-scope check reads two questions, so its fixture holds the pair.
    if check.scope == 'query':
        return {'questions': example.get('pair', [])}

    # The same shape a run shows a state-scoped check. A fixture writes its
    # question as text where it carries no criteria, and as an object where it
    # does, so the two cannot drift apart.
    question = example.get('question', '')

    return {
        'question': question if isinstance(question, dict) else {'instructions': question},
        'state': example.get('state'),
    }
