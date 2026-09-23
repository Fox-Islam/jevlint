"""
The pieces every formatter needs: ANSI escapes, column padding, and the two ways
this prints a number.

`fixed` is C's `printf("%.2f")`: it rounds half to even on the value the double
holds, so 0.705 prints 0.70 because the nearest double to it is below the half.
`grouped` is PHP's `number_format`: it rounds half away from zero on the shortest
decimal that names the double, so the same input prints 0.71. Both appear in the
report, and a reader comparing two columns would otherwise be reading the
difference between two rounding rules.
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

from .support import bytes_of


def paint(colour: bool, text: str, code: str) -> str:
    return f'\u001b[{code}m{text}\u001b[0m' if colour else text


def dim(colour: bool, text: str) -> str:
    return paint(colour, text, '2')


def pad(text: str, width: int) -> str:
    """
    Pad to a width in bytes, which is what a column of a report is measured in.

    A `·` between a target and its field is one character and two bytes, so
    padding by characters pushes every row carrying one a column to the right of
    the rows that do not.
    """
    length = bytes_of(text)

    return text if length >= width else text + ' ' * (width - length)


def pad_left(text: str, width: int) -> str:
    """The same, right-aligned."""
    length = bytes_of(text)

    return text if length >= width else ' ' * (width - length) + text


def pad_characters(text: str, width: int) -> str:
    """
    Pad to a width in characters.

    One column is measured this way: the severity label, whose width comes from
    the three translations rather than from a number written here, so a language
    whose word for `warning` carries an accent still lines up.
    """
    return text if len(text) >= width else text + ' ' * (width - len(text))


def fixed(value: float, digits: int) -> str:
    """`printf("%.<digits>f")`: half to even, on the exact value."""
    if not math.isfinite(value):
        return str(value)

    # Negative zero prints as zero, which is what the report's other half does and
    # what a reader of a delta column expects beside a `+0.000`.
    return format(value + 0.0 if value != 0 else 0.0, f'.{digits}f')


def signed(value: float, digits: int) -> str:
    """The same with an explicit sign, as `printf("%+.3f")` writes one."""
    printed = fixed(value, digits)

    return printed if printed.startswith('-') else f'+{printed}'


def grouped(value: float, digits: int = 0) -> str:
    """
    `number_format`: half away from zero, grouped in threes.

    The separators are `,` and `.` whatever the reader's locale, because the
    report's own numbers are not translated and a probability written `0,71`
    beside a trigger written `0.71` reads as two different measurements.
    """
    if not math.isfinite(value):
        return str(value)

    # Negative zero, as above: a token count or a spread of `-0` is zero.
    quantised = Decimal(repr(float(value) if value != 0 else 0.0)).quantize(
        Decimal(1).scaleb(-digits),
        rounding=ROUND_HALF_UP,
    )

    return f'{quantised:,.{digits}f}'
