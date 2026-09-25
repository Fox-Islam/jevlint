import { JevLintError } from '../exceptions/jevLintError.js';
import { CheckText } from '../i18n/checkText.js';
import { Text } from '../i18n/text.js';
import { Query } from '../query/query.js';
import { PRIMITIVES, type Criteria } from '../query/reviewedQuestion.js';
import { Severity } from '../report/severity.js';
import { Wording } from './wording.js';

/** A Jev version, as the catalogue and the command line write one */
export const VERSION = /^\d+(\.\d+)*$/;

/**
 * Compare two Jev versions, oldest first.
 *
 * Each dot-separated part is a number, so 1.9 comes before 1.13. Comparing them
 * as text puts 1.13 first and runs a query against the wrong build's rules
 */
export function compareVersions(a: string, b: string): number {
    const left = a.split('.').map(Number);
    const right = b.split('.').map(Number);

    for (let i = 0; i < Math.max(left.length, right.length); i++) {
        const difference = (left[i] ?? 0) - (right[i] ?? 0);

        if (difference !== 0) {
            return difference < 0 ? -1 : 1;
        }
    }

    return 0;
}

/** Answers that do not count as a finding */
export interface Suppression {
    answer: string;
    when: string;
}

/**
 * A question asked beside a check that overrules its verdict, and the reading it
 * takes. It asks something different from the check, so it decides on its own
 * instead of being averaged in with the check's wordings
 */
export interface SecondQuestion {
    wording: Wording;
    trigger: number;
}

/**
 * One entry from `checks/catalogue.json`.
 *
 * A static check names a rule implemented in code. A model check carries the
 * Jev question that decides it, and the probability above which that question's
 * answer becomes a finding
 */
export class Check {
    /** Conditions a `suppress` entry may name */
    static readonly SUPPRESSIONS = ['question_has_fallback_option'];

    /** The parts of a query `path()` can address */
    static readonly READS = ['query', 'state', 'field', 'instructions', 'criteria', 'type', 'question'];

    private constructor(
        public readonly id: string,
        public readonly title: string,
        public readonly mode: string,
        public readonly scope: string,
        public readonly appliesTo: string[],
        public readonly severity: string,
        public readonly rule: string | null,
        public readonly message: string | null,
        public readonly question: Record<string, unknown> | null,
        public readonly wordings: Wording[],
        public readonly trigger: number,
        public readonly requires: string | null,
        public readonly compare: string | null,
        public readonly hint: string,
        public readonly suggest: string,
        public readonly reads: string,
        public readonly action: string,
        public readonly locate: string | null,
        public readonly removes: string | null,
        public readonly locateMode: string,
        public readonly supersedes: string[],
        /** The documented failure modes this check is written against */
        public readonly jaggedness: string[],
        public readonly suppress: Suppression[],
        /**
         * Reading above its own trigger, one sets a finding aside and the other
         * raises one the check's own reading did not
         */
        public readonly clearedBy: SecondQuestion | null,
        public readonly firedBy: SecondQuestion | null,
        /**
         * Whether a reading under the trigger says nothing.
         *
         * A check whose clean and defective readings overlap is reported either
         * way, because silence from it would read as a clean bill of health
         */
        public readonly inconclusive: boolean,
        public readonly docs: string | null,
        public readonly advice: string,
        public readonly since: string | null,
        public readonly until: string | null,
    ) {}

