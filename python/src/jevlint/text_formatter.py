"""The report as a terminal reads it: grouped by what the finding is about."""
from __future__ import annotations

from .formatting import dim, fixed, grouped, pad, pad_characters, paint
from .model_linter import ModelLinter
from .report import Finding, Patch, Report, Severity
from .support import Json, bytes_of
from .text import Text

WIDTH = 96

LABEL = 11


class TextFormatter:
    def __init__(
        self,
        colour: bool = True,
        brief: bool = False,
        show_accepted: bool = False,
        show_cleared: bool = False,
    ) -> None:
        self._colour = colour
        self._brief = brief
        self._show_accepted = show_accepted
        self._show_cleared = show_cleared
        # The checks whose reasoning has already been printed in this run. One
        # check firing on six state fields printed the same two lines of Why and
        # the same Docs link six times, which buries the six field names that are
        # the only part that differs.
        self._explained: set[str] = set()
        self._patched: set[str] = set()

    def format(self, report: Report, floor: Severity | None = None) -> str:
        findings = report.findings(floor)
        lines: list[str] = [self._dim(Text.of('report.header', {
            'source': report.source,
            'version': report.catalogue_version,
            'fingerprint': report.fingerprint,
            'model': report.model,
            'pinned': 'no' if report.asked_through is None else 'yes',
            'through': report.asked_through or '',
        }))]

        if _has_probabilities(findings):
            lines.append(self._dim(Text.of('report.probability_note')))

        lines.append('')

        if len(findings) == 0:
            hidden = len(report.findings())

            if report.asked_count() == 0:
                # A run that evaluated nothing has nothing to report in a sense no
                # reader means by it.
                lines.append(self._paint(Text.of('report.nothing_ran'), '31'))
            elif hidden > 0:
                lines.append(self._paint(Text.of('report.all_hidden', {'count': hidden}), '33'))
            elif len(report.unstable()) > 0:
                # "Nothing to report" beside an exit of 3 reads as a pass.
                lines.append(self._paint(Text.of('report.only_undecided'), '33'))
            else:
                lines.append(self._paint(Text.of('report.nothing_to_report'), '32'))

            lines.append('')

        for target, group in _group_by_target(findings).items():
            lines.append(self._paint(target, '1'))

            for index, finding in enumerate(group):
                if index > 0 and not self._brief:
                    lines.append('')

                lines += self._briefly(finding) if self._brief else self._fully(finding, report)

            lines.append('')

        cleared = report.cleared()

        # Without `--all` the report still carries the readings that landed near
        # their trigger, because they are the ones worth a second look and they
        # cost nothing more to print.
        if not self._show_cleared:
            cleared = [
                # A caveat on a cleared reading says what that reading cannot tell
                # you, so it is kept however far from the trigger it landed.
                finding for finding in cleared
                if finding.advice != ''
                or (finding.probability is not None
                    and finding.trigger is not None
                    and abs(finding.probability - finding.trigger) <= ModelLinter.WORTH_SEEING)
            ]

        if len(cleared) > 0:
            lines.append(self._paint(
                Text.of('report.cleared_all') if self._show_cleared else Text.of('report.cleared_near'),
                '1',
            ))

            for finding in cleared:
                if finding.cleared_because != '':
                    # A reading over the trigger in a list of things that cleared
                    # needs the reason beside it, or it reads as a defect that got
                    # away.
                    tail = f' - {finding.cleared_because}'
                elif finding.near_trigger:
                    tail = Text.of('report.close_to_the_line')
                else:
                    tail = ''

                lines.append(self._dim(
                    f'  {pad(finding.check_id, 34)} '
                    # A per-field check reports every field against the same
                    # target, so without the path these rows are
                    # indistinguishable.
                    f'{pad(_shorten(_where(finding), 30), 24)} '
                    + Text.of('report.against_trigger', {
                        'probability': finding.probability or 0.0,
                        'trigger': finding.trigger or 0.0,
                    })
                    + tail,
                ))

                # The reading cleared and the caveat says that proves nothing.
                # Printing the number without it is the misreading it warns of.
                if finding.advice != '':
                    lines += self._wrap('  ' + Text.of('label.caveat'), finding.advice, '33')

            lines.append('')

        unstable = report.unstable()

        if len(unstable) > 0:
            lines.append(self._paint(Text.of('report.undecided_heading', {'count': len(unstable)}), '33'))

            for finding in unstable:
                if len(finding.readings) == 0:
                    readings = Text.of('report.against_trigger', {
                        'probability': finding.probability or 0.0,
                        'trigger': finding.trigger or 0.0,
                    })
                else:
                    readings = ', '.join(
                        Text.of('report.probability', {'probability': probability})
                        for probability in finding.readings
                    ) + Text.of('report.against_trigger_tail', {'trigger': finding.trigger or 0.0})

                lines.append(self._dim('  ' + Text.of('report.undecided_row', {
                    'check': finding.check_id,
                    'target': finding.target,
                    'readings': readings,
                })))

                # What the check was looking for, and what to do if it is right.
                # The uncertainty is about whether, not about what to do, and
                # printing the id alone made the deepest finding in some runs the
                # least useful line in the report.
                lines += self._wrap('', finding.message)

                if finding.suggest != '':
                    lines += self._wrap(Text.of('label.if_it_is'), finding.suggest)

            lines.append('')

        accepted = report.accepted()

        if len(accepted) > 0:
            lines.append(self._dim(Text.of('report.accepted_heading', {
                'count': len(accepted),
                'source': report.accepted_from(),
                'listed': 'yes' if self._show_accepted else 'no',
            })))

            if self._show_accepted:
                for finding in accepted:
                    lines.append(self._dim('  ' + Text.of('report.check_on_target', {
                        'check': finding.check_id,
                        'target': finding.target,
                    })))
                    lines += self._wrap('', finding.accepted or '')

            lines.append('')

        unreachable = report.unreachable_notes()

        if len(unreachable) > 0:
            lines.append(self._paint(Text.of('report.calls_lost', {'count': len(unreachable)}), '31'))
            lines.append('')

        for note in report.notes():
            label = Text.of('label.failed') if note.is_unreachable() else Text.of('label.note')
            lines.append(self._paint(label, '33') + ' ' + note.message)

        if len(report.notes()) > 0:
            lines.append('')

        if len(self._patched) > 0:
            means = {
                Patch.LOSSLESS: Text.of('patch.lossless'),
                Patch.LOSSY: Text.of('patch.lossy'),
                Patch.DESTRUCTIVE: Text.of('patch.destructive'),
            }

            lines.append(self._dim(Text.of('patch.legend', {
                'kinds': '; '.join(
                    f'{kind}, {means[kind]}' for kind in means if kind in self._patched
                ),
            })))
            lines.append('')

        lines.append(self._summary(report))

        return '\n'.join(lines) + '\n'

    def _fully(self, finding: Finding, report: Report) -> list[str]:
        """
        The finding as somebody meeting the check for the first time reads it: what
        is wrong, then what to write instead, then why it matters.
        """
        repeat = finding.check_id in self._explained
        self._explained.add(finding.check_id)

        lines = ['  ' + self._severity_label(finding.severity) + '  ' + self._paint(finding.title, '1')]
        lines.append(f'           {self._dim(finding.check_id)}')
        lines += self._wrap('', finding.message)
        lines += self._wrap(
            Text.of('label.weight') if finding.measure == 'weight' else Text.of('label.likelihood'),
            self._likelihood(finding),
        )

        superseded_by = report.superseded_by(finding)

        if superseded_by is not None:
            lines += self._wrap(
                Text.of('label.moot_if'),
                Text.of('report.moot_if', {'check': superseded_by}),
            )

        supersedes = report.superseding(finding)

        if len(supersedes) > 0:
            lines += self._wrap(
                Text.of('label.also_drops'),
                Text.of('report.also_drops', {'checks': ', '.join(supersedes)}),
            )

        if finding.evidence is not None:
            # A static rule quotes what it read, which for a thirty-option Choice
            # is every label. The JSON carries it whole.
            lines += self._wrap(Text.of('label.found'), _shorten(finding.evidence, 220))

        if len(finding.readings) > 0:
            places = 3 if finding.near_trigger or finding.unstable else 2
            lines += self._wrap(Text.of('label.readings'), Text.of('report.readings', {
                'of': finding.readings_of or Text.of('readings.repeats_word'),
                'readings': ', '.join(grouped(probability, places) for probability in finding.readings),
                'spread': grouped(max(finding.readings) - min(finding.readings), places),
            }))

        # Both, always. A patch says what to do to the file; the suggestion says
        # what to do about the query. On a `remove` patch the suggestion is the
        # only one of the two that tells you how to keep the answer you wanted.
        if finding.suggest != '':
            lines += self._wrap(Text.of('label.suggested'), finding.suggest, '32')

        # What the self-test measured about this suggestion, where it is weak. A
        # reader deciding whether to act on advice is owed how far it got on the
        # check's own example.
        if finding.advice != '' and not repeat:
            lines += self._wrap(Text.of('label.advice'), finding.advice, '33')

        if finding.patch is not None:
            self._patched.add(finding.patch.safety)
            covered = report.patch_covered_by(finding)

            if finding.patch.op == 'remove':
                written = Text.of('report.patch', {
                    'safety': finding.patch.safety,
                    'op': finding.patch.op,
                    'path': finding.patch.path,
                })
            else:
                written = Text.of('report.patch_with_value', {
                    'safety': finding.patch.safety,
                    'op': finding.patch.op,
                    'path': finding.patch.path,
                    # The whole value goes out in the JSON, where a program reads
                    # it. Printing a rewritten thirty-option Choice to a terminal
                    # buries the finding it belongs to.
                    'value': _shorten(Json.inline(finding.patch.value), 160),
                })

            lines += self._wrap(
                Text.of('label.patch'),
                written + ('' if covered is None else Text.of('report.patch_covered_by', {'check': covered})),
                '32',
            )

        if finding.hint != '' and not repeat:
            lines += self._wrap(Text.of('label.why'), finding.hint)

        if finding.docs is not None and not repeat:
            lines.append(self._dim('           ' + pad(Text.of('label.docs'), LABEL) + ' ' + finding.docs))

        return lines

    def _briefly(self, finding: Finding) -> list[str]:
        head = '  ' + self._severity_label(finding.severity) + '  ' + self._paint(finding.check_id, '36')

        if finding.probability is not None:
            head += self._dim(f'  {fixed(finding.probability, 2)}')

        lines = [head, f'    {finding.message}']

        if finding.suggest != '':
            lines.append('    ' + self._paint('→ ', '32') + finding.suggest)

        return lines

    def _likelihood(self, finding: Finding) -> str:
        """
        How strongly the check read the defect, and the bar it had to clear.

        Its own field, beside what was found and what to do, because it is one of
        the things a reader weighs and not a footnote on the check's name.
        """
        if finding.probability is None:
            return Text.of('likelihood.certain')

        # One check asks which primitive fits instead of whether a defect is
        # present, so its number is a weight and the bands do not apply to it.
        if finding.measure == 'weight':
            return Text.of('likelihood.weight', {
                'weight': grouped(finding.probability, 2),
                'trigger': grouped(finding.trigger or 0.0, 2),
            })

        near = Text.of('likelihood.near_trigger', {'near': ModelLinter.NEAR}) if finding.near_trigger else ''
        straddled = Text.of('likelihood.straddled') if finding.unstable else ''

        # Two places rounded 0.704 and its 0.70 trigger to the same number, so a
        # finding said its readings disagreed and printed numbers that did not.
        places = 3 if finding.near_trigger or finding.unstable else 2

        return Text.of('likelihood.probability', {
            'probability': grouped(finding.probability, places),
            'band': _band(finding.probability),
            'trigger': grouped(finding.trigger or 0.0, places),
            'near': near,
            'straddled': straddled,
        })

    def _wrap(self, label: str, text: str, colour: str | None = None) -> list[str]:
        indent = ' ' * (11 + (0 if label == '' else LABEL + 1))
        words = text.split()
        broken: list[str] = []
        current = ''

        for word in words:
            if current != '' and bytes_of(current) + bytes_of(word) + 1 > WIDTH - len(indent):
                broken.append(current)
                current = word

                continue

            current = word if current == '' else f'{current} {word}'

        if current != '':
            broken.append(current)

        lines: list[str] = []

        for index, line in enumerate(broken):
            body = line if colour is None else self._paint(line, colour)
            lines.append(f'           {pad(label, LABEL)} {body}' if index == 0 and label != '' else indent + body)

        return lines

    def _summary(self, report: Report) -> str:
        counts = Text.of('report.counts', {
            'errors': report.count(Severity.Error),
            'warnings': report.count(Severity.Warning),
            'advice': report.count(Severity.Advice),
        })

        if report.calls() == 0:
            return counts + self._dim(Text.of('report.no_calls'))

        # A call whose answer carried no usage is not a call that cost nothing, so
        # the token figure is marked a floor instead of printing a total that is
        # short by an unknown amount.
        return counts + self._dim(Text.of('report.cost', {
            'calls': report.calls(),
            'floor': 'yes' if report.calls_without_usage() > 0 else 'no',
            'tokens': grouped(report.tokens()),
        }))

    def _severity_label(self, severity: Severity) -> str:
        """
        The severity, padded so the titles beside it line up.

        The width comes from the three translations and not from the seven
        characters `warning` happens to take, because another language has its own
        longest word.
        """
        words = {
            'error': Text.of('severity.error'),
            'warning': Text.of('severity.warning'),
            'advice': Text.of('severity.advice'),
        }
        width = max(len(word) for word in words.values())
        codes = {'error': '31', 'warning': '33', 'advice': '34'}

        return self._paint(
            pad_characters(words.get(severity.value, ''), width),
            codes.get(severity.value, '33'),
        )

    def _paint(self, text: str, code: str) -> str:
        return paint(self._colour, text, code)

    def _dim(self, text: str) -> str:
        return dim(self._colour, text)


