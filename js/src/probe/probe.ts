import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';
import type { Query } from '../query/query.js';
import type { ReviewedQuestion } from '../query/reviewedQuestion.js';
import { Note } from '../report/note.js';
import { Cause } from '../support/cause.js';
import { ChoiceAnswer, type SystemOneResponse } from '../typesafe/answers.js';
import type { Client } from '../typesafe/client.js';
import { TypeSafeError } from '../typesafe/errors.js';
import { QuestionBuilder } from './questionBuilder.js';
import { QuestionProbe } from './questionProbe.js';
import { Reading } from './reading.js';
import type { Baseline, Variant } from './variant.js';
import {
    CriteriaStripped,
    KeysHidden,
    LevelsReversed,
    NoulAsChoice,
    OptionsReversed,
    Reworded,
    Unchanged,
} from './variants.js';

/**
 * Runs the query, then runs rewrites of it that mean the same thing, and
 * reports how far each one moved the answer.
 *
 * The linter reports that a question is vague. This reports that your question,
 * against your state, answers 0.72 one way round and 0.31 the other.
 *
 * Movement is measured against the spread of the unchanged query repeated, so a
 * variant that moves less than the model's own jitter is reported as moving
 * nothing
 */
export class Probe {
    /**
     * The floor used when a run is too short to measure its own spread.
     *
     * TypeSafe's consistency cookbook publishes 0.0102 as the mean per-question
     * probability deviation over 15 repeats per condition, which is the nearest
     * published figure; where this one came from is not recorded here
     */
    static readonly PUBLISHED_NOISE = 0.0085;

    private callCount = 0;

    private tokenCount = 0;

    private readonly foundNotes: Note[] = [];

    /** Calls that failed or came back without answering */
    private unreachableCount = 0;

    constructor(private readonly client: Client) {}

    async run(query: Query, repeats = 5, extra: Variant[] = []): Promise<Map<string, QuestionProbe>> {
        if (!query.hasState()) {
            throw new JevLintError(Text.of('probe.needs_state'));
        }

        const probes = new Map<string, QuestionProbe>();
        const unsendable: string[] = [];

        for (const question of query.questions) {
            if (question.isKnownType()) {
                probes.set(question.id, new QuestionProbe(question));

                continue;
            }

            unsendable.push(question.id);
        }

        if (probes.size === 0) {
            throw new JevLintError(Text.of('probe.nothing_sendable'));
        }

        // A question of a type this cannot send is left out of every reading, so
        // a report that does not name it says nothing moved on a question it
        // never asked. `check` reports the same query as an error.
        if (unsendable.length > 0) {
            this.foundNotes.push(new Note(Text.of('probe.unsendable_questions', {
                ids: unsendable.join(', '),
                count: unsendable.length,
            }), 'skipped'));
        }

        const baseline = await this.baseline(query, probes, repeats);

        for (const variant of [...Probe.variants(), ...extra]) {
            await this.variant(query, probes, variant, baseline);
        }

        return probes;
    }

    static variants(): Variant[] {
        return [
            new CriteriaStripped(),
            new NoulAsChoice(),
            new OptionsReversed(),
            new KeysHidden(),
            new LevelsReversed(),
        ];
    }

    /** `rewordings` maps a variant name to a map of question id to its rewording */
    static rewordings(rewordings: Record<string, unknown>): Variant[] {
        const variants: Variant[] = [];

        // The built-ins and the baseline. Two rows under one name share a legend
        // line, and the footer's note about which rewrites are expected to move
        // would speak about the wrong one.
        const taken = ['unchanged', ...Probe.variants().map((variant) => variant.name())];

        for (const [name, instructions] of Object.entries(rewordings)) {
            if (taken.includes(name)) {
                throw JevLintError.of(JevLintError.USAGE, Text.of('probe.variant_name_taken', {
                    name,
                    taken: taken.join(', '),
                }));
            }

            // A file written as {"question_id": "text"} names no variant, and the
            // one input written by hand is the one that has to fail loudly.
            if (typeof instructions !== 'object' || instructions === null || Object.keys(instructions).length === 0) {
                throw JevLintError.of(JevLintError.USAGE, Text.of('probe.variant_not_a_map', { name }));
            }

            const strings: Record<string, string> = {};

            for (const [id, text] of Object.entries(instructions as Record<string, unknown>)) {
                if (typeof text !== 'string') {
                    throw JevLintError.of(JevLintError.USAGE, Text.of('probe.variant_not_text', {
                        name,
                        id,
                        type: phpType(text),
                    }));
                }

                strings[id] = text;
            }

            variants.push(new Reworded(name, strings));
        }

        return variants;
    }