    static fromObject(data: Record<string, unknown>): Check {
        const id = typeof data['id'] === 'string' ? data['id'] : '?';
        const trigger = data['trigger'];

        if (trigger !== null && trigger !== undefined
            && (typeof trigger !== 'number' || !Number.isFinite(trigger) || trigger < 0.3 || trigger > 0.95)) {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.trigger_out_of_range', {
                id,
                trigger: typeof trigger === 'object' ? typeof trigger : String(trigger),
            }));
        }

        for (const required of ['id', 'title', 'mode', 'scope', 'severity']) {
            if (typeof data[required] !== 'string') {
                throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.missing_field', { field: required }));
            }
        }

        // A severity nobody recognises cannot fall back to `warning`: one typo in
        // the catalogue would demote an error and a failing run would pass.
        const severities = Severity.cases().map((severity) => severity.value);

        if (!severities.includes(data['severity'] as never)) {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.bad_severity', {
                id,
                given: String(data['severity']),
                allowed: severities.join(', '),
            }));
        }

        const modes = ['static', 'model'];

        if (!modes.includes(String(data['mode']))) {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.bad_mode', {
                id,
                given: String(data['mode']),
                allowed: modes.join(', '),
            }));
        }

        if (data['mode'] === 'model' && (trigger === undefined || trigger === null)) {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.model_without_trigger', { id }));
        }

        // Every one of these is asked by name in the model linter. A check under
        // a scope it does not ask never runs.
        const scopes = ['question', 'state', 'state-field', 'state-once', 'query'];

        if (!scopes.includes(String(data['scope']))) {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.bad_scope', {
                id,
                given: String(data['scope']),
                allowed: scopes.join(', '),
            }));
        }

        const declared = data['applies_to'] ?? ['*'];
        const appliesTo = Array.isArray(declared)
            ? declared.filter((value): value is string => typeof value === 'string')
            : [];

        if (appliesTo.length === 0) {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.applies_to_nothing', { id }));
        }

        const since = bound(data, 'since', id);
        const until = bound(data, 'until', id);

        if (since !== null && until !== null && compareVersions(since, until) > 0) {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.empty_version_span', { id, since, until }));
        }

        const translated = CheckText.for(id);

        return new Check(
            id,
            translated['title'] ?? String(data['title']),
            String(data['mode']),
            String(data['scope']),
            appliesTo,
            String(data['severity']),
            text(data['rule']),
            translated['message'] ?? text(data['message']),
            typeof data['question'] === 'object' && data['question'] !== null ? data['question'] as Record<string, unknown> : null,
            readWordings(data),
            typeof trigger === 'number' ? trigger : 0.7,
            text(data['requires']),
            text(data['compare']),
            translated['hint'] ?? (text(data['hint']) ?? ''),
            translated['suggest'] ?? (text(data['suggest']) ?? ''),
            readsOf(data, id),
            text(data['action']) ?? 'rewrite',
            text(data['locate']),
            text(data['removes']),
            text(data['locate_mode']) ?? 'pick',
            strings(data['supersedes']),
            strings(data['jaggedness']),
            suppressions(data, id),
            secondQuestion(data, 'cleared_by', id),
            secondQuestion(data, 'fired_by', id),
            data['inconclusive'] === true,
            text(data['docs']),
            text(data['advice']) ?? '',
            since,
            until,
        );
    }

    /**
     * Whether this check is one of the rules for this Jev version.
     *
     * A defect one build reads past is a defect the next one may not have, so a
     * check retired by `until` keeps working for the versions it was written for
     */
    coversJev(version: string): boolean {
        if (this.since !== null && compareVersions(version, this.since) < 0) {
            return false;
        }

        return this.until === null || compareVersions(version, this.until) <= 0;
    }

    /** Whether this check is asked more than one way */
    isComposite(): boolean {
        return this.wordings.length > 1;
    }

    /**
     * Where in the query file the finding points, as a JSON pointer.
     *
     * An agent patching a query needs the node, not the question id
     */
    path(target: string, field: string | null = null): string {
        switch (this.reads) {
            case 'query':
                return '';
            case 'state':
                return '/state';
            case 'field':
                return `/state${pointer(field ?? '')}`;
            case 'instructions':
                return `/questions/${Check.escape(target)}/instructions`;
            case 'criteria':
                return `/questions/${Check.escape(target)}/criteria`;
            case 'type':
                return `/questions/${Check.escape(target)}/type`;
            default:
                // `reads` is checked against READS at load, so this is `question`
                // and not a typo that fell through.
                return `/questions/${Check.escape(target)}`;
        }
    }

    /**
     * One segment of an RFC 6901 pointer.
     *
     * A question id is a key somebody chose, so it can hold a `/` or a `~`, and
     * an unescaped one addresses a different node or none at all.
     */
    static escape(segment: string): string {
        return segment.replace(/~/g, '~0').replace(/\//g, '~1');
    }

    isStatic(): boolean {
        return this.mode === 'static';
    }

    isModel(): boolean {
        return this.mode === 'model';
    }

    /** Whether this check has anything to say about a question of this type */
    covers(type: string): boolean {
        return this.appliesTo.includes('*') || this.appliesTo.includes(type);
    }

    /** The key this check's answer comes back under, with `/` and `-` mapped to `_` */
    answerKey(): string {
        return this.id.replace(/[/-]/g, '_');
    }

    /** The question type this check asks, for a model check */
    questionType(): string {
        return this.wordings[0]?.type ?? 'noul';
    }

    /**
     * The check's own instructions, with `{field}` replaced where the check is
     * asked once per state field
     */
    instructions(field = ''): string {
        return this.wordings[0]?.instructions(field) ?? '';
    }

    criteria(): Criteria | null {
        return this.wordings[0]?.criteria ?? null;
    }
}

