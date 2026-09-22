/**
 * The two ways this prints a number, which round differently.
 *
 * `fixed` is C's `printf("%.2f")`: it rounds half to even on the value the
 * double holds, so 0.705 prints 0.70 because the nearest double to it is below
 * the half. `grouped` is PHP's `number_format`: it rounds half away
 * from zero on the shortest decimal that names the double, so the same input
 * prints 0.71. Both appear in the report, and a reader comparing two columns
 * would otherwise be reading the difference between two rounding rules
 */

/** `printf("%.<digits>f")`: half to even, on the exact value */
export function fixed(value: number, digits: number): string {
    if (!Number.isFinite(value)) {
        return String(value);
    }

    // Negative zero prints as zero, which is what the report's other half does
    // and what a reader of a delta column expects beside a `+0.000`.
    const negative = value < 0;
    // Twenty places resolve every tie: doubles near 1 are about 1e-16 apart, so
    // a value that is not exactly a half differs from one by the 17th place.
    const exact = Math.abs(value).toFixed(20);
    const dot = exact.indexOf('.');
    const whole = exact.slice(0, dot);
    const fraction = exact.slice(dot + 1);
    const keep = fraction.slice(0, digits).padEnd(digits, '0');
    const rest = fraction.slice(digits);

    let scaled = BigInt(whole + keep);

    if (rest !== '') {
        const half = `5${'0'.repeat(rest.length - 1)}`;

        if (rest > half || (rest === half && scaled % 2n === 1n)) {
            scaled += 1n;
        }
    }

    const printed = scaled.toString().padStart(digits + 1, '0');
    const body = digits === 0
        ? printed
        : `${printed.slice(0, printed.length - digits)}.${printed.slice(printed.length - digits)}`;

    return negative ? `-${body}` : body;
}

/** The same with an explicit sign, as `printf("%+.3f")` writes one */
export function signed(value: number, digits: number): string {
    const printed = fixed(value, digits);

    return printed.startsWith('-') ? printed : `+${printed}`;
}

const formatters = new Map<number, Intl.NumberFormat>();

/**
 * `number_format`: half away from zero, grouped in threes.
 *
 * The separators are `,` and `.` whatever the reader's locale, because the
 * report's own numbers are not translated and a probability written `0,71`
 * beside a trigger written `0.71` reads as two different measurements
 */
export function grouped(value: number, digits = 0): string {
    let formatter = formatters.get(digits);

    if (formatter === undefined) {
        formatter = new Intl.NumberFormat('en-US', {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
            roundingMode: 'halfExpand',
        });
        formatters.set(digits, formatter);
    }

    // Negative zero, as above: a token count or a spread of `-0` is zero.
    return formatter.format(Object.is(value, -0) ? 0 : value);
}
