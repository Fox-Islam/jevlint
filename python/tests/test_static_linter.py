import json

from jevlint.catalogue import Catalogue
from jevlint.query import Query
from jevlint.report import Report, Severity
from jevlint.rules import RULES
from jevlint.static_linter import StaticLinter

catalogue = Catalogue.load()


def check(json_text, max_state=20000):
    report = Report(source='test', catalogue_version=catalogue.version)
    StaticLinter(catalogue, max_state).run(Query.from_json(json_text), report)

    return report


def ids(json_text, max_state=20000):
    return [finding.check_id for finding in check(json_text, max_state).findings()]


def found(report, check_id):
    return next((finding for finding in report.findings() if finding.check_id == check_id), None)


def query(questions, state='"x"'):
    return '{"state":' + state + ',"questions":' + questions + '}'


def test_reports_a_query_with_no_questions():
    assert ids('{"state":"x"}') == ['query/no-questions']


def test_reports_a_query_with_no_state():
    assert 'state/missing' in ids(
        '{"questions":{"a":{"type":"noul","instructions":"Does it ask for a refund?"}}}',
    )


def test_reports_a_state_past_the_threshold_in_characters():
    long = json.dumps('é' * 30)

    assert 'state/oversized' in ids(
        query('{"a":{"type":"noul","instructions":"Does it ask for a refund?"}}', long), 20,
    )


def test_reports_a_key_the_api_does_not_take_and_points_at_it():
    finding = found(check(
        '{"state":"x","extra":1,"questions":'
        '{"a":{"type":"noul","instructions":"Does it ask for a refund?"}}}',
    ), 'query/unknown-key')

    assert finding is not None
    assert finding.patch.op == 'remove'
    assert finding.patch.path == '/extra'


def test_reports_two_questions_asking_the_same_thing():
    assert 'query/duplicate-instructions' in ids(query(
        '{"a":{"type":"noul","instructions":"Same?"},"b":{"type":"noul","instructions":"Same?"}}',
    ))


def test_reports_a_model_the_run_cannot_pin_to_a_build():
    assert 'query/floating-model' in ids(
        '{"model":"jev-latest","state":"x","questions":'
        '{"a":{"type":"noul","instructions":"Does it ask for a refund?"}}}',
    )
    assert 'query/floating-model' not in ids(
        '{"model":"jev-1.13.0","state":"x","questions":'
        '{"a":{"type":"noul","instructions":"Does it ask for a refund?"}}}',
    )


def test_reports_a_type_jev_does_not_answer():
    assert ids(query('{"a":{"type":"rating","instructions":"How good?"}}')) == ['question/unknown-type']


def test_offers_to_lower_case_a_type_written_in_capitals():
    finding = found(
        check(query('{"a":{"type":"NOUL","instructions":"Does the customer want money back?"}}')),
        'question/type-not-lowercase',
    )

    assert finding.patch.value == 'noul'
    assert finding.patch.safety == 'lossless'


def test_reports_an_instruction_made_only_of_spaces_nobody_can_see():
    assert 'question/no-instructions' in ids(query('{"a":{"type":"noul","instructions":"\\u00a0\\u200b"}}'))


def test_reports_an_instruction_that_says_no_more_than_its_id():
    assert 'question/instruction-is-id' in ids(
        query('{"refund_requested":{"type":"noul","instructions":"Refund requested?"}}'),
    )


def test_leaves_a_whole_question_alone_even_where_it_contains_its_id():
    assert 'question/instruction-is-id' not in ids(
        query('{"blocked":{"type":"noul","instructions":"Is the customer blocked?"}}'),
    )


def test_reports_a_noul_keyed_anything_but_true_and_false_and_renames_yes_and_no():
    finding = found(check(query(
        '{"a":{"type":"noul","instructions":"Does the customer want money back?",'
        '"criteria":{"yes":"Y","no":"N"}}}',
    )), 'noul/criteria-shape')

    assert finding.patch.value == {'true': 'Y', 'false': 'N'}


def test_offers_no_rename_where_two_keys_collapse_onto_one():
    finding = found(check(query(
        '{"a":{"type":"noul","instructions":"Does the customer want money back?",'
        '"criteria":{"yes":"Y","YES":"Y2"}}}',
    )), 'noul/criteria-shape')

    assert finding.patch is None


def test_reports_a_choice_written_as_a_list_and_offers_the_map():
    finding = found(check(query(
        '{"a":{"type":"choice","instructions":"Which team should take this?",'
        '"criteria":["billing","shipping","other"]}}',
    )), 'choice/criteria-shape')

    assert finding.patch.value == {'billing': '', 'shipping': '', 'other': ''}
    assert finding.patch.safety == 'lossy'


