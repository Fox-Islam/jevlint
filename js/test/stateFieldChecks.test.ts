import { strict as assert } from 'node:assert';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, it } from 'node:test';
import { Catalogue } from '../src/catalogue/catalogue.js';
import { ModelLinter } from '../src/lint/modelLinter.js';
import { Query } from '../src/query/query.js';
import { Report } from '../src/report/report.js';
import { fakeClient } from './helpers/fake.js';

/**
 * A state-field check is asked once per field, and the readings are held by
 * field so one finding can speak for every question. Held by field alone, a
 * second such check overwrites the first's readings and is reported under the
 * first's id, which is a wrong answer wearing a check's name.
 */
describe('a catalogue with two state-field checks', () => {
    it('reports each of them under its own id', async () => {
        const source = JSON.parse(readFileSync('checks/catalogue.json', 'utf8')) as {
            checks: Record<string, unknown>[];
        };
        const first = source.checks.find((check) => check['id'] === 'state/irrelevant-field');
        assert.ok(first, 'the catalogue no longer ships a state-field check to copy');

        source.checks.push({ ...first, id: 'state/second-opinion', trigger: 0.7 });

        const path = join(mkdtempSync(join(tmpdir(), 'jevlint-')), 'catalogue.json');
        writeFileSync(path, JSON.stringify(source));

        const { client } = fakeClient({
            state_irrelevant_field__ticket: 0.95,
            state_second_opinion__ticket: 0.8,
        });

        const catalogue = Catalogue.load(path);
        const report = new Report({ source: 'test', catalogueVersion: catalogue.version });

        await new ModelLinter(catalogue, client).run(Query.fromObject({
            state: { ticket: 'I was charged twice.' },
            questions: { refund: { type: 'noul', instructions: 'Does the customer ask for a refund?' } },
        }, 'test'), report);

        const read = new Map(report.findings().map((finding) => [finding.checkId, finding.probability]));

        assert.equal(read.get('state/irrelevant-field'), 0.95);
        assert.equal(read.get('state/second-opinion'), 0.8);
    });
});
