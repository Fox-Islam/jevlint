import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';
import { Catalogue } from '../src/catalogue/catalogue.js';
import { Config } from '../src/config/config.js';
import { JevLintError } from '../src/exceptions/jevLintError.js';
import { Linter } from '../src/lint/linter.js';
import { Query } from '../src/query/query.js';
import { Severity } from '../src/report/severity.js';
import { fakeClient } from './helpers/fake.js';

const clean = (): Query => Query.fromObject({
    state: { ticket: 'I was charged twice for order A-104.' },
    questions: {
        refund: {
            type: 'noul',
            instructions: 'Does the customer ask for a refund?',
            criteria: { true: 'They ask for money back.', false: 'They report a problem only.' },
        },
    },
}, 'test');

describe('the linter facade', () => {
    it('runs the rules and makes no calls', async () => {
        const report = await Linter.rulesOnly().check(clean());

        assert.equal(report.calls(), 0);
        assert.ok(report.askedCount() > 0);
        assert.ok(report.skippedNotes().some((note) => note.message.includes('Jev was not asked')));
    });

    it('asks its model checks through a client it is given', async () => {
        const { client, calls } = fakeClient({}, 0.02);
        const report = await Linter.make(client).check(clean());

        assert.ok(calls.length > 0);
        assert.equal(report.calls(), calls.length);
        assert.deepEqual(report.answeringModels(), ['jev-1.13.0']);
        assert.equal(report.isComplete(), true);
    });

    it('reports a finding where the answer clears the trigger', async () => {
        const { client } = fakeClient({ question_compound_judgment: 0.95 }, 0.02);
        const report = await Linter.make(client).only(['question/compound-judgment']).check(clean());

        assert.deepEqual(report.findings().map((finding) => finding.checkId), ['question/compound-judgment']);
        assert.equal(report.findings()[0]?.probability, 0.95);
    });

    it('refuses a narrowing the catalogue does not hold', () => {
        assert.throws(() => Linter.rulesOnly().only(['nope/nope']), JevLintError);
    });

    it('says what a narrowed query left unchecked', async () => {
        const whole = Query.fromObject({
            state: { a: 'x' },
            questions: {
                one: { type: 'noul', instructions: 'Does the customer ask for a refund?' },
                two: { type: 'noul', instructions: 'Is the customer blocked from working?' },
            },
        }, 'test');

        const report = await Linter.rulesOnly().check(whole.only(['one']), whole);

        assert.ok(report.skippedNotes().some((note) => note.message.includes('left')));
    });

    it('refuses a config accepting a check that is not in the catalogue', async () => {
        const config = Config.load('local/js/cfg/unknown-check.json');

        await assert.rejects(
            () => Linter.rulesOnly(Catalogue.load(), config).check(clean()),
            (error: JevLintError) => error.kind === 'config',
        );
    });

    it('counts a call that failed and says the run is incomplete', async () => {
        const { client } = fakeClient({}, 0.1, { status: 500 });
        const report = await Linter.make(client).only(['question/compound-judgment']).check(clean());

        assert.equal(report.isComplete(), false);
        assert.equal(report.unreachableNotes()[0]?.cause, 'server');
        assert.ok(report.calls() > 0, 'A call that left the machine was paid for.');
    });

    /**
     * A wrong key answers every call the same way, so a run that keeps going
     * spends the rest of its calls buying the same refusal.
     */
    it('stops after a failure every later call would repeat', async () => {
        const { client, calls } = fakeClient({}, 0.1, { status: 401 });
        const query = Query.fromObject({
            state: { a: 'x' },
            questions: {
                one: { type: 'noul', instructions: 'Does the customer ask for a refund?' },
                two: { type: 'noul', instructions: 'Is the customer blocked from working?' },
                three: { type: 'noul', instructions: 'Has the customer written in before?' },
            },
        }, 'test');

        await Linter.make(client).check(query);

        assert.equal(calls.length, 1, 'Only the first call should have been paid for.');
    });
});

describe('the report a run hands back', () => {
    it('counts findings whole while a floor filters the list', async () => {
        const report = await Linter.rulesOnly().check(Query.fromFile('examples/broken-triage.json'));

        assert.equal(report.hasErrors(), true);
        assert.ok(report.count(Severity.Advice) > 0);
        assert.equal(report.findings(Severity.Error).length, report.count(Severity.Error));
        assert.ok(
            report.findings(Severity.Error).length < report.findings().length,
            'A floor hides rows; it does not change the counts.',
        );
    });

    it('is the document the schema describes', async () => {
        const report = await Linter.rulesOnly().check(clean());
        const row = report.toObject();

        assert.deepEqual(Object.keys(row), [
            'source', 'catalogue', 'asked_through', 'answered_by', 'summary',
            'accepted_from', 'notes', 'cleared', 'accepted', 'unstable', 'findings',
        ]);
        assert.deepEqual(Object.keys(row['summary'] as object), [
            'error', 'warning', 'advice', 'calls', 'tokens', 'tokens_unreported_for',
            'accepted', 'unstable', 'unreachable', 'asked', 'complete', 'narrowed',
        ]);
    });

    it('sets a finding aside where the config accepts it, and still counts nothing for it', async () => {
        const report = await Linter.rulesOnly(Catalogue.load(), Config.load('local/js/cfg/good.json'))
            .check(Query.fromFile('local/js/cfg/query.json'));

        assert.equal(report.accepted().length, 1);
        assert.ok(!report.findings().some((finding) => finding.checkId === 'choice/no-fallback'));
        assert.equal(report.accepted()[0]?.accepted, 'The router falls back in code.');
    });
});
