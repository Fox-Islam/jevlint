/**
 * ANSI escapes for a formatter, or plain text where the caller asked for none.
 *
 * Every formatter needs both and none of them needs anything else from the
 * others, so this is a pair of functions and not a base class
 */
export function paint(colour: boolean, text: string, code: string): string {
    return colour ? `\u001b[${code}m${text}\u001b[0m` : text;
}

export function dim(colour: boolean, text: string): string {
    return paint(colour, text, '2');
}

/**
 * Pad to a width in bytes, which is what a column of a report is measured in.
 *
 * A `·` between a target and its field is one character and two bytes, so
 * padding by characters pushes every row carrying one a column to the right of
 * the rows that do not
 */
export function pad(text: string, width: number): string {
    const length = Buffer.byteLength(text, 'utf8');

    return length >= width ? text : text + ' '.repeat(width - length);
}

/** The same, right-aligned */
export function padLeft(text: string, width: number): string {
    const length = Buffer.byteLength(text, 'utf8');

    return length >= width ? text : ' '.repeat(width - length) + text;
}

/**
 * Pad to a width in characters.
 *
 * One column is measured this way: the severity label, whose width comes from
 * the three translations rather than from a number written here, so a language
 * whose word for `warning` carries an accent still lines up
 */
export function padCharacters(text: string, width: number): string {
    const length = [...text].length;

    return length >= width ? text : text + ' '.repeat(width - length);
}
