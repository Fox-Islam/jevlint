"""
The report prints numbers two ways, and the two round differently. A reader
comparing a probability with its trigger would otherwise be reading the
difference between two rounding rules.
"""
from jevlint.formatting import fixed, grouped, signed


def test_rounds_a_printed_probability_half_to_even_on_the_value_the_double_holds():
    assert fixed(0.705, 2) == '0.70'
    assert fixed(0.715, 2) == '0.71'
    assert fixed(2.5, 0) == '2'
    assert fixed(3.5, 0) == '4'
    assert fixed(0.25, 1) == '0.2'
    assert fixed(1.005, 2) == '1.00'


def test_rounds_a_grouped_number_half_away_from_zero_on_the_shortest_decimal():
    assert grouped(0.705, 2) == '0.71'
    assert grouped(0.715, 2) == '0.72'
    assert grouped(0.725, 2) == '0.73'
    assert grouped(2.5, 0) == '3'
    assert grouped(1234567) == '1,234,567'


def test_prints_a_sign_on_a_delta_and_no_sign_on_a_negative_zero():
    assert signed(0.0015, 3) == '+0.002'
    assert signed(-0.0005, 3) == '-0.001'
    assert signed(-0.0, 3) == '+0.000'
    assert grouped(-0.0, 2) == '0.00'
