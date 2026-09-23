import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';
import { Json } from '../support/json.js';
import { ReviewedQuestion } from './reviewedQuestion.js';
import { entriesOf, ordered } from '../support/ordered.js';

/** What a query may carry as its state */
export type State = string | unknown[] | Record<string, unknown> | null;

/**
 * A Jev query as it would be sent: one state and the questions asked about it.
 *
 * The file format is the request body, so what you already send is what you
 * check. A `model` key is read if present and otherwise ignored
 */
export class Query {
    private constructor(
        public readonly state: State,
        public readonly questions: ReviewedQuestion[],
        public readonly model: string | null,
        public readonly source: string,
        /** the request as it was written */
        public readonly raw: Record<string, unknown> = {},
    ) {}

    /** The same query against state from somewhere else, for `probe --state` */
    withState(state: Record<string, unknown>): Query {
        return new Query(state, this.questions, this.model, this.source, ordered([...entriesOf(this.raw), ['state', state]]));
    }

    static fromFile(path: string): Query {
        return Query.fromJson(Json.contents(path), path);
    }

    /**
     * A query from the request body as it was written.
     *
     * `criteria` written as a JSON object and as a JSON array are different
     * requests, and this is the entry point that cannot get the two confused
     */
    static fromJson(json: string, source = 'query'): Query {
        // `[]` decodes to something the checks can walk, so a JSON list reached
        // them and came back as `query/no-questions` instead of a shape error.
        if (Json.isList(json)) {
            throw JevLintError.of(JevLintError.QUERY, Text.of('query.is_a_list', { source }));
        }

        return Query.fromObject(Json.decode(json, source), source);
    }

    static fromObject(data: Record<string, unknown>, source = 'query'): Query {
        const questions = data['questions'];

        if (questions !== null && questions !== undefined && (typeof questions !== 'object' || Array.isArray(questions))) {
            throw JevLintError.of(JevLintError.QUERY, Text.of('query.questions_is_a_list', { source }));
        }

        const reviewed: ReviewedQuestion[] = [];

        for (const [id, question] of entriesOf((questions ?? {}) as object)) {
            if (typeof question !== 'object' || question === null || Array.isArray(question)) {
                throw JevLintError.of(JevLintError.QUERY, Text.of('query.question_not_an_object', { source, id }));
            }

            reviewed.push(ReviewedQuestion.fromObject(id, question as Record<string, unknown>));
        }

        const state = data['state'] ?? null;

        // A number or a boolean here is a request the API rejects. Coercing it to
        // null reported the query as carrying no state, which is a different
        // defect and one the caller can exit 0 on.
        if (state !== null && typeof state !== 'string' && typeof state !== 'object') {
            throw JevLintError.of(JevLintError.QUERY, Text.of('query.state_wrong_type', {
                source,
                holds: typeof state === 'number'
                    ? Text.of('query.state_a_number')
                    : typeof state === 'boolean'
                        ? Text.of('query.state_a_boolean')
                        : `a ${typeof state}`,
            }));
        }

        const model = data['model'];

        return new Query(
            state as State,
            reviewed,
            typeof model === 'string' ? model : null,
            source,
            data,
        );
    }

    hasState(): boolean {
        if (this.state === null || this.state === '') {
            return false;
        }

        // An empty object is as much "no state" as an empty list: the request
        // goes out with nothing for the questions to read.
        if (typeof this.state === 'object') {
            return Array.isArray(this.state)
                ? this.state.length > 0
                : Object.keys(this.state).length > 0;
        }

        return true;
    }

    /** State as a JSON object, or null when it is a bare string or a list */
    stateFields(): Record<string, unknown> | null {
        return typeof this.state === 'object' && this.state !== null && !Array.isArray(this.state)
            ? this.state
            : null;
    }

    /**
     * The removable parts of the state, by dotted path.
     *
     * A state is commonly one object holding everything, so stopping at the top
     * level would ask whether that object is needed and never get a useful
     * answer. Nesting is followed to `depth` levels, however wide each one is:
     * a width limit would blind this on exactly the states it exists for
     */
    stateLeaves(depth = 2): string[] {
        const fields = this.stateFields();

        return fields === null ? [] : walk(fields, '', depth);
    }

    /**
     * A key with the separator in it, made safe to join with.
     *
     * A state key can hold a `.`, so joining it into a dotted path unescaped is
     * indistinguishable from nesting: the field `a.b` reads as `a` containing
     * `b`, and addresses a node that is not there.
     */
    static quote(segment: string): string {
        return segment.replace(/\\/g, '\\\\').replace(/\./g, '\\.');
    }

    /** A dotted path back into the keys it was built from */
    static segments(path: string): string[] {
        const parts: string[] = [];
        let current = '';
        let escaped = false;

        for (const char of path) {
            if (escaped) {
                current += char;
                escaped = false;

                continue;
            }

            if (char === '\\') {
                escaped = true;
            } else if (char === '.') {
                parts.push(current);
                current = '';
            } else {
                current += char;
            }
        }

        parts.push(current);

        return parts;
    }

    stateAt(path: string): unknown {
        let node: unknown = this.stateFields();

        for (const part of Query.segments(path)) {
            if (typeof node !== 'object' || node === null || Array.isArray(node) || !Object.hasOwn(node, part)) {
                return null;
            }

            node = (node as Record<string, unknown>)[part];
        }

        return node;
    }

    /**
     * The state's size, in characters.
     *
     * The threshold is described in characters, so this counts code points and
     * not the bytes a multi-byte state takes on the wire
     */
    stateSize(): number {
        return [...Json.inline(this.state ?? '')].length;
    }

    /**
     * The state a state-scoped check is shown: the question it is about, and
     * the material itself, each under a name the check can point at.
     *
     * The question goes in whole. Its `criteria` decide as much about whether a
     * query is any good as its instruction does, and a check shown the
     * instruction alone cannot tell a query that settles an edge case from one
     * that leaves it open
     */
    stateWith(question: ReviewedQuestion): Record<string, unknown> {
        return {
            question: question.asState(),
            state: this.state,
        };
    }

    /** The same query narrowed to some of its questions, for a cheap re-check */
    only(ids: string[]): Query {
        if (ids.length === 0) {
            return this;
        }

        return new Query(
            this.state,
            this.questions.filter((question) => ids.includes(question.id)),
            this.model,
            this.source,
            this.raw,
        );
    }

    question(id: string): ReviewedQuestion | null {
        return this.questions.find((question) => question.id === id) ?? null;
    }
}

function walk(node: Record<string, unknown>, prefix: string, depth: number): string[] {
    const paths: string[] = [];

    for (const [key, value] of entriesOf(node)) {
        const path = prefix === '' ? Query.quote(key) : `${prefix}.${Query.quote(key)}`;

        // Descend on size, not in spite of it. A width limit blinds the field
        // checks on exactly the states they exist for: the bigger the object,
        // the fewer fields they see, and a fifteen-field object reads as one
        // field nobody reads.
        const nest = depth > 1 && typeof value === 'object' && value !== null && !Array.isArray(value);

        if (nest) {
            paths.push(...walk(value as Record<string, unknown>, path, depth - 1));

            continue;
        }

        paths.push(path);
    }

    return paths;
}
