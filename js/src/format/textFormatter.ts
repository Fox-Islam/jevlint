import { Text } from '../i18n/text.js';
import { ModelLinter } from '../lint/modelLinter.js';
import type { Finding } from '../report/finding.js';
import { Patch } from '../report/patch.js';
import type { Report } from '../report/report.js';
import { Severity } from '../report/severity.js';
import { Json } from '../support/json.js';
import { dim, pad, padCharacters, paint } from './colour.js';
import { fixed, grouped } from './numbers.js';

const WIDTH = 96;

const LABEL = 11;

/** The report as a terminal reads it: grouped by what the finding is about */
export class TextFormatter {
    /**
     * The checks whose reasoning has already been printed in this run.
     *
     * One check firing on six state fields printed the same two lines of Why and
     * the same Docs link six times, which buries the six field names that are
     * the only part that differs
     */
    private readonly explained = new Set<string>();

    private readonly patched = new Set<string>();

    constructor(
        private readonly colour = true,
        private readonly brief = false,
        private readonly showAccepted = false,
        private readonly showCleared = false,
    ) {}

    format(report: Report, floor: Severity | null = null): string {
        const findings = report.findings(floor);
        const lines: string[] = [this.dim(Text.of('report.header', {
            source: report.source,
            version: report.catalogueVersion,
            fingerprint: report.fingerprint,
            model: report.model,
            pinned: report.askedThrough === null ? 'no' : 'yes',
            through: report.askedThrough ?? '',
        }))];

        if (hasProbabilities(findings)) {
            lines.push(this.dim(Text.of('report.probability_note')));
        }

        lines.push('');

        if (findings.length === 0) {
            const hidden = report.findings().length;

            lines.push(
                // A run that evaluated nothing has nothing to report in a sense
                // no reader means by it.
                report.askedCount() === 0
                    ? this.paint(Text.of('report.nothing_ran'), '31')
                    : hidden > 0
                        ? this.paint(Text.of('report.all_hidden', { count: hidden }), '33')
                        // "Nothing to report" beside an exit of 3 reads as a pass.
                        : report.unstable().length > 0
                            ? this.paint(Text.of('report.only_undecided'), '33')
                            : this.paint(Text.of('report.nothing_to_report'), '32'),
            );
            lines.push('');
        }

        for (const [target, group] of groupByTarget(findings)) {
            lines.push(this.paint(target, '1'));

            for (const [i, finding] of group.entries()) {
                if (i > 0 && !this.brief) {
                    lines.push('');
                }

                lines.push(...(this.brief ? this.briefly(finding) : this.fully(finding, report)));
            }

            lines.push('');
        }

        let cleared = report.cleared();

        // Without `--all` the report still carries the readings that landed near
        // their trigger, because they are the ones worth a second look and they
        // cost nothing more to print.
        if (!this.showCleared) {
            cleared = cleared.filter(
                // A caveat on a cleared reading says what that reading cannot
                // tell you, so it is kept however far from the trigger it landed.
                (finding) => finding.advice !== ''
                    || (finding.probability !== null
                        && finding.trigger !== null
                        && Math.abs(finding.probability - finding.trigger) <= ModelLinter.WORTH_SEEING),
            );
        }

        if (cleared.length > 0) {
            lines.push(this.paint(
                this.showCleared ? Text.of('report.cleared_all') : Text.of('report.cleared_near'),
                '1',
            ));

            for (const finding of cleared) {
                lines.push(this.dim(
                    `  ${pad(finding.checkId, 34)} `
                    // A per-field check reports every field against the same
                    // target, so without the path these rows are
                    // indistinguishable.
                    + `${pad(shorten(where(finding), 30), 24)} `
                    + Text.of('report.against_trigger', {
                        probability: finding.probability ?? 0.0,
                        trigger: finding.trigger ?? 0.0,
                    })
                    // A reading over the trigger in a list of things that cleared
                    // needs the reason beside it, or it reads as a defect that
                    // got away.
                    + (finding.clearedBecause !== ''
                        ? ` - ${finding.clearedBecause}`
                        : finding.nearTrigger ? Text.of('report.close_to_the_line') : ''),
                ));

                // The reading cleared and the caveat says that proves nothing.
                // Printing the number without it is the misreading it warns of.
                if (finding.advice !== '') {
                    lines.push(...this.wrap(`  ${Text.of('label.caveat')}`, finding.advice, '33'));
                }
            }

            lines.push('');
        }

        const unstable = report.unstable();

        if (unstable.length > 0) {
            lines.push(this.paint(Text.of('report.undecided_heading', { count: unstable.length }), '33'));

            for (const finding of unstable) {
                lines.push(this.dim(`  ${Text.of('report.undecided_row', {
                    check: finding.checkId,
                    target: finding.target,
                    readings: finding.readings.length === 0
                        ? Text.of('report.against_trigger', {
                            probability: finding.probability ?? 0.0,
                            trigger: finding.trigger ?? 0.0,
                        })
                        : finding.readings
                            .map((probability) => Text.of('report.probability', { probability }))
                            .join(', ')
                        + Text.of('report.against_trigger_tail', { trigger: finding.trigger ?? 0.0 }),
                })}`));

                // What the check was looking for, and what to do if it is right.
                // The uncertainty is about whether, not about what to do, and
                // printing the id alone made the deepest finding in some runs the
                // least useful line in the report.
                lines.push(...this.wrap('', finding.message));

                if (finding.suggest !== '') {
                    lines.push(...this.wrap(Text.of('label.if_it_is'), finding.suggest));
                }
            }

            lines.push('');
        }

        const accepted = report.accepted();

        if (accepted.length > 0) {
            lines.push(this.dim(Text.of('report.accepted_heading', {
                count: accepted.length,
                source: report.acceptedFrom(),
                listed: this.showAccepted ? 'yes' : 'no',
            })));

            if (this.showAccepted) {
                for (const finding of accepted) {
                    lines.push(this.dim(`  ${Text.of('report.check_on_target', {
                        check: finding.checkId,
                        target: finding.target,
                    })}`));
                    lines.push(...this.wrap('', finding.accepted ?? ''));
                }
            }

            lines.push('');
        }

        const unreachable = report.unreachableNotes();

        if (unreachable.length > 0) {
            lines.push(this.paint(Text.of('report.calls_lost', { count: unreachable.length }), '31'));
            lines.push('');
        }

        for (const note of report.notes()) {
            lines.push(`${this.paint(note.isUnreachable() ? Text.of('label.failed') : Text.of('label.note'), '33')} ${note.message}`);
        }

        if (report.notes().length > 0) {
            lines.push('');
        }

        if (this.patched.size > 0) {
            const means: Record<string, string> = {
                [Patch.LOSSLESS]: Text.of('patch.lossless'),
                [Patch.LOSSY]: Text.of('patch.lossy'),
                [Patch.DESTRUCTIVE]: Text.of('patch.destructive'),
            };

            lines.push(this.dim(Text.of('patch.legend', {
                kinds: Object.keys(means)
                    .filter((kind) => this.patched.has(kind))
                    .map((kind) => `${kind}, ${means[kind] ?? ''}`)
                    .join('; '),
            })));
            lines.push('');
        }

        lines.push(this.summary(report));

        return `${lines.join('\n')}\n`;
    }

