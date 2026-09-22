import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';
import { entriesOf, keysOf, ordered, parse, stringify } from '../src/support/ordered.js';
import { Query } from '../src/query/query.js';
import { Patch } from '../src/report/patch.js';
import { OptionsReversed } from '../src/probe/variants.js';
import { QuestionBuilder } from '../src/probe/questionBuilder.js';

/**
 * A JavaScript object lists a key that looks like an array index first, and in
 * ascending numeric order however it was written. Option order changes answers,
 * so everything that reads a query has to see the order the file wrote
 */
describe('a key that looks like an array index', () => {
    it('is reordered by the platform parser', () => {
        assert.deepEqual(Object.keys(JSON.parse('{"30":"a","7":"b","x":"c"}') as object), ['7', '30', 'x']);
    });

    it('keeps its place through this one', () => {
        assert.deepEqual(keysOf(parse('{"30":"a","7":"b","x":"c"}') as object), ['30', '7', 'x']);
    });

    it('keeps its place on the way back out', () => {
        assert.equal(stringify(parse('{"30":"a","7":"b"}')), '{"30":"a","7":"b"}');
    });

    it('keeps its place through a query', () => {
        const query = Query.fromJson('{"state":"x","questions":{"2":{"type":"noul","instructions":"Is it?"},"1":{"type":"noul","instructions":"Or not?"}}}');

        assert.deepEqual(query.questions.map((question) => question.id), ['2', '1']);
    });

    it('keeps its place through a question criteria block', () => {
        const query = Query.fromJson('{"state":"x","questions":{"q":{"type":"choice","instructions":"Which?","criteria":{"30":"A month","7":"A week"}}}}');

        assert.deepEqual(query.questions[0]?.entries().map(([label]) => label), ['30', '7']);
    });

    it('is really reversed by the probe variant that reverses options', () => {
        const query = Query.fromJson('{"state":"x","questions":{"q":{"type":"choice","instructions":"Which?","criteria":{"7":"A week","30":"A month"}}}}');
        const question = query.questions[0];

        assert.ok(question);

        const reversed = new OptionsReversed().apply(question);

        assert.deepEqual(reversed.entries().map(([label]) => label), ['30', '7']);
        assert.equal(
            stringify(QuestionBuilder.build(reversed).toJSON()),
            '{"type":"choice","instructions":"Which?","criteria":{"30":"A month","7":"A week"}}',
        );
    });

    it('keeps its place through a patch', () => {
        const query = parse('{"questions":{"30":{"type":"noul"},"7":{"type":"noul"}}}') as Record<string, unknown>;
        const patched = new Patch('remove', '/questions/7').applyTo(query);

        assert.equal(stringify(patched), '{"questions":{"30":{"type":"noul"}}}');
    });

    it('keeps its place in an object this builds itself', () => {
        assert.deepEqual(keysOf(ordered([['30', 'a'], ['7', 'b']])), ['30', '7']);
    });
});

describe('the ordered writer', () => {
    it('writes what the platform writer writes, for everything else', () => {
        for (const text of [
            '{"a":1,"b":[1,2,{"c":null}],"d":"e"}',
            '[]',
            '{}',
            '{"a":{}}',
            '{"nested":{"deep":{"deeper":[true,false,null,1.5,-2,1e3]}}}',
            '{"escapes":"a\\"b\\\\c\\nd\\u00e9"}',
        ]) {
            const value = JSON.parse(text) as unknown;

            assert.equal(stringify(value), JSON.stringify(value), text);
            assert.equal(stringify(value, 4), JSON.stringify(value, null, 4), text);
        }
    });

    it('reads back what it wrote, for the whole catalogue', () => {
        const text = stringify(parse('{"a":[1,{"b":"c"}],"d":true}'), 4);

        assert.deepEqual(JSON.parse(text), { a: [1, { b: 'c' }], d: true });
    });
});

describe('entriesOf', () => {
    it('answers for an object that was never parsed', () => {
        assert.deepEqual(entriesOf({ a: 1, b: 2 }), [['a', 1], ['b', 2]]);
    });

    it('answers for keys added after the parse, recorded ones first', () => {
        const value = parse('{"b":1,"a":2}') as Record<string, unknown>;
        value['c'] = 3;

        assert.deepEqual(keysOf(value), ['b', 'a', 'c']);
    });
});
