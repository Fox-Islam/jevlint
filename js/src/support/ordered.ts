/**
 * JSON objects that keep the order their keys were written in.
 *
 * A JavaScript object lists a key that looks like an array index before every
 * other key, and lists those in ascending numeric order however they were
 * written. A Choice keyed `{"30": ..., "7": ...}` therefore reaches the API the
 * other way round, `probe`'s `options-reversed` reverses a Choice into the same
 * order it started in, and a rubric written as a numeric map is silently
 * re-sorted. Option order changes answers, which is the reason the probe
 * measures it.
 *
 * So the values this reads come from a parser that records each object's keys
 * as the file wrote them, on a property that is not enumerable and so never
 * reaches output. Everything that cares about order goes through `entriesOf`;
 * everything else reads the object as it always did
 */

const ORDER = Symbol('jevlint.keyOrder');

interface Ordered {
    [ORDER]?: string[];
}

/** The keys of an object, in the order the file wrote them */
export function keysOf(value: object): string[] {
    const recorded = (value as Ordered)[ORDER];

    if (recorded === undefined) {
        return Object.keys(value);
    }

    // Keys added or removed since the parse - a patch value built from a spread
    // - are answered from the object itself, with the recorded ones first.
    const own = new Set(Object.keys(value));
    const kept = recorded.filter((key) => own.has(key));

    if (kept.length === own.size) {
        return kept;
    }

    return [...kept, ...[...own].filter((key) => !kept.includes(key))];
}

/** The entries of an object, in the order the file wrote them */
export function entriesOf(value: object): [string, unknown][] {
    return keysOf(value).map((key) => [key, (value as Record<string, unknown>)[key]]);
}

/** An object that will list these keys in this order, whatever they look like */
export function ordered(entries: Iterable<readonly [string, unknown]>): Record<string, unknown> {
    const pairs = [...entries];
    const object: Record<string, unknown> = {};

    for (const [key, value] of pairs) {
        object[key] = value;
    }

    return remember(object, pairs.map(([key]) => key));
}

function remember<T extends object>(value: T, keys: string[]): T {
    Object.defineProperty(value, ORDER, { value: keys, enumerable: false, writable: true });

    return value;
}

/**
 * `JSON.stringify`, reading each object in the order its keys were written.
 *
 * `JSON.stringify` walks `Object.keys`, so it would undo the whole point of the
 * parser above on the way out
 */
export function stringify(value: unknown, indent = 0): string {
    return write(value, indent, '');
}

function write(value: unknown, indent: number, prefix: string): string {
    if (value === null || value === undefined) {
        return 'null';
    }

    if (typeof value === 'boolean') {
        return value ? 'true' : 'false';
    }

    if (typeof value === 'number') {
        return Number.isFinite(value) ? String(value) : 'null';
    }

    if (typeof value === 'string') {
        return JSON.stringify(value);
    }

    if (typeof value === 'function' || typeof value === 'symbol') {
        return 'null';
    }

    const inner = prefix + ' '.repeat(indent);
    const open = indent === 0 ? '' : `\n${inner}`;
    const close = indent === 0 ? '' : `\n${prefix}`;
    const between = indent === 0 ? ',' : `,\n${inner}`;
    const colon = indent === 0 ? ':' : ': ';

    if (Array.isArray(value)) {
        if (value.length === 0) {
            return '[]';
        }

        return `[${open}${value.map((item) => write(item, indent, inner)).join(between)}${close}]`;
    }

    const entries = entriesOf(value as object)
        .filter(([, item]) => item !== undefined && typeof item !== 'function' && typeof item !== 'symbol');

    if (entries.length === 0) {
        return '{}';
    }

    const written = entries.map(([key, item]) => `${JSON.stringify(key)}${colon}${write(item, indent, inner)}`);

    return `{${open}${written.join(between)}${close}}`;
}

/** A parse error, carrying the message the platform parser gives for the same text */
export class ParseError extends Error {}

/**
 * JSON, with every object's key order recorded.
 *
 * The text is handed to `JSON.parse` first, so a file that will not parse is
 * refused with the message a reader of this platform expects, and the reader
 * below then runs over text already known to be valid
 */
export function parse(text: string): unknown {
    JSON.parse(text);

    const reader = new Reader(text);
    reader.space();
    const value = reader.value();
    reader.space();

    return value;
}

class Reader {
    private at = 0;

    constructor(private readonly text: string) {}

    value(): unknown {
        const char = this.text[this.at];

        switch (char) {
            case '{':
                return this.object();
            case '[':
                return this.array();
            case '"':
                return this.string();
            case 't':
                this.at += 4;

                return true;
            case 'f':
                this.at += 5;

                return false;
            case 'n':
                this.at += 4;

                return null;
            default:
                return this.number();
        }
    }

    private object(): Record<string, unknown> {
        this.at++;
        const object: Record<string, unknown> = {};
        const keys: string[] = [];
        this.space();

        if (this.text[this.at] === '}') {
            this.at++;

            return remember(object, keys);
        }

        for (;;) {
            this.space();
            const key = this.string();
            this.space();
            this.at++; // the colon
            this.space();
            object[key] = this.value();
            keys.push(key);
            this.space();

            if (this.text[this.at] === ',') {
                this.at++;

                continue;
            }

            this.at++; // the closing brace

            return remember(object, keys);
        }
    }

    private array(): unknown[] {
        this.at++;
        const items: unknown[] = [];
        this.space();

        if (this.text[this.at] === ']') {
            this.at++;

            return items;
        }

        for (;;) {
            this.space();
            items.push(this.value());
            this.space();

            if (this.text[this.at] === ',') {
                this.at++;

                continue;
            }

            this.at++; // the closing bracket

            return items;
        }
    }

    private string(): string {
        const start = this.at;
        this.at++;

        while (this.at < this.text.length) {
            const char = this.text[this.at];

            if (char === '\\') {
                this.at += 2;

                continue;
            }

            this.at++;

            if (char === '"') {
                // Escapes and surrogate pairs are the platform parser's job, and
                // it has already accepted this text.
                return JSON.parse(this.text.slice(start, this.at)) as string;
            }
        }

        throw new ParseError('Unterminated string.');
    }

    private number(): number {
        const start = this.at;

        while (this.at < this.text.length && /[-+0-9.eE]/.test(this.text[this.at] ?? '')) {
            this.at++;
        }

        return Number(this.text.slice(start, this.at));
    }

    space(): void {
        while (this.at < this.text.length && /[\s]/.test(this.text[this.at] ?? '')) {
            this.at++;
        }
    }
}