    /**
     * Send the query unchanged, several times. The mean is what everything is
     * compared with; the spread is what counts as movement
     */
    private async baseline(
        query: Query,
        probes: Map<string, QuestionProbe>,
        repeats: number,
    ): Promise<Map<string, Baseline>> {
        const unchanged = new Unchanged();
        const meta = new Map<string, Baseline>();

        for (const [id, probe] of probes) {
            meta.set(id, { levels: probe.question.entries().length || 2 });
        }

        for (let run = 0; run < Math.max(1, repeats); run++) {
            const questions = new Map<string, ReviewedQuestion>(
                [...probes].map(([id, probe]) => [id, probe.question]),
            );
            const response = await this.send(query, questions);

            if (response === null) {
                continue;
            }

            for (const [id, probe] of probes) {
                const about = meta.get(id) ?? {};

                if (run === 0 && response.has(id)) {
                    const answer = response.answer(id);

                    if (answer instanceof ChoiceAnswer) {
                        about.winner = answer.choice();
                        probe.reading = Text.of('probe.reading_choice', { label: answer.choice() });
                    }

                    if (probe.question.type === 'score') {
                        probe.reading = Text.of('probe.reading_score', { levels: about.levels ?? 2 });
                    }

                    if (probe.question.type === 'noul') {
                        probe.reading = Text.of('probe.reading_yes');
                    }

                    meta.set(id, about);
                }

                const value = unchanged.read(response, probe.question, about);

                if (value !== null) {
                    probe.repeats.push(value);
                }
            }
        }

        return meta;
    }

    private async variant(
        query: Query,
        probes: Map<string, QuestionProbe>,
        variant: Variant,
        meta: Map<string, Baseline>,
    ): Promise<void> {
        const questions = new Map<string, ReviewedQuestion>();

        for (const [id, probe] of probes) {
            if (variant.applies(probe.question)) {
                questions.set(id, variant.apply(probe.question));
            }
        }

        if (questions.size === 0) {
            return;
        }

        const response = await this.send(query, questions);

        for (const [id, question] of questions) {
            probes.get(id)?.readings.push(new Reading(
                variant.name(),
                variant.describe(),
                response === null ? null : variant.read(response, question, meta.get(id) ?? {}),
                response === null ? Text.of('probe.call_failed') : null,
            ));
        }
    }

    private async send(query: Query, questions: Map<string, ReviewedQuestion>): Promise<SystemOneResponse | null> {
        const request = this.client.systemOne().state(query.state);

        for (const [id, question] of questions) {
            request.ask(id, QuestionBuilder.build(question));
        }

        let response: SystemOneResponse;

        try {
            response = await request.send();
        } catch (error) {
            if (!(error instanceof TypeSafeError)) {
                throw error;
            }

            this.foundNotes.push(new Note(error.message, 'unreachable', null, null, Cause.of(error)));
            this.unreachableCount++;

            return null;
        }

        const missing = [...questions.keys()].filter((id) => !response.has(id));

        if (missing.length > 0) {
            this.foundNotes.push(new Note(Text.of('probe.partial_answer', {
                answered: questions.size - missing.length,
                asked: questions.size,
                missing: missing[0] ?? '',
            }), 'unreachable', missing[0] ?? '', null, Cause.ANSWER));
            this.unreachableCount++;
        }

        this.callCount++;
        this.tokenCount += response.usage.totalTokens() ?? 0;

        return response;
    }

    calls(): number {
        return this.callCount;
    }

    unreachable(): number {
        return this.unreachableCount;
    }

    /** Whether every call this probe made came back with what it asked for */
    isComplete(): boolean {
        return this.unreachableCount === 0;
    }

    tokens(): number {
        return this.tokenCount;
    }

    notes(): Note[] {
        return this.foundNotes;
    }
}

/** `gettype`, which is what the message about a rewording's value names */
function phpType(value: unknown): string {
    if (value === null) return 'NULL';
    if (Array.isArray(value)) return 'array';

    switch (typeof value) {
        case 'number':
            return Number.isInteger(value) ? 'integer' : 'double';
        case 'boolean':
            return 'boolean';
        case 'object':
            return 'array';
        default:
            return typeof value;
    }
}
