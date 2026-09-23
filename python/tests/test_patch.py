import json

import pytest

from jevlint.catalogue import Catalogue
from jevlint.linter import Linter
from jevlint.query import Query
from jevlint.report import Patch
from jevlint.support import Json

catalogue = Catalogue.load()


def test_is_destructive_whenever_it_takes_a_node_out_whatever_the_caller_passed():
    assert Patch('remove', '/questions/a', None, Patch.LOSSLESS).safety == Patch.DESTRUCTIVE


def test_writes_no_value_for_a_remove_because_there_is_nothing_to_write():
    assert Patch('remove', '/questions/a').to_dict() == {
        'op': 'remove', 'path': '/questions/a', 'safety': 'destructive',
    }


def test_leaves_a_questions_block_an_object_when_the_keys_left_run_0_1_2():
    query = json.loads('{"questions":{"0":{"type":"noul"},"1":{"type":"noul"},"2":{"type":"noul"}}}')

    assert Json.inline(Patch('remove', '/questions/2').apply_to(query)) == (
        '{"questions":{"0":{"type":"noul"},"1":{"type":"noul"}}}'
    )


def test_resolves_an_escaped_pointer_back_to_the_key_somebody_wrote():
    query = json.loads('{"questions":{"a/b":{"type":"noul"},"c~d":{"type":"noul"}}}')

    assert Json.inline(Patch('remove', '/questions/a~1b').apply_to(query)) == (
        '{"questions":{"c~d":{"type":"noul"}}}'
    )
    assert Json.inline(Patch('remove', '/questions/c~0d').apply_to(query)) == (
        '{"questions":{"a/b":{"type":"noul"}}}'
    )


def test_leaves_a_query_alone_where_there_is_nothing_at_the_path_to_remove():
    query = json.loads('{"questions":{"a":{"type":"noul"}}}')

    assert Json.inline(Patch('remove', '/questions/b/c').apply_to(query)) == Json.inline(query)


CASES = [
    ('question/type-not-lowercase',
     '{"state":"x","questions":{"a":{"type":"NOUL","instructions":"Does the customer want money back?"}}}'),
    ('noul/criteria-shape',
     '{"state":"x","questions":{"a":{"type":"noul","instructions":"Does the customer want money back?",'
     '"criteria":{"yes":"Y","no":"N"}}}}'),
    ('choice/criteria-shape',
     '{"state":"x","questions":{"a":{"type":"choice","instructions":"Which team should take this?",'
     '"criteria":["billing","shipping","other"]}}}'),
    ('choice/no-fallback',
     '{"state":"x","questions":{"a":{"type":"choice","instructions":"Which team should take this?",'
     '"criteria":{"billing":"Money things","shipping":"Delivery"}}}}'),
    ('score/criteria-shape',
     '{"state":"x","questions":{"a":{"type":"score","instructions":"How ready are they?",'
     '"criteria":{"2":"Ready","0":"Not ready","1":"Nearly"}}}}'),
    ('query/unknown-key',
     '{"state":"x","extra":1,"questions":{"a":{"type":"noul","instructions":"Does the customer want money back?"}}}'),
]


@pytest.mark.parametrize(('check_id', 'json_text'), CASES, ids=[case[0] for case in CASES])
def test_every_patch_the_rules_offer_clears_the_finding_behind_it(check_id, json_text):
    before = Linter.rules_only(catalogue).check(Query.from_json(json_text, 'test'))
    finding = next((found for found in before.findings() if found.check_id == check_id), None)

    assert finding is not None, f'{check_id} did not fire on its own example.'
    assert finding.patch is not None, f'{check_id} offered no patch.'

    patched = finding.patch.apply_to(json.loads(json_text))
    after = Linter.rules_only(catalogue).check(Query.from_json(Json.inline(patched), 'test'))

    assert not any(found.check_id == check_id for found in after.findings()), (
        f'{check_id} still fires after its own patch was applied.'
    )


SHAPES = [
    ('a score level with no text',
     '{"type":"score","instructions":"How urgent is it?","criteria":{"0":"","1":"Inconvenient","2":"Blocked"}}',
     False),
    ('score levels that are numbers',
     '{"type":"score","instructions":"How urgent is it?","criteria":{"0":10,"1":20}}', False),
    ('a score map of one',
     '{"type":"score","instructions":"How urgent is it?","criteria":{"0":"Only one"}}', False),
    ('score levels that are all text',
     '{"type":"score","instructions":"How urgent is it?","criteria":{"0":"Fine","1":"Bad"}}', True),
    ('choice options that are numbers',
     '{"type":"choice","instructions":"Which team takes it?","criteria":["0","1","2"]}', False),
    ('a choice list holding a nested option',
     '{"type":"choice","instructions":"Which team takes it?","criteria":["billing",{"technical":"broken"}]}', False),
    ('a choice list of labels',
     '{"type":"choice","instructions":"Which team takes it?","criteria":["billing","technical","other"]}', True),
    ('noul keys that differ only in case',
     '{"type":"noul","instructions":"Refund asked for?",'
     '"criteria":{"yes":"Money back","YES":"Chargeback","no":"No"}}', False),
    ('noul keys written as yes and no',
     '{"type":"noul","instructions":"Refund asked for?","criteria":{"yes":"Money back","no":"No"}}', True),
]


@pytest.mark.parametrize(('name', 'question', 'offered'), SHAPES, ids=[shape[0] for shape in SHAPES])
def test_a_shape_patch_is_offered_only_where_nothing_the_caller_wrote_goes_missing(name, question, offered):
    json_text = '{"state":{"t":"x"},"questions":{"q":' + question + '}}'
    report = Linter.rules_only(catalogue).check(Query.from_json(json_text, 'test'))
    shape = next(
        (found for found in report.findings() if found.check_id.endswith('/criteria-shape')), None,
    )

    assert shape is not None, 'No shape finding was raised, so this case tests nothing.'
    assert (shape.patch is not None) == offered

    # What a lossless patch has to keep is the text somebody wrote. The keys are
    # what it renames, which is the whole change.
    if shape.patch is not None and shape.patch.safety == Patch.LOSSLESS:
        after = Json.inline(shape.patch.apply_to(json.loads(json_text)))

        for word in _descriptions(json.loads(question)):
            assert word in after, f'A lossless patch dropped "{word}".'


def test_a_check_that_removes_a_question_is_in_the_catalogue():
    assert any(check.removes == 'question' for check in catalogue.written()), (
        'No check removes a question, so this pins nothing.'
    )


def _descriptions(value):
    """Every string a caller wrote as content, which is every value and no key."""
    if isinstance(value, str):
        return [value]

    if isinstance(value, list):
        return [word for item in value for word in _descriptions(item)]

    if isinstance(value, dict):
        return [word for item in value.values() for word in _descriptions(item)]

    return []
