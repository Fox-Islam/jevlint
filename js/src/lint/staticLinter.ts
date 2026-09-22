import { Catalogue } from '../catalogue/catalogue.js';
import { Check } from '../catalogue/check.js';
import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';
import type { Query } from '../query/query.js';
import type { ReviewedQuestion } from '../query/reviewedQuestion.js';
import { Finding } from '../report/finding.js';
import { Patch } from '../report/patch.js';
import type { Report } from '../report/report.js';
import { Severity } from '../report/severity.js';
import { Json } from '../support/json.js';
import { RULES, type Rule } from './rules.js';
import { entriesOf, keysOf, ordered } from '../support/ordered.js';

/**
 * The rules that need no call: shapes the API rejects, and defects visible in
 * the structure instead of in the wording.
 *
 * These run first and always. A query that fails one of them either cannot be
 * sent or is broken in a way no amount of rephrasing fixes, and finding that
 * out should not cost a round trip
 */
export class StaticLinter {
    static readonly RULES = RULES;

    constructor(
        private readonly catalogue: Catalogue,
        private readonly maxStateChars = 20000,
        /** check ids to run, or all of them when empty */
        private readonly only: string[] = [],
    ) {}

    run(query: Query, report: Report): void {
        report.asked(this.applicable(query));
        this.queryRules(query, report);

        for (const question of query.questions) {
            this.questionRules(question, report);
        }
    }

    /**
     * How many static checks have anything to look at in this query.
     *
     * A question-scoped rule needs a question of a type it covers; a
     * query-scoped one always has the query
     */
    private applicable(query: Query): number {
        const types = [...new Set(query.questions.map((question) => question.type))];
        let applicable = 0;

        for (const check of this.catalogue.static()) {
            if (this.only.length > 0 && !this.only.includes(check.id)) {
                continue;
            }

            if (check.scope === 'query' || types.some((type) => check.covers(type))) {
                applicable++;
            }
        }

        return applicable;
    }

    private queryRules(query: Query, report: Report): void {
        if (query.questions.length === 0) {
            this.raise('query.noQuestions', 'query', report);

            return;
        }

        const seen = new Map<string, string>();

        for (const question of query.questions) {
            const text = question.instructionsText().trim();

            if (text === '') {
                continue;
            }

            const other = seen.get(text);

            if (other !== undefined) {
                this.raise(
                    'query.duplicateInstructions',
                    question.id,
                    report,
                    Text.of('evidence.identical_to', { other }),
                );

                continue;
            }

            seen.set(text, question.id);
        }

        const extra = keysOf(query.raw).filter((key) => !['state', 'questions', 'model'].includes(key));

        if (extra.length > 0) {
            // The keys as pointers, not only inside the sentence. An error whose
            // fix is "delete this key" gave a fixer nothing but prose to parse.
            this.raise(
                'query.unknownKey',
                'query',
                report,
                Text.of('evidence.found', { what: extra.map((key) => `\`${key}\``).join(', ') }),
                extra.length === 1 ? new Patch('remove', `/${Check.escape(extra[0] ?? '')}`) : null,
                extra.map((key) => `/${Check.escape(key)}`),
            );
        }

        if (!query.hasState()) {
            this.raise('state.missing', 'query', report);

            return;
        }

        const size = query.stateSize();

        if (size > this.maxStateChars) {
            this.raise(
                'state.oversized',
                'state',
                report,
                Text.of('evidence.state_size', { size, threshold: this.maxStateChars }),
            );
        }
    }

