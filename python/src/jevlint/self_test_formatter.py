"""What each check scored against its own clean and broken examples."""
from __future__ import annotations

from .formatting import dim, fixed, pad, pad_left, paint
from .selftest import CheckScore
from .text import Text


class SelfTestFormatter:
    def __init__(self, colour: bool = True) -> None:
        self._colour = colour

    def format(self, scores: list[CheckScore]) -> str:
        lines = [
            dim(self._colour, Text.of('self_test.heading')),
            '',
            paint(self._colour, _row(
                Text.of('self_test.column_check'),
                Text.of('self_test.column_clean'),
                Text.of('self_test.column_broken'),
                Text.of('self_test.column_fixed'),
                Text.of('self_test.column_span'),
                Text.of('self_test.column_verdict'),
            ), '1'),
        ]

        for score in scores:
            lines.append(_row(
                score.check.id if score.domain == '' else score.check.id + ' (' + score.domain + ')',
                _number(score.clean),
                _number(score.broken),
                _number(score.fixed),
                _number(score.span()),
                self._verdict(score),
            ))

        failed = [score for score in scores if not score.passed()]
        lines.append('')
        # One row per example set, and every check ships two. Counting rows as
        # checks read as though `--check=one-id` had matched two ids.
        checks = {score.check.id for score in scores}
        lines.append(Text.of('self_test.summary', {
            'separated': len(scores) - len(failed),
            'sets': len(scores),
            'checks': len(checks),
        }))

        if len(failed) > 0:
            lines.append(dim(self._colour, Text.of('self_test.footer')))

        return '\n'.join(lines) + '\n'

    def _verdict(self, score: CheckScore) -> str:
        verdict = score.verdict()

        if verdict == 'ok':
            return paint(self._colour, verdict, '32')

        return paint(self._colour, verdict, '33' if verdict == 'weak' else '31')


def _row(check: str, clean: str, broken: str, fix: str, span: str, verdict: str) -> str:
    return (
        pad(check, 44) + ' ' + pad_left(clean, 7) + ' ' + pad_left(broken, 7) + ' '
        + pad_left(fix, 7) + ' ' + pad_left(span, 7) + '  ' + verdict
    )


def _number(value: float | None) -> str:
    return 'n/a' if value is None else fixed(value, 2)
