import type { Question as SdkQuestion } from '@typesafe-ai/sdk';
import { TypeSafeError } from '@typesafe-ai/sdk';
import { entriesOf, ordered } from '../support/ordered.js';

/** Instructions, and every criterion description: text, a JSON-ready value, or nothing */
export type Content = string | unknown[] | Record<string, unknown> | null;

/**
 * A question put to the model, built up a call at a time.
 *
 * The SDK takes plain objects. These builders exist because a check and a
 * reviewed question are both assembled piece by piece from data, and because a
 * Choice's labels have to keep the order they were written in, which a plain
 * object does not do for a label that looks like an array index
 */
export abstract class Question {
    protected instructionsValue: Content = null;

    /** Set the question itself: text, a JSON-ready value, or nothing */
    instructions(instructions: Content): this {
        this.instructionsValue = instructions;

        return this;
    }

    getInstructions(): Content {
        return this.instructionsValue;
    }

    /** The discriminator the API uses to pick an answer shape */
    abstract type(): string;

    /** Reject a question the API would refuse, naming it as the caller keyed it */
    abstract validate(name: string): void;

    /** The criteria half of the request body */
    protected abstract payload(): Record<string, unknown>;

    toJSON(): Record<string, unknown> {
        return { type: this.type(), instructions: this.instructionsValue, ...this.payload() };
    }

    /** The question as the SDK takes it */
    toQuestion(): SdkQuestion {
        return this.toJSON() as unknown as SdkQuestion;
    }
}

/**
 * A yes/no question, answered with the probability of yes.
 *
 * @see https://docs.typesafe.ai/primitives/noul
 */
export class Noul extends Question {
    private yesValue: Content = null;

    private noValue: Content = null;

    private described = false;

    static ask(instructions: Content = null): Noul {
        return new Noul().instructions(instructions);
    }

    /** Describe what a yes answer means */
    yes(description: Content): this {
        this.yesValue = description;
        this.described = true;

        return this;
    }

    /** Describe what a no answer means */
    no(description: Content): this {
        this.noValue = description;
        this.described = true;

        return this;
    }

    type(): string {
        return 'noul';
    }

    validate(): void {
        // Both outcomes are optional: a noul question with no criteria is valid.
    }

    protected payload(): Record<string, unknown> {
        if (!this.described) {
            return {};
        }

        return { criteria: { true: this.yesValue, false: this.noValue } };
    }
}

/**
 * A question answered with one of several named labels.
 *
 * @see https://docs.typesafe.ai/primitives/choice
 */
export class Choice extends Question {
    private readonly criteria = new Map<string, Content>();

    static ask(instructions: Content = null): Choice {
        return new Choice().instructions(instructions);
    }

    /** Start from a set of labels, as a list of names or a map of name to description */
    static between(options: string[] | Record<string, Content>): Choice {
        return new Choice().options(options);
    }

    /** Add one label, with an optional description of when it applies */
    option(label: string, description: Content = null): this {
        this.criteria.set(label, description);

        return this;
    }

    /** Add several labels, as a list of names or a map of name to description */
    options(options: string[] | Record<string, Content>): this {
        if (Array.isArray(options)) {
            for (const label of options) {
                if (typeof label !== 'string') {
                    throw new TypeSafeError('Choice options given as a list must be label strings.');
                }

                this.option(label);
            }

            return this;
        }

        for (const [label, description] of entriesOf(options)) {
            this.option(label, description as Content);
        }

        return this;
    }

    getOptions(): Record<string, Content> {
        return ordered(this.criteria) as Record<string, Content>;
    }

    type(): string {
        return 'choice';
    }

    validate(name: string): void {
        if (this.criteria.size === 0) {
            throw new TypeSafeError(`Choice question "${name}" has no options; at least one label is required.`);
        }
    }

    protected payload(): Record<string, unknown> {
        // An object that lists its labels in the order they were added, whatever
        // they look like. A plain one puts `30` after `7`, and option order
        // changes answers.
        return { criteria: ordered(this.criteria) };
    }
}

/**
 * A question answered with a level on an ordered rubric, scored from zero.
 *
 * @see https://docs.typesafe.ai/primitives/score
 */
export class Score extends Question {
    private readonly criteria: Content[] = [];

    static ask(instructions: Content = null): Score {
        return new Score().instructions(instructions);
    }

    /** Start from a rubric: descriptions in order, indexed by score from zero */
    static rubric(levels: Content[]): Score {
        return new Score().levels(levels);
    }

    /** Append the next level of the rubric. The first call describes score 0 */
    level(description: Content): this {
        this.criteria.push(description);

        return this;
    }

    levels(levels: Content[]): this {
        for (const description of levels) {
            this.level(description);
        }

        return this;
    }

    getLevels(): Content[] {
        return [...this.criteria];
    }

    type(): string {
        return 'score';
    }

    validate(name: string): void {
        if (this.criteria.length < 2) {
            throw new TypeSafeError(
                `Score question "${name}" has ${this.criteria.length} level(s); a rubric needs at least two.`,
            );
        }
    }

    protected payload(): Record<string, unknown> {
        return { criteria: this.criteria };
    }
}
