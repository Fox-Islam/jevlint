import { existsSync } from 'node:fs';
import { Json } from '../support/json.js';
import { Text } from './text.js';
import { from } from '../support/paths.js';

/**
 * What a check reports about your query, in the reader's language.
 *
 * These live beside the catalogue and not in `lang/`, because the catalogue is
 * not JavaScript: an implementation in another language reads the same file. A
 * locale with no file, or a check with no entry in it, is answered from the
 * catalogue
 *
 * The question a model check puts to Jev is never read from here. Translating
 * it would change what the check measures, and every number in docs/evidence.md
 * was taken with the wording in the catalogue
 */
export const CheckText = {
    /** What a translation may replace. `question`, `trigger` and `docs` are not words about a query */
    FIELDS: ['title', 'message', 'hint', 'suggest'] as const,

    /**
     * The fields a translation replaces for one check, in the order Text reads
     * its locales, so a region file wins over its language
     */
    for(id: string): Partial<Record<string, string>> {
        const found: Record<string, string> = {};

        for (const locale of locales()) {
            const fields = bundle(locale)[id] ?? {};

            for (const [field, text] of Object.entries(fields)) {
                if (!(field in found) && (CheckText.FIELDS as readonly string[]).includes(field)) {
                    found[field] = text;
                }
            }
        }

        return found;
    },

    reset(): void {
        loaded.clear();
    },
};

type Overlay = Record<string, Record<string, string>>;

const loaded = new Map<string, Overlay>();

function locales(): string[] {
    const locale = Text.locale();

    if (locale === Text.FALLBACK) {
        return [];
    }

    return locale.includes('_')
        ? [locale, locale.slice(0, locale.indexOf('_'))]
        : [locale];
}

function bundle(locale: string): Overlay {
    const already = loaded.get(locale);

    if (already !== undefined) {
        return already;
    }

    const path = locate(locale);
    const overlay: Overlay = {};

    if (path !== null) {
        for (const [id, fields] of Object.entries(Json.readFile(path))) {
            if (typeof fields === 'object' && fields !== null && !Array.isArray(fields)) {
                const strings: Record<string, string> = {};

                for (const [field, text] of Object.entries(fields as Record<string, unknown>)) {
                    if (typeof text === 'string') {
                        strings[field] = text;
                    }
                }

                overlay[id] = strings;
            }
        }
    }

    loaded.set(locale, overlay);

    return overlay;
}

function locate(locale: string): string | null {
    const dir = process.env['JEVLINT_CHECKS_DIR'];
    const candidates: string[] = [];

    if (typeof dir === 'string' && dir !== '') {
        candidates.push(`${dir.replace(/\/+$/, '')}/lang/${locale}.json`);
    }

    candidates.push(from(import.meta.url, '../../../../checks/lang', `${locale}.json`));
    candidates.push(from(import.meta.url, '../../../checks/lang', `${locale}.json`));

    return candidates.find(existsSync) ?? null;
}
