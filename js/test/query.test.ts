import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';
import { JevLintError } from '../src/exceptions/jevLintError.js';
import { Query } from '../src/query/query.js';

describe('a query', () => {
    it('refuses a JSON list, which decodes to something the checks could walk', () => {
        assert.throws(() => Query.fromJson('[{"state":"x"}]'), (error: JevLintError) => error.kind === 'query');
    });

    it('refuses questions written as a list, which the API rejects', () => {
        assert.throws(
            () => Query.fromJson('{"state":"x","questions":[{"type":"noul"}]}'),
            (error: JevLintError) => error.kind === 'query',
        );
    });

    it('takes questions keyed by numbers, which the API accepts', () => {
        const query = Query.fromJson('{"state":"x","questions":{"0":{"type":"noul","instructions":"Is it?"}}}');

        assert.deepEqual(query.questions.map((question) => question.id), ['0']);
    });

    it('refuses a state that is a number, which is a different defect from having none', () => {
        assert.throws(() => Query.fromJson('{"state":42,"questions":{}}'), (error: JevLintError) => error.kind === 'query');
    });

    it('reads an empty object as no state', () => {
        assert.equal(Query.fromJson('{"state":{},"questions":{}}').hasState(), false);
        assert.equal(Query.fromJson('{"state":"","questions":{}}').hasState(), false);
        assert.equal(Query.fromJson('{"state":[],"questions":{}}').hasState(), false);
        assert.equal(Query.fromJson('{"state":{"a":1},"questions":{}}').hasState(), true);
    });

    it('counts a state in characters, not in the bytes it takes on the wire', () => {
        assert.equal(Query.fromObject({ state: 'héllo' }).stateSize(), 5);
    });

    it('follows nesting to two levels, however wide each one is', () => {
        const query = Query.fromObject({
            state: { a: { b: 1, c: 2 }, d: 3, e: { f: { g: 4 } } },
        });

        assert.deepEqual(query.stateLeaves(), ['a.b', 'a.c', 'd', 'e.f']);
    });

    it('escapes a dot inside a key, so it is not read as nesting', () => {
        const query = Query.fromObject({ state: { 'a.b': 1 } });

        assert.deepEqual(query.stateLeaves(), ['a\\.b']);
        assert.equal(query.stateAt('a\\.b'), 1);
        assert.deepEqual(Query.segments('a\\.b'), ['a.b']);
        assert.deepEqual(Query.segments('a.b'), ['a', 'b']);
    });

    it('narrows to some of its questions and keeps the rest of itself', () => {
        const query = Query.fromObject({
            state: 'x',
            questions: {
                a: { type: 'noul', instructions: 'One?' },
                b: { type: 'noul', instructions: 'Two?' },
            },
        });

        assert.deepEqual(query.only(['b']).questions.map((question) => question.id), ['b']);
        assert.deepEqual(query.only([]).questions.map((question) => question.id), ['a', 'b']);
    });
});

describe('a question under review', () => {
    const of = (json: string) => Query.fromJson(`{"state":"x","questions":{"q":${json}}}`).questions[0];

    it('lower-cases the type it was given', () => {
        assert.equal(of('{"type":"NOUL"}')?.type, 'noul');
    });

    it('knows criteria written as a list from criteria written as a map', () => {
        assert.equal(of('{"type":"choice","criteria":["a","b"]}')?.criteriaIsList(), true);
        assert.equal(of('{"type":"choice","criteria":{"0":"a","1":"b"}}')?.criteriaIsList(), false);
    });

    it('finds a catch-all by its label or by what its description covers', () => {
        assert.equal(of('{"type":"choice","criteria":{"a":"A","other":"Rest"}}')?.hasFallbackOption(), true);
        assert.equal(of('{"type":"choice","criteria":{"a":"A","misc":"Anything else"}}')?.hasFallbackOption(), true);
        assert.equal(of('{"type":"choice","criteria":{"a":"A","b":"B"}}')?.hasFallbackOption(), false);
        assert.equal(of('{"type":"score","criteria":["a","other"]}')?.hasFallbackOption(), false);
    });

    it('shows a check the question and not its id', () => {
        const state = of('{"type":"noul","instructions":"Is it?","criteria":{"true":"Yes","false":"No"}}')?.asState();

        assert.deepEqual(Object.keys(state ?? {}), ['instructions', 'criteria']);
    });
});
