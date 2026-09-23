import re
from pathlib import Path

from jevlint.icu import arguments_of, format, parses
from jevlint.lang.en import MESSAGES
from jevlint.text import Text

SOURCES = sorted((Path(__file__).resolve().parents[1] / 'src/jevlint').rglob('*.py'))


def test_reads_a_run_of_braces_quoted_together():
    assert format('en', "a '{' b '}}' c") == 'a { b }} c'
    assert format('en', "'{'answer, when'}'") == '{answer, when}'


def test_leaves_an_apostrophe_alone_in_front_of_an_ordinary_letter():
    assert format('en', "the SDK's own") == "the SDK's own"
    assert format('en', "it''s here") == "it's here"


def test_chooses_a_plural_by_the_locale_rules_and_not_by_a_count_written_here():
    pattern = '{n, plural, one {# sprawdzenie} few {# sprawdzenia} many {# sprawdzeń} other {# sprawdzenia}}'

    assert format('pl', pattern, {'n': 1}) == '1 sprawdzenie'
    assert format('pl', pattern, {'n': 3}) == '3 sprawdzenia'
    assert format('pl', pattern, {'n': 12}) == '12 sprawdzeń'


def test_prefers_an_exact_count_to_the_category_it_falls_in():
    pattern = '{n, plural, =0 {none} one {# thing} other {# things}}'

    assert format('en', pattern, {'n': 0}) == 'none'
    assert format('en', pattern, {'n': 1}) == '1 thing'


def test_rounds_a_number_style_half_to_even_as_icu_does():
    assert format('en', '{n, number, ::.00}', {'n': 0.705}) == '0.70'
    assert format('en', '{n, number, ::.00}', {'n': 0.715}) == '0.72'
    assert format('en', '{n, number, ::.00}', {'n': 0.725}) == '0.72'
    assert format('en', '{n, number, integer}', {'n': 2.5}) == '2'


def test_prints_an_argument_with_no_type_instead_of_formatting_it():
    assert format('en', '{n} tokens', {'n': 1234.5}) == '1234.5 tokens'


def test_leaves_an_argument_nobody_supplied_as_its_own_name():
    assert format('en', '{missing} here') == '{missing} here'
    assert format('en', '{n, plural, one {a} other {b}} here') == '{n} here'


PATTERNS = [(key, value) for key, value in MESSAGES.items() if isinstance(value, str)]


def test_the_shipped_messages_have_one_entry_per_key_and_three_word_lists():
    lists = sorted(key for key, value in MESSAGES.items() if isinstance(value, list))

    assert lists == ['words.catch_all_phrases', 'words.fallback_labels', 'words.grammar']


def test_every_pattern_parses():
    broken = [key for key, pattern in PATTERNS if not parses(pattern)]

    assert broken == [], 'A pattern this cannot parse prints unformatted and loses its arguments.'


def test_every_pattern_leaves_no_argument_unfilled_when_it_is_given_them_all():
    unfilled = []

    for key, pattern in PATTERNS:
        names = arguments_of(pattern)
        filled = format('en', pattern, dict.fromkeys(names, 'x'))
        unfilled += [f'{key}: {{{name}}}' for name in names if '{' + name + '}' in filled]

    assert unfilled == []


def test_the_messages_hold_every_key_the_source_asks_for():
    """
    A key with no pattern prints as itself, which is a run that works and prints
    an identifier at a person.
    """
    asked = set()

    for path in SOURCES:
        asked |= set(re.findall(
            r"Text\.(?:of|list)\(\s*'([^']+)'", path.read_text(encoding='utf-8'),
        ))

    assert len(asked) > 100, f'Only found {len(asked)} keys, so the sweep is not reading the source.'
    assert [key for key in sorted(asked) if key not in MESSAGES] == []


def test_the_messages_are_never_asked_for_a_key_built_at_runtime():
    """A dynamic key is one the sweep above cannot see, so there are none."""
    built = []

    for path in SOURCES:
        built += [
            f'{path.name}: {match}' for match in re.findall(
                r"Text\.(?:of|list)\(\s*([^'\s)][^,)]*)", path.read_text(encoding='utf-8'),
            )
        ]

    assert built == []


def test_a_locale_nobody_has_translated_prints_english_rather_than_a_key():
    Text.use('fr')

    assert Text.of('report.nothing_to_report') == 'Nothing to report.'


def test_a_locale_falls_back_a_step_at_a_time_region_to_language_to_english():
    Text.use('fr_CA')
    assert Text.locale() == 'fr_CA'

    Text.use('FR-ca')
    assert Text.locale() == 'fr_CA'

    Text.use('fr_CA.UTF-8')
    assert Text.locale() == 'fr_CA'

    Text.use('C')
    assert Text.locale() == 'en'


def test_every_key_the_messages_hold_is_one_the_source_asks_for():
    """
    A pattern nothing reads is a message a translator pays to translate and
    nobody ever sees.
    """
    asked = set()

    for path in SOURCES:
        asked |= set(re.findall(
            r"Text\.(?:of|list)\(\s*'([^']+)'", path.read_text(encoding='utf-8'),
        ))

    unread = [key for key in MESSAGES if key not in asked]

    assert unread == []
