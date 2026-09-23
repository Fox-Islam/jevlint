"""
The three implementations print one report, and a harness diffs every command
through each. These are the halves a harness cannot reach: the message files have
to hold the same patterns, the formatters have to agree on what each one means,
and the catalogue has to read to the same two digests.
"""
import json
import re
import shutil
import subprocess
import sys
from itertools import product

import pytest
from conftest import ROOT

from jevlint.catalogue import Catalogue
from jevlint.icu import format
from jevlint.lang.en import MESSAGES
from jevlint.support import Json

php = shutil.which('php') is not None and (ROOT / 'vendor/autoload.php').is_file()

pytestmark = pytest.mark.skipif(not php, reason='The PHP package is not installed here.')


def run_php(code):
    return subprocess.run(
        ['php', '-r', code], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout


def test_the_two_implementations_hold_the_same_messages_under_the_same_keys():
    theirs = json.loads(run_php(
        'echo json_encode(require "php/lang/en.php", JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);',
    ))

    assert list(MESSAGES) == list(theirs), 'One file has a key the other does not.'

    for key, pattern in MESSAGES.items():
        assert pattern == theirs[key], f'The two files word {key} differently.'


def test_the_two_implementations_format_every_pattern_to_the_same_text():
    """
    A plural chosen one way here and another way there is two tools with one name.
    Every pattern is formatted by both, on every plural branch it has and every
    branch of every select.
    """
    cases = [
        {'key': key, 'pattern': pattern, 'values': values}
        for key, pattern in MESSAGES.items() if isinstance(pattern, str)
        for values in samples(pattern)
    ]

    assert len(cases) > 300, f'Only {len(cases)} cases, so this is not reading the file.'

    theirs = json.loads(run_php(
        '$cases = json_decode(' + _quote(json.dumps(cases)) + ", true);"
        '$out = [];'
        'foreach ($cases as $case) {'
        "    $formatted = MessageFormatter::formatMessage('en', $case['pattern'], $case['values']);"
        "    $out[] = $formatted === false ? '__WOULD_NOT_PARSE__' : $formatted;"
        '}'
        'echo json_encode($out, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);',
    ))

    differ = [
        f'{case["key"]} {json.dumps(case["values"])}\n  php {theirs[index]!r}\n  py  {mine!r}'
        for index, case in enumerate(cases)
        if (mine := format('en', case['pattern'], case['values'])) != theirs[index]
    ]

    assert differ == []


def test_the_two_implementations_read_the_catalogue_to_the_same_two_digests():
    catalogue = Catalogue.load()
    theirs = json.loads(run_php(
        'require "vendor/autoload.php"; $c = Phox\\JevLint\\Catalogue\\Catalogue::load();'
        ' echo json_encode(["fingerprint" => $c->fingerprint, "asked" => $c->asked, "jev" => $c->jev]);',
    ))

    assert catalogue.fingerprint == theirs['fingerprint']
    assert catalogue.asked == theirs['asked'], 'A corpus keeps its readings against this digest.'
    assert catalogue.jev == theirs['jev']


def _quote(text):
    """A PHP single-quoted string holding JSON."""
    return "'" + text.replace('\\', '\\\\').replace("'", "\\'") + "'"


def samples(pattern):
    """One set of arguments per plural count and per branch of every select."""
    names = list(dict.fromkeys(re.findall(r'\{\s*([^\s{},]+)', pattern)))

    def kind(name):
        escaped = re.escape(name)

        for word in ('plural', 'select', 'number'):
            if re.search(r'\{\s*' + escaped + r'\s*,\s*' + word, pattern):
                return word

        return 'text'

    selects = [name for name in names if kind(name) == 'select']
    counts = [0, 1, 2, 5, 11] if any(kind(name) == 'plural' for name in names) else [1]
    branches = [()] if len(selects) == 0 else list(product(*(
        [(name, branch) for branch in branches_of(pattern, name)] for name in selects
    )))

    out = []

    for count in counts:
        for chosen in branches:
            values = {
                name: count if kind(name) == 'plural'
                else 1234.5678 if kind(name) == 'number'
                else 'other' if kind(name) == 'select'
                else f'<{name}>'
                for name in names
            }
            values.update(dict(chosen))
            out.append(values)

    return out


def branches_of(pattern, name):
    """The keywords one select offers, read out of the pattern."""
    at = re.search(r'\{\s*' + re.escape(name) + r'\s*,\s*select\s*,', pattern)

    if at is None:
        return ['other']

    keys = []
    depth = 0
    word = ''

    for char in pattern[at.end():]:
        if char == '{':
            if depth == 0 and word.strip() != '':
                keys.append(word.strip())

            word = ''
            depth += 1

            continue

        if char == '}':
            depth -= 1

            if depth < 0:
                break

            continue

        if depth == 0:
            word += char

    return keys or ['other']


@pytest.mark.parametrize('example', ['examples/broken-triage.json', 'examples/support-triage.json'])
def test_the_two_implementations_write_one_report(example):
    """
    The whole document, not a field of it: the rounding, the key order, the notes
    and the counts are all things two implementations can disagree about quietly.
    """
    command = ['check', example, '--static-only', '--format=json']
    theirs = subprocess.run(
        ['php', 'php/bin/jevlint', *command], cwd=ROOT, capture_output=True, text=True,
    )
    mine = subprocess.run(
        [sys.executable, '-m', 'jevlint', *command], cwd=ROOT, capture_output=True, text=True,
    )

    assert mine.stdout == theirs.stdout
    assert mine.returncode == theirs.returncode


def test_the_two_implementations_write_the_same_json_for_the_same_value():
    """
    A whole float writes as `1` in PHP and in JavaScript, and Python's own encoder
    writes `1.0`. A probability that lands on the end of its range is then two
    documents.
    """
    value = {
        'whole': 1.0,
        'zero': 0.0,
        'fraction': 0.075,
        'negative': -0.5,
        'counts': [0, 1, 20000],
        'text': 'a "quoted" path/here\nwith é and 日本語',
        'empty_list': [],
        'nested': {'a': [{'b': None}, True, False]},
    }

    theirs = run_php(
        'echo json_encode(json_decode(' + _quote(json.dumps(value))
        + ', true), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);',
    )

    assert Json.encode(value) == theirs
