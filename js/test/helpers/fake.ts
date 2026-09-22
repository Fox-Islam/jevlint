import { Client } from '../../src/typesafe/client.js';

/** One call the fake was asked to make, as the body that went out */
export interface Call {
    body: Record<string, unknown>;
}

/**
 * A client that answers from a table instead of calling anything, so the model
 * path runs in a test without a key and without a network.
 *
 * The SDK takes a `fetch`, so the whole of it - retries, error mapping, the
 * request body - runs exactly as it does against the API
 */
export function fakeClient(
    answers: Record<string, number | Record<string, unknown>> = {},
    fallback = 0.1,
    failWith: { status: number; body?: unknown } | null = null,
): { client: Client; calls: Call[] } {
    const calls: Call[] = [];

    const client = Client.make({
        apiKey: 'fake-key',
        // eslint-disable-next-line @typescript-eslint/require-await
        fetch: async (_input, init) => {
            const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
            calls.push({ body });

            if (failWith !== null) {
                return new Response(JSON.stringify(failWith.body ?? { error: 'no' }), {
                    status: failWith.status,
                    headers: { 'content-type': 'application/json' },
                });
            }

            const asked = (body['questions'] ?? {}) as Record<string, Record<string, unknown>>;
            const given: Record<string, unknown> = {};

            for (const [name, question] of Object.entries(asked)) {
                const answer = answers[name];

                if (typeof answer === 'object') {
                    given[name] = answer;

                    continue;
                }

                const value = answer ?? fallback;

                if (question['type'] === 'choice') {
                    const labels = Object.keys((question['criteria'] ?? {}) as Record<string, unknown>);
                    const pick = labels[0] ?? '';
                    given[name] = {
                        type: 'choice',
                        choice: pick,
                        confidence: value,
                        probabilities: Object.fromEntries(labels.map((label) => [label, label === pick ? value : 0])),
                    };

                    continue;
                }

                if (question['type'] === 'score') {
                    given[name] = { type: 'score', score: value, confidence: value, legend: {}, probabilities: {} };

                    continue;
                }

                given[name] = { type: 'noul', noul: value };
            }

            return new Response(JSON.stringify({
                model: 'jev-1.13.0',
                answers: given,
                usage: { input_tokens: 10, output_tokens: 2 },
            }), { status: 200, headers: { 'content-type': 'application/json' } });
        },
    });

    return { client, calls };
}
