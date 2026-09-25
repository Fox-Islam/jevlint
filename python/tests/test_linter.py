import pytest
from conftest import FakeClient

from jevlint.catalogue import Catalogue
from jevlint.config import Config
from jevlint.errors import JevLintError
from jevlint.linter import Linter
from jevlint.query import Query
from jevlint.report import Severity


def clean():
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


def test_runs_the_rules_and_makes_no_calls():
    report = Linter.rules_only().check(clean())

    assert report.calls() == 0
    assert report.asked_count() > 0
    assert any('Jev was not asked' in note.message for note in report.skipped_notes())


def test_asks_its_model_checks_through_a_client_it_is_given():
    fake = FakeClient({}, 0.02)
    report = Linter.make(fake.client).check(clean())

    assert len(fake.calls) > 0
    assert report.calls() == len(fake.calls)
    assert report.answering_models() == ['jev-1.13.0']
    assert report.is_complete() is True


def test_reports_a_finding_where_the_answer_clears_the_trigger():
    fake = FakeClient({'question_compound_judgment': 0.95}, 0.02)
    report = Linter.make(fake.client).only(['question/compound-judgment']).check(clean())

    assert [finding.check_id for finding in report.findings()] == ['question/compound-judgment']
    assert report.findings()[0].probability == 0.95


def test_refuses_a_narrowing_the_catalogue_does_not_hold():
    with pytest.raises(JevLintError):
        Linter.rules_only().only(['nope/nope'])


def test_says_what_a_narrowed_query_left_unchecked():
    whole = Query.from_dict({
        'state': {'a': 'x'},
        'questions': {
            'one': {'type': 'noul', 'instructions': 'Does the customer ask for a refund?'},
            'two': {'type': 'noul', 'instructions': 'Is the customer blocked from working?'},
        },
    }, 'test')

    report = Linter.rules_only().check(whole.only(['one']), whole)

    assert any('left' in note.message for note in report.skipped_notes())


def test_refuses_a_config_accepting_a_check_that_is_not_in_the_catalogue(tmp_path):
    path = tmp_path / '.jevlint.json'
    path.write_text('{"accept": [{"check": "nope/nope", "reason": "because"}]}', encoding='utf-8')

    with pytest.raises(JevLintError) as raised:
        Linter.rules_only(Catalogue.load(), Config.load(str(path))).check(clean())

    assert raised.value.kind == 'config'


def test_counts_a_call_that_failed_and_says_the_run_is_incomplete():
    fake = FakeClient({}, 0.1, {'status': 500})
    report = Linter.make(fake.client).only(['question/compound-judgment']).check(clean())

    assert report.is_complete() is False
    assert report.unreachable_notes()[0].cause == 'server'
    assert report.calls() > 0, 'A call that left the machine was paid for.'


def test_stops_after_a_failure_every_later_call_would_repeat():
    """
    A wrong key answers every call the same way, so a run that keeps going spends
    the rest of its calls buying the same refusal.
    """
    fake = FakeClient({}, 0.1, {'status': 401})
    query = Query.from_dict({
        'state': {'a': 'x'},
        'questions': {
            'one': {'type': 'noul', 'instructions': 'Does the customer ask for a refund?'},
            'two': {'type': 'noul', 'instructions': 'Is the customer blocked from working?'},
            'three': {'type': 'noul', 'instructions': 'Has the customer written in before?'},
        },
    }, 'test')

    Linter.make(fake.client).check(query)

    assert len(fake.calls) == 1, 'Only the first call should have been paid for.'


def test_counts_findings_whole_while_a_floor_filters_the_list():
    report = Linter.rules_only().check(Query.from_file('examples/broken-triage.json'))

    assert report.has_errors() is True
    assert report.count(Severity.Advice) > 0
    assert len(report.findings(Severity.Error)) == report.count(Severity.Error)
    assert len(report.findings(Severity.Error)) < len(report.findings())


def test_the_report_is_the_document_the_schema_describes():
    row = Linter.rules_only().check(clean()).to_dict()

    assert list(row) == [
        'source', 'catalogue', 'asked_through', 'answered_by', 'summary',
        'accepted_from', 'notes', 'cleared', 'accepted', 'unstable', 'findings',
    ]
    assert list(row['summary']) == [
        'error', 'warning', 'advice', 'calls', 'tokens', 'tokens_unreported_for',
        'accepted', 'unstable', 'unreachable', 'asked', 'complete', 'narrowed',
    ]


