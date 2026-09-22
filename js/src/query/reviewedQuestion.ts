import { Text } from '../i18n/text.js';
import { Json } from '../support/json.js';
import { entriesOf } from '../support/ordered.js';

/** Instructions and criteria descriptions, which may be text or a JSON-ready value */
export type Content = string | unknown[] | Record<string, unknown> | null;

/** A `criteria` block: a map of labels, or an ordered list of levels */
export type Criteria = Record<string, unknown> | unknown[];

/** The primitives Jev takes. The catalogue is checked against this list, so a
 * check narrowed to a primitive that does not exist is refused at load */
export const PRIMITIVES = ['noul', 'choice', 'score'] as const;

/** One question from the query under review */
export class ReviewedQuestion {
    constructor(
        public readonly id: string,
        public readonly type: string,
        public readonly instructions: Content,
        public readonly criteria: Criteria | null,
        public readonly raw: Record<string, unknown>,
    ) {}

    /** The same question with other criteria, for a probe variant */
    withCriteria(criteria: Criteria | null): ReviewedQuestion {
        return new ReviewedQuestion(this.id, this.type, this.instructions, criteria, this.raw);
    }

    /** The same question asked in other words */
    withInstructions(instructions: string): ReviewedQuestion {
        return new ReviewedQuestion(this.id, this.type, instructions, this.criteria, this.raw);
    }

    static fromObject(id: string, data: Record<string, unknown>): ReviewedQuestion {
        const type = data['type'];
        const instructions = data['instructions'];
        const criteria = data['criteria'];

        return new ReviewedQuestion(
            id,
            typeof type === 'string' ? type.toLowerCase() : '',
            typeof instructions === 'string' || (typeof instructions === 'object' && instructions !== null)
                ? (instructions as Content)
                : null,
            typeof criteria === 'object' && criteria !== null ? (criteria as Criteria) : null,
            data,
        );
    }

    /**
     * Whether `criteria` was written as a JSON array.
     *
     * The shape survives decoding here, so this reads the value. An
     * implementation whose decoder collapses `{"0":"a","1":"b"}` into a list has
     * to carry the shape from the text instead
     */
    criteriaIsList(): boolean {
        return Array.isArray(this.criteria);
    }

    /** The criteria entries in order, as label and value pairs */
    entries(): [string, unknown][] {
        if (this.criteria === null) {
            return [];
        }

        return Array.isArray(this.criteria)
            ? this.criteria.map((value, index): [string, unknown] => [String(index), value])
            : entriesOf(this.criteria);
    }

    /** The instructions as one string, whatever structure they were given in */
    instructionsText(): string {
        if (this.instructions === null) {
            return '';
        }

        return typeof this.instructions === 'string' ? this.instructions : Json.inline(this.instructions);
    }

    hasCriteria(): boolean {
        return this.criteria !== null && this.entries().length > 0;
    }

    /**
     * Whether a Choice carries an option for what the others do not cover.
     *
     * A Score's levels are steps along one quality and cannot hold one, so this
     * is evidence the question is a Choice whatever else it looks like.
     */
    hasFallbackOption(): boolean {
        if (this.type !== 'choice' || this.criteria === null) {
            return false;
        }

        const labels = this.entries().map(([label]) => label.toLowerCase());
        const known = Text.list('words.fallback_labels');

        if (labels.some((label) => known.includes(label))) {
            return true;
        }

        // A catch-all can be called anything. Matching only a list of labels
        // missed one named `misc` and offered to add a second one beside it,
        // which splits the mass the catch-all exists to collect. What makes an
        // option a catch-all is what its description says it holds.
        const phrases = Text.list('words.catch_all_phrases');

        for (const [, description] of this.entries()) {
            if (typeof description !== 'string') {
                continue;
            }

            const text = description.toLowerCase();

            if (phrases.some((phrase) => text.includes(phrase))) {
                return true;
            }
        }

        return false;
    }

    isKnownType(): boolean {
        return (PRIMITIVES as readonly string[]).includes(this.type);
    }

    /**
     * What a question-scoped check is shown.
     *
     * The id is left out: Jev never sees it when the query runs, so the checker
     * should not see it either, or a well-named id papers over an instruction
     * that says nothing. The declared type is left out for a second reason -
     * `question/type-mismatch` works out which primitive fits the answer, and
     * naming the declared one in the state hands it what it is meant to decide.
     * Which checks apply to which type is settled in code before the call
     */
    asState(): Record<string, unknown> {
        const state: Record<string, unknown> = {
            instructions: this.instructions ?? '',
        };

        if (this.hasCriteria()) {
            state['criteria'] = this.criteria;
        }

        return state;
    }
}
