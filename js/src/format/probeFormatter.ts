import { Text } from '../i18n/text.js';
import { Probe } from '../probe/probe.js';
import { QuestionProbe } from '../probe/questionProbe.js';
import type { Reading } from '../probe/reading.js';
import type { Note } from '../report/note.js';
import { dim, pad, paint } from './colour.js';
import { fixed, grouped, signed } from './numbers.js';

/** The probe's readings as a table per question */
export class ProbeFormatter {
    constructor(private readonly colour = true) {}

    format(
        probes: Map<string, QuestionProbe>,
        source: string,
        repeats: number,
        calls: number,
        tokens: number,
        notes: Note[] = [],
    ): string {
        const lines: string[] = [
            dim(this.colour, Text.of('probe.header', {
                source,
                repeats,
                calls,
                tokens: grouped(tokens),
            })),
            '',
        ];

        let moved = 0;

        for (const [id, probe] of probes) {
            lines.push(...this.question(id, probe));
            lines.push('');

            if (probe.readings.some((reading) => probe.moved(reading))) {
                moved++;
            }
        }

        lines.push(...this.legend(probes));

        for (const note of notes) {
            lines.push(`${paint(this.colour, note.isUnreachable() ? Text.of('label.failed') : Text.of('label.note'), '33')} ${note.message}`);
        }

        // Name the rewrites that moved. Reassuring the reader about
        // `criteria-stripped` whenever it merely ran pointed them away from
        // whichever variant was the reason the run failed.
        const movers = moversIn(probes);

        const undecided = [...probes.values()].filter((probe) => probe.undecided()).length;

        lines.push(
            Text.of('probe.summary', { moved, questions: probes.size })
            + (undecided === 0 ? '' : Text.of('probe.undecided_summary', { count: undecided }))
            + (movers.length === 0 ? '' : Text.of('probe.movers', {
                count: movers.length,
                names: movers.map((variant) => `\`${variant}\``).join(', '),
            }))
            + (movers.includes('criteria-stripped') ? Text.of('probe.criteria_stripped_moved') : ''),
        );
        lines.push(dim(this.colour, Text.of('probe.starred_legend', {
            negligible: QuestionProbe.NEGLIGIBLE,
            floor: Probe.PUBLISHED_NOISE,
        })));

        return `${lines.join('\n')}\n`;
    }

    /** What each rewrite did to the query, named once at the end */
    private legend(probes: Map<string, QuestionProbe>): string[] {
        // The key is the variant name, which is an identifier the JSON carries
        // and `--variants` matches on, so it is not translated.
        const seen = new Map<string, string>([['unchanged', Text.of('probe.unchanged_describe')]]);

        for (const probe of probes.values()) {
            for (const reading of probe.readings) {
                seen.set(reading.variant, reading.describe);
            }
        }

        const lines = [dim(this.colour, Text.of('probe.legend_heading'))];

        for (const [name, describe] of seen) {
            lines.push(dim(this.colour, `  ${pad(name, 20)} ${describe}`));
        }

        return [...lines, ''];
    }

    private question(id: string, probe: QuestionProbe): string[] {
        const baseline = probe.baseline();
        const lines = [paint(this.colour, id, '1') + dim(
            this.colour,
            `  ${probe.question.type}${probe.reading === null ? '' : `, ${probe.reading}`}`,
        )];

        if (baseline === null) {
            lines.push(`  ${paint(this.colour, Text.of('probe.no_reading'), '31')}`);

            return lines;
        }

        const noise = probe.noise();
        lines.push(`    ${pad('unchanged', 20)} ${fixed(baseline, 3)} ${dim(this.colour, noise === null ? '' : Text.of('probe.noise', {
            noise,
            below: noise < Probe.PUBLISHED_NOISE ? 'yes' : 'no',
        }))}`);

        // Under the unchanged row, because it is a fact about that reading and
        // not about any of the rewrites below it.
        if (probe.undecided()) {
            lines.push(`    ${paint(this.colour, Text.of('probe.undecided', {
                flips: probe.flips() ? 'yes' : 'no',
            }), '33')}`);
        }

        for (const reading of probe.readings) {
            lines.push(this.reading(probe, reading));
        }

        return lines;
    }

    private reading(probe: QuestionProbe, reading: Reading): string {
        if (reading.value === null) {
            return `  ${pad(reading.variant, 20)} ${paint(this.colour, reading.error ?? Text.of('probe.no_reading'), '31')}`;
        }

        const delta = probe.delta(reading) ?? 0.0;
        const ratio = probe.ratio(reading) ?? 0.0;
        const moved = probe.moved(reading);

        const line = `  ${moved ? paint(this.colour, '*', '33') : ' '} ${pad(reading.variant, 20)} ${fixed(reading.value, 3)}  ${signed(delta, 3)}`;
        const tail = Text.of('probe.noise_ratio', { ratio });

        return `${line}  ${moved ? paint(this.colour, `${tail}, moved`, '33') : dim(this.colour, tail)}`;
    }
}

/** Every variant name that moved an answer, across all the questions */
function moversIn(probes: Map<string, QuestionProbe>): string[] {
    const movers = new Set<string>();

    for (const probe of probes.values()) {
        for (const reading of probe.readings) {
            if (probe.moved(reading)) {
                movers.add(reading.variant);
            }
        }
    }

    return [...movers];
}