def _band(probability: float) -> str:
    """Words for a probability, so the number is not read as a score out of one."""
    if probability >= 0.90:
        return Text.of('band.almost_certain')

    if probability >= 0.75:
        return Text.of('band.very_likely')

    if probability >= 0.50:
        return Text.of('band.likely')

    if probability >= 0.25:
        return Text.of('band.unlikely')

    return Text.of('band.very_unlikely')


def _has_probabilities(findings: list[Finding]) -> bool:
    # A weight is not a probability, so a report carrying only weights should not
    # print the sentence explaining probabilities.
    return any(
        finding.probability is not None and finding.measure == 'probability' for finding in findings
    )


def _group_by_target(findings: list[Finding]) -> dict[str, list[Finding]]:
    grouped_findings: dict[str, list[Finding]] = {}

    for finding in findings:
        grouped_findings.setdefault(finding.target, []).append(finding)

    return grouped_findings


def _where(finding: Finding) -> str:
    """
    Which thing this reading was about.

    The target alone is right for a question check and useless for a per-field
    one, where every row reads `state`. What the path adds beyond the target is
    the field name, which is the only part that differs.
    """
    target = finding.target
    prefix = '/state' if target == 'state' else f'/questions/{target}'

    if finding.path == '' or finding.path == prefix:
        return target

    extra = finding.path[len(prefix) + 1:] if finding.path.startswith(f'{prefix}/') else finding.path.lstrip('/')

    return target + ' · ' + extra.replace('/', '.')


def _shorten(text: str, limit: int) -> str:
    """Cut to a byte length, as the report has always counted it."""
    encoded = text.encode('utf-8')

    return text if len(encoded) <= limit else encoded[:limit - 1].decode('utf-8', 'replace') + '…'
