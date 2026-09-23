import type { ReviewedQuestion } from '../query/reviewedQuestion.js';
import { Probe } from './probe.js';
import type { Reading } from './reading.js';

/** Every reading taken of one question, and what they add up to */
export class QuestionProbe {
    /** Movement smaller than this could not cross a threshold anybody sets */
    static readonly NEGLIGIBLE = 0.05;

    /**
     * How near the middle a yes/no answer sits before the threshold reading it
     * decides the outcome.
     *
     * A Noul answers with the probability of yes, and a caller turns that into
     * a decision at a threshold of their own. This band is a judgement and not
     * a measured figure: no corpus run sets it, and the probe reports what it
     * covers without gating on it
     */
    static readonly UNDECIDED = 0.15;

    public repeats: number[] = [];

    public readings: Reading[] = [];

    /** The label a Choice's probability belongs to, where the question is one */
    public reading: string | null = null;

    constructor(public readonly question: ReviewedQuestion) {}

    /**
     * Whether a rewrite moved the answer.
     *
     * The rule lives here so the table and the JSON cannot disagree about it:
     * movement counts when it clears both three times the repeat spread and a
     * size any threshold would notice
     */
    moved = (reading: Reading): boolean => {
        const delta = this.delta(reading);

        return delta !== null && Math.abs(delta) > 3 * this.floor() && Math.abs(delta) >= QuestionProbe.NEGLIGIBLE;
    };

    /**
     * Whether the query as written failed to decide this question.
     *
     * Only a Noul has a middle. A Choice reports the winning label's own
     * probability and a Score a position on its scale, and neither is undecided
     * for sitting halfway
     */
    undecided(): boolean {
        const baseline = this.baseline();

        return this.question.type === 'noul'
            && baseline !== null
            && Math.abs(baseline - 0.5) <= QuestionProbe.UNDECIDED;
    }

    /**
     * Whether the repeats of the unchanged query fell on both sides of the
     * middle, so the answer did not hold still from one send to the next
     */
    flips(): boolean {
        if (this.question.type !== 'noul' || this.repeats.length < 2) {
            return false;
        }

        return Math.min(...this.repeats) <= 0.5 && Math.max(...this.repeats) > 0.5;
    }

    baseline(): number | null {
        if (this.repeats.length === 0) {
            return null;
        }

        return this.repeats.reduce((sum, value) => sum + value, 0) / this.repeats.length;
    }

    /**
     * The spread of the unchanged query across its repeats.
     *
     * These repeats are sent back to back. Requests spread out over time vary
     * more than clustered ones, and nothing here sends them that way, so this is
     * a floor
     */
    noise(): number | null {
        const count = this.repeats.length;

        if (count < 2) {
            return null;
        }

        const mean = this.repeats.reduce((sum, value) => sum + value, 0) / count;
        const sum = this.repeats.reduce((total, value) => total + (value - mean) ** 2, 0);

        return Math.sqrt(sum / (count - 1));
    }

    /** The noise floor to compare against: the measured one, or the published one */
    floor(): number {
        return Math.max(this.noise() ?? 0.0, Probe.PUBLISHED_NOISE);
    }

    delta(reading: Reading): number | null {
        const baseline = this.baseline();

        if (baseline === null || reading.value === null) {
            return null;
        }

        return reading.value - baseline;
    }

    /** How far a variant moved the answer, in multiples of the noise floor */
    ratio(reading: Reading): number | null {
        const delta = this.delta(reading);

        return delta === null ? null : Math.abs(delta) / this.floor();
    }
}
