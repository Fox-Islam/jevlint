import tempfile
from pathlib import Path

import pytest

from jevlint.catalogue import Catalogue, compare_versions
from jevlint.errors import JevLintError
from jevlint.support import Json

catalogue = Catalogue.load()


def damaged(change):
    """The same file with one thing wrong with it, written somewhere temporary."""
    data = Json.read_file(Catalogue.locate('catalogue.json'))
    change(data)
    path = Path(tempfile.mkdtemp(prefix='jevlint-')) / 'catalogue.json'
    path.write_text(Json.encode(data), encoding='utf-8')

    return str(path)


def checks(data):
    return data['checks']


def test_loads_the_shipped_file():
    assert len(catalogue.all()) > 0
    assert len(catalogue.fingerprint) == 12
    assert len(catalogue.asked) == 12
    assert catalogue.model == f'jev-{catalogue.jev}'


def test_orders_jev_versions_by_number_and_not_by_text():
    assert compare_versions('1.9', '1.13') < 0
    assert compare_versions('1.13', '1.13') == 0
    assert compare_versions('2', '1.99') > 0


def test_refuses_a_version_it_holds_no_rules_for():
    with pytest.raises(JevLintError) as raised:
        catalogue.for_jev('9.9')

    assert raised.value.kind == 'usage'

    with pytest.raises(JevLintError) as raised:
        catalogue.for_jev('latest-ish')

    assert raised.value.kind == 'usage'
    assert catalogue.for_jev('latest').jev == catalogue.jev


def _duplicate_id(data):
    checks(data).append(dict(checks(data)[0]))


def _unknown_rule(data):
    next(check for check in checks(data) if check['mode'] == 'static')['rule'] = 'nothing.raisesThis'


def _shadowed_rule(data):
    statics = [check for check in checks(data) if check['mode'] == 'static']
    statics[1]['rule'] = statics[0]['rule']


def _model_without_question(data):
    found = next(check for check in checks(data) if check['mode'] == 'model')
    found.pop('question', None)
    found.pop('questions', None)


def _model_without_trigger(data):
    next(check for check in checks(data) if check['mode'] == 'model').pop('trigger')


def _trigger_that_fires_on_everything(data):
    next(check for check in checks(data) if check['mode'] == 'model')['trigger'] = 0.05


def _unknown_severity(data):
    checks(data)[0]['severity'] = 'critical'


def _unknown_scope(data):
    checks(data)[0]['scope'] = 'somewhere'


def _unknown_primitive(data):
    checks(data)[0]['applies_to'] = ['rating']


def _unknown_reads(data):
    checks(data)[0]['reads'] = 'somewhere'


def _supersedes_nothing(data):
    checks(data)[0]['supersedes'] = ['nope/nope']


def _empty_version_span(data):
    checks(data)[0]['since'] = '2.0'
    checks(data)[0]['until'] = '1.0'


def _written_for_no_version(data):
    checks(data)[0]['since'] = '99.0'


def _no_jev_version(data):
    data.pop('jev')


def _no_checks(data):
    data['checks'] = []


def _check_that_is_not_an_object(data):
    checks(data).append(None)


def _unknown_suppression(data):
    found = next(check for check in checks(data) if check['mode'] == 'model')
    found['suppress'] = [{'answer': 'noul', 'when': 'the_moon_is_full'}]


def _clearing_trigger_outside_zero_to_one(data):
    found = next(check for check in checks(data) if 'cleared_by' in check)
    found['cleared_by']['trigger'] = 1.5


def _colliding_answer_keys(data):
    models = [check for check in checks(data) if check['mode'] == 'model']
    models[0]['id'] = 'a/b-c'
    models[1]['id'] = 'a-b/c'


@pytest.mark.parametrize('change', [
    _duplicate_id,
    _unknown_rule,
    _shadowed_rule,
    _model_without_question,
    _model_without_trigger,
    _trigger_that_fires_on_everything,
    _unknown_severity,
    _unknown_scope,
    _unknown_primitive,
    _unknown_reads,
    _supersedes_nothing,
    _empty_version_span,
    _written_for_no_version,
    _no_jev_version,
    _no_checks,
    _check_that_is_not_an_object,
    _unknown_suppression,
    _clearing_trigger_outside_zero_to_one,
    _colliding_answer_keys,
], ids=lambda change: change.__name__.strip('_'))
def test_refuses_a_catalogue_with_something_wrong_with_it(change):
    """
    Each of these loaded without complaint at some point and produced a report
    that read like a clean one.
    """
    with pytest.raises(JevLintError) as raised:
        Catalogue.load(damaged(change))

    assert raised.value.kind in ('catalogue', 'not-found')


def test_the_asked_digest_does_not_move_when_a_message_is_reworded():
    path = damaged(lambda data: next(
        check for check in checks(data) if check['mode'] == 'model'
    ).update({'message': 'Something else entirely.'}))

    assert Catalogue.load(path).asked == catalogue.asked
    assert Catalogue.load(path).fingerprint != catalogue.fingerprint


def test_the_asked_digest_moves_when_a_check_asks_something_else():
    def change(data):
        found = next(check for check in checks(data) if check['mode'] == 'model')
        found['question']['instructions'] = 'Something else entirely?'

    assert Catalogue.load(damaged(change)).asked != catalogue.asked


def test_the_asked_digest_moves_when_a_trigger_moves():
    path = damaged(lambda data: next(
        check for check in checks(data) if check['mode'] == 'model'
    ).update({'trigger': 0.55}))

    assert Catalogue.load(path).asked != catalogue.asked
