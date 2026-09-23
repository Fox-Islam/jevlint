"""
Jev answers in whatever language the query is written in, so a query in French is
a query this has to check. The messages are one half of that; the word lists a
check matches against are the other, and only the second can turn a clean query
into a finding.
"""
import json
import shutil

import pytest

from jevlint.catalogue import Catalogue
from jevlint.linter import Linter
from jevlint.query import Query
from jevlint.text import CheckText, Text


@pytest.fixture
def french(tmp_path, monkeypatch):
    (tmp_path / 'fr.json').write_text(json.dumps({
        'file.unreadable': 'Impossible de lire {path}.',
        'words.fallback_labels': ['autre', 'autres', 'aucun'],
    }), encoding='utf-8')

    (tmp_path / 'checks/lang').mkdir(parents=True)
    shutil.copy(Catalogue.locate('catalogue.json'), tmp_path / 'checks/catalogue.json')
    shutil.copy(Catalogue.locate('fixtures.json'), tmp_path / 'checks/fixtures.json')
    (tmp_path / 'checks/lang/fr.json').write_text(json.dumps({
        'choice/no-fallback': {
            'title': "Le Choice n'a pas d'option de repli",
            'question': {'instructions': 'traduit'},
        },
    }), encoding='utf-8')

    monkeypatch.setenv('JEVLINT_LANG_DIR', str(tmp_path))
    Text.reset()
    CheckText.reset()

    return tmp_path


def fallback_findings(catch_all):
    report = Linter.rules_only().only(['choice/no-fallback']).check(Query.from_dict({
        'state': {'demande': "J'ai été facturé deux fois."},
        'questions': {
            'service': {
                'type': 'choice',
                'instructions': 'Quel service doit traiter cette demande ?',
                'criteria': {
                    'facturation': 'Les factures',
                    'expedition': 'La livraison',
                    catch_all: 'Le reste',
                },
            },
        },
    }, 'test'))

    return [finding.check_id for finding in report.findings()]


def test_answers_in_the_locale_where_the_locale_has_the_message(french):
    Text.use('fr')

    assert Text.of('file.unreadable', {'path': 'q.json'}) == 'Impossible de lire q.json.'


def test_prints_english_where_the_locale_leaves_a_message_out(french):
    """A part-finished translation prints English, never a key."""
    Text.use('fr')

    assert Text.of('report.nothing_to_report') == 'Nothing to report.'


def test_reaches_the_language_before_it_reaches_english(french):
    Text.use('fr_CA')

    assert Text.of('file.unreadable', {'path': 'q.json'}) == 'Impossible de lire q.json.'


def test_clears_the_check_that_looks_for_a_catch_all_once_the_list_is_translated(french):
    """
    The check reads option labels, and `autre` is a catch-all to every French
    reader and to nothing in an English list.
    """
    Text.use('en')
    assert fallback_findings('autre') == ['choice/no-fallback']

    Text.use('fr')
    assert fallback_findings('autre') == []


def test_reads_the_english_list_beside_the_locale_one(french):
    """An English label in a query written in French is still a catch-all."""
    Text.use('fr')

    assert fallback_findings('other') == []


def test_says_its_piece_in_the_locale_from_the_file_beside_the_catalogue(french, monkeypatch):
    Text.use('fr')
    monkeypatch.setenv('JEVLINT_CHECKS_DIR', str(french / 'checks'))
    CheckText.reset()

    check = Catalogue.load(str(french / 'checks/catalogue.json')).find('choice/no-fallback')

    assert check.title == "Le Choice n'a pas d'option de repli"


def test_cannot_translate_what_a_check_asks_jev(french, monkeypatch):
    """
    The question a check puts to Jev is what the check measures, and every figure
    in docs/evidence.md was taken with the wording in the catalogue. A translation
    cannot reach it.
    """
    Text.use('fr')
    monkeypatch.setenv('JEVLINT_CHECKS_DIR', str(french / 'checks'))
    CheckText.reset()

    assert list(CheckText.for_check('choice/no-fallback')) == ['title']
