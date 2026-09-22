import { entriesOf } from './ordered.js';

/**
 * JSON as PHP's `json_encode` writes it with no flags.
 *
 * One digest in the report is a hash over this text, and the implementations
 * have to agree on it or two runs of the same catalogue compare as different
 * catalogues. PHP escapes `/` and every character above ASCII, which
 * `JSON.stringify` leaves alone
 */
export function encodeLikePhp(value: unknown): string {
    if (value === null || value === undefined) {
        return 'null';
    }

    if (typeof value === 'boolean') {
        return value ? 'true' : 'false';
    }

    if (typeof value === 'number') {
        return Number.isFinite(value) ? String(value) : '0';
    }

    if (typeof value === 'string') {
        return quote(value);
    }

    if (Array.isArray(value)) {
        return `[${value.map(encodeLikePhp).join(',')}]`;
    }

    const entries = entriesOf(value as object)
        .filter(([, item]) => item !== undefined)
        .map(([key, item]) => `${quote(key)}:${encodeLikePhp(item)}`);

    return `{${entries.join(',')}}`;
}

const escapes: Record<string, string> = {
    '"': '\\"',
    '\\': '\\\\',
    '/': '\\/',
    '\b': '\\b',
    '\f': '\\f',
    '\n': '\\n',
    '\r': '\\r',
    '\t': '\\t',
};

function quote(text: string): string {
    let out = '"';

    for (const character of text) {
        const escaped = escapes[character];

        if (escaped !== undefined) {
            out += escaped;

            continue;
        }

        const code = character.codePointAt(0) ?? 0;

        if (code < 0x20) {
            out += `\\u${code.toString(16).padStart(4, '0')}`;

            continue;
        }

        if (code < 0x80) {
            out += character;

            continue;
        }

        // Above ASCII, PHP writes the UTF-16 code units, so a character outside
        // the basic plane comes out as its surrogate pair.
        for (let i = 0; i < character.length; i++) {
            out += `\\u${character.charCodeAt(i).toString(16).padStart(4, '0')}`;
        }
    }

    return `${out}"`;
}