/**
 * A dotted field path as an RFC 6901 pointer.
 *
 * `application.role` addresses `/application/role`, and a `/` or `~` inside a
 * key is escaped so a key containing one still resolves
 */
function pointer(dotted: string): string {
    if (dotted === '') {
        return '';
    }

    return `/${Query.segments(dotted).map(Check.escape).join('/')}`;
}

/** One end of the range of Jev versions a check is written for */
function bound(data: Record<string, unknown>, key: string, id: string): string | null {
    const value = data[key] ?? null;

    if (value === null) {
        return null;
    }

    if (typeof value !== 'string' || !VERSION.test(value)) {
        throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.bad_version', {
            id,
            field: key,
            given: typeof value === 'object' ? typeof value : `"${String(value)}"`,
        }));
    }

    return value;
}

/**
 * Every way this check can be asked.
 *
 * `question` holds one wording, `questions` holds several. Several go in the
 * same call, so they cost the questions but not a round trip, and their answers
 * are combined
 */
function readWordings(data: Record<string, unknown>): Wording[] {
    const questions = data['questions'];

    if (Array.isArray(questions) && questions.length > 0) {
        return questions.map((wording) => Wording.fromObject(
            typeof wording === 'object' && wording !== null ? wording as Record<string, unknown> : {},
        ));
    }

    const question = data['question'];

    return typeof question === 'object' && question !== null
        ? [Wording.fromObject(question as Record<string, unknown>)]
        : [];
}

function secondQuestion(data: Record<string, unknown>, name: string, id: string): SecondQuestion | null {
    const declared = data[name];

    if (declared === undefined || declared === null) {
        return null;
    }

    const row = typeof declared === 'object' ? declared as Record<string, unknown> : {};
    const question = row['question'];
    const trigger = row['trigger'];

    if (typeof question !== 'object' || question === null
        || ((question as Record<string, unknown>)['type'] ?? 'noul') !== 'noul'
        || typeof (question as Record<string, unknown>)['instructions'] !== 'string'
        || typeof trigger !== 'number'
        || !(trigger > 0 && trigger < 1)) {
        throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.bad_second_question', { id, name }));
    }

    return { wording: Wording.fromObject(question as Record<string, unknown>), trigger };
}

function suppressions(data: Record<string, unknown>, id: string): Suppression[] {
    const declared = data['suppress'];
    const rules: Suppression[] = [];

    for (const rule of Array.isArray(declared) ? declared : []) {
        if (typeof rule !== 'object' || rule === null
            || typeof (rule as Record<string, unknown>)['answer'] !== 'string'
            || typeof (rule as Record<string, unknown>)['when'] !== 'string') {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.bad_suppress_entry', { id }));
        }

        const row = rule as { answer: string; when: string };

        if (!Check.SUPPRESSIONS.includes(row.when)) {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.unknown_suppression', {
                id,
                given: row.when,
                allowed: Check.SUPPRESSIONS.join(', '),
            }));
        }

        rules.push({ answer: row.answer, when: row.when });
    }

    return rules;
}

/**
 * Which part of the query a check looks at, checked against what `path()` knows
 * how to address. A typo would fall through to the default arm and report a
 * pointer to the question instead of the node, which reads as a real value
 */
function readsOf(data: Record<string, unknown>, id: string): string {
    const reads = data['reads'] ?? 'question';

    if (typeof reads !== 'string' || !Check.READS.includes(reads)) {
        throw JevLintError.of(JevLintError.CATALOGUE, Text.of('check.unknown_reads', {
            id,
            given: typeof reads === 'object' ? typeof reads : String(reads),
            allowed: Check.READS.join(', '),
        }));
    }

    return reads;
}

function text(value: unknown): string | null {
    return typeof value === 'string' ? value : null;
}

function strings(value: unknown): string[] {
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

export { PRIMITIVES };
