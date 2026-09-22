/**
 * The subset of ICU MessageFormat the message files use.
 *
 * `Intl.PluralRules` supplies the CLDR categories, so a plural is chosen by the
 * locale's own rules and not by a `=== 1` written here. Node ships full ICU, so
 * every locale it knows has its own categories
 */

type Argument = string | number | boolean | null | undefined;

/** Named arguments a pattern reads */
export type Values = Record<string, Argument>;

type Node =
    | { kind: 'text'; text: string }
    | { kind: 'argument'; name: string; style: NumberStyle | null }
    | { kind: 'hash' }
    | { kind: 'plural'; name: string; branches: Map<string, Node[]>; exact: Map<number, Node[]> }
    | { kind: 'select'; name: string; branches: Map<string, Node[]> };

/** `integer`, or a skeleton naming how many fraction digits to print */
type NumberStyle = { kind: 'integer' } | { kind: 'fraction'; digits: number };

/** A pattern that will not parse, so the caller can print it unformatted */
export class PatternError extends Error {}

const cache = new Map<string, Node[]>();

/**
 * One pattern, with its arguments filled in.
 *
 * @throws PatternError The pattern is not MessageFormat this can read.
 */
export function format(locale: string, pattern: string, values: Values = {}): string {
    let nodes = cache.get(pattern);

    if (nodes === undefined) {
        nodes = parse(pattern);
        cache.set(pattern, nodes);
    }

    return render(nodes, locale, values, null);
}

/** Whether a pattern parses at all, for the test that holds the file to its job */
export function parses(pattern: string): boolean {
    try {
        parse(pattern);

        return true;
    } catch {
        return false;
    }
}

/**
 * Every argument name a pattern reads, so a caller can tell a missing value from
 * a pattern that never wanted one
 */
export function argumentsOf(pattern: string): string[] {
    const names = new Set<string>();
    const walk = (nodes: Node[]): void => {
        for (const node of nodes) {
            if (node.kind === 'argument' || node.kind === 'plural' || node.kind === 'select') {
                names.add(node.name);
            }

            if (node.kind === 'plural') {
                for (const branch of node.exact.values()) {
                    walk(branch);
                }
            }

            if (node.kind === 'plural' || node.kind === 'select') {
                for (const branch of node.branches.values()) {
                    walk(branch);
                }
            }
        }
    };

    walk(parse(pattern));

    return [...names];
}

class Reader {
    public at = 0;

    constructor(public readonly source: string) {}

    peek(offset = 0): string {
        return this.source[this.at + offset] ?? '';
    }

    done(): boolean {
        return this.at >= this.source.length;
    }
}

function parse(pattern: string): Node[] {
    const reader = new Reader(pattern);
    const nodes = readMessage(reader, false);

    if (!reader.done()) {
        throw new PatternError(`Unexpected "${reader.peek()}" at ${reader.at}.`);
    }

    return nodes;
}

/**
 * Text up to the end of the pattern, or to the `}` that closes the branch this
 * is inside. `#` is an argument only inside a plural branch
 */
function readMessage(reader: Reader, nested: boolean): Node[] {
    const nodes: Node[] = [];
    let text = '';

    const flush = (): void => {
        if (text !== '') {
            nodes.push({ kind: 'text', text });
            text = '';
        }
    };

    while (!reader.done()) {
        const char = reader.peek();

        if (char === '}' && nested) {
            break;
        }

        if (char === '{') {
            flush();
            nodes.push(readArgument(reader));

            continue;
        }

        if (char === '#' && nested) {
            flush();
            nodes.push({ kind: 'hash' });
            reader.at++;

            continue;
        }

        if (char === "'") {
            text += readQuoted(reader);

            continue;
        }

        text += char;
        reader.at++;
    }

    flush();

    return nodes;
}

/**
 * The ICU apostrophe rules, which are what a translator gets wrong first.
 *
 * `''` is one apostrophe. A lone `'` opens a quoted run only where it stands in
 * front of a `{`, `}`, `#` or `|`, so `the SDK's` needs no escaping. Inside an
 * open quote `''` is again one apostrophe and does not close it, which is why a
 * run of braces has to be quoted together as `'}}'` and not as `'}''}'`
 */
