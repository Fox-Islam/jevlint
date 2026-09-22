import { Catalogue } from '../../catalogue/catalogue.js';
import { Config } from '../../config/config.js';
import { JevLintError } from '../../exceptions/jevLintError.js';
import { TextFormatter } from '../../format/textFormatter.js';
import { Text } from '../../i18n/text.js';
import { Linter } from '../../lint/linter.js';
import { Query } from '../../query/query.js';
import { Severity } from '../../report/severity.js';
import { Json } from '../../support/json.js';
import type { Args } from '../args.js';
import type { Output } from '../output.js';

/** `jevlint check <query.json>` - the linter */
export class CheckCommand {
    async run(args: Args, output: Output): Promise<number> {
        const path = args.argument(1);

        if (path === null) {
            throw new JevLintError(Text.of('check.no_query_file'));
        }

        const whole = Query.fromFile(path);
        const wanted = list(args.value('question'), 'question');
        const missing = wanted.filter((id) => !whole.questions.some((question) => question.id === id));

        if (missing.length > 0) {
            throw new JevLintError(Text.of('query.no_such_question', { path, ids: missing.join(', ') }));
        }

        const query = whole.only(wanted);
        const config = Config.discover(args.value('config'), path);
        const catalogue = Catalogue.forRun(args.value('jev'), config);
        const only = list(args.value('only'), 'only');

        let linter = args.flag('static-only')
            ? Linter.rulesOnly(catalogue, config)
            : Linter.fromEnvironment({
                model: args.value('model'),
                openRouter: args.flag('openrouter'),
                timeout: args.has('timeout') ? args.seconds('timeout', 10.0) : null,
                catalogue,
                config,
            });

        linter = linter
            .only(only)
            .repeats(args.int('repeats', 1))
            .maxStateChars(args.int('max-state', 20000, Number.MAX_SAFE_INTEGER));

        if (args.flag('no-state')) {
            linter = linter.withoutState();
        }

        if (args.flag('all')) {
            linter = linter.reportingCleared();
        }

        const report = await linter.check(query, whole);

        const floor = Severity.fromName(args.value('min', 'advice') ?? 'advice');

        // The counts stay whole while the list is filtered, so a reader who sees
        // `4 advice` and no advice rows is owed the reason.
        const hidden = report.findings().length - report.findings(floor).length;

        if (hidden > 0) {
            report.note(Text.of('note.below_the_floor', { floor: floor.value, count: hidden }), hidden);
        }

        if (args.value('format') === 'json') {
            output.line(Json.encode(report.toObject(floor)));
        } else {
            output.write(new TextFormatter(
                output.colour(),
                args.flag('brief'),
                args.flag('show-accepted'),
                args.flag('all'),
            ).format(report, floor));
        }

        // Checks that could not be asked did not pass. Reporting 0 here would
        // tell a caller gating on the exit code that a query nobody checked is
        // fine.
        if (!report.isComplete()) {
            return 2;
        }

        // A run can leave nothing to do - a narrowing that names a state check on
        // a query with no state - and every reason is recorded as a skipped note.
        // Reporting that as a pass is the same lie as reporting a failed call as
        // one.
        if (report.askedCount() === 0) {
            return 2;
        }

        if (report.hasErrors()) {
            return 1;
        }

        if (args.flag('strict') && !report.isEmpty(floor)) {
            return 1;
        }

        // A run that could not decide is not a run that passed.
        return report.unstable().length === 0 ? 0 : 3;
    }
}

function list(value: string | null, option = ''): string[] {
    if (value === null) {
        return [];
    }

    const named = value.split(',').map((item) => item.trim()).filter((item) => item !== '');

    // `--only=$CHECKS` with the variable unset read as no narrowing at all, so a
    // run meant to carry one check carried the catalogue and paid for it.
    if (named.length === 0) {
        throw JevLintError.of(JevLintError.USAGE, Text.of('narrow.nothing_named', { option }));
    }

    return named;
}
