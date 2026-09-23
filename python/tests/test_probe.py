import json
import re

import httpx2
import pytest
from conftest import ROOT

from jevlint.probe import Probe, QuestionProbe
from jevlint.query import Query
from jevlint.typesafe import Client


def replying(answers):
    """A client whose answers are read off a list, one call at a time."""
    at = [0]

    def handle(request):
        body = json.loads(request.content or b'{}')
        answer = answers[min(at[0], len(answers) - 1)]
        at[0] += 1

        return httpx2.Response(200, json={
            'model': 'jev-1.13.0',
            'answers': {name: answer(name, question['type']) for name, question in body['questions'].items()},
            'usage': {'input_tokens': 1, 'output_tokens': 1},
        })

    return Client(api_key='fake-key', transport=httpx2.MockTransport(handle))


def noul(value):
    return lambda *_: {'type': 'noul', 'noul': value}


def choice(value):
    return lambda *_: {
        'type': 'choice',
        'choice': 'yes',
        'confidence': value,
        'probabilities': {'yes': value, 'no': 1 - value},
    }


def score(value):
    return lambda *_: {
        'type': 'score', 'score': value, 'confidence': 0.8, 'legend': {}, 'probabilities': {},
    }


def yes_no():
    return Query.from_dict({
        'state': {'ticket': 'I was charged twice for order A-104.'},
        'questions': {
            'refund': {
                'type': 'noul',
                'instructions': 'Does the customer ask for a refund?',
                'criteria': {'true': 'They ask for money back.', 'false': 'They report a problem only.'},
            },
        },
    }, 'test')


def test_a_question_the_query_did_not_decide_is_named_when_the_answer_sits_near_the_middle():
    probes = Probe(replying([*[noul(0.58)] * 6, choice(0.58)])).run(yes_no(), 5)
    probe = probes['refund']

    assert probe.undecided() is True
    assert probe.flips() is False, 'Every repeat answered the same side of the middle.'


def test_a_decided_question_is_left_alone():
    probes = Probe(replying([*[noul(0.9)] * 6, choice(0.9)])).run(yes_no(), 5)

    assert probes['refund'].undecided() is False


def test_repeats_that_fall_on_both_sides_of_the_middle_are_flagged():
    probes = Probe(replying([
        noul(0.48), noul(0.55), noul(0.47), noul(0.52), noul(0.49), noul(0.5), choice(0.5),
    ])).run(yes_no(), 5)
    probe = probes['refund']

    assert probe.undecided() is True
    assert probe.flips() is True


def test_undecided_is_only_asked_of_a_yes_no_question():
    """
    A Choice reports its winning label's own probability and a Score a position on
    its scale, so neither is undecided for sitting halfway.
    """
    probes = Probe(replying([score(1.0)])).run(Query.from_dict({
        'state': {'ticket': 'x'},
        'questions': {
            'urgency': {
                'type': 'score',
                'instructions': 'How urgent is this ticket?',
                'criteria': ['Not urgent at all', 'Somewhat urgent', 'Blocking work right now'],
            },
        },
    }, 'test'), 3)
    probe = probes['urgency']

    assert probe.baseline() == 0.5
    assert probe.undecided() is False, 'Halfway up a rubric is an answer, not an undecided one.'
    assert probe.flips() is False


# The README wraps, so a sentence is matched without its line breaks.
README = re.sub(r'\s+', ' ', (ROOT / 'README.md').read_text(encoding='utf-8'))

FIGURES = [
    ('the band a yes/no answer is undecided inside', QuestionProbe.UNDECIDED, 2, 'within %s of the middle'),
    ('the movement too small to cross a threshold', QuestionProbe.NEGLIGIBLE, 2, 'three times that spread and %s'),
    ('the floor used where a run cannot measure its own', Probe.PUBLISHED_NOISE, 4, 'or %s where'),
]


@pytest.mark.parametrize(('name', 'value', 'places', 'sentence'), FIGURES, ids=[row[0] for row in FIGURES])
def test_the_readme_prints_the_figure_the_code_uses(name, value, places, sentence):
    """
    The README states the probe's thresholds as figures a reader takes on trust. A
    constant moved without the page moving leaves the page describing a run nobody
    can get.

    Each figure is matched inside the sentence that explains it, because the
    README holds enough numbers that a bare search finds one somewhere whatever
    the constant is set to.
    """
    printed = format(value, f'.{places}f').rstrip('0').rstrip('.')

    assert sentence.replace('%s', printed) in README, (
        'The README explains this threshold with a figure the code does not use.'
    )