def test_sets_a_finding_aside_where_the_config_accepts_it_and_still_counts_nothing_for_it(tmp_path):
    path = tmp_path / '.jevlint.json'
    path.write_text(
        '{"accept": [{"check": "choice/no-fallback", "question": "department",'
        ' "reason": "The router falls back in code."}]}',
        encoding='utf-8',
    )
    query = Query.from_dict({
        'state': {'ticket': 'I was charged twice for order A-104.'},
        'questions': {
            'department': {
                'type': 'choice',
                'instructions': 'Which team should pick this ticket up?',
                'criteria': {'billing': 'Charges and refunds', 'shipping': 'Delivery'},
            },
        },
    }, 'test')

    report = Linter.rules_only(Catalogue.load(), Config.load(str(path))).check(query)

    assert len(report.accepted()) == 1
    assert not any(finding.check_id == 'choice/no-fallback' for finding in report.findings())
    assert report.accepted()[0].accepted == 'The router falls back in code.'


def test_does_not_ask_whether_a_lone_question_depends_on_a_sibling():
    fake = FakeClient({'question_refers_to_sibling': 0.95}, 0.02)
    report = Linter.make(fake.client).only(['question/refers-to-sibling']).check(clean())

    assert report.findings() == []
    assert fake.calls == []


def test_asks_whether_a_question_depends_on_a_sibling_the_narrowing_left_out():
    whole = Query.from_dict({
        'state': {'ticket': 'I was charged twice for order A-104.'},
        'questions': {
            'refund': {'type': 'noul', 'instructions': 'Does the customer ask for a refund?'},
            'urgent': {'type': 'noul', 'instructions': 'Given the refund answer, is this urgent?'},
        },
    }, 'test')
    fake = FakeClient({'question_refers_to_sibling': 0.95}, 0.02)
    report = Linter.make(fake.client).only(['question/refers-to-sibling']).check(whole.only(['urgent']), whole)

    assert [finding.check_id for finding in report.findings()] == ['question/refers-to-sibling']


def draw():
    return Query.from_dict({
        'state': 'A die was rolled inside a closed box and nobody has looked.',
        'questions': {
            'face': {
                'type': 'choice',
                'instructions': 'Which face came up?',
                'criteria': {'low': 'One to three', 'high': 'Four to six'},
            },
        },
    }, 'test')


def test_reports_a_finding_its_clearing_question_does_not_set_aside():
    fake = FakeClient({'choice_undetermined_outcome': 0.95, 'choice_undetermined_outcome__clear': 0.05}, 0.02)
    report = Linter.make(fake.client).only(['choice/undetermined-outcome']).check(draw())

    assert [finding.check_id for finding in report.findings()] == ['choice/undetermined-outcome']


def test_sets_a_finding_aside_where_its_clearing_question_reads_above_its_trigger():
    fake = FakeClient({'choice_undetermined_outcome': 0.95, 'choice_undetermined_outcome__clear': 0.9}, 0.02)
    report = Linter.make(fake.client).only(['choice/undetermined-outcome']).reporting_cleared().check(draw())

    assert report.findings() == []
    assert [finding.check_id for finding in report.cleared()] == ['choice/undetermined-outcome']
    assert 'clearing question read 0.90' in report.cleared()[0].cleared_because


def test_raises_a_finding_its_second_question_reads_above_its_trigger():
    fake = FakeClient({'question_arithmetic': 0.1, 'question_arithmetic__fire': 0.9}, 0.02)
    report = Linter.make(fake.client).only(['question/arithmetic']).check(clean())

    assert [finding.check_id for finding in report.findings()] == ['question/arithmetic']
    assert report.findings()[0].probability == 0.9
    assert report.findings()[0].trigger == 0.5
    assert 'own question read 0.10 against its 0.60 trigger' in report.findings()[0].evidence


def test_raises_nothing_where_neither_question_reads_above_its_trigger():
    fake = FakeClient({'question_arithmetic': 0.1, 'question_arithmetic__fire': 0.3}, 0.02)
    report = Linter.make(fake.client).only(['question/arithmetic']).check(clean())

    assert report.findings() == []
