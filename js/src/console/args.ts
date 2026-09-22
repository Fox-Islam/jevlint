import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';

/** The bare minimum that reads `--name=value`, `--flag` and positionals */
export class Args {
    private constructor(
        public readonly positional: string[],
        private readonly options: Map<string, string | true>,
        /** options written with one dash */
        public readonly malformed: string[] = [],
        /** options given more than once */
        public readonly repeated: string[] = [],
    ) {}

    static parse(argv: string[]): Args {
        const positional: string[] = [];
        const options = new Map<string, string | true>();
        const malformed: string[] = [];
        const repeated = new Set<string>();

        for (const argument of argv) {
            if (!argument.startsWith('--')) {
                // `-static-only`, written with one dash, parsed as a positional,
                // so the option guard never saw it and the run paid for the calls
                // the caller believed they had switched off.
                if (argument.startsWith('-') && argument.length > 1) {
                    malformed.push(argument);

                    continue;
                }

                positional.push(argument);

                continue;
            }

            const body = argument.slice(2);
            const at = body.indexOf('=');

            if (at >= 0) {
                const name = body.slice(0, at);

                if (options.has(name)) {
                    repeated.add(name);
                }

                options.set(name, body.slice(at + 1));

                continue;
            }

            if (options.has(body)) {
                repeated.add(body);
            }

            options.set(body, true);
        }

        return new Args(positional, options, malformed, [...repeated]);
    }

    has(name: string): boolean {
        return this.options.has(name);
    }

    flag(name: string): boolean {
        const value = this.options.get(name);

        if (value === undefined) {
            return false;
        }

        // `--strict=false` read as true, which is the opposite of what anybody
        // typing it means. A switch takes no value.
        if (value !== true && value !== '') {
            throw JevLintError.of(JevLintError.USAGE, Text.of('args.switch_takes_no_value', { option: name }));
        }

        return true;
    }

    value(name: string, fallback: string | null = null): string | null {
        const value = this.options.get(name);

        return typeof value === 'string' ? value : fallback;
    }

    /**
     * A count, with a ceiling.
     *
     * Every count here multiplies calls, and a typed `--repeats=50` is a bill
     * nobody meant to run. The limit is refused out loud, naming what the most is
     */
    int(name: string, fallback: number, most = 20): number {
        const value = this.value(name);

        if (value === null) {
            return fallback;
        }

        // Falling back to the default here runs a threshold the caller believes
        // they raised, and says nothing about it.
        if (!isNumeric(value)) {
            throw JevLintError.of(JevLintError.USAGE, Text.of('args.not_a_number', { option: name, given: value }));
        }

        const whole = Math.trunc(Number(value));

        // `1.9` truncates to 1 and a huge value saturates, both in silence, so
        // the threshold that runs is not the one the caller wrote.
        if (String(whole) !== value.replace(/^\+/, '')) {
            throw JevLintError.of(JevLintError.USAGE, Text.of('args.not_a_whole_number', { option: name, given: value }));
        }

        if (whole < 1) {
            throw JevLintError.of(JevLintError.USAGE, Text.of('args.not_a_count', { option: name, given: value }));
        }

        if (whole > most) {
            throw JevLintError.of(JevLintError.USAGE, Text.of('args.above_the_most', { option: name, given: value, most }));
        }

        return whole;
    }

    /**
     * A duration in seconds, which can carry a fraction.
     *
     * The count reader calls `--timeout=0.5` "not a count", which is a message
     * about the wrong kind of number
     */
    seconds(name: string, fallback: number): number {
        const value = this.value(name);

        if (value === null) {
            return fallback;
        }

        if (!isNumeric(value) || Number(value) <= 0) {
            throw JevLintError.of(JevLintError.USAGE, Text.of('args.not_seconds', { option: name, given: value }));
        }

        return Number(value);
    }

    argument(index: number): string | null {
        return this.positional[index] ?? null;
    }

    /**
     * Options the caller did not list.
     *
     * A mistyped flag is otherwise indistinguishable from one left out, so
     * `--static-onlyy` spends money on a run the caller takes for free
     */
    unknown(known: string[]): string[] {
        return [...this.options.keys()].filter((name) => !known.includes(name));
    }
}

/**
 * A decimal or a float, with an optional sign and exponent, and whitespace
 * around it. The whole-number check then compares the parsed value against what
 * was typed, so a padded `--repeats= 5` is refused there and not here
 */
function isNumeric(value: string): boolean {
    return /^\s*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\s*$/.test(value);
}
