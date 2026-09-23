"""The probe's readings as a table per question."""
from __future__ import annotations

from .formatting import dim, fixed, grouped, pad, paint, signed
from .probe import Probe, QuestionProbe, Reading
from .report import Note
from .text import Text


class ProbeFormatter:
    def __init__(self, colour: bool = True) -> None:
        self._colour = colour

    def format(
        self,
        probes: dict[str, QuestionProbe],
        source: str,
        repeats: int,
        calls: int,
        tokens: int,
        notes: list[Note] | None = None,
    ) -> str:
        lines = [
            dim(self._colour, Text.of('probe.header', {
                'source': source,
                'repeats': repeats,
                'calls': calls,
                'tokens': grouped(tokens),
            })),
            '',
        ]

        moved = 0

        for question_id, probe in probes.items():
            lines += self._question(question_id, probe)
            lines.append('')

            if any(probe.moved(reading) for reading in probe.readings):
                moved += 1

        lines += self._legend(probes)

        for note in notes or []:
            label = Text.of('label.failed') if note.is_unreachable() else Text.of('label.note')
            lines.append(paint(self._colour, label, '33') + ' ' + note.message)

        # Name the rewrites that moved. Reassuring the reader about
        # `criteria-stripped` whenever it merely ran pointed them away from
        # whichever variant was the reason the run failed.
        movers = _movers_in(probes)

        undecided = len([probe for probe in probes.values() if probe.undecided()])

        lines.append(
            Text.of('probe.summary', {'moved': moved, 'questions': len(probes)})
            + ('' if undecided == 0 else Text.of('probe.undecided_summary', {'count': undecided}))
            + ('' if len(movers) == 0 else Text.of('probe.movers', {
                'count': len(movers),
                'names': ', '.join('`' + variant + '`' for variant in movers),
            }))
            + (Text.of('probe.criteria_stripped_moved') if 'criteria-stripped' in movers else ''),
        )
        lines.append(dim(self._colour, Text.of('probe.starred_legend', {
            'negligible': QuestionProbe.NEGLIGIBLE,
            'floor': Probe.PUBLISHED_NOISE,
        })))

        return '\n'.join(lines) + '\n'

    def _legend(self, probes: dict[str, QuestionProbe]) -> list[str]:
        """What each rewrite did to the query, named once at the end."""
        # The key is the variant name, which is an identifier the JSON carries and
        # `--variants` matches on, so it is not translated.
        seen = {'unchanged': Text.of('probe.unchanged_describe')}

        for probe in probes.values():
            for reading in probe.readings:
                seen[reading.variant] = reading.describe

        lines = [dim(self._colour, Text.of('probe.legend_heading'))]

        for name, describes in seen.items():
            lines.append(dim(self._colour, '  ' + pad(name, 20) + ' ' + describes))

        return [*lines, '']

    def _question(self, question_id: str, probe: QuestionProbe) -> list[str]:
        baseline = probe.baseline()
        reading = '' if probe.reading is None else ', ' + probe.reading
        lines = [
            paint(self._colour, question_id, '1')
            + dim(self._colour, '  ' + probe.question.type + reading),
        ]

        if baseline is None:
            lines.append('  ' + paint(self._colour, Text.of('probe.no_reading'), '31'))

            return lines

        noise = probe.noise()
        measured = '' if noise is None else Text.of('probe.noise', {
            'noise': noise,
            'below': 'yes' if noise < Probe.PUBLISHED_NOISE else 'no',
        })
        lines.append(
            '    ' + pad('unchanged', 20) + ' ' + fixed(baseline, 3) + ' '
            + dim(self._colour, measured),
        )

        # Under the unchanged row, because it is a fact about that reading and not
        # about any of the rewrites below it.
        if probe.undecided():
            lines.append('    ' + paint(self._colour, Text.of('probe.undecided', {
                'flips': 'yes' if probe.flips() else 'no',
            }), '33'))

        for reading_row in probe.readings:
            lines.append(self._reading(probe, reading_row))

        return lines

    def _reading(self, probe: QuestionProbe, reading: Reading) -> str:
        if reading.value is None:
            return (
                '  ' + pad(reading.variant, 20) + ' '
                + paint(self._colour, reading.error or Text.of('probe.no_reading'), '31')
            )

        delta = probe.delta(reading) or 0.0
        ratio = probe.ratio(reading) or 0.0
        moved = probe.moved(reading)

        star = paint(self._colour, '*', '33') if moved else ' '
        line = (
            '  ' + star + ' ' + pad(reading.variant, 20) + ' '
            + fixed(reading.value, 3) + '  ' + signed(delta, 3)
        )
        tail = Text.of('probe.noise_ratio', {'ratio': ratio})

        return line + '  ' + (
            paint(self._colour, tail + ', moved', '33') if moved else dim(self._colour, tail)
        )


def _movers_in(probes: dict[str, QuestionProbe]) -> list[str]:
    """Every variant name that moved an answer, across all the questions."""
    movers: dict[str, None] = {}

    for probe in probes.values():
        for reading in probe.readings:
            if probe.moved(reading):
                movers[reading.variant] = None

    return list(movers)