    /**
     * The finding as somebody meeting the check for the first time reads it:
     * what is wrong, then what to write instead, then why it matters
     */
    private fully(finding: Finding, report: Report): string[] {
        const repeat = this.explained.has(finding.checkId);
        this.explained.add(finding.checkId);

        const lines: string[] = [`  ${this.severityLabel(finding.severity)}  ${this.paint(finding.title, '1')}`];
        lines.push(`           ${this.dim(finding.checkId)}`);
        lines.push(...this.wrap('', finding.message));
        lines.push(...this.wrap(
            finding.measure === 'weight' ? Text.of('label.weight') : Text.of('label.likelihood'),
            this.likelihood(finding),
        ));

        const supersededBy = report.supersededBy(finding);

        if (supersededBy !== null) {
            lines.push(...this.wrap(
                Text.of('label.moot_if'),
                Text.of('report.moot_if', { check: supersededBy }),
            ));
        }

        const supersedes = report.superseding(finding);

        if (supersedes.length > 0) {
            lines.push(...this.wrap(
                Text.of('label.also_drops'),
                Text.of('report.also_drops', { checks: supersedes.join(', ') }),
            ));
        }

        if (finding.evidence !== null) {
            // A static rule quotes what it read, which for a thirty-option Choice
            // is every label. The JSON carries it whole.
            lines.push(...this.wrap(Text.of('label.found'), shorten(finding.evidence, 220)));
        }

        if (finding.readings.length > 0) {
            const places = finding.nearTrigger || finding.unstable ? 3 : 2;
            lines.push(...this.wrap(Text.of('label.readings'), Text.of('report.readings', {
                of: finding.readingsOf ?? Text.of('readings.repeats_word'),
                readings: finding.readings.map((probability) => grouped(probability, places)).join(', '),
                spread: grouped(Math.max(...finding.readings) - Math.min(...finding.readings), places),
            })));
        }

        // Both, always. A patch says what to do to the file; the suggestion says
        // what to do about the query. On a `remove` patch the suggestion is the
        // only one of the two that tells you how to keep the answer you wanted.
        if (finding.suggest !== '') {
            lines.push(...this.wrap(Text.of('label.suggested'), finding.suggest, '32'));
        }

        // What the self-test measured about this suggestion, where it is weak. A
        // reader deciding whether to act on advice is owed how far it got on the
        // check's own example.
        if (finding.advice !== '' && !repeat) {
            lines.push(...this.wrap(Text.of('label.advice'), finding.advice, '33'));
        }

        if (finding.patch !== null) {
            this.patched.add(finding.patch.safety);
            const covered = report.patchCoveredBy(finding);

            lines.push(...this.wrap(
                Text.of('label.patch'),
                (finding.patch.op === 'remove'
                    ? Text.of('report.patch', {
                        safety: finding.patch.safety,
                        op: finding.patch.op,
                        path: finding.patch.path,
                    })
                    : Text.of('report.patch_with_value', {
                        safety: finding.patch.safety,
                        op: finding.patch.op,
                        path: finding.patch.path,
                        // The whole value goes out in the JSON, where a program
                        // reads it. Printing a rewritten thirty-option Choice to
                        // a terminal buries the finding it belongs to.
                        value: shorten(Json.inline(finding.patch.value), 160),
                    }))
                + (covered === null ? '' : Text.of('report.patch_covered_by', { check: covered })),
                '32',
            ));
        }

        if (finding.hint !== '' && !repeat) {
            lines.push(...this.wrap(Text.of('label.why'), finding.hint));
        }

        if (finding.docs !== null && !repeat) {
            lines.push(this.dim(`           ${pad(Text.of('label.docs'), LABEL)} ${finding.docs}`));
        }

        return lines;
    }

