import { strict as assert } from 'node:assert';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { describe, it } from 'node:test';
import { Catalogue } from '../src/catalogue/catalogue.js';
import { Linter } from '../src/lint/linter.js';
import { Query } from '../src/query/query.js';
import { Severity } from '../src/report/severity.js';
import { root } from './helpers/root.js';
import { sources } from './helpers/sources.js';

const pages = ['README.md', ...readdirSync(join(root, 'docs')).map((name) => `docs/${name}`)];

/**
 * A relative link is written against the page it sits in, so moving prose from
 * one page to another leaves a link that resolves to nothing
 */
describe('every link in the pages', () => {
    it('resolves to a file that is there', () => {
        const broken: string[] = [];

        for (const page of pages) {
            const text = readFileSync(join(root, page), 'utf8');

            for (const match of text.matchAll(/\]\(([^)#\s]+)(?:#[^)\s]*)?\)/g)) {
                const target = match[1] ?? '';

                if (target.startsWith('http') || target.startsWith('mailto:')) {
                    continue;
                }

                if (!existsSync(resolve(root, dirname(page), target))) {
                    broken.push(`${page} -> ${target}`);
                }
            }
        }

        assert.deepEqual(broken, []);
    });

    /**
     * The pages name checks by id, and a renamed check would leave the name
     * behind in prose that still reads as though it were right
     */
    it('names only checks the catalogue holds', () => {
        const written = Catalogue.load().written();
        const known = new Set(written.map((check) => check.id));
        // The families the catalogue uses, so a dataset or a repository named
        // the same way is not read as a check id that has gone missing.
        const families = new Set(written.map((check) => check.id.split('/')[0] ?? ''));
        const missing: string[] = [];

        for (const page of pages) {
            const text = readFileSync(join(root, page), 'utf8');

            for (const match of text.matchAll(/`([a-z-]+)\/([a-z-]+)`/g)) {
                const id = `${match[1] ?? ''}/${match[2] ?? ''}`;

                if (families.has(match[1] ?? '') && !known.has(id)) {
                    missing.push(`${page}: ${id}`);
                }
            }
        }

        assert.deepEqual(missing, []);
    });
});

/**
 * The JavaScript page names methods by hand, and a renamed one leaves a page
 * that reads as though it were right
 */
describe('the JavaScript page', () => {
    const page = readFileSync(join(root, 'docs/javascript.md'), 'utf8');
    const exported = sources().find(({ path }) => path.endsWith('src/index.ts'))?.contents ?? '';

    it('names only methods the linter has', () => {
        const has = new Set([
            ...Object.getOwnPropertyNames(Linter.prototype),
            ...Object.getOwnPropertyNames(Linter),
        ]);
        const missing: string[] = [];

        // `.only(` and `.check(` in the page, and `Linter.make(` with its class.
        for (const match of page.matchAll(/(?:^|[^\w])(?:Linter)?\.([a-zA-Z]+)\(/gm)) {
            const name = match[1] ?? '';

            if (!has.has(name)) {
                missing.push(name);
            }
        }

        assert.deepEqual([...new Set(missing)], []);
    });

    it('names only things the package exports', () => {
        for (const name of ['Linter', 'Query', 'Client', 'Config', 'Severity', 'Report']) {
            assert.ok(exported.includes(name), `The page names ${name} and index.ts does not export it.`);
        }
    });

    it('names the static factories the page says start a linter', () => {
        for (const name of ['make', 'fromEnvironment', 'rulesOnly']) {
            assert.ok(name in Linter, `The page names Linter.${name} and there is none.`);
            assert.ok(page.includes(`Linter.${name}(`));
        }
    });
});

/**
 * The README's first command is the first thing anybody runs, and it states
 * what they will see. A count that drifts is wrong in the thirty seconds a
 * reader spends deciding whether to trust the rest
 */
describe('the quickstart', () => {
    it('reports what the README says it does', async () => {
        const report = await Linter.rulesOnly().check(Query.fromFile(join(root, 'examples/broken-triage.json')));
        const word = (count: number): string => ['zero', 'one', 'two', 'three', 'four', 'five', 'six'][count] ?? String(count);

        const said = `reports ${word(report.count(Severity.Error))} error, `
            + `${word(report.count(Severity.Warning))} warnings and `
            + `${word(report.count(Severity.Advice))} advisories`;

        // The README wraps, so the sentence is compared without its line breaks.
        const readme = readFileSync(join(root, 'README.md'), 'utf8').replace(/\s+/g, ' ');

        assert.ok(readme.includes(said), `The quickstart no longer describes this run: "${said}".`);
    });
});
