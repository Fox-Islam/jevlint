import { TypeSafeError } from '@typesafe-ai/sdk';
import type { Content } from './questions.js';

/**
 * One question's answer. The SDK hands back plain objects; these wrap them so a
 * caller can ask what kind of answer it is, and so a shape mismatch surfaces
 * here rather than as a missing field further down
 */
export abstract class Answer {
    constructor(protected readonly data: Record<string, unknown>) {}

    /** The discriminator the API sent */
    abstract type(): string;

    toObject(): Record<string, unknown> {
        return this.data;
    }

    /** The answer class matching the payload's `type`, or `null` for one not modelled here */
    static fromObject(data: Record<string, unknown>): Answer | null {
        switch (data['type']) {
            case 'noul':
                return new NoulAnswer(data);
            case 'choice':
                return new ChoiceAnswer(data);
            case 'score':
                return new ScoreAnswer(data);
            default:
                return null;
        }
    }

    protected number(key: string): number {
        const value = this.data[key];

        if (typeof value !== 'number') {
            throw new TypeSafeError(`Expected a number for "${key}" in a ${this.type()} answer.`);
        }

        return value;
    }

    protected numberMap(key: string): Map<string, number> {
        const values = this.data[key] ?? {};

        if (typeof values !== 'object' || values === null) {
            throw new TypeSafeError(`Expected a map for "${key}" in a ${this.type()} answer.`);
        }

        const map = new Map<string, number>();

        for (const [name, value] of Object.entries(values as Record<string, unknown>)) {
            map.set(name, typeof value === 'number' ? value : Number(value) || 0);
        }

        return map;
    }
}

/** A yes/no answer */
export class NoulAnswer extends Answer {
    type(): string {
        return 'noul';
    }

    /** Probability of a yes answer, from zero to one */
    noul(): number {
        return this.number('noul');
    }
}

/** The label the model selected, with its probability across every label */
export class ChoiceAnswer extends Answer {
    type(): string {
        return 'choice';
    }

    choice(): string {
        const choice = this.data['choice'];

        return typeof choice === 'string' ? choice : '';
    }

    confidence(): number {
        return this.number('confidence');
    }

    probabilities(): Map<string, number> {
        return this.numberMap('probabilities');
    }

    /** The probability of one label, or `null` when the model did not report it */
    probabilityOf(label: string): number | null {
        return this.probabilities().get(label) ?? null;
    }
}

/** An expected score with the rubric it was drawn from */
export class ScoreAnswer extends Answer {
    type(): string {
        return 'score';
    }

    /** Expected score, which may fall between the integer rubric levels */
    score(): number {
        return this.number('score');
    }

    nearestLevel(): number {
        return Math.round(this.score());
    }

    confidence(): number {
        return this.number('confidence');
    }

    legend(): Map<number, Content> {
        const legend = this.data['legend'] ?? {};

        if (typeof legend !== 'object' || legend === null) {
            return new Map();
        }

        const keyed = new Map<number, Content>();

        for (const [score, description] of Object.entries(legend as Record<string, Content>)) {
            keyed.set(Number(score), description);
        }

        return keyed;
    }
}

/**
 * Token counts for a request, when the API reports them.
 *
 * A provider that reports none is not a call that cost nothing, so the two are
 * kept apart and the report says how many calls it could not price
 */
export class Usage {
    private constructor(
        public readonly inputTokens: number | null,
        public readonly outputTokens: number | null,
    ) {}

    static fromObject(data: Record<string, unknown> | undefined): Usage {
        return new Usage(asNumber(data?.['input_tokens']), asNumber(data?.['output_tokens']));
    }

    /** Input and output tokens combined, or `null` when neither was reported */
    totalTokens(): number | null {
        if (this.inputTokens === null && this.outputTokens === null) {
            return null;
        }

        return (this.inputTokens ?? 0) + (this.outputTokens ?? 0);
    }
}

function asNumber(value: unknown): number | null {
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Answers keyed by question name, with the model that produced them and the tokens they cost */
export class SystemOneResponse {
    private constructor(
        public readonly model: string,
        private readonly byName: Map<string, Answer>,
        public readonly usage: Usage,
    ) {}

    static fromObject(data: Record<string, unknown>): SystemOneResponse {
        const byName = new Map<string, Answer>();
        const raw = data['answers'];

        if (typeof raw === 'object' && raw !== null) {
            for (const [name, answer] of Object.entries(raw as Record<string, unknown>)) {
                if (typeof answer !== 'object' || answer === null) {
                    continue;
                }

                // An answer type a later API adds is left out rather than fatal.
                const built = Answer.fromObject(answer as Record<string, unknown>);

                if (built !== null) {
                    byName.set(name, built);
                }
            }
        }

        const model = data['model'];
        const usage = data['usage'];

        return new SystemOneResponse(
            typeof model === 'string' ? model : '',
            byName,
            Usage.fromObject(typeof usage === 'object' && usage !== null ? usage as Record<string, unknown> : undefined),
        );
    }

    answers(): Map<string, Answer> {
        return this.byName;
    }

    answer(name: string): Answer {
        const answer = this.byName.get(name);

        if (answer === undefined) {
            throw new TypeSafeError(
                `No answer named "${name}" in the response; got: ${this.byName.size === 0 ? 'none' : [...this.byName.keys()].join(', ')}.`,
            );
        }

        return answer;
    }

    has(name: string): boolean {
        return this.byName.has(name);
    }

    noul(name: string): NoulAnswer {
        return this.expect(name, NoulAnswer, 'noul');
    }

    choice(name: string): ChoiceAnswer {
        return this.expect(name, ChoiceAnswer, 'choice');
    }

    score(name: string): ScoreAnswer {
        return this.expect(name, ScoreAnswer, 'score');
    }

    private expect<T extends Answer>(name: string, expected: new (data: Record<string, unknown>) => T, wanted: string): T {
        const answer = this.answer(name);

        if (!(answer instanceof expected)) {
            throw new TypeSafeError(`Answer "${name}" is a ${answer.type()} answer, not ${wanted}.`);
        }

        return answer;
    }
}
