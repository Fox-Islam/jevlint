import { strict as assert } from 'node:assert';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';
import { root } from './helpers/root.js';

const site = join(root, 'site');
const pages = readdirSync(site).filter((name) => name.endsWith('.html'));

/**
 * The pages are written by hand, so a page added without its link is a page
 * nobody reaches from the one beside it
 */
describe('the site', () => {
    it('has a page for every page in docs, and for the README', () => {
        const expected = readdirSync(join(root, 'docs'))
            .filter((name) => name.endsWith('.md'))
            .map((name) => name.replace(/\.md$/, '.html'));

        for (const page of [...expected, 'index.html']) {
            assert.ok(pages.includes(page), `docs has a page the site does not: ${page}.`);
        }
    });

    it('links every page from every page', () => {
        // `corpus.html` and `examples.html` are written for the site and have no
        // page in docs, so the navigation is the list and not the directory.
        const navigation = [...(readFileSync(join(site, 'index.html'), 'utf8')
            .matchAll(/<nav>(.*?)<\/nav>/gs))][0]?.[1] ?? '';
        const linked = [...navigation.matchAll(/href="([^"]+)"/g)].map((match) => match[1]);

        assert.deepEqual([...linked].sort(), [...pages].sort());

        for (const page of pages) {
            const text = readFileSync(join(site, page), 'utf8');

            for (const target of linked) {
                assert.ok(text.includes(`href="${target ?? ''}"`), `${page} does not link ${target ?? ''}.`);
            }

            assert.ok(
                text.includes(`<a href="${page}" aria-current="page">`),
                `${page} does not mark itself as the page being read.`,
            );
        }
    });

    it('leaves no tag unclosed', () => {
        for (const page of pages) {
            const text = readFileSync(join(site, page), 'utf8');

            for (const tag of ['main', 'p', 'table', 'code', 'pre', 'ul', 'tbody']) {
                const open = (text.match(new RegExp(`<${tag}[ >]`, 'g')) ?? []).length;
                const close = (text.match(new RegExp(`</${tag}>`, 'g')) ?? []).length;

                assert.equal(open, close, `${page} has ${open} <${tag}> and ${close} </${tag}>.`);
            }
        }
    });
});
