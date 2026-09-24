import { Text } from '../i18n/text.js';
import type { CheckScore } from '../selftest/checkScore.js';
import { dim, pad, padLeft, paint } from './colour.js';
import { fixed } from './numbers.js';

/** What each check scored against its own clean and broken examples */
export class SelfTestFormatter {
    constructor(private readonly colour = true) {}

    format(scores: CheckScore[]): string {
        const name = (score: CheckScore): string => (score.domain === '' ? score.check.id : `${score.check.id} (${score.domain})`);
        // Wide enough for the longest id with its domain, so a long one does not push its row out of line.
        const width = Math.max(44, ...scores.map((score) => name(score).length));
        const lines = [
            dim(this.colour, Text.of('self_test.heading')),
            '',
            paint(this.colour, row(
                width,
                Text.of('self_test.column_check'),
                Text.of('self_test.column_clean'),
                Text.of('self_test.column_broken'),
                Text.of('self_test.column_fixed'),
                Text.of('self_test.column_span'),
                Text.of('self_test.column_verdict'),
            ), '1'),
        ];

        for (const score of scores) {
            lines.push(row(
                width,
                name(score),
                number(score.clean),
                number(score.broken),
                number(score.fixed),
                number(score.span()),
                this.verdict(score),
            ));
        }

        const failed = scores.filter((score) => !score.passed());
        lines.push('');
        // One row per example set, and every check ships two. Counting rows as
        // checks read as though `--check=one-id` had matched two ids.
        const checks = new Set(scores.map((score) => score.check.id));
        lines.push(Text.of('self_test.summary', {
            separated: scores.length - failed.length,
            sets: scores.length,
            checks: checks.size,
        }));

        if (failed.length > 0) {
            lines.push(dim(this.colour, Text.of('self_test.footer')));
        }

        return `${lines.join('\n')}\n`;
    }

    private verdict(score: CheckScore): string {
        const verdict = score.verdict();

        if (verdict === 'ok') {
            return paint(this.colour, verdict, '32');
        }

        return paint(this.colour, verdict, verdict === 'weak' ? '33' : '31');
    }
}

function row(width: number, check: string, clean: string, broken: string, fix: string, span: string, verdict: string): string {
    return `${pad(check, width)} ${padLeft(clean, 7)} ${padLeft(broken, 7)} ${padLeft(fix, 7)} ${padLeft(span, 7)}  ${verdict}`;
}

function number(value: number | null): string {
    return value === null ? 'n/a' : fixed(value, 2);
}
