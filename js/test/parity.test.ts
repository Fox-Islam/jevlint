import { strict as assert } from 'node:assert';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';
import { format } from '../src/i18n/icu.js';
import { messages } from '../src/lang/en.js';
import { Catalogue } from '../src/catalogue/catalogue.js';
import { root } from './helpers/root.js';

/**
 * The two implementations print one report, and the harness in `local/` diffs
 * every command through both. These are the two halves a harness cannot reach:
 * the message files have to hold the same patterns, and the formatters have to
 * agree on what each one means
 */
const php = existsSync(join(root, 'php/lang/en.php')) && existsSync(join(root, 'vendor/autoload.php'))
    ? (code: string): string => execFileSync('php', ['-r', code], { cwd: root, encoding: 'utf8' })
    : null;

describe('the two implementations', { skip: php === null ? 'The PHP package is not installed here.' : false }, () => {
    it('hold the same messages under the same keys', () => {
        const theirs = JSON.parse(php?.(
            'echo json_encode(require "php/lang/en.php", JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);',
        ) ?? '{}') as Record<string, unknown>;

        assert.deepEqual(Object.keys(messages), Object.keys(theirs), 'One file has a key the other does not.');

        for (const [key, pattern] of Object.entries(messages)) {
            assert.deepEqual(pattern, theirs[key], `The two files word ${key} differently.`);
        }
    });

    /**
     * A plural chosen one way here and another way there is two tools with one
     * name. Every pattern is formatted by both, on every plural branch it has
     * and every branch of every select
     */
    it('format every pattern to the same text', () => {
        const cases: { key: string; pattern: string; values: Record<string, unknown> }[] = [];

        for (const [key, pattern] of Object.entries(messages)) {
            if (typeof pattern !== 'string') {
                continue;
            }

            for (const values of samples(pattern)) {
                cases.push({ key, pattern, values });
            }
        }

        assert.ok(cases.length > 300, `Only ${cases.length} cases, so this is not reading the file.`);

        const theirs = JSON.parse(php?.(`
            $cases = json_decode(${quote(JSON.stringify(cases))}, true);
            $out = [];
            foreach ($cases as $case) {
                $formatted = MessageFormatter::formatMessage('en', $case['pattern'], $case['values']);
                $out[] = $formatted === false ? '__WOULD_NOT_PARSE__' : $formatted;
            }
            echo json_encode($out, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
        `) ?? '[]') as string[];

        const differ: string[] = [];

        for (const [i, one] of cases.entries()) {
            const mine = format('en', one.pattern, one.values as Record<string, string | number>);

            if (mine !== theirs[i]) {
                differ.push(`${one.key} ${JSON.stringify(one.values)}\n  php ${JSON.stringify(theirs[i])}\n  js  ${JSON.stringify(mine)}`);
            }
        }

        assert.deepEqual(differ, []);
    });

    it('read the catalogue to the same two digests', () => {
        const catalogue = Catalogue.load();
        const theirs = JSON.parse(php?.(
            'require "vendor/autoload.php"; $c = Phox\\JevLint\\Catalogue\\Catalogue::load();'
            + ' echo json_encode(["fingerprint" => $c->fingerprint, "asked" => $c->asked, "jev" => $c->jev]);',
        ) ?? '{}') as Record<string, string>;

        assert.equal(catalogue.fingerprint, theirs['fingerprint']);
        assert.equal(catalogue.asked, theirs['asked'], 'A corpus keeps its readings against this digest.');
        assert.equal(catalogue.jev, theirs['jev']);
    });
});

/** One set of arguments per plural count and per branch of every select */
function samples(pattern: string): Record<string, unknown>[] {
    const names = [...new Set([...pattern.matchAll(/\{\s*([^\s{},]+)/g)].map((match) => match[1] ?? ''))];
    const kind = (name: string): string => {
        const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

        if (new RegExp(`\\{\\s*${escaped}\\s*,\\s*plural`).test(pattern)) return 'plural';
        if (new RegExp(`\\{\\s*${escaped}\\s*,\\s*select`).test(pattern)) return 'select';
        if (new RegExp(`\\{\\s*${escaped}\\s*,\\s*number`).test(pattern)) return 'number';

        return 'text';
    };

    const selects = names.filter((name) => kind(name) === 'select');
    const counts = names.some((name) => kind(name) === 'plural') ? [0, 1, 2, 5, 11] : [1];
    const branches = selects.length === 0
        ? [[] as [string, string][]]
        : product(selects.map((name) => branchesOf(pattern, name).map((branch): [string, string] => [name, branch])));

    const out: Record<string, unknown>[] = [];

    for (const count of counts) {
        for (const chosen of branches) {
            const values: Record<string, unknown> = {};

            for (const name of names) {
                values[name] = kind(name) === 'plural' ? count
                    : kind(name) === 'number' ? 1234.5678
                        : kind(name) === 'select' ? 'other' : `<${name}>`;
            }

            for (const [name, branch] of chosen) {
                values[name] = branch;
            }

            out.push(values);
        }
    }

    return out;
}

/** The keywords one select offers, read out of the pattern */
function branchesOf(pattern: string, name: string): string[] {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const at = pattern.search(new RegExp(`\\{\\s*${escaped}\\s*,\\s*select\\s*,`));

    if (at < 0) {
        return ['other'];
    }

    const keys: string[] = [];
    let depth = 0;
    let word = '';

    for (let i = pattern.indexOf(',', pattern.indexOf(',', at) + 1) + 1; i < pattern.length; i++) {
        const char = pattern[i];

        if (char === '{') {
            if (depth === 0 && word.trim() !== '') {
                keys.push(word.trim());
            }

            word = '';
            depth++;

            continue;
        }

        if (char === '}') {
            depth--;

            if (depth < 0) {
                break;
            }

            continue;
        }

        if (depth === 0) {
            word += char;
        }
    }

    return keys.length === 0 ? ['other'] : keys;
}

function product<T>(sets: T[][]): T[][] {
    return sets.reduce<T[][]>((all, set) => all.flatMap((one) => set.map((item) => [...one, item])), [[]]);
}

/** A PHP single-quoted string holding JSON */
function quote(text: string): string {
    return `'${text.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;
}
