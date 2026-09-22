import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';
import { Catalogue } from '../src/catalogue/catalogue.js';
import { StaticLinter } from '../src/lint/staticLinter.js';
import { RULES } from '../src/lint/rules.js';
import { Query } from '../src/query/query.js';
import { Report } from '../src/report/report.js';
import { Severity } from '../src/report/severity.js';
import { sources } from './helpers/sources.js';

const catalogue = Catalogue.load();

function check(json: string, maxState = 20000): Report {
    const report = new Report({ source: 'test', catalogueVersion: catalogue.version });
    new StaticLinter(catalogue, maxState).run(Query.fromJson(json), report);

    return report;
}

function ids(json: string, maxState = 20000): string[] {
    return check(json, maxState).findings().map((finding) => finding.checkId);
}

const query = (questions: string, state = '"x"'): string => `{"state":${state},"questions":${questions}}`;

describe('the rules that need no call', () => {
    it('reports a query with no questions', () => {
        assert.deepEqual(ids('{"state":"x"}'), ['query/no-questions']);
    });

    it('reports a query with no state', () => {
        assert.ok(ids('{"questions":{"a":{"type":"noul","instructions":"Does it ask for a refund?"}}}')
            .includes('state/missing'));
    });

    it('reports a state past the threshold, in characters', () => {
        const long = 'é'.repeat(30);

        assert.ok(ids(query('{"a":{"type":"noul","instructions":"Does it ask for a refund?"}}', JSON.stringify(long)), 20)
            .includes('state/oversized'));
    });

    it('reports a key the API does not take, and points at it', () => {
        const report = check('{"state":"x","extra":1,"questions":{"a":{"type":"noul","instructions":"Does it ask for a refund?"}}}');
        const finding = report.findings().find((found) => found.checkId === 'query/unknown-key');

        assert.ok(finding);
        assert.equal(finding.patch?.op, 'remove');
        assert.equal(finding.patch?.path, '/extra');
    });

    it('reports two questions asking the same thing', () => {
        assert.ok(ids(query('{"a":{"type":"noul","instructions":"Same?"},"b":{"type":"noul","instructions":"Same?"}}'))
            .includes('query/duplicate-instructions'));
    });

    it('reports a type Jev does not answer', () => {
        assert.deepEqual(
            ids(query('{"a":{"type":"rating","instructions":"How good?"}}')),
            ['question/unknown-type'],
        );
    });

    it('offers to lower-case a type written in capitals', () => {
        const finding = check(query('{"a":{"type":"NOUL","instructions":"Does the customer want money back?"}}'))
            .findings().find((found) => found.checkId === 'question/type-not-lowercase');

        assert.equal(finding?.patch?.value, 'noul');
        assert.equal(finding?.patch?.safety, 'lossless');
    });

    it('reports an instruction made only of spaces nobody can see', () => {
        assert.ok(ids(query('{"a":{"type":"noul","instructions":"\\u00a0\\u200b"}}'))
            .includes('question/no-instructions'));
    });

    it('reports an instruction that says no more than its id', () => {
        assert.ok(ids(query('{"refund_requested":{"type":"noul","instructions":"Refund requested?"}}'))
            .includes('question/instruction-is-id'));
    });

    it('leaves a whole question alone even where it contains its id', () => {
        assert.ok(!ids(query('{"blocked":{"type":"noul","instructions":"Is the customer blocked?"}}'))
            .includes('question/instruction-is-id'));
    });

    it('reports a Noul keyed anything but true and false, and renames yes and no', () => {
        const finding = check(query('{"a":{"type":"noul","instructions":"Does the customer want money back?","criteria":{"yes":"Y","no":"N"}}}'))
            .findings().find((found) => found.checkId === 'noul/criteria-shape');

        assert.deepEqual(finding?.patch?.value, { true: 'Y', false: 'N' });
    });

    it('offers no rename where two keys collapse onto one', () => {
        const finding = check(query('{"a":{"type":"noul","instructions":"Does the customer want money back?","criteria":{"yes":"Y","YES":"Y2"}}}'))
            .findings().find((found) => found.checkId === 'noul/criteria-shape');

        assert.equal(finding?.patch, null);
    });

    it('reports a Choice written as a list, and offers the map', () => {
        const finding = check(query('{"a":{"type":"choice","instructions":"Which team should take this?","criteria":["billing","shipping","other"]}}'))
            .findings().find((found) => found.checkId === 'choice/criteria-shape');

        assert.deepEqual(finding?.patch?.value, { billing: '', shipping: '', other: '' });
        assert.equal(finding?.patch?.safety, 'lossy');
    });

    it('offers no map where the labels are numbers, which would encode as a list again', () => {
        const finding = check(query('{"a":{"type":"choice","instructions":"Which team should take this?","criteria":["0","1"]}}'))
            .findings().find((found) => found.checkId === 'choice/criteria-shape');

        assert.equal(finding?.patch, null);
    });

    it('reports a Choice with one option, and one with no catch-all', () => {
        const found = ids(query('{"a":{"type":"choice","instructions":"Which team should take this?","criteria":{"billing":"Money"}}}'));

        assert.ok(found.includes('choice/too-few-options'));
        assert.ok(found.includes('choice/no-fallback'));
    });

    it('reports a Choice whose descriptions are not text', () => {
        assert.ok(ids(query('{"a":{"type":"choice","instructions":"Which team should take this?","criteria":{"a":1,"b":"Two"}}}'))
            .includes('choice/description-not-text'));
    });

    it('offers no catch-all where nothing is described, which the next rule would refuse', () => {
        const report = check(query('{"a":{"type":"choice","instructions":"Which team should take this?","criteria":{"a":"","b":""}}}'));
        const fallback = report.findings().find((found) => found.checkId === 'choice/no-fallback');

        assert.equal(fallback?.patch, null);
        assert.ok(report.findings().map((found) => found.checkId).includes('choice/undescribed-options'));
    });

    it('reports a Score written as a numeric map, and orders the rubric by its keys', () => {
        const finding = check(query('{"a":{"type":"score","instructions":"How ready are they?","criteria":{"2":"Ready","0":"Not ready","1":"Nearly"}}}'))
            .findings().find((found) => found.checkId === 'score/criteria-shape');

        assert.deepEqual(finding?.patch?.value, ['Not ready', 'Nearly', 'Ready']);
        assert.equal(finding?.patch?.safety, 'lossless');
    });

    it('offers no rubric where the keys are names, which say nothing about the order', () => {
        const finding = check(query('{"a":{"type":"score","instructions":"How ready are they?","criteria":{"low":"Not ready","high":"Ready"}}}'))
            .findings().find((found) => found.checkId === 'score/criteria-shape');

        assert.equal(finding?.patch, null);
    });

    it('reports a rubric of bare numbers, too few levels and too many', () => {
        assert.ok(ids(query('{"a":{"type":"score","instructions":"How bad is it?","criteria":["0","1","2"]}}'))
            .includes('score/numeric-levels'));
        assert.ok(ids(query('{"a":{"type":"score","instructions":"How bad is it?","criteria":["Only one"]}}'))
            .includes('score/too-few-levels'));
        assert.ok(ids(query(`{"a":{"type":"score","instructions":"How bad is it?","criteria":${JSON.stringify(
            Array.from({ length: 11 }, (_, i) => `Level ${i} of the rubric`),
        )}}}`)).includes('score/too-many-levels'));
    });

    it('reports criteria that are neither a list nor a map', () => {
        assert.ok(ids(query('{"a":{"type":"choice","instructions":"Which plan?","criteria":"free, paid"}}'))
            .includes('question/criteria-not-a-structure'));
    });
});

/**
 * A static check is a name in the catalogue bound to a branch here. A rule the
 * catalogue does not claim throws where it is raised; a rule nothing raises
 * loads, lists, documents itself and never fires
 */
describe('the rules and the catalogue', () => {
    it('names a check for every rule the code can raise', () => {
        const unclaimed = RULES.filter((rule) => catalogue.rule(rule) === null);

        assert.deepEqual(unclaimed, []);
    });

    it('names a rule in the code for every static check', () => {
        const unbound = catalogue.static()
            .filter((check) => check.rule === null || !(RULES as readonly string[]).includes(check.rule))
            .map((check) => check.id);

        assert.deepEqual(unbound, []);
    });

    it('raises every rule it lists somewhere in the linter', () => {
        const linter = sources().find(({ path }) => path.endsWith('staticLinter.ts'))?.contents ?? '';
        const never = RULES.filter((rule) => !linter.includes(`'${rule}'`));

        assert.deepEqual(never, []);
    });

    it('gives every static check a severity the report knows', () => {
        const names = Severity.cases().map((severity) => severity.value);
        const odd = catalogue.written().filter((check) => !names.includes(check.severity as never));

        assert.deepEqual(odd.map((check) => check.id), []);
    });
});
