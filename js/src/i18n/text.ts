import { existsSync, readFileSync } from 'node:fs';
import { format, type Values } from './icu.js';
import { messages } from '../lang/en.js';
import { from } from '../support/paths.js';

type Bundle = Record<string, string | string[]>;

/**
 * Every message the tool prints, in the reader's language.
 *
 * Patterns are ICU MessageFormat, so a plural is chosen by the locale's CLDR
 * rules instead of by a `=== 1` written here. English takes two forms and
 * Polish four. A locale file needs only the keys it translates, and the rest
 * are read from English, so a part-finished translation prints English
 */
export const Text = {
    FALLBACK: 'en',

    /**
     * The locale to answer in.
     *
     * A tag no file has falls back a step at a time, `fr_CA` to `fr` to
     * English, so a missing `fr_CA` reaches French before it reaches English
     */
    use(locale: string | null): void {
        current = normalise(locale) ?? Text.FALLBACK;
    },

    locale(): string {
        return current;
    },

    /**
     * Read the locale from the environment, for a run nobody told.
     *
     * `LC_ALL` outranks `LC_MESSAGES`, which outranks `LANG`, which is the order
     * POSIX gives them
     */
    fromEnvironment(): void {
        for (const name of ['JEVLINT_LANG', 'LC_ALL', 'LC_MESSAGES', 'LANG']) {
            const value = process.env[name];

            if (typeof value === 'string' && value !== '' && normalise(value) !== null) {
                Text.use(value);

                return;
            }
        }

        Text.use(null);
    },

    /**
     * One message, formatted.
     *
     * A key no locale has prints as itself, which is findable by eye; an empty
     * string is not. A pattern this cannot parse prints unformatted, so a
     * translation with a stray brace loses its arguments and not the line
     */
    of(key: string, values: Values = {}): string {
        const pattern = lookup(key);

        if (typeof pattern !== 'string') {
            return key;
        }

        try {
            return format(current, pattern, values);
        } catch {
            return pattern;
        }
    },

    /**
     * A list of words or phrases a check matches against.
     *
     * The locale's list and English are both returned. A query written in
     * French can still name its options in English, and a check given only the
     * French list would stop finding them
     */
    list(key: string): string[] {
        const mine = lookup(key);
        const english = current === Text.FALLBACK ? [] : bundle(Text.FALLBACK)[key];
        const merged = [
            ...(Array.isArray(mine) ? mine : []),
            ...(Array.isArray(english) ? english : []),
        ];

        return [...new Set(merged.filter((word): word is string => typeof word === 'string'))];
    },

    /** Forget what is loaded, so a test can change locale inside one process */
    reset(): void {
        bundles.clear();
        current = Text.FALLBACK;
    },
};

let current: string = Text.FALLBACK;

const bundles = new Map<string, Bundle>();

function lookup(key: string): string | string[] | undefined {
    for (const locale of candidates(current)) {
        const loaded = bundle(locale);

        if (Object.hasOwn(loaded, key)) {
            return loaded[key];
        }
    }

    return undefined;
}

/** The locale, then what it falls back to, then English */
function candidates(locale: string): string[] {
    const found = [locale];

    if (locale.includes('_')) {
        found.push(locale.slice(0, locale.indexOf('_')));
    }

    found.push(Text.FALLBACK);

    return [...new Set(found)];
}

function bundle(locale: string): Bundle {
    const loaded = bundles.get(locale);

    if (loaded !== undefined) {
        return loaded;
    }

    const found = read(locale);
    bundles.set(locale, found);

    return found;
}

/**
 * A locale file, from `JEVLINT_LANG_DIR` before the shipped English, so a
 * language nobody has contributed can be added without forking.
 *
 * Unlike `JEVLINT_CHECKS_DIR` this falls through to the shipped messages: a
 * directory holding only `fr.json` is a translation and not a rule set, and
 * English still has to be found behind it
 */
function read(locale: string): Bundle {
    const dir = process.env['JEVLINT_LANG_DIR'];

    if (typeof dir === 'string' && dir !== '') {
        const path = `${dir.replace(/\/+$/, '')}/${locale}.json`;

        if (existsSync(path)) {
            try {
                const parsed: unknown = JSON.parse(readFileSync(path, 'utf8'));

                if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
                    return parsed as Bundle;
                }
            } catch {
                // A locale file that will not parse is answered in English, the
                // same as one that does not exist. Failing here would take the
                // whole run down over the language it was going to print in.
            }
        }
    }

    return locale === Text.FALLBACK ? messages : {};
}

/**
 * A language tag as the files are named: `fr_CA` from `fr_CA.UTF-8`, `fr-ca` or
 * `fr_ca`. `C` and `POSIX` name no language and are read as none
 */
function normalise(locale: string | null): string | null {
    if (locale === null) {
        return null;
    }

    const tag = locale.trim().replace(/[.@].*$/, '').replace(/-/g, '_');
    const named = /^([a-zA-Z]{2,3})(?:_([a-zA-Z0-9]{2,4}))?$/.exec(tag);

    if (named === null) {
        return null;
    }

    const language = (named[1] ?? '').toLowerCase();

    if (language === 'c' || language === 'posix') {
        return null;
    }

    return named[2] === undefined ? language : `${language}_${named[2].toUpperCase()}`;
}

export { from };
