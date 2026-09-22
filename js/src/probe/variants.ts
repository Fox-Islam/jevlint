import { ReviewedQuestion } from '../query/reviewedQuestion.js';
import { ChoiceAnswer, ScoreAnswer, type SystemOneResponse } from '../typesafe/answers.js';
import { Variant, type Baseline } from './variant.js';
import { ordered } from '../support/ordered.js';

/**
 * The query exactly as written. Sent several times, it gives the spread every
 * other variant's movement is measured against
 */
export class Unchanged extends Variant {
    name(): string {
        return 'unchanged';
    }

    describe(): string {
        return 'the query as written';
    }
}

/**
 * The same instructions with the criteria removed.
 *
 * This variant changes the question, which the others do not. The gap it opens
 * is how much of the answer the criteria are carrying
 */
export class CriteriaStripped extends Variant {
    name(): string {
        return 'criteria-stripped';
    }

    describe(): string {
        return 'the instructions alone, with the criteria removed - the one rewrite here that changes the question';
    }

    override applies(question: ReviewedQuestion): boolean {
        // The criteria that reach the request, not the ones in the file. A Noul
        // is sent with `true` and `false` and nothing else, so criteria under any
        // other key never leave, and stripping them would send the baseline again
        // under the name of a rewrite.
        const criteria = (question.criteria ?? {}) as Record<string, unknown>;

        return question.type === 'noul'
            && (criteria['true'] !== undefined || criteria['false'] !== undefined);
    }

    override apply(question: ReviewedQuestion): ReviewedQuestion {
        return question.withCriteria(null);
    }
}

/**
 * The same yes/no question asked as a two-option Choice.
 *
 * The documented example has a Noul at 0.22 and the same question as a Choice
 * at 0.01 on the same ticket. Nothing guarantees the two agree, so a threshold
 * tuned on one does not carry to the other, and this measures the gap on your
 * question
 */
export class NoulAsChoice extends Variant {
    name(): string {
        return 'asked-as-choice';
    }

    describe(): string {
        return 'the same yes/no question asked as a two-option Choice';
    }

    override applies(question: ReviewedQuestion): boolean {
        return question.type === 'noul';
    }

    override apply(question: ReviewedQuestion): ReviewedQuestion {
        const criteria = (question.criteria ?? {}) as Record<string, unknown>;

        // A criterion written as a list of bullets is a shape the request takes.
        // Requiring a string here would replace it with a placeholder, and the
        // row would measure the criteria going missing as well as the primitive
        // changing.
        const describes = (value: unknown, fallback: string): unknown => (
            typeof value === 'string' || (typeof value === 'object' && value !== null) ? value : fallback
        );

        return new ReviewedQuestion(question.id, 'choice', question.instructions, {
            yes: describes(criteria['true'], 'The answer to the question is yes.'),
            no: describes(criteria['false'], 'The answer to the question is no.'),
        }, question.raw);
    }

    override read(response: SystemOneResponse, question: ReviewedQuestion, _baseline: Baseline): number | null {
        const answer = response.has(question.id) ? response.answer(question.id) : null;

        if (!(answer instanceof ChoiceAnswer)) {
            return null;
        }

        return answer.probabilityOf('yes');
    }
}

/**
 * The same Choice with its options listed back to front.
 *
 * Nothing about the question changes, so any movement comes from the order the
 * options were listed in, which the calling code has no way to see
 */
export class OptionsReversed extends Variant {
    name(): string {
        return 'options-reversed';
    }

    describe(): string {
        return 'the same options in the opposite order';
    }

    override applies(question: ReviewedQuestion): boolean {
        return question.type === 'choice' && question.entries().length > 1;
    }

    override apply(question: ReviewedQuestion): ReviewedQuestion {
        return question.withCriteria(ordered([...question.entries()].reverse()));
    }
}

/**
 * The same rubric with its levels in the opposite order, read back flipped.
 *
 * The rubric describes the same situations either way, and each level is
 * evaluated on its own, so the flipped reading should fall where the original
 * did. Where it does not, the scale is being read as an ordering instead of as
 * the descriptions it is made of
 */
export class LevelsReversed extends Variant {
    name(): string {
        return 'levels-reversed';
    }

    describe(): string {
        return 'the same levels in the opposite order, with the reading flipped back';
    }

    override applies(question: ReviewedQuestion): boolean {
        return question.type === 'score' && question.entries().length > 1;
    }

    override apply(question: ReviewedQuestion): ReviewedQuestion {
        return question.withCriteria([...question.entries().map(([, value]) => value)].reverse());
    }

    override read(response: SystemOneResponse, question: ReviewedQuestion, baseline: Baseline): number | null {
        const answer = response.has(question.id) ? response.answer(question.id) : null;

        if (!(answer instanceof ScoreAnswer)) {
            return null;
        }

        return 1.0 - (answer.score() / Math.max(1, (baseline.levels ?? 2) - 1));
    }
}

/**
 * A rewording you wrote yourself, read from `--variants`.
 *
 * A paraphrase belongs here, where you have judged it to mean the same thing.
 * When the answer then moves, the disagreement is between you and the model,
 * with no generator in between
 */
export class Reworded extends Variant {
    constructor(
        private readonly variantName: string,
        /** question id to its rewording */
        private readonly instructions: Record<string, string>,
    ) {
        super();
    }

    name(): string {
        return this.variantName;
    }

    describe(): string {
        return 'your rewording';
    }

    override applies(question: ReviewedQuestion): boolean {
        return this.instructions[question.id] !== undefined;
    }

    override apply(question: ReviewedQuestion): ReviewedQuestion {
        // `applies()` has already found the id, so there is nothing to fall back to.
        return question.withInstructions(this.instructions[question.id] ?? '');
    }
}
