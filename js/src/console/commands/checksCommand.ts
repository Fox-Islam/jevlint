import { Catalogue } from '../../catalogue/catalogue.js';
import type { Check } from '../../catalogue/check.js';
import type { Wording } from '../../catalogue/wording.js';
import { Config } from '../../config/config.js';
import { JevLintError } from '../../exceptions/jevLintError.js';
import { pad } from '../../format/colour.js';
import { Text } from '../../i18n/text.js';
import { Json } from '../../support/json.js';
import type { Args } from '../args.js';
import type { Output } from '../output.js';

/** `jevlint checks` - what the catalogue holds */
export class ChecksCommand {
    run(args: Args, output: Output): number {
        const config = Config.discover(args.value('config'), '.');
        const catalogue = Catalogue.forRun(args.value('jev'), config);
        const wanted = args.argument(1);

        // The README says a check id is how you look one up. Printing all of them
        // instead answers a question nobody asked.
        if (wanted !== null) {
            const check = catalogue.find(wanted);

            if (check === null) {
                throw JevLintError.of(JevLintError.USAGE, catalogue.findWritten(wanted) !== null
                    ? Text.of('catalogue.check_not_for_version', {
                        id: wanted,
                        jev: catalogue.jev,
                        versions: catalogue.versions.join(', '),
                    })
                    : Text.of('catalogue.no_such_check', { ids: wanted }));
            }

            if (args.value('format') === 'json') {
                output.line(Json.encode(describe(check)));

                return 0;
            }

            for (const [key, value] of Object.entries(describe(check))) {
                output.line(`${pad(key, 12)} ${
                    typeof value === 'object' && value !== null ? Json.inline(value) : String(value)
                }`);
            }

            return 0;
        }

        if (args.value('format') === 'json') {
            output.line(Json.encode(catalogue.all().map(describe)));

            return 0;
        }

        output.line(Text.of('catalogue.header', {
            version: catalogue.version,
            model: catalogue.model,
            withheld: catalogue.withheld(),
        }));
        output.line();

        for (const mode of ['static', 'model']) {
            output.line(mode.toUpperCase());

            for (const check of catalogue.all()) {
                if (check.mode !== mode) {
                    continue;
                }

                output.line(`  ${pad(check.severity, 8)} ${pad(check.id, 34)} ${pad(check.appliesTo.join(','), 12)} ${check.title}`);
            }

            output.line();
        }

        return 0;
    }
}

function describe(check: Check): Record<string, unknown> {
    return present({
        id: check.id,
        title: check.title,
        mode: check.mode,
        scope: check.scope,
        applies_to: check.appliesTo,
        severity: check.severity,
        // Which builds the check is a rule for, where it is not all of them
        since: check.since,
        until: check.until,
        reads: check.reads,
        action: check.action,
        message: check.message,
        hint: check.hint,
        suggest: check.suggest,
        docs: check.docs,
        removes: check.removes,
        // What a static check tests, and which findings it puts out of date. A
        // consumer that reads `superseded_by` in a report had nowhere to look the
        // relationship up.
        rule: check.rule,
        supersedes: check.supersedes.length === 0 ? null : check.supersedes,
        // A model check is a judgement against a threshold, and a caller that
        // cannot see the threshold cannot say what it gated on.
        trigger: check.isModel() ? check.trigger : null,
        questions: check.isModel() ? check.wordings.map(wording) : null,
    });
}

function wording(one: Wording): Record<string, unknown> {
    return Object.fromEntries(Object.entries({
        type: one.type,
        // Keep the placeholder: the catalogue's own text is what a reader is
        // being shown, and blanking it prints a hole.
        instructions: one.instructions('{field}'),
        criteria: one.criteria,
    }).filter(([, value]) => value !== null));
}

function present(row: Record<string, unknown>): Record<string, unknown> {
    return Object.fromEntries(
        Object.entries(row).filter(([, value]) => value !== null && value !== undefined && value !== ''),
    );
}
