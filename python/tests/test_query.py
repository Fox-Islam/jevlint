import pytest

from jevlint.errors import JevLintError
from jevlint.query import Query


def kind_of(json_text):
    with pytest.raises(JevLintError) as raised:
        Query.from_json(json_text)

    return raised.value.kind


def test_refuses_a_json_list_which_decodes_to_something_the_checks_could_walk():
    assert kind_of('[{"state":"x"}]') == 'query'


def test_refuses_questions_written_as_a_list_which_the_api_rejects():
    assert kind_of('{"state":"x","questions":[{"type":"noul"}]}') == 'query'


def test_takes_questions_keyed_by_numbers_which_the_api_accepts():
    query = Query.from_json('{"state":"x","questions":{"0":{"type":"noul","instructions":"Is it?"}}}')

    assert [question.id for question in query.questions] == ['0']


def test_refuses_a_state_that_is_a_number_which_is_a_different_defect_from_having_none():
    assert kind_of('{"state":42,"questions":{}}') == 'query'


def test_reads_an_empty_object_as_no_state():
    assert Query.from_json('{"state":{},"questions":{}}').has_state() is False
    assert Query.from_json('{"state":"","questions":{}}').has_state() is False
    assert Query.from_json('{"state":[],"questions":{}}').has_state() is False
    assert Query.from_json('{"state":{"a":1},"questions":{}}').has_state() is True


def test_counts_a_state_in_characters_not_in_the_bytes_it_takes_on_the_wire():
    assert Query.from_dict({'state': 'héllo'}).state_size() == 5


def test_follows_nesting_to_two_levels_however_wide_each_one_is():
    query = Query.from_dict({'state': {'a': {'b': 1, 'c': 2}, 'd': 3, 'e': {'f': {'g': 4}}}})

    assert query.state_leaves() == ['a.b', 'a.c', 'd', 'e.f']


def test_escapes_a_dot_inside_a_key_so_it_is_not_read_as_nesting():
    query = Query.from_dict({'state': {'a.b': 1}})

    assert query.state_leaves() == ['a\\.b']
    assert query.state_at('a\\.b') == 1
    assert Query.segments('a\\.b') == ['a.b']
    assert Query.segments('a.b') == ['a', 'b']


def test_narrows_to_some_of_its_questions_and_keeps_the_rest_of_itself():
    query = Query.from_dict({
        'state': 'x',
        'questions': {
            'a': {'type': 'noul', 'instructions': 'One?'},
            'b': {'type': 'noul', 'instructions': 'Two?'},
        },
    })

    assert [question.id for question in query.only(['b']).questions] == ['b']
    assert [question.id for question in query.only([]).questions] == ['a', 'b']


def a_question(json_text):
    return Query.from_json('{"state":"x","questions":{"q":' + json_text + '}}').questions[0]


def test_lower_cases_the_type_it_was_given():
    assert a_question('{"type":"NOUL"}').type == 'noul'


def test_knows_criteria_written_as_a_list_from_criteria_written_as_a_map():
    assert a_question('{"type":"choice","criteria":["a","b"]}').criteria_is_list() is True
    assert a_question('{"type":"choice","criteria":{"0":"a","1":"b"}}').criteria_is_list() is False


def test_finds_a_catch_all_by_its_label_or_by_what_its_description_covers():
    assert a_question('{"type":"choice","criteria":{"a":"A","other":"Rest"}}').has_fallback_option() is True
    assert a_question('{"type":"choice","criteria":{"a":"A","misc":"Anything else"}}').has_fallback_option() is True
    assert a_question('{"type":"choice","criteria":{"a":"A","b":"B"}}').has_fallback_option() is False
    assert a_question('{"type":"score","criteria":["a","other"]}').has_fallback_option() is False


def test_shows_a_check_the_question_and_not_its_id():
    state = a_question(
        '{"type":"noul","instructions":"Is it?","criteria":{"true":"Yes","false":"No"}}',
    ).as_state()

    assert list(state) == ['instructions', 'criteria']


def test_keeps_a_key_that_looks_like_an_array_index_in_the_place_the_file_wrote_it():
    query = Query.from_json(
        '{"state":"x","questions":{"2":{"type":"noul","instructions":"Is it?"},'
        '"1":{"type":"noul","instructions":"Or not?"}}}',
    )

    assert [question.id for question in query.questions] == ['2', '1']

    criteria = a_question('{"type":"choice","instructions":"Which?","criteria":{"30":"A month","7":"A week"}}')

    assert [label for label, _ in criteria.entries()] == ['30', '7']
