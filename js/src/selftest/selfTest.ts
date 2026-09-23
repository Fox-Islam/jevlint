import { Catalogue } from '../catalogue/catalogue.js';
import type { Check } from '../catalogue/check.js';
import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';
import { ModelLinter } from '../lint/modelLinter.js';
import { ReviewedQuestion } from '../query/reviewedQuestion.js';
import { Json } from '../support/json.js';
import type { Client } from '../typesafe/client.js';
import { TypeSafeError } from '../typesafe/errors.js';
import { CheckScore } from './checkScore.js';

/**
 * Does each model check separate a clean question from a broken one?
 *
 * Every check ships one example it should fire on and one it should not. This
 * asks both and reports the span between them. A check whose span is small is
 * not measuring what its title claims, whatever it reports about your query
 */
export class SelfTest {
    /** Below this, a check is not telling clean and broken apart */
    static readonly FLAT = 0.15;

    /** Below this, it separates them, but not by much */
    static readonly WEAK = 0.30;

    constructor(
        private readonly catalogue: Catalogue,
        private readonly client: Client,
    ) {}

    async run(only: string[] = []): Promise<CheckScore[]> {
        const path = Catalogue.locate('fixtures.json');
        const data = Json.readFile(path);
        const results: CheckScore[] = [];
        const fixtures = Array.isArray(data['fixtures']) ? data['fixtures'] : [];

        for (const raw of fixtures) {
            const fixture = (typeof raw === 'object' && raw !== null ? raw : {}) as Record<string, unknown>;
            const id = typeof fixture['check'] === 'string' ? fixture['check'] : '';
            const check = this.catalogue.find(id);

            // A fixture naming a check that is not there is a typo in a file
            // nobody reads twice, and skipping it quietly took a check's second
            // domain out of the run while the summary still said it separated.
            // The same typo on the command line is refused loudly.
            if (check === null && this.catalogue.findWritten(id) === null) {
                throw JevLintError.of(JevLintError.CATALOGUE, Text.of('self_test.fixture_unknown_check', { path, id }));
            }

            if (check === null || (only.length > 0 && !only.includes(id))) {
                continue;
            }

            results.push(await this.score(check, fixture));
        }

        return results;
    }

    private async score(check: Check, fixture: Record<string, unknown>): Promise<CheckScore> {
        const clean = await this.probability(check, fixture['clean']);
        const broken = await this.probability(check, fixture['broken']);
        const offersFixed = fixture['fixed'] !== undefined;
        const fixed = offersFixed ? await this.probability(check, fixture['fixed']) : null;

        return new CheckScore(
            check,
            clean,
            broken,
            fixed,
            typeof fixture['domain'] === 'string' ? fixture['domain'] : '',
            offersFixed,
        );
    }

    /** The probability this check puts on its own defect being present */
    private async probability(check: Check, example: unknown): Promise<number | null> {
        if (typeof example !== 'object' || example === null || Array.isArray(example)) {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('self_test.fixture_missing_example', { id: check.id }));
        }

        const row = example as Record<string, unknown>;
        const field = typeof row['field'] === 'string' ? row['field'] : '';
        const linter = new ModelLinter(this.catalogue, this.client);
        const request = this.client.systemOne().state(state(check, row));
        const keys: string[] = [];

        const pair = Array.isArray(row['pair']) ? row['pair'] : null;

        for (const [index, wording] of check.wordings.entries()) {
            keys[index] = `${check.answerKey()}__w${index}`;
            const question = linter.build(wording, field);

            if (pair !== null && pair.length === 2) {
                question.instructions(wording.instructions().split('{pair}').join(
                    `"${String(pair[0])}" and "${String(pair[1])}"`,
                ));
            }

            request.ask(keys[index] ?? '', question);
        }

        let response;

        try {
            response = await request.send();
        } catch (error) {
            if (!(error instanceof TypeSafeError)) {
                throw error;
            }

            return null;
        }

        if (check.compare === 'type') {
            const declared = typeof row['type'] === 'string' ? row['type'] : '';

            return 1.0 - (response.choice(keys[0] ?? '').probabilityOf(declared) ?? 0.0);
        }

        // The wordings mean the same thing, so the check's answer is their mean
        const probabilities = keys.map((key) => response.noul(key).noul());

        return probabilities.reduce((sum, value) => sum + value, 0) / probabilities.length;
    }
}

function state(check: Check, example: Record<string, unknown>): Record<string, unknown> {
    if (check.scope === 'question') {
        return ReviewedQuestion.fromObject('fixture', example).asState();
    }

    // A query-scope check reads two questions, so its fixture holds the pair.
    if (check.scope === 'query') {
        return { questions: example['pair'] ?? [] };
    }

    // The same shape a run shows a state-scoped check. A fixture writes its
    // question as text where it carries no criteria, and as an object where it
    // does, so the two cannot drift apart.
    const question = example['question'] ?? '';

    return {
        question: typeof question === 'object' && question !== null ? question : { instructions: question },
        state: example['state'] ?? null,
    };
}