function readQuoted(reader: Reader): string {
    if (reader.peek(1) === "'") {
        reader.at += 2;

        return "'";
    }

    if (!'{}#|'.includes(reader.peek(1)) || reader.peek(1) === '') {
        reader.at++;

        return "'";
    }

    reader.at++;
    let text = '';

    while (!reader.done()) {
        if (reader.peek() === "'") {
            if (reader.peek(1) === "'") {
                text += "'";
                reader.at += 2;

                continue;
            }

            reader.at++;

            return text;
        }

        text += reader.peek();
        reader.at++;
    }

    // An unterminated quote runs to the end of the pattern, which is what ICU does.
    return text;
}

function readArgument(reader: Reader): Node {
    reader.at++;
    skipSpace(reader);
    const name = readName(reader);
    skipSpace(reader);

    if (reader.peek() === '}') {
        reader.at++;

        return { kind: 'argument', name, style: null };
    }

    expect(reader, ',');
    skipSpace(reader);
    const type = readName(reader);
    skipSpace(reader);

    if (type === 'plural') {
        expect(reader, ',');

        return readPlural(reader, name);
    }

    if (type === 'select') {
        expect(reader, ',');

        return readSelect(reader, name);
    }

    if (type !== 'number') {
        throw new PatternError(`"${type}" is not an argument type this reads.`);
    }

    if (reader.peek() === '}') {
        reader.at++;

        return { kind: 'argument', name, style: null };
    }

    expect(reader, ',');
    skipSpace(reader);
    const style = readStyle(reader);
    skipSpace(reader);
    expect(reader, '}');

    return { kind: 'argument', name, style };
}

/**
 * `integer`, or the fraction-digit part of a number skeleton.
 *
 * `::.00` is two places, `::.` is none. The rest of the skeleton syntax is not
 * read, because a pattern using it would format differently here from the
 * implementation it was written against
 */
function readStyle(reader: Reader): NumberStyle {
    let raw = '';

    while (!reader.done() && reader.peek() !== '}') {
        raw += reader.peek();
        reader.at++;
    }

    raw = raw.trim();

    if (raw === 'integer') {
        return { kind: 'integer' };
    }

    if (raw.startsWith('::')) {
        const skeleton = raw.slice(2).trim();
        const fraction = /^\.(0*)$/.exec(skeleton);

        if (fraction !== null) {
            return { kind: 'fraction', digits: (fraction[1] ?? '').length };
        }
    }

    throw new PatternError(`"${raw}" is not a number style this reads.`);
}

function readPlural(reader: Reader, name: string): Node {
    const branches = new Map<string, Node[]>();
    const exact = new Map<number, Node[]>();

    for (;;) {
        skipSpace(reader);

        if (reader.peek() === '}') {
            reader.at++;

            break;
        }

        if (reader.done()) {
            throw new PatternError(`The plural on "${name}" is not closed.`);
        }

        if (reader.peek() === '=') {
            reader.at++;
            const digits = readName(reader);
            skipSpace(reader);
            exact.set(Number(digits), readBranch(reader));

            continue;
        }

        const keyword = readName(reader);
        skipSpace(reader);
        branches.set(keyword, readBranch(reader));
    }

    if (!branches.has('other')) {
        throw new PatternError(`The plural on "${name}" has no "other" branch.`);
    }

    return { kind: 'plural', name, branches, exact };
}

function readSelect(reader: Reader, name: string): Node {
    const branches = new Map<string, Node[]>();

    for (;;) {
        skipSpace(reader);

        if (reader.peek() === '}') {
            reader.at++;

            break;
        }

        if (reader.done()) {
            throw new PatternError(`The select on "${name}" is not closed.`);
        }

        const keyword = readName(reader);
        skipSpace(reader);
        branches.set(keyword, readBranch(reader));
    }

    if (!branches.has('other')) {
        throw new PatternError(`The select on "${name}" has no "other" branch.`);
    }

    return { kind: 'select', name, branches };
}

function readBranch(reader: Reader): Node[] {
    expect(reader, '{');
    const nodes = readMessage(reader, true);
    expect(reader, '}');

    return nodes;
}

