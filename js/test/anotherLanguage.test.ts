import { strict as assert } from 'node:assert';
import { cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, before, describe, it } from 'node:test';
import { Catalogue } from '../src/catalogue/catalogue.js';
import { CheckText } from '../src/i18n/checkText.js';
import { Text } from '../src/i18n/text.js';
import { Linter } from '../src/lint/linter.js';
import { Query } from '../src/query/query.js';

/**
 * Jev answers in whatever language the query is written in, so a query in
 * French is a query this has to check. The messages are one half of that; the
 * word lists a check matches against are the other, and only the second can
 * turn a clean query into a finding
 */
describe('a query written in another language', () => {
    let dir = '';

    before(() => {
        dir = mkdtempSync(join(tmpdir(), 'jevlint-lang-'));
        writeFileSync(join(dir, 'fr.json'), JSON.stringify({
            'file.unreadable': 'Impossible de lire {path}.',
            'words.fallback_labels': ['autre', 'autres', 'aucun'],
        }));

        mkdirSync(join(dir, 'checks/lang'), { recursive: true });
        cpSync(Catalogue.locate('catalogue.json'), join(dir, 'checks/catalogue.json'));
        cpSync(Catalogue.locate('fixtures.json'), join(dir, 'checks/fixtures.json'));
        writeFileSync(join(dir, 'checks/lang/fr.json'), JSON.stringify({
            'choice/no-fallback': {
                title: "Le Choice n'a pas d'option de repli",
                question: { instructions: 'traduit' },
            },
        }));

        process.env['JEVLINT_LANG_DIR'] = dir;
        Text.reset();
        CheckText.reset();
    });

    after(() => {
        rmSync(dir, { recursive: true, force: true });
        delete process.env['JEVLINT_LANG_DIR'];
        delete process.env['JEVLINT_CHECKS_DIR'];
        Text.reset();
        CheckText.reset();
    });

    it('answers in the locale where the locale has the message', () => {
        Text.use('fr');

        assert.equal(Text.of('file.unreadable', { path: 'q.json' }), 'Impossible de lire q.json.');
    });

    /** A part-finished translation prints English, never a key */
    it('prints English where the locale leaves a message out', () => {
        Text.use('fr');

        assert.equal(Text.of('report.nothing_to_report'), 'Nothing to report.');
    });

    it('reaches the language before it reaches English', () => {
        Text.use('fr_CA');

        assert.equal(Text.of('file.unreadable', { path: 'q.json' }), 'Impossible de lire q.json.');
    });

    /**
     * The check reads option labels, and `autre` is a catch-all to every French
     * reader and to nothing in an English list
     */
    it('clears the check that looks for a catch-all, once the list is translated', async () => {
        Text.use('en');
        assert.deepEqual(await fallbackFindings('autre'), ['choice/no-fallback']);

        Text.use('fr');
        assert.deepEqual(await fallbackFindings('autre'), []);
    });

    /** An English label in a query written in French is still a catch-all */
    it('reads the English list beside the locale one', async () => {
        Text.use('fr');

        assert.deepEqual(await fallbackFindings('other'), []);
    });

    it('says its piece in the locale, from the file beside the catalogue', () => {
        Text.use('fr');
        process.env['JEVLINT_CHECKS_DIR'] = join(dir, 'checks');
        CheckText.reset();

        const check = Catalogue.load(join(dir, 'checks/catalogue.json')).find('choice/no-fallback');

        assert.equal(check?.title, "Le Choice n'a pas d'option de repli");
    });

    /**
     * The question a check puts to Jev is what the check measures, and every
     * figure in docs/evidence.md was taken with the wording in the catalogue. A
     * translation cannot reach it
     */
    it('cannot translate what a check asks Jev', () => {
        Text.use('fr');
        process.env['JEVLINT_CHECKS_DIR'] = join(dir, 'checks');
        CheckText.reset();

        assert.deepEqual(Object.keys(CheckText.for('choice/no-fallback')), ['title']);
    });
});

async function fallbackFindings(catchAll: string): Promise<string[]> {
    const report = await Linter.rulesOnly().only(['choice/no-fallback']).check(Query.fromObject({
        state: { demande: "J'ai été facturé deux fois." },
        questions: {
            service: {
                type: 'choice',
                instructions: 'Quel service doit traiter cette demande ?',
                criteria: {
                    facturation: 'Les factures',
                    expedition: 'La livraison',
                    [catchAll]: 'Le reste',
                },
            },
        },
    }, 'test'));

    return report.findings().map((finding) => finding.checkId);
}
