import { ChoiceAnswer, NoulAnswer, ScoreAnswer, type SystemOneResponse } from '../typesafe/answers.js';
import type { ReviewedQuestion } from '../query/reviewedQuestion.js';

/** What the unchanged run recorded about one question */
export interface Baseline {
    winner?: string;
    levels?: number;
}

/**
 * One meaning-preserving rewrite of a query, and how to read its answers back
 * onto the same scale as the original's.
 *
 * Every variant here is mechanical. A generated paraphrase would move both the
 * wording and whatever the generator took the question to mean, leaving the
 * spread attributable to neither
 */
export abstract class Variant {
    abstract name(): string;

    abstract describe(): string;

    /** Whether this variant changes anything about this question */
    applies(_question: ReviewedQuestion): boolean {
        return true;
    }

    apply(question: ReviewedQuestion): ReviewedQuestion {
        return question;
    }

    /** The answer as one number on [0, 1], comparable with the original's */
    read(response: SystemOneResponse, question: ReviewedQuestion, baseline: Baseline): number | null {
        if (!response.has(question.id)) {
            return null;
        }

        const answer = response.answer(question.id);

        if (answer instanceof NoulAnswer) {
            return answer.noul();
        }

        if (answer instanceof ChoiceAnswer) {
            return answer.probabilityOf(baseline.winner ?? answer.choice());
        }

        if (answer instanceof ScoreAnswer) {
            return answer.score() / Math.max(1, (baseline.levels ?? 2) - 1);
        }

        return null;
    }
}
