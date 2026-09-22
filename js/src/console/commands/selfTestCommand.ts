import { Catalogue } from '../../catalogue/catalogue.js';
import type { Check } from '../../catalogue/check.js';
import { Config } from '../../config/config.js';
import { JevLintError } from '../../exceptions/jevLintError.js';
import { SelfTestFormatter } from '../../format/selfTestFormatter.js';
import { Text } from '../../i18n/text.js';
import { ClientFactory } from '../../lint/clientFactory.js';
import { SelfTest } from '../../selftest/selfTest.js';
import { Json } from '../../support/json.js';
import type { Args } from '../args.js';
import type { Output } from '../output.js';
import { basename } from 'node:path';

/** `jevlint self-test` - does each check separate its own two examples? */
export class SelfTestCommand {
    async run(args: Args, output: Output): Promise<number> {
        const config = Config.discover(args.value('config'), '.');
        const catalogue = Catalogue.forRun(args.value('jev'), config);
        const only = (args.value('check', '') ?? '')
            .split(',')
            .map((id) => id.trim())
            .filter((id) => id !== '');

        if (args.has('check') && only.length === 0) {
            throw JevLintError.of(JevLintError.USAGE, Text.of('narrow.no_check_named'));
        }

        // A check id the catalogue does not hold is a typo or a rename. Scoring
        // nothing and exiting 0 leaves a pinned CI job green for ever.
        const ids = catalogue.written().map((check) => check.id);
        const unknown = only.filter((id) => !ids.includes(id));

        if (unknown.length > 0) {
            throw new JevLintError(Text.of('catalogue.no_such_check', { ids: unknown.join(', ') }));
        }

        const withheld = only.filter((id) => catalogue.find(id) === null);

        if (withheld.length > 0) {
            throw new JevLintError(Text.of('self_test.withheld_for_version', {
                ids: withheld.join(', '),
                count: withheld.length,
                jev: catalogue.jev,
            }));
        }

        const staticChecks = only.filter((id) => catalogue.find(id)?.isStatic() === true);

        if (staticChecks.length > 0) {
            throw new JevLintError(Text.of('self_test.static_has_nothing_to_score', {
                ids: staticChecks.join(', '),
                count: staticChecks.length,
            }));
        }

        const scores = await new SelfTest(catalogue, ClientFactory.make(
            args.value('model'),
            args.flag('openrouter'),
        )).run(only);

        if (args.value('format') === 'json') {
            output.line(Json.encode(scores.map((score) => score.toObject())));
        } else {
            output.write(new SelfTestFormatter(output.colour()).format(scores));
        }

        // A model check with no fixture is scored by nothing and would leave the
        // run reporting `0 of 0 checks separate their own examples`, which a
        // pinned CI job reads as a pass for ever.
        const scored = scores.map((score) => score.check.id);
        const unscored = catalogue.all().filter((check: Check) => check.isModel()
            && (only.length === 0 || only.includes(check.id))
            && !scored.includes(check.id));

        if (unscored.length > 0) {
            output.error(Text.of('self_test.no_examples', {
                ids: unscored.map((check) => check.id).join(', '),
                count: unscored.length,
                file: basename(Catalogue.locate('fixtures.json')),
            }));

            return 1;
        }

        // A check that could not be asked has not failed its examples; the run
        // did not happen. Exit 1 is for a catalogue that is wrong, exit 2 for a
        // run that could not tell.
        if (scores.some((score) => score.errored())) {
            return 2;
        }

        if (scores.some((score) => !score.passed())) {
            return 1;
        }

        return 0;
    }
}