def test_offers_no_map_where_the_labels_are_numbers_which_would_encode_as_a_list_again():
    finding = found(check(query(
        '{"a":{"type":"choice","instructions":"Which team should take this?","criteria":["0","1"]}}',
    )), 'choice/criteria-shape')

    assert finding.patch is None


def test_reports_a_choice_with_one_option_and_one_with_no_catch_all():
    reported = ids(query(
        '{"a":{"type":"choice","instructions":"Which team should take this?","criteria":{"billing":"Money"}}}',
    ))

    assert 'choice/too-few-options' in reported
    assert 'choice/no-fallback' in reported


def test_reports_a_choice_whose_descriptions_are_not_text():
    assert 'choice/description-not-text' in ids(query(
        '{"a":{"type":"choice","instructions":"Which team should take this?","criteria":{"a":1,"b":"Two"}}}',
    ))


def test_offers_no_catch_all_where_nothing_is_described_which_the_next_rule_would_refuse():
    report = check(query(
        '{"a":{"type":"choice","instructions":"Which team should take this?","criteria":{"a":"","b":""}}}',
    ))

    assert found(report, 'choice/no-fallback').patch is None
    assert 'choice/undescribed-options' in [finding.check_id for finding in report.findings()]


def test_reports_a_score_written_as_a_numeric_map_and_orders_the_rubric_by_its_keys():
    finding = found(check(query(
        '{"a":{"type":"score","instructions":"How ready are they?",'
        '"criteria":{"2":"Ready","0":"Not ready","1":"Nearly"}}}',
    )), 'score/criteria-shape')

    assert finding.patch.value == ['Not ready', 'Nearly', 'Ready']
    assert finding.patch.safety == 'lossless'


def test_offers_no_rubric_where_the_keys_are_names_which_say_nothing_about_the_order():
    finding = found(check(query(
        '{"a":{"type":"score","instructions":"How ready are they?",'
        '"criteria":{"low":"Not ready","high":"Ready"}}}',
    )), 'score/criteria-shape')

    assert finding.patch is None


def test_reports_a_rubric_of_bare_numbers_too_few_levels_and_too_many():
    assert 'score/numeric-levels' in ids(query(
        '{"a":{"type":"score","instructions":"How bad is it?","criteria":["0","1","2"]}}',
    ))
    assert 'score/too-few-levels' in ids(query(
        '{"a":{"type":"score","instructions":"How bad is it?","criteria":["Only one"]}}',
    ))
    assert 'score/too-many-levels' in ids(query(
        '{"a":{"type":"score","instructions":"How bad is it?","criteria":'
        + json.dumps([f'Level {index} of the rubric' for index in range(11)]) + '}}',
    ))


def test_reports_criteria_that_are_neither_a_list_nor_a_map():
    assert 'question/criteria-not-a-structure' in ids(query(
        '{"a":{"type":"choice","instructions":"Which plan?","criteria":"free, paid"}}',
    ))


def test_names_a_check_for_every_rule_the_code_can_raise():
    assert [rule for rule in RULES if catalogue.rule(rule) is None] == []


def test_names_a_rule_in_the_code_for_every_static_check():
    unbound = [check.id for check in catalogue.static() if check.rule not in RULES]

    assert unbound == []


def test_raises_every_rule_it_lists_somewhere_in_the_linter():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / 'src/jevlint/static_linter.py').read_text(encoding='utf-8')

    assert [rule for rule in RULES if f"'{rule}'" not in source] == []


def test_gives_every_static_check_a_severity_the_report_knows():
    names = [severity.value for severity in Severity.cases()]

    assert [check.id for check in catalogue.written() if check.severity not in names] == []


def test_reports_choice_keys_a_javascript_object_would_reorder():
    finding = found(check(query(
        '{"a":{"type":"choice","instructions":"Which hour does the log give?",'
        '"criteria":{"06":"Six","07":"Seven","10":"Ten","11":"Eleven","other":"Anything else"}}}',
    )), 'choice/index-like-options')

    assert 'Written 06, 07, 10, 11, other' in finding.evidence
    assert 'sends 10, 11, 06, 07, other' in finding.evidence


def test_reports_no_reordering_where_the_index_keys_are_already_written_in_order():
    assert 'choice/index-like-options' not in ids(query(
        '{"a":{"type":"choice","instructions":"How many attempts are logged?",'
        '"criteria":{"1":"One","2":"Two","3":"Three","other":"Anything else"}}}',
    ))


def test_reports_no_reordering_where_a_key_is_a_number_no_object_reads_as_an_index():
    assert 'choice/index-like-options' not in ids(query(
        '{"a":{"type":"choice","instructions":"Which release is named?",'
        '"criteria":{"2.5":"The 2.5 line","1.0":"The 1.0 line","other":"Anything else"}}}',
    ))