    private questionRules(question: ReviewedQuestion, report: Report): void {
        if (!question.isKnownType()) {
            this.raise('question.unknownType', question.id, report, Text.of('evidence.found_quoted', { what: question.type }));

            return;
        }

        const declared = question.raw['type'];

        if (typeof declared === 'string' && declared !== declared.toLowerCase()) {
            // The whole fix is one call to lower-case, so it is a patch and not
            // advice, and it addresses `type` and not the question around it.
            this.raise(
                'question.typeNotLowercase',
                question.id,
                report,
                Text.of('evidence.found_quoted', { what: declared }),
                new Patch(
                    'replace',
                    `/questions/${Check.escape(question.id)}/type`,
                    declared.toLowerCase(),
                    Patch.LOSSLESS,
                ),
            );
        }

        // `criteria` present but neither a list nor a map: a comma-separated
        // string reads as options to a person and is one value to the API.
        if (Object.hasOwn(question.raw, 'criteria')
            && (typeof question.raw['criteria'] !== 'object' || question.raw['criteria'] === null)) {
            this.raise(
                'question.criteriaNotAStructure',
                question.id,
                report,
                Text.of('evidence.found', { what: Json.inline(question.raw['criteria']) }),
            );
        }

        // `trim()` knows five ASCII characters. A non-breaking space, a
        // zero-width space or an ideographic space is an instruction carrying no
        // words, and the model answers a blank question instead of yours.
        if (question.instructionsText().replace(/[\s\p{Z}\p{C}]+/gu, '') === '') {
            this.raise('question.noInstructions', question.id, report);
        } else if (typeof question.instructions === 'object' && question.instructions !== null
            && words(question.instructions).trim() === '') {
            this.raise('question.instructionsEmpty', question.id, report);
        } else if (instructionIsId(question)) {
            this.raise(
                'question.instructionIsId',
                question.id,
                report,
                Text.of('evidence.instructions', { text: question.instructionsText() }),
            );
        }

        switch (question.type) {
            case 'noul':
                this.noulRules(question, report);
                break;
            case 'choice':
                this.choiceRules(question, report);
                break;
            case 'score':
                this.scoreRules(question, report);
                break;
            default:
                break;
        }
    }

    private noulRules(question: ReviewedQuestion, report: Report): void {
        if (!question.hasCriteria()) {
            this.raise('noul.noCriteria', question.id, report);

            return;
        }

        const entries = question.entries();
        const keys = entries.map(([key]) => key.toLowerCase());

        if (question.criteriaIsList() || keys.some((key) => key !== 'true' && key !== 'false')) {
            let renamed: Record<string, unknown> | null = null;

            // Two keys that differ only in case - `yes` beside `YES` - collapse
            // onto one renamed key, and the second description overwrites the
            // first. Nothing may be lost under a lossless patch, so where the
            // keys collide the advice stands without one.
            if (!question.criteriaIsList()
                && keys.every((key) => key === 'yes' || key === 'no')
                && new Set(keys).size === keys.length) {
                renamed = ordered(entries.map(
                    ([key, value]) => [key.toLowerCase() === 'yes' ? 'true' : 'false', value],
                ));
            }

            this.raise(
                'noul.criteriaShape',
                question.id,
                report,
                Text.of('evidence.keys', { keys: keys.length === 0 ? Text.of('evidence.none') : keys.join(', ') }),
                renamed === null
                    ? null
                    : new Patch('replace', `/questions/${Check.escape(question.id)}/criteria`, renamed, Patch.LOSSLESS),
            );
        }
    }