    private briefly(finding: Finding): string[] {
        let head = `  ${this.severityLabel(finding.severity)}  ${this.paint(finding.checkId, '36')}`;

        if (finding.probability !== null) {
            head += this.dim(`  ${fixed(finding.probability, 2)}`);
        }

        const lines = [head, `    ${finding.message}`];

        if (finding.suggest !== '') {
            lines.push(`    ${this.paint('→ ', '32')}${finding.suggest}`);
        }

        return lines;
    }

    /**
     * How strongly the check read the defect, and the bar it had to clear.
     *
     * Its own field, beside what was found and what to do, because it is one of
     * the things a reader weighs and not a footnote on the check's name
     */
    private likelihood(finding: Finding): string {
        if (finding.probability === null) {
            return Text.of('likelihood.certain');
        }

        // One check asks which primitive fits instead of whether a defect is
        // present, so its number is a weight and the bands do not apply to it.
        if (finding.measure === 'weight') {
            return Text.of('likelihood.weight', {
                weight: grouped(finding.probability, 2),
                trigger: grouped(finding.trigger ?? 0.0, 2),
            });
        }

        const near = finding.nearTrigger
            ? Text.of('likelihood.near_trigger', { near: ModelLinter.NEAR })
            : '';

        const straddled = finding.unstable ? Text.of('likelihood.straddled') : '';

        // Two places rounded 0.704 and its 0.70 trigger to the same number, so a
        // finding said its readings disagreed and printed numbers that did not.
        const places = finding.nearTrigger || finding.unstable ? 3 : 2;

        return Text.of('likelihood.probability', {
            probability: grouped(finding.probability, places),
            band: band(finding.probability),
            trigger: grouped(finding.trigger ?? 0.0, places),
            near,
            straddled,
        });
    }

