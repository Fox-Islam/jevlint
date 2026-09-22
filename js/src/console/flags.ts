import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';
import { Severity } from '../report/severity.js';
import type { Args } from './args.js';

const BY_COMMAND: Record<string, string[]> = {
    check: ['static-only', 'no-state', 'min', 'strict', 'max-state', 'timeout', 'brief', 'repeats', 'question', 'only', 'all', 'config', 'show-accepted', 'jev'],
    probe: ['state', 'repeats', 'variants', 'strict', 'question'],
    'self-test': ['check', 'config', 'jev'],
    checks: ['config', 'jev'],
};

const SWITCHES = ['no-color', 'openrouter', 'help', 'version', 'static-only', 'no-state', 'strict', 'brief', 'all', 'show-accepted'];

/** How many arguments each command takes after its own name */
const ARGUMENTS: Record<string, number> = { check: 1, probe: 1, 'self-test': 0, checks: 1, help: 1, version: 0 };

/** Options that shape a call, and so do nothing in a run that makes none */
const NEEDS_CALLS = ['repeats', 'timeout', 'no-state', 'all', 'model', 'openrouter'];

/** Options whose value is a count */
const COUNTS = ['repeats', 'max-state'];

/** What each command accepts, and what it does when given something else */
export const Flags = {
    EVERYWHERE: ['no-color', 'env-file', 'lang', 'model', 'openrouter', 'format', 'help', 'version'],

    /**
     * Every option this tool takes, with the commands it belongs to. `help
     * --format=json` prints it, so a caller can discover the interface
     */
    documented(): Record<string, string[]> {
        return { everywhere: Flags.EVERYWHERE, ...BY_COMMAND };
    },

    guard(command: string, args: Args): void {
        if (args.malformed.length > 0) {
            throw JevLintError.of(JevLintError.USAGE, Text.of('flags.needs_two_dashes', {
                options: args.malformed
                    .map((given) => Text.of('flags.needs_two_dashes_item', { given, fixed: given.replace(/^-+/, '') }))
                    .join(', '),
            }));
        }

        // Silently letting the last one win reports at a floor the caller wrote
        // twice and meant once.
        if (args.repeated.length > 0) {
            throw JevLintError.of(JevLintError.USAGE, Text.of('flags.repeated', {
                options: args.repeated.map((option) => `--${option}`).join(', '),
                count: args.repeated.length,
            }));
        }

        // A second file is the shape of a caller who takes both as checked. Only
        // the first is.
        const extra = args.positional.slice(1 + (ARGUMENTS[command] ?? 0));

        if (extra.length > 0) {
            throw JevLintError.of(JevLintError.USAGE, Text.of('flags.too_many_arguments', {
                command,
                takes: ARGUMENTS[command] ?? 0,
                extra: extra.join(', '),
            }));
        }

        const known = [...Flags.EVERYWHERE, ...(BY_COMMAND[command] ?? [])];
        const unknown = args.unknown(known);

        if (unknown.length > 0) {
            throw new JevLintError(Text.of('flags.unknown_option', {
                count: unknown.length,
                options: unknown.map((option) => `--${option}`).join(', '),
                command,
                accepts: known.map((option) => `--${option}`).join(', '),
            }));
        }

        // A value option written bare reads as `true`, and `value()` then hands
        // back its default, so `--jev` on its own ran the newest version's checks
        // while the caller believed they had pinned one.
        for (const option of known) {
            if (SWITCHES.includes(option) || !args.has(option)) {
                continue;
            }

            if (args.value(option) === null) {
                throw JevLintError.of(JevLintError.USAGE, Text.of('flags.needs_a_value', { option }));
            }

            // An empty value reaches the client as an empty model name, and the
            // report reads "asked through " with nothing after it.
            if (args.value(option) === '') {
                throw JevLintError.of(JevLintError.USAGE, Text.of('flags.empty_value', { option }));
            }
        }

        Flags.format(args);
        allowed(args, 'min', Severity.cases().map((severity) => severity.value));

        // Up front, before anything runs. A switch given a value reads as true
        // whatever the value is, so `--strict=false` would turn strict on, and
        // saying so after the report is printed is too late.
        for (const option of SWITCHES) {
            args.flag(option);
        }

        // Read up front. A count this run never reads is a count nobody
        // validated, so `--static-only --repeats=abc` ran clean and reported
        // nothing.
        for (const count of COUNTS) {
            if (known.includes(count) && args.has(count)) {
                args.int(count, 1);
            }
        }

        if (known.includes('timeout') && args.has('timeout')) {
            args.seconds('timeout', 10.0);
        }

        // A flag that cannot do anything in this run is a flag the caller thinks
        // is doing something.
        if (args.flag('static-only')) {
            const dead = NEEDS_CALLS.filter((option) => args.has(option));

            if (dead.length > 0) {
                throw JevLintError.of(JevLintError.USAGE, Text.of('flags.dead_with_static_only', {
                    options: dead.map((option) => `--${option}`).join(', '),
                    count: dead.length,
                }));
            }
        }

        // `--brief` shapes the text report. Accepting it beside `--format=json`
        // and doing nothing is the silent no-op this tool refuses elsewhere.
        if (args.flag('brief') && args.value('format') === 'json') {
            throw JevLintError.of(JevLintError.USAGE, Text.of('flags.brief_with_json'));
        }

        if (args.flag('show-accepted') && args.value('format') === 'json') {
            throw JevLintError.of(JevLintError.USAGE, Text.of('flags.show_accepted_with_json'));
        }
    },

    /**
     * The one option every command reads, including the ones that take no others.
     *
     * It decides how a caller parses the output, so an unrecognised value has to
     * be refused on every command, `help` included
     */
    format(args: Args): void {
        allowed(args, 'format', ['text', 'json']);
    },
};

function allowed(args: Args, name: string, values: string[]): void {
    const given = args.value(name);

    if (given !== null && !values.includes(given)) {
        throw new JevLintError(Text.of('flags.value_not_allowed', {
            option: name,
            given,
            allowed: values.join(', '),
        }));
    }
}
