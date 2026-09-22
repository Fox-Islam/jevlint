import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';
import { argumentsOf, format, parses } from '../src/i18n/icu.js';
import { messages } from '../src/lang/en.js';
import { Text } from '../src/i18n/text.js';
import { sources } from './helpers/sources.js';

describe('the message formatter', () => {
    it('reads a run of braces quoted together', () => {
        assert.equal(format('en', "a '{' b '}}' c"), 'a { b }} c');
        assert.equal(format('en', "'{'answer, when'}'"), '{answer, when}');
    });

    it('leaves an apostrophe alone in front of an ordinary letter', () => {
        assert.equal(format('en', "the SDK's own"), "the SDK's own");
        assert.equal(format('en', "it''s here"), "it's here");
    });

    it('chooses a plural by the locale rules and not by a count written here', () => {
        const pattern = '{n, plural, one {# sprawdzenie} few {# sprawdzenia} many {# sprawdzeń} other {# sprawdzenia}}';

        assert.equal(format('pl', pattern, { n: 1 }), '1 sprawdzenie');
        assert.equal(format('pl', pattern, { n: 3 }), '3 sprawdzenia');
        assert.equal(format('pl', pattern, { n: 12 }), '12 sprawdzeń');
    });

    it('prefers an exact count to the category it falls in', () => {
        const pattern = '{n, plural, =0 {none} one {# thing} other {# things}}';

        assert.equal(format('en', pattern, { n: 0 }), 'none');
        assert.equal(format('en', pattern, { n: 1 }), '1 thing');
    });

    it('rounds a number style half to even, as ICU does', () => {
        assert.equal(format('en', '{n, number, ::.00}', { n: 0.705 }), '0.70');
        assert.equal(format('en', '{n, number, ::.00}', { n: 0.715 }), '0.72');
        assert.equal(format('en', '{n, number, ::.00}', { n: 0.725 }), '0.72');
        assert.equal(format('en', '{n, number, integer}', { n: 2.5 }), '2');
    });

    it('prints an argument with no type instead of formatting it', () => {
        assert.equal(format('en', '{n} tokens', { n: 1234.5 }), '1234.5 tokens');
    });

    it('leaves an argument nobody supplied as its own name', () => {
        assert.equal(format('en', '{missing} here'), '{missing} here');
        assert.equal(format('en', '{n, plural, one {a} other {b}} here'), '{n} here');
    });
});

describe('the shipped messages', () => {
    const patterns = Object.entries(messages)
        .filter((entry): entry is [string, string] => typeof entry[1] === 'string');

    it('has one entry per key and three word lists', () => {
        const lists = Object.entries(messages).filter(([, value]) => Array.isArray(value)).map(([key]) => key);

        assert.deepEqual(lists.sort(), ['words.catch_all_phrases', 'words.fallback_labels', 'words.grammar']);
    });

    it('every pattern parses', () => {
        const broken = patterns.filter(([, pattern]) => !parses(pattern)).map(([key]) => key);

        assert.deepEqual(broken, [], 'A pattern this cannot parse prints unformatted and loses its arguments.');
    });

    it('every pattern leaves no argument unfilled when it is given them all', () => {
        const unfilled: string[] = [];

        for (const [key, pattern] of patterns) {
            const values = Object.fromEntries(argumentsOf(pattern).map((name) => [name, 'x']));
            const filled = format('en', pattern, values);

            for (const name of argumentsOf(pattern)) {
                if (filled.includes(`{${name}}`)) {
                    unfilled.push(`${key}: {${name}}`);
                }
            }
        }

        assert.deepEqual(unfilled, []);
    });

    /**
     * A key with no pattern prints as itself, which is a run that works and
     * prints an identifier at a person.
     */
    it('holds every key the source asks for', () => {
        const asked = new Set<string>();

        for (const { contents } of sources()) {
            for (const match of contents.matchAll(/Text\.(?:of|list)\(\s*'([^']+)'/g)) {
                asked.add(match[1] ?? '');
            }
        }

        assert.ok(asked.size > 100, `Only found ${asked.size} keys, so the sweep is not reading the source.`);

        const missing = [...asked].filter((key) => !(key in messages));

        assert.deepEqual(missing, []);
    });

    /** A dynamic key is one the sweep above cannot see, so there are none. */
    it('is never asked for a key built at runtime', () => {
        const built: string[] = [];

        for (const { path, contents } of sources()) {
            for (const match of contents.matchAll(/Text\.(?:of|list)\(\s*([^'\s)][^,)]*)/g)) {
                built.push(`${path}: ${match[1] ?? ''}`);
            }
        }

        assert.deepEqual(built, []);
    });
});

describe('a locale nobody has translated', () => {
    it('prints English rather than a key', () => {
        Text.use('fr');

        assert.equal(Text.of('report.nothing_to_report'), 'Nothing to report.');

        Text.reset();
    });

    it('falls back a step at a time, region to language to English', () => {
        Text.use('fr_CA');
        assert.equal(Text.locale(), 'fr_CA');

        Text.use('FR-ca');
        assert.equal(Text.locale(), 'fr_CA');

        Text.use('fr_CA.UTF-8');
        assert.equal(Text.locale(), 'fr_CA');

        Text.use('C');
        assert.equal(Text.locale(), 'en');

        Text.reset();
    });
});
