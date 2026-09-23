"""
A state-field check is asked once per field, and the readings are held by field so
one finding can speak for every question. Held by field alone, a second such check
overwrites the first's readings and is reported under the first's id, which is a
wrong answer wearing a check's name.
"""
import json
from pathlib import Path

from conftest import FakeClient

from jevlint.catalogue import Catalogue
from jevlint.model_linter import ModelLinter
from jevlint.query import Query
from jevlint.report import Report


def test_a_catalogue_with_two_state_field_checks_reports_each_under_its_own_id(tmp_path):
    source = json.loads(Path(Catalogue.locate('catalogue.json')).read_text(encoding='utf-8'))
    first = next(
        (check for check in source['checks'] if check['id'] == 'state/irrelevant-field'), None,
    )

    assert first is not None, 'the catalogue no longer ships a state-field check to copy'

    source['checks'].append({**first, 'id': 'state/second-opinion', 'trigger': 0.7})

    path = tmp_path / 'catalogue.json'
    path.write_text(json.dumps(source), encoding='utf-8')

    fake = FakeClient({
        'state_irrelevant_field__ticket': 0.95,
        'state_second_opinion__ticket': 0.8,
    })

    catalogue = Catalogue.load(str(path))
    report = Report(source='test', catalogue_version=catalogue.version)

    ModelLinter(catalogue, fake.client).run(Query.from_dict({
        'state': {'ticket': 'I was charged twice.'},
        'questions': {'refund': {'type': 'noul', 'instructions': 'Does the customer ask for a refund?'}},
    }, 'test'), report)

    read = {finding.check_id: finding.probability for finding in report.findings()}

    assert read['state/irrelevant-field'] == 0.95
    assert read['state/second-opinion'] == 0.8
