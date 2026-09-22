import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';
import { Catalogue } from '../src/catalogue/catalogue.js';
import { Linter } from '../src/lint/linter.js';
import { Query } from '../src/query/query.js';
import { Patch } from '../src/report/patch.js';
import { parse, stringify } from '../src/support/ordered.js';

describe('a patch', () => {
    it('is destructive whenever it takes a node out, whatever the caller passed', () => {
        assert.equal(new Patch('remove', '/questions/a', null, Patch.LOSSLESS).safety, Patch.DESTRUCTIVE);
    });

    it('writes no value for a remove, because there is nothing to write', () => {
        assert.deepEqual(new Patch('remove', '/questions/a').toObject(), {
            op: 'remove', path: '/questions/a', safety: 'destructive',
        });
    });

    it('leaves a questions block an object when the keys left run 0, 1, 2', () => {
        const query = parse('{"questions":{"0":{"type":"noul"},"1":{"type":"noul"},"2":{"type":"noul"}}}') as Record<string, unknown>;
        const patched = new Patch('remove', '/questions/2').applyTo(query);

        assert.equal(stringify(patched), '{"questions":{"0":{"type":"noul"},"1":{"type":"noul"}}}');
    });

    it('resolves an escaped pointer back to the key somebody wrote', () => {
        const query = parse('{"questions":{"a/b":{"type":"noul"},"c~d":{"type":"noul"}}}') as Record<string, unknown>;

        assert.equal(
            stringify(new Patch('remove', '/questions/a~1b').applyTo(query)),
            '{"questions":{"c~d":{"type":"noul"}}}',
        );
        assert.equal(
            stringify(new Patch('remove', '/questions/c~0d').applyTo(query)),
            '{"questions":{"a/b":{"type":"noul"}}}',
        );
    });

    it('leaves a query alone where there is nothing at the path to remove', () => {
        const query = parse('{"questions":{"a":{"type":"noul"}}}') as Record<string, unknown>;

        assert.equal(stringify(new Patch('remove', '/questions/b/c').applyTo(query)), stringify(query));
    });
});

/**
 * A patch is only worth offering where applying it clears the finding behind
 * it. Each of these is applied and the query re-checked
 */
describe('every patch the rules offer', () => {
    const catalogue = Catalogue.load();

    const cases: [string, string][] = [
        ['question/type-not-lowercase', '{"state":"x","questions":{"a":{"type":"NOUL","instructions":"Does the customer want money back?"}}}'],
        ['noul/criteria-shape', '{"state":"x","questions":{"a":{"type":"noul","instructions":"Does the customer want money back?","criteria":{"yes":"Y","no":"N"}}}}'],
        ['choice/criteria-shape', '{"state":"x","questions":{"a":{"type":"choice","instructions":"Which team should take this?","criteria":["billing","shipping","other"]}}}'],
        ['choice/no-fallback', '{"state":"x","questions":{"a":{"type":"choice","instructions":"Which team should take this?","criteria":{"billing":"Money things","shipping":"Delivery"}}}}'],
        ['score/criteria-shape', '{"state":"x","questions":{"a":{"type":"score","instructions":"How ready are they?","criteria":{"2":"Ready","0":"Not ready","1":"Nearly"}}}}'],
        ['query/unknown-key', '{"state":"x","extra":1,"questions":{"a":{"type":"noul","instructions":"Does the customer want money back?"}}}'],
    ];

    for (const [id, json] of cases) {
        it(`clears ${id} when it is applied`, async () => {
            const before = await Linter.rulesOnly(catalogue).check(Query.fromJson(json, 'test'));
            const finding = before.findings().find((found) => found.checkId === id);

            assert.ok(finding, `${id} did not fire on its own example.`);
            assert.ok(finding.patch, `${id} offered no patch.`);

            const patched = finding.patch.applyTo(parse(json) as Record<string, unknown>);
            const after = await Linter.rulesOnly(catalogue).check(Query.fromJson(stringify(patched), 'test'));

            assert.ok(
                !after.findings().some((found) => found.checkId === id),
                `${id} still fires after its own patch was applied.`,
            );
        });
    }

    /**
     * A shape patch rebuilds `criteria` from what is there, so it is offered
     * only where nothing the caller wrote goes missing on the way
     */
    const shapes: [string, string, boolean][] = [
        ['a score level with no text', '{"type":"score","instructions":"How urgent is it?","criteria":{"0":"","1":"Inconvenient","2":"Blocked"}}', false],
        ['score levels that are numbers', '{"type":"score","instructions":"How urgent is it?","criteria":{"0":10,"1":20}}', false],
        ['a score map of one', '{"type":"score","instructions":"How urgent is it?","criteria":{"0":"Only one"}}', false],
        ['score levels that are all text', '{"type":"score","instructions":"How urgent is it?","criteria":{"0":"Fine","1":"Bad"}}', true],
        ['choice options that are numbers', '{"type":"choice","instructions":"Which team takes it?","criteria":["0","1","2"]}', false],
        ['a choice list holding a nested option', '{"type":"choice","instructions":"Which team takes it?","criteria":["billing",{"technical":"broken"}]}', false],
        ['a choice list of labels', '{"type":"choice","instructions":"Which team takes it?","criteria":["billing","technical","other"]}', true],
        ['noul keys that differ only in case', '{"type":"noul","instructions":"Refund asked for?","criteria":{"yes":"Money back","YES":"Chargeback","no":"No"}}', false],
        ['noul keys written as yes and no', '{"type":"noul","instructions":"Refund asked for?","criteria":{"yes":"Money back","no":"No"}}', true],
    ];

    for (const [name, question, offered] of shapes) {
        it(`${offered ? 'offers a shape patch for' : 'offers none for'} ${name}`, async () => {
            const json = `{"state":{"t":"x"},"questions":{"q":${question}}}`;
            const report = await Linter.rulesOnly(catalogue).check(Query.fromJson(json, 'test'));
            const shape = report.findings().find((found) => found.checkId.endsWith('/criteria-shape'));

            assert.ok(shape, 'No shape finding was raised, so this case tests nothing.');
            assert.equal(shape.patch !== null, offered);

            // What a lossless patch has to keep is the text somebody wrote.
            // The keys are what it renames, which is the whole change.
            if (shape.patch?.safety === Patch.LOSSLESS) {
                const after = stringify(shape.patch.applyTo(parse(json) as Record<string, unknown>));

                for (const word of descriptions(parse(question))) {
                    assert.ok(after.includes(word), `A lossless patch dropped "${word}".`);
                }
            }
        });
    }
});

/**
 * A check that says a question should not be asked at all offers a patch that
 * removes it, and taking the last one out leaves a query this tool reports as
 * an error of its own
 */
describe('a patch that removes a question', () => {
    it('is not offered where it would leave the query asking nothing', () => {
        const check = Catalogue.load().written().find((found) => found.removes === 'question');

        assert.ok(check, 'No check removes a question, so this pins nothing.');
    });
});

/** Every string a caller wrote as content, which is every value and no key */
function descriptions(value: unknown): string[] {
    if (typeof value === 'string') {
        return [value];
    }

    if (Array.isArray(value)) {
        return value.flatMap(descriptions);
    }

    if (typeof value === 'object' && value !== null) {
        return Object.values(value).flatMap(descriptions);
    }

    return [];
}