    private wrap(label: string, text: string, colour: string | null = null): string[] {
        const indent = ' '.repeat(11 + (label === '' ? 0 : LABEL + 1));
        const words = text.trim() === '' ? [] : text.trim().split(/\s+/);
        const broken: string[] = [];
        let current = '';

        for (const word of words) {
            if (current !== '' && bytes(current) + bytes(word) + 1 > WIDTH - indent.length) {
                broken.push(current);
                current = word;

                continue;
            }

            current = current === '' ? word : `${current} ${word}`;
        }

        if (current !== '') {
            broken.push(current);
        }

        return broken.map((line, i) => {
            const body = colour === null ? line : this.paint(line, colour);

            return i === 0 && label !== ''
                ? `           ${pad(label, LABEL)} ${body}`
                : indent + body;
        });
    }

    private summary(report: Report): string {
        const counts = Text.of('report.counts', {
            errors: report.count(Severity.Error),
            warnings: report.count(Severity.Warning),
            advice: report.count(Severity.Advice),
        });

        if (report.calls() === 0) {
            return counts + this.dim(Text.of('report.no_calls'));
        }

        // A call whose answer carried no usage is not a call that cost nothing,
        // so the token figure is marked a floor instead of printing a total that
        // is short by an unknown amount.
        return counts + this.dim(Text.of('report.cost', {
            calls: report.calls(),
            floor: report.callsWithoutUsage() > 0 ? 'yes' : 'no',
            tokens: grouped(report.tokens()),
        }));
    }

    /**
     * The severity, padded so the titles beside it line up.
     *
     * The width comes from the three translations and not from the seven
     * characters `warning` happens to take, because another language has its own
     * longest word
     */
    private severityLabel(severity: Severity): string {
        const words: Record<string, string> = {
            error: Text.of('severity.error'),
            warning: Text.of('severity.warning'),
            advice: Text.of('severity.advice'),
        };
        const width = Math.max(...Object.values(words).map((word) => [...word].length));
        const codes: Record<string, string> = { error: '31', warning: '33', advice: '34' };

        return this.paint(padCharacters(words[severity.value] ?? '', width), codes[severity.value] ?? '33');
    }

    private paint(text: string, code: string): string {
        return paint(this.colour, text, code);
    }

    private dim(text: string): string {
        return dim(this.colour, text);
    }
}

/** Words for a probability, so the number is not read as a score out of one */
function band(probability: number): string {
    if (probability >= 0.90) return Text.of('band.almost_certain');
    if (probability >= 0.75) return Text.of('band.very_likely');
    if (probability >= 0.50) return Text.of('band.likely');
    if (probability >= 0.25) return Text.of('band.unlikely');

    return Text.of('band.very_unlikely');
}

function hasProbabilities(findings: Finding[]): boolean {
    // A weight is not a probability, so a report carrying only weights should not
    // print the sentence explaining probabilities.
    return findings.some((finding) => finding.probability !== null && finding.measure === 'probability');
}

function groupByTarget(findings: Finding[]): Map<string, Finding[]> {
    const grouped = new Map<string, Finding[]>();

    for (const finding of findings) {
        const group = grouped.get(finding.target) ?? [];
        group.push(finding);
        grouped.set(finding.target, group);
    }

    return grouped;
}

/**
 * Which thing this reading was about.
 *
 * The target alone is right for a question check and useless for a per-field
 * one, where every row reads `state`. What the path adds beyond the target is
 * the field name, which is the only part that differs
 */
function where(finding: Finding): string {
    const target = finding.target;
    const prefix = `/${target === 'state' ? 'state' : `questions/${target}`}`;

    if (finding.path === '' || finding.path === prefix) {
        return target;
    }

    const extra = finding.path.startsWith(`${prefix}/`)
        ? finding.path.slice(prefix.length + 1)
        : finding.path.replace(/^\/+/, '');

    return `${target} · ${extra.replace(/\//g, '.')}`;
}

/** Cut to a byte length, as the report has always counted it */
function shorten(text: string, limit: number): string {
    const buffer = Buffer.from(text, 'utf8');

    return buffer.length <= limit ? text : `${buffer.subarray(0, limit - 1).toString('utf8')}…`;
}

function bytes(text: string): number {
    return Buffer.byteLength(text, 'utf8');
}