    private choiceRules(question: ReviewedQuestion, report: Report): void {
        const criteria = question.criteria;

        // `criteria` absent altogether, as opposed to the wrong shape, left every
        // Choice rule unreached and the query reported clean.
        if (criteria === null) {
            if (!Object.hasOwn(question.raw, 'criteria')) {
                this.raise('choice.noCriteria', question.id, report);
            }

            return;
        }

        if (Array.isArray(criteria)) {
            const labels = criteria.filter((value): value is string => typeof value === 'string');

            // Only where every entry is a label this can keep, and every label is
            // distinct. An entry that is a number or a nested object has no label
            // to carry over, and two entries spelled the same collapse onto one
            // key, so either way a patch here removes an option the caller wrote.
            const whole = labels.length === criteria.length && new Set(labels).size === labels.length;

            // Numeric-looking labels would be written back as a JSON array - the
            // very shape this check exists to refuse, so the patch would not
            // clear its own finding.
            const keyed = labels.every((label) => label !== '' && String(Number.parseInt(label, 10)) !== label);

            this.raise(
                'choice.criteriaShape',
                question.id,
                report,
                null,
                whole && keyed && labels.length >= 2
                    ? new Patch(
                        'replace',
                        `/questions/${Check.escape(question.id)}/criteria`,
                        ordered(labels.map((label) => [label, ''])),
                        Patch.LOSSY,
                    )
                    : null,
            );

            return;
        }

        const entries = question.entries();
        const labels = entries.map(([label]) => label);

        if (labels.length < 2) {
            this.raise('choice.tooFewOptions', question.id, report, Text.of('evidence.option_count', { count: labels.length }));
        }

        const notText = entries
            .map(([, value]) => value)
            .filter((value) => value !== null && typeof value !== 'string');

        if (notText.length > 0) {
            this.raise(
                'choice.descriptionNotText',
                question.id,
                report,
                Text.of('evidence.found', { what: Json.inline(notText[0]) }),
            );

            return;
        }

        const described = entries.filter(([, value]) => value !== null && value !== '' && !isEmptyArray(value));

        // One definition of a catch-all, on the question that owns it, so the
        // rule cannot offer to add a second one beside a catch-all it failed to
        // recognise by name.
        if (!question.hasFallbackOption()) {
            this.raise(
                'choice.noFallback',
                question.id,
                report,
                Text.of('evidence.options', { options: labels.join(', ') }),
                // Adding a fallback to options that carry no descriptions leaves
                // the criteria in a shape the next check rejects, so no patch
                described.length === 0
                    ? null
                    : new Patch(
                        'add',
                        `/questions/${Check.escape(question.id)}/criteria`,
                        ordered([...question.entries(), ['other', Text.of('patch.fallback_option')]]),
                        Patch.LOSSY,
                    ),
            );
        }

        if (described.length === 0) {
            this.raise('choice.undescribedOptions', question.id, report);
        }
    }

    private scoreRules(question: ReviewedQuestion, report: Report): void {
        const criteria = question.criteria;

        if (criteria === null) {
            if (!Object.hasOwn(question.raw, 'criteria')) {
                this.raise('score.noCriteria', question.id, report);
            }

            return;
        }

        const values = question.entries().map(([, value]) => value);
        const structured = values.filter((value) => typeof value === 'object' && value !== null);

        if (structured.length > 0) {
            this.raise(
                'score.levelsNotText',
                question.id,
                report,
                Text.of('evidence.found', { what: Json.inline(structured[0]) }),
            );

            return;
        }

        if (!Array.isArray(criteria)) {
            const entries = question.entries();

            // A Score is an ordered rubric, so the order of the list this becomes
            // is the meaning. Keys that are all numbers say what the order is,
            // and taking them in the order they happened to be written ships a
            // reversed scale that clears this check and is wrong.
            const numeric = entries.length > 0 && entries.every(([key]) => /^-?\d+$/.test(key));
            const inOrder = numeric
                ? [...entries].sort(([a], [b]) => Number(a) - Number(b))
                : entries;

            const levels = inOrder.map(([key, value]) => (typeof value === 'string' && value !== '' ? value : key));

            // Every level has to survive as the text somebody wrote. Where a
            // value is empty or is not text, the line above puts the key in its
            // place, and a rubric level replaced by its own index is content
            // lost under a patch that says nothing is.
            const describes = inOrder.every(([, value]) => typeof value === 'string' && value !== '');

            // A map of one is not a rubric, and a map of more than ten is past
            // what a Score takes, so reshaping either produces a file that fails
            // the query schema.
            const sized = inOrder.length >= 2 && inOrder.length <= 10;

            this.raise(
                'score.criteriaShape',
                question.id,
                report,
                numeric ? Text.of('evidence.keys_are_numbers') : Text.of('evidence.keys_are_names'),
                // Only where the keys say what the order is. With names, the
                // order of a map is the order it happened to be written in, and a
                // patch built from that ships a scrambled rubric that clears this
                // check. A caller applying patches unattended cannot read the
                // line above.
                numeric && describes && sized
                    ? new Patch('replace', `/questions/${Check.escape(question.id)}/criteria`, levels, Patch.LOSSLESS)
                    : null,
            );

            return;
        }

        const levels = criteria;

        if (levels.length < 2) {
            this.raise('score.tooFewLevels', question.id, report, Text.of('evidence.level_count', { count: levels.length }));

            return;
        }

        if (levels.length > 10) {
            this.raise('score.tooManyLevels', question.id, report, Text.of('evidence.level_count', { count: levels.length }));
        }

        const wordless = levels.filter(
            (level) => (typeof level !== 'object' || level === null) && !/\p{L}/u.test(scalar(level)),
        );

        if (wordless.length === levels.length) {
            this.raise(
                'score.numericLevels',
                question.id,
                report,
                Text.of('evidence.levels', { levels: levels.map(scalar).join(', ') }),
            );
        }
    }