function readName(reader: Reader): string {
    let name = '';

    while (!reader.done() && /[^\s{},]/.test(reader.peek())) {
        name += reader.peek();
        reader.at++;
    }

    if (name === '') {
        throw new PatternError(`Expected a name at ${reader.at}.`);
    }

    return name;
}

function skipSpace(reader: Reader): void {
    while (!reader.done() && /\s/.test(reader.peek())) {
        reader.at++;
    }
}

function expect(reader: Reader, char: string): void {
    if (reader.peek() !== char) {
        throw new PatternError(`Expected "${char}" at ${reader.at}, found "${reader.peek()}".`);
    }

    reader.at++;
}

/** `$hash` is the plural argument the branch belongs to, where it is inside one */
function render(nodes: Node[], locale: string, values: Values, hash: number | null): string {
    let out = '';

    for (const node of nodes) {
        out += renderNode(node, locale, values, hash);
    }

    return out;
}

function renderNode(node: Node, locale: string, values: Values, hash: number | null): string {
    switch (node.kind) {
        case 'text':
            return node.text;

        case 'hash':
            // The plural's own value, through the locale's default number
            // format, so a count in the thousands is grouped.
            return hash === null ? '#' : number(locale, hash, null);

        case 'argument':
            return node.name in values
                ? argument(locale, values[node.name], node.style)
                : `{${node.name}}`;

        case 'plural': {
            if (!(node.name in values)) {
                return `{${node.name}}`;
            }

            const value = Number(values[node.name] ?? 0);
            const branch = node.exact.get(value)
                ?? node.branches.get(category(locale, value))
                ?? node.branches.get('other')
                ?? [];

            return render(branch, locale, values, value);
        }

        case 'select': {
            if (!(node.name in values)) {
                return `{${node.name}}`;
            }

            const value = String(values[node.name] ?? '');
            const branch = node.branches.get(value) ?? node.branches.get('other') ?? [];

            return render(branch, locale, values, hash);
        }
    }
}

function argument(locale: string, value: Argument, style: NumberStyle | null): string {
    if (value === null || value === undefined) {
        return '';
    }

    if (style !== null) {
        return number(locale, Number(value), style);
    }

    // An argument with no type is printed, not formatted: `{tokens}` arrives
    // already grouped by its caller, and putting it through a number format
    // again would group it a second time or round its fraction away.
    return typeof value === 'boolean' ? (value ? '1' : '') : String(value);
}

const formatters = new Map<string, Intl.NumberFormat>();

function number(locale: string, value: number, style: NumberStyle | null): string {
    const key = `${locale}\u0000${style === null ? 'plain' : style.kind}\u0000${style !== null && style.kind === 'fraction' ? style.digits : ''}`;
    let formatter = formatters.get(key);

    if (formatter === undefined) {
        formatter = new Intl.NumberFormat(tag(locale), options(style));
        formatters.set(key, formatter);
    }

    return formatter.format(value);
}

/**
 * `halfEven` is ICU's own default, and the two modes disagree on every exact
 * half: a 0.715 reading prints 0.72 under both, and 0.725 prints 0.72 here and
 * 0.73 under the mode JavaScript defaults to
 */
function options(style: NumberStyle | null): Intl.NumberFormatOptions {
    const rounding = { roundingMode: 'halfEven' } as const;

    if (style === null) {
        return { ...rounding, maximumFractionDigits: 3 };
    }

    if (style.kind === 'integer') {
        return { ...rounding, maximumFractionDigits: 0 };
    }

    return { ...rounding, minimumFractionDigits: style.digits, maximumFractionDigits: style.digits };
}

const rules = new Map<string, Intl.PluralRules>();

function category(locale: string, value: number): string {
    let rule = rules.get(locale);

    if (rule === undefined) {
        rule = new Intl.PluralRules(tag(locale));
        rules.set(locale, rule);
    }

    return rule.select(value);
}

/**
 * A locale as the message files name it, as a BCP 47 tag.
 *
 * The files are named `pt_BR` and `Intl` takes `pt-BR`. A tag `Intl` cannot read
 * falls back to English, because throwing here would take a report down over the
 * language it was going to be printed in
 */
function tag(locale: string): string {
    const bcp = locale.replace('_', '-');

    try {
        return Intl.getCanonicalLocales(bcp)[0] ?? 'en';
    } catch {
        return 'en';
    }
}
