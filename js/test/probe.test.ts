import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Probe } from '../src/probe/probe.js';
import { Query } from '../src/query/query.js';
import { Client } from '../src/typesafe/client.js';
import { QuestionProbe } from '../src/probe/questionProbe.js';
import { root } from './helpers/root.js';

/** A client whose answers are read off a list, one call at a time */
function replying(answers: ((name: string, type: string) => unknown)[]): Client {
    let at = 0;

    return Client.make({
        apiKey: 'fake-key',
        // eslint-disable-next-line @typescript-eslint/require-await
        fetch: async (_input, init) => {
            const body = JSON.parse(String(init?.body ?? '{}')) as { questions: Record<string, { type: string }> };
            const answer = answers[Math.min(at++, answers.length - 1)];
            const given: Record<string, unknown> = {};

            for (const [name, question] of Object.entries(body.questions)) {
                given[name] = answer?.(name, question.type);
            }

            return new Response(JSON.stringify({
                model: 'jev-1.13.0', answers: given, usage: { input_tokens: 1, output_tokens: 1 },
            }), { status: 200, headers: { 'content-type': 'application/json' } });
        },
    });
}

const noul = (value: number) => () => ({ type: 'noul', noul: value });
const choice = (value: number) => () => ({
    type: 'choice', choice: 'yes', confidence: value, probabilities: { yes: value, no: 1 - value },
});
const score = (value: number) => () => ({ type: 'score', score: value, confidence: 0.8, legend: {}, probabilities: {} });

const yesNo = (): Query => Query.fromObject({
    state: { ticket: 'I was charged twice for order A-104.' },
    questions: {
        refund: {
            type: 'noul',
            instructions: 'Does the customer ask for a refund?',
            criteria: { true: 'They ask for money back.', false: 'They report a problem only.' },
        },
    },
}, 'test');

describe('a question the query did not decide', () => {
    /**
     * A yes/no answer near the middle is the threshold's answer and not the
     * query's, whatever the rewrites do to it
     */
    it('is named when the answer sits near the middle', async () => {
        const probes = await new Probe(replying([
            ...Array<() => unknown>(6).fill(noul(0.58)), choice(0.58),
        ])).run(yesNo(), 5);
        const probe = probes.get('refund');

        assert.ok(probe);
        assert.equal(probe.undecided(), true);
        assert.equal(probe.flips(), false, 'Every repeat answered the same side of the middle.');
    });

    it('is left alone when the answer is decided', async () => {
        const probes = await new Probe(replying([
            ...Array<() => unknown>(6).fill(noul(0.9)), choice(0.9),
        ])).run(yesNo(), 5);

        assert.equal(probes.get('refund')?.undecided(), false);
    });

    /**
     * The repeats landing on both sides of the middle is the stronger fact: the
     * answer did not hold still from one send to the next
     */
    it('is flagged when the repeats fall on both sides', async () => {
        const probes = await new Probe(replying([
            noul(0.48), noul(0.55), noul(0.47), noul(0.52), noul(0.49), noul(0.5), choice(0.5),
        ])).run(yesNo(), 5);
        const probe = probes.get('refund');

        assert.ok(probe);
        assert.equal(probe.undecided(), true);
        assert.equal(probe.flips(), true);
    });

    /**
     * A Choice reports its winning label's own probability and a Score a
     * position on its scale, so neither is undecided for sitting halfway
     */
    it('is only asked of a yes/no question', async () => {
        const probes = await new Probe(replying([score(1.0)])).run(Query.fromObject({
            state: { ticket: 'x' },
            questions: {
                urgency: {
                    type: 'score',
                    instructions: 'How urgent is this ticket?',
                    criteria: ['Not urgent at all', 'Somewhat urgent', 'Blocking work right now'],
                },
            },
        }, 'test'), 3);
        const probe = probes.get('urgency');

        assert.ok(probe);
        assert.equal(probe.baseline(), 0.5);
        assert.equal(probe.undecided(), false, 'Halfway up a rubric is an answer, not an undecided one.');
        assert.equal(probe.flips(), false);
    });
});

/**
 * The README states the probe's thresholds as figures a reader takes on trust.
 * A constant moved without the page moving leaves the page describing a run
 * nobody can get.
 *
 * Each figure is matched inside the sentence that explains it, because the
 * README holds enough numbers that a bare search finds one somewhere whatever
 * the constant is set to
 */
describe('the figures the README prints', () => {
    // The README wraps, so a sentence is matched without its line breaks.
    const readme = readFileSync(join(root, 'README.md'), 'utf8').replace(/\s+/g, ' ');

    const figures: [string, number, number, string][] = [
        ['the band a yes/no answer is undecided inside', QuestionProbe.UNDECIDED, 2, 'within %s of the middle'],
        ['the movement too small to cross a threshold', QuestionProbe.NEGLIGIBLE, 2, 'three times that spread and %s'],
        ['the floor used where a run cannot measure its own', Probe.PUBLISHED_NOISE, 4, 'or %s where'],
    ];

    for (const [name, value, places, sentence] of figures) {
        it(`prints ${name}`, () => {
            const printed = value.toFixed(places).replace(/0+$/, '').replace(/\.$/, '');

            assert.ok(
                readme.includes(sentence.replace('%s', printed)),
                'The README explains this threshold with a figure the code does not use.',
            );
        });
    }
});

describe('a choice asked with its labels hidden', () => {
    const team = (technical: string | null): Query => Query.fromObject({
        state: { ticket: 'I was charged twice. Please refund the duplicate.' },
        questions: {
            team: {
                type: 'choice',
                instructions: 'Which team takes this ticket?',
                criteria: { billing: 'Charges and invoices', technical },
            },
        },
    }, 'test');
    const answered = (choice: string, probabilities: Record<string, number>) => () => ({
        type: 'choice', choice, confidence: 0.8, probabilities,
    });

    /**
     * The winner is second, so a readback that ignored position and took the
     * first option would read 0.35 here instead of 0.65
     */
    it('is read back at the winner\'s position', async () => {
        const probes = await new Probe(replying([
            ...Array<() => unknown>(6).fill(answered('technical', { billing: 0.2, technical: 0.8 })),
            answered('option_2', { option_1: 0.35, option_2: 0.65 }),
        ])).run(team('Something is broken'), 5);
        const probe = probes.get('team');
        const reading = probe?.readings.find((each) => each.variant === 'keys-hidden');

        assert.ok(probe && reading);
        assert.ok(Math.abs((probe.delta(reading) ?? 0) + 0.15) < 0.0001);
    });

    /** A label with no description is all that option means, so it is not hidden */
    it('is not asked when an option has no description', async () => {
        const probes = await new Probe(replying([
            answered('billing', { billing: 0.8, technical: 0.2 }),
        ])).run(team(null), 5);

        assert.deepEqual(probes.get('team')?.readings.map((each) => each.variant), ['options-reversed']);
    });
});