    /** `paths` names every node at fault, where a finding names more than one */
    private raise(
        rule: Rule,
        target: string,
        report: Report,
        evidence: string | null = null,
        patch: Patch | null = null,
        paths: string[] = [],
    ): void {
        const check = this.catalogue.rule(rule);

        // A rule the catalogue does not name is a typo, not a condition.
        // Returning quietly drops the finding, turns a failing run green, and
        // leaves every test passing, so it is raised as the programming error it
        // is.
        if (check === null) {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.rule_unclaimed', { rule }));
        }

        if (this.only.length > 0 && !this.only.includes(check.id)) {
            return;
        }

        report.add(new Finding({
            checkId: check.id,
            title: check.title,
            severity: Severity.fromName(check.severity),
            target,
            message: check.message ?? check.title,
            hint: check.hint,
            suggest: check.suggest.split('{target}').join(target),
            advice: check.advice,
            mode: check.mode,
            action: check.action,
            path: paths.length === 0 ? check.path(target) : paths[0] ?? '',
            supersedes: check.supersedes,
            docs: check.docs,
            evidence,
            patch,
            paths,
        }));
    }
}

/** Every string anywhere inside a structured instruction */
function words(node: object): string {
    let text = '';

    for (const [, value] of entriesOf(node)) {
        text += typeof value === 'object' && value !== null
            ? words(value)
            : (typeof value === 'string' ? value : '');
    }

    return text;
}

/**
 * An instruction that says no more than the id does. Ids are never sent, so the
 * model sees nothing
 */
function instructionIsId(question: ReviewedQuestion): boolean {
    // Letters and digits in any script, so an accented word survives instead of
    // being cut into the pieces between its accents.
    const normalise = (value: string): string => value
        .toLowerCase()
        .replace(/[^\p{L}\p{N} ]+/gu, ' ')
        .trim();

    const id = normalise(question.id.replace(/[_\-.]/g, ' '));
    const instructions = normalise(question.instructionsText());

    if (id === '' || instructions === '') {
        return false;
    }

    const instructionWords = instructions.split(/\s+/);

    if (instructionWords.length > 4) {
        return false;
    }

    const idWords = id.split(/\s+/);

    // "Is the customer blocked?" is four words and contains the id, and it is a
    // whole question. What makes an instruction lean on its id is that it adds
    // nothing to it: "Refund requested?" beside `refund_requested` does, and the
    // grammar around it is not content.
    const grammar = Text.list('words.grammar');
    const content = instructionWords.filter((word) => !grammar.includes(word));

    if (content.some((word) => !idWords.includes(word))) {
        return false;
    }

    return idWords.every((word) => instructionWords.includes(word));
}

function scalar(value: unknown): string {
    if (typeof value === 'boolean') {
        return value ? '1' : '';
    }

    return value === null ? '' : String(value);
}

function isEmptyArray(value: unknown): boolean {
    return Array.isArray(value) && value.length === 0;
}
