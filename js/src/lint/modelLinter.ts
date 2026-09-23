import type { Catalogue } from '../catalogue/catalogue.js';
import { Check } from '../catalogue/check.js';
import type { Wording } from '../catalogue/wording.js';
import { Text } from '../i18n/text.js';
import { Query } from '../query/query.js';
import type { ReviewedQuestion } from '../query/reviewedQuestion.js';
import { Finding } from '../report/finding.js';
import { Patch } from '../report/patch.js';
import type { Report } from '../report/report.js';
import { Severity } from '../report/severity.js';
import { Cause } from '../support/cause.js';
import { Json } from '../support/json.js';
import type { SystemOneResponse } from '../typesafe/answers.js';
import type { Client, SystemOne } from '../typesafe/client.js';
import { TypeSafeError } from '../typesafe/errors.js';
import { Choice, Noul } from '../typesafe/questions.js';
import { entriesOf, ordered } from '../support/ordered.js';

/** One check put on a call, with the keys its answers come back under */
interface Asked {
    check: Check;
    field: string | null;
    keys: string[];
    /** answer key to the element it is about */
    locator: Map<string, string>;
}

/**
 * The half that asks Jev about the query.
 *
 * Every check for one reviewed question goes in a single call, because a call
 * costs its round trip and not its question count. The question under review is
 * the state; the checks are the questions. State-scoped checks need the real
 * state in front of them, so they are a second call.
 *
 * A check may be asked several ways at once. The wordings are meant to mean the
 * same thing, so their mean is the answer and their spread is the error bar.
 *
 * Jev's answers about prompts are not calibrated against human judgement, so
 * every model finding carries the probability that produced it, and
 * `jevlint self-test` measures whether each check separates a clean question
 * from a broken one
 */
export class ModelLinter {
    /** Beyond this many questions the pairs outgrow one call */
    static readonly MOST_QUESTIONS = 12;

    /** How close to its trigger a probability has to be before the finding is a coin flip */
    static readonly NEAR = 0.05;

    /**
     * How close to its trigger a cleared reading has to be to be worth printing
     * without `--all`.
     *
     * `--all` costs nothing extra in calls but a whole second run to ask for,
     * and a check sitting just under its trigger is the reading a reader is most
     * likely to want. This is the band the corpus tables count as shaky
     */
    static readonly WORTH_SEEING = 0.1;

    /** field to question id to probability */
    /** check id to field to question id to probability */
    private fields = new Map<string, Map<string, Map<string, number>>>();


    /** How many questions the query under review holds */
    private questionCount = 0;

    /** Set when a call failed in a way every later call would repeat */
    private stopped = false;

    constructor(
        private readonly catalogue: Catalogue,
        private readonly client: Client,
        private readonly checkState = true,
        private readonly repeatCount = 1,
        /** check ids to run, or all of them when empty */
        private readonly only: string[] = [],
        private readonly reportAll = false,
        private readonly narrowed = false,
    ) {}

    private wanted(check: Check): boolean {
        return this.only.length === 0 || this.only.includes(check.id);
    }

    async run(query: Query, report: Report): Promise<void> {
        this.fields = new Map();
        this.stopped = false;
        this.questionCount = query.questions.length;
        const asked: string[] = [];
        const unreadable: string[] = [];

        for (const question of query.questions) {
            // Nothing here can read a question whose type is not one Jev answers
            // or whose instruction is blank. Skipping it in silence left a report
            // that could not be told from one where every check ran.
            if (!question.isKnownType() || question.instructionsText().trim() === '') {
                unreadable.push(question.id);

                continue;
            }

            asked.push(question.id);
            await this.askAboutQuestion(question, report);

            if (this.checkState && query.hasState()) {
                await this.askAboutState(query, question, report);
            }
        }

        if (unreadable.length > 0) {
            report.skipped(Text.of('skipped.unreadable_questions', {
                ids: unreadable.join(', '),
                count: unreadable.length,
            }), this.catalogue.modelChecks('question').length * unreadable.length);
        }

        // A check that asks whether a field serves the query cannot answer it
        // from some of the questions. Narrowed, it reads a field the hidden
        // questions use as one nothing reads, which is a wrong answer rather
        // than a partial one, so it is not asked.
        if (this.narrowed && this.fields.size > 0) {
            const fieldChecks = this.catalogue.modelChecks('state-field').length;

            report.skipped(Text.of('skipped.state_field_needs_whole_query', { count: fieldChecks }), fieldChecks);

            this.fields = new Map();
        }

        this.reportFields(asked, report);

        if (this.checkState && query.hasState()) {
            await this.askAboutStateAlone(query, report);
        } else if (this.checkState) {
            // A query with no state leaves every state-scoped check out. The only
            // other sign is a `state/missing` finding, which `--min=warning`
            // filters away.
            const stateScoped = ['state', 'state-field', 'state-once'].flatMap(
                (scope) => this.catalogue.modelChecks(scope).filter((check) => this.wanted(check)),
            );

            if (stateScoped.length > 0) {
                report.skipped(Text.of('skipped.no_state', { count: stateScoped.length }), stateScoped.length);
            }
        }

        await this.askAboutQuery(query, report);

        // Last, once every call has been made: anything that went into a call and
        // never came back with a verdict is a loss, whichever path lost it.
        report.reconcile();
    }

    /**
     * One call for the checks that read the question set.
     *
     * Every check but these sees one question at a time, so two questions that
     * ask the same thing in different words are invisible to all of them. The
     * pairs go in a single call, which is why this is affordable at all.
     */
    private async askAboutQuery(query: Query, report: Report): Promise<void> {
        const checks = this.catalogue.modelChecks('query').filter((check) => this.wanted(check));
        const questions = query.questions.filter(
            (question) => question.isKnownType() && question.instructionsText().trim() !== '',
        );

        if (checks.length === 0) {
            return;
        }

        // Not `unreachable`: nothing failed, and this check was never going to run
        // on a query this size. It is a note because the alternative is a report
        // that silently omits a check the caller may have asked for by name.
        if (questions.length > ModelLinter.MOST_QUESTIONS) {
            report.skipped(Text.of('skipped.too_many_questions', {
                questions: questions.length,
                most: ModelLinter.MOST_QUESTIONS,
            }), checks.length);

            return;
        }

        // One question makes no pairs. Returning bare left these checks out of a
        // report that then read as a full run.
        if (questions.length < 2) {
            report.skipped(Text.of('skipped.too_few_questions', { questions: questions.length }), checks.length);

            return;
        }

        report.asked(checks.length);
        const request = this.client.systemOne().state({
            questions: questions.map((question) => question.instructionsText()),
        });
        const pairs = new Map<string, [Check, ReviewedQuestion, ReviewedQuestion]>();

        for (const check of checks) {
            for (const [i, first] of questions.entries()) {
                for (const second of questions.slice(i + 1)) {
                    const key = `${check.answerKey()}__${slug(first.id)}__${slug(second.id)}`;

                    pairs.set(key, [check, first, second]);
                    request.ask(key, this.build(check.wordings[0] as Wording).instructions(
                        check.instructions().split('{pair}').join(`"${first.instructionsText()}" and "${second.instructionsText()}"`),
                    ));
                }
            }
        }

        if (pairs.size === 0) {
            return;
        }

        for (const [check, , second] of pairs.values()) {
            report.expecting(check.id, second.id);
        }

        const response = await this.send(request, 'query', report);

        if (response === null || !this.answered([...pairs.keys()], response, 'query', report)) {
            return;
        }

        for (const [key, [check, first, second]] of pairs) {
            if (!response.has(key)) {
                continue;
            }

            report.reached(check.id, second.id);
            const probability = reading(response, key);

            if (probability === null) {
                report.unreachable(second.id, Text.of('report.no_usable_reading', { key }));

                continue;
            }

            const fired = probability > check.trigger;

            if (!fired && !this.reportAll) {
                continue;
            }

            report.add(new Finding({
                checkId: check.id,
                title: Text.of('finding.pair_title', { title: check.title, first: first.id, second: second.id }),
                severity: Severity.fromName(check.severity),
                target: second.id,
                message: check.message ?? check.title,
                hint: check.hint,
                suggest: check.suggest,
                advice: check.advice,
                mode: check.mode,
                action: check.action,
                path: `/questions/${Check.escape(second.id)}`,
                trigger: check.trigger,
                nearTrigger: Math.abs(probability - check.trigger) <= ModelLinter.NEAR,
                docs: check.docs,
                probability,
                fired,
                evidence: Text.of('evidence.both_ask', {
                    first: shorten(first.instructionsText(), 70),
                    second: shorten(second.instructionsText(), 70),
                }),
                paths: [`/questions/${Check.escape(first.id)}`, `/questions/${Check.escape(second.id)}`],
            }));
        }
    }

    /**
     * Every question put on a call came back with an answer.
     *
     * A transport failure throws and is already handled. A 200 carrying none of
     * the keys that were asked for - an answer-key skew, a truncated payload, a
     * proxy answering on the endpoint's behalf - does not, and every check would
     * then be skipped one at a time by `has()` with nothing recorded. The run
     * would report a clean query it never looked at.
     */
    private answered(keys: string[], response: SystemOneResponse, target: string, report: Report): boolean {
        const missing = keys.filter((key) => !response.has(key));

        if (missing.length === 0) {
            return true;
        }

        report.unreachable(target, Text.of('report.partial_answer', {
            answered: keys.length - missing.length,
            asked: keys.length,
            missing: missing.length === 1
                ? `\`${missing[0] ?? ''}\``
                : `\`${missing[0] ?? ''}\` and ${missing.length - 1} more`,
        }));

        // Some answers are still answers. Only a call that came back with none of
        // what it was asked has nothing to record.
        return missing.length < keys.length;
    }

    /**
     * Send one call and record what it cost.
     *
     * A call that fails is a note on the report and a null here. One set of
     * checks that could not be asked is not a reason to abandon the rest.
     */
    private async send(request: SystemOne, target: string, report: Report): Promise<SystemOneResponse | null> {
        if (this.stopped) {
            return null;
        }

        try {
            const response = await request.send();

            report.recordCall(response.usage.totalTokens());
            report.answeredBy(response.model);

            return response;
        } catch (error) {
            if (!(error instanceof TypeSafeError)) {
                throw error;
            }

            // Counted: it left the machine and was paid for, and the client
            // retries twice before giving up, so one failed call is up to three
            // requests.
            report.recordCall(null);
            report.unreachable(target, error.message, Cause.of(error));

            // A wrong key answers every call the same way, so the rest of the run
            // is spent buying the same refusal again.
            if (Cause.isSettled(error)) {
                this.stopped = true;
            }

            return null;
        }
    }

    /**
     * One call for the checks that read the material and nothing else.
     *
     * Asking them once per question asked the same question of the same state
     * as many times as the query had questions
     */
    private async askAboutStateAlone(query: Query, report: Report): Promise<void> {
        const request = this.client.systemOne().state({ state: query.state });
        const asked: Asked[] = [];
        const parts = this.stateParts(query);

        for (const check of this.catalogue.modelChecks('state-once')) {
            if (this.wanted(check)) {
                asked.push(this.ask(request, check, null, parts));
            }
        }

        report.asked(asked.length);

        if (asked.length === 0) {
            return;
        }

        const keys = answerKeys(asked);

        for (const { check } of asked) {
            report.expecting(check.id, 'state');
        }

        const response = await this.send(request, 'state', report);

        if (response === null || !this.answered(keys, response, 'state', report)) {
            return;
        }

        for (const { check, keys: theseKeys, locator } of asked) {
            this.record(check, theseKeys, null, [response], 'state', report, null, locator);
        }
    }

    /** The state's own parts, as something to choose between */
    private stateParts(query: Query): Map<string, string> {
        const parts = new Map<string, string>();

        for (const path of query.stateLeaves()) {
            const value = Json.inline(query.stateAt(path));
            parts.set(path, shorten(value === '' ? path : value, 120));
        }

        return parts;
    }

    /** One finding per state field, however many questions were asked about it */
    private reportFields(asked: string[], report: Report): void {
        for (const check of this.catalogue.modelChecks('state-field')) {
            this.reportField(check, this.fields.get(check.id) ?? new Map(), asked, report);
        }
    }

    /** One finding per state field, for one check asked about every field */
    private reportField(check: Check, fields: Map<string, Map<string, number>>, asked: string[], report: Report): void {
        for (const [field, byQuestion] of fields) {
            if (byQuestion.size === 0) {
                continue;
            }

            const readings = [...byQuestion.values()];
            const unused = readings.filter((probability) => probability > check.trigger);

            const fired = unused.length === asked.length && asked.length > 0;

            // The verdict is that *every* question ignored the field, so the
            // statistic behind it is the weakest reading, not the average of
            // them. Publishing the mean printed 0.86 beside a cleared verdict
            // against a 0.75 trigger, which is a number arguing with itself.
            const decided = Math.min(...readings);

            if (!fired && !this.reportAll) {
                continue;
            }

            const read = { asked: asked.length === 1 ? asked[0] ?? '' : asked.join(', '), field };
            const evidence = fired
                ? Text.of('evidence.field_unread', read)
                : Text.of('evidence.field_read', read);

            report.add(new Finding({
                checkId: check.id,
                title: check.title.split('{field}').join(field),
                severity: Severity.fromName(check.severity),
                target: 'state',
                message: (check.message ?? check.title).split('{field}').join(field),
                hint: check.hint,
                suggest: check.suggest.split('{field}').join(field),
                advice: check.advice,
                mode: check.mode,
                action: check.action,
                path: check.path('state', field),
                trigger: check.trigger,
                nearTrigger: Math.abs(decided - check.trigger) <= ModelLinter.NEAR,
                supersedes: check.supersedes,
                docs: check.docs,
                probability: decided,
                readings: readings.length > 1 ? readings : [],
                readingsOf: readings.length > 1 ? Text.of('evidence.question_count', { count: readings.length }) : null,
                spread: readings.length > 1 ? Math.max(...readings) - Math.min(...readings) : null,
                fired,
                patch: this.removal(check, 'state', field),
                evidence,
            }));
        }
    }

    /** One call: every question-scoped check, with the question as the state */
    private async askAboutQuestion(question: ReviewedQuestion, report: Report): Promise<void> {
        const request = this.client.systemOne().state(question.asState());
        const asked: Asked[] = [];
        const elements = this.elements(question);

        for (const check of this.catalogue.modelChecks('question', question.type)) {
            if (!this.wanted(check)) {
                continue;
            }

            if (check.requires === 'criteria' && !question.hasCriteria()) {
                continue;
            }

            asked.push(this.ask(request, check, null, elements));
        }

        report.asked(asked.length);
        await this.collect(asked, request, question, question.id, report, question.asState());
    }

    /** One call: the state-scoped checks, with the real state in front of them */
    private async askAboutState(query: Query, question: ReviewedQuestion, report: Report): Promise<void> {
        const request = this.client.systemOne().state(query.stateWith(question));
        const asked: Asked[] = [];

        for (const check of this.catalogue.modelChecks('state', question.type)) {
            if (this.wanted(check)) {
                asked.push(this.ask(request, check));
            }
        }

        for (const check of this.catalogue.modelChecks('state-field', question.type)) {
            if (!this.wanted(check)) {
                continue;
            }

            const leaves = query.stateLeaves();

            // A state that is a string or a list has no named fields, so a check
            // asked once per field is asked zero times. Saying nothing left that
            // looking like a state whose every field was needed.
            if (leaves.length === 0) {
                report.skipped(Text.of('skipped.no_fields_to_name', { id: check.id }), 1);

                continue;
            }

            for (const field of leaves) {
                asked.push(this.ask(request, check, field));
            }
        }

        report.asked(asked.length);
        await this.collect(asked, request, question, question.id, report, query.stateWith(question));
    }

    /** Put every wording of one check on the request */
    private ask(request: SystemOne, check: Check, field: string | null = null, options = new Map<string, string>()): Asked {
        const keys: string[] = [];
        const suffix = field === null ? '' : `__${slug(field)}`;

        for (const [index, wording] of check.wordings.entries()) {
            const key = check.answerKey() + suffix + (check.isComposite() ? `__w${index}` : '');
            keys.push(key);
            request.ask(key, this.build(wording, field ?? ''));
        }

        const locator = new Map<string, string>();

        if (check.locate !== null && options.size > 1) {
            if (check.locateMode === 'each') {
                for (const [label, text] of options) {
                    const key = `${check.answerKey()}__where__${slug(label)}`;
                    locator.set(key, label);
                    request.ask(key, Noul.ask(check.locate.split('{element}').join(`"${text}"`)));
                }
            } else {
                const key = `${check.answerKey()}__where`;
                locator.set(key, '');
                request.ask(key, Choice.ask(check.locate).options(ordered(options) as Record<string, string>));
            }
        }

        return { check, field, keys, locator };
    }

    /** The reviewed question's own levels or options, as something to choose from */
    private elements(question: ReviewedQuestion): Map<string, string> {
        const options = new Map<string, string>();

        if (question.criteria === null || !question.hasCriteria()) {
            return options;
        }

        for (const [key, value] of question.entries()) {
            const label = question.criteriaIsList() ? `level_${key}` : key;
            const text = typeof value === 'string' ? value : Json.inline(value);
            options.set(label, text === '' ? label : text);
        }

        return options;
    }

    /** Turn one wording into the question that asks it */
    build(wording: Wording, field = ''): Noul | Choice {
        const criteria = wording.criteria ?? {};

        if (wording.type === 'choice') {
            const options = ordered(entriesOf(criteria).map(
                ([label, description]) => [label, typeof description === 'string' ? description : null],
            ));

            return Choice.ask(wording.instructions(field)).options(options as Record<string, string | null>);
        }

        const noul = Noul.ask(wording.instructions(field));
        const map = criteria as Record<string, unknown>;

        if (typeof map['true'] === 'string') {
            noul.yes(map['true']);
        }

        if (typeof map['false'] === 'string') {
            noul.no(map['false']);
        }

        return noul;
    }

    private async collect(
        asked: Asked[],
        request: SystemOne,
        question: ReviewedQuestion,
        target: string,
        report: Report,
        /** the state the first call used */
        state: Record<string, unknown>,
    ): Promise<void> {
        if (asked.length === 0) {
            return;
        }

        for (const { check } of asked) {
            report.expecting(check.id, target);
        }

        const responses: SystemOneResponse[] = [];

        for (let run = 0; run < Math.max(1, this.repeatCount); run++) {
            const response = await this.send(request, target, report);

            if (response !== null) {
                responses.push(response);
            }
        }

        if (responses.length === 0) {
            return;
        }

        const keys = answerKeys(asked);

        // Every response, not the first: a repeat can answer 200 with the answer
        // keys missing, and a verdict resting on the calls that did answer is
        // not the verdict the caller asked for.
        for (const response of responses) {
            if (!this.answered(keys, response, target, report)) {
                return;
            }
        }

        const extra = await this.settle(asked, responses, question, report, state);

        // The re-ask is a call like any other: if it answers nothing, the
        // borderline verdict it was asked to settle is still unsettled.
        for (const [checkId, settled] of extra) {
            for (const response of settled) {
                this.answered(keysFor(asked, checkId), response, target, report);
            }
        }

        for (const { check, field, keys: theseKeys, locator } of asked) {
            if (check.compare === 'type') {
                this.recordTypeComparison(check, theseKeys[0] ?? '', responses[0] as SystemOneResponse, question, target, report);

                continue;
            }

            this.record(
                check,
                theseKeys,
                field,
                [...responses, ...(extra.get(check.id) ?? [])],
                target,
                report,
                question,
                locator,
            );
        }
    }

    /**
     * Ask again, once, about every check whose first answer sat on its trigger.
     *
     * The repeats ride in a single call and only for the checks that need them,
     * so settling a borderline verdict costs one round trip however many are
     * borderline
     */
    private async settle(
        asked: Asked[],
        responses: SystemOneResponse[],
        question: ReviewedQuestion,
        report: Report,
        state: Record<string, unknown>,
    ): Promise<Map<string, SystemOneResponse[]>> {
        const out = new Map<string, SystemOneResponse[]>();

        if (responses.length === 0 || this.repeatCount > 1) {
            return out;
        }

        const borderline: Asked[] = [];

        for (const entry of asked) {
            const { check, keys } = entry;

            if (check.compare === 'type' || check.scope === 'state-field') {
                continue;
            }

            const values: number[] = [];

            for (const response of responses) {
                for (const key of keys) {
                    const value = reading(response, key);

                    if (value !== null) {
                        values.push(value);
                    }
                }
            }

            if (values.length > 0 && Math.abs(mean(values) - check.trigger) <= ModelLinter.NEAR) {
                borderline.push(entry);
            }
        }

        if (borderline.length === 0) {
            return out;
        }

        // The same state the first call used. Rebuilding it from the question
        // alone showed a state-scoped check `{instructions, criteria}` when its
        // wording asks about `question` and `state`, so the re-ask answered a
        // question that was not on the page and was averaged in regardless.
        const request = this.client.systemOne().state(state);

        for (const { check, keys } of borderline) {
            for (const [index, wording] of check.wordings.entries()) {
                request.ask(keys[index] ?? `${check.answerKey()}__w${index}`, this.build(wording));
            }
        }

        let again: SystemOneResponse;

        try {
            again = await request.send();
        } catch (error) {
            if (!(error instanceof TypeSafeError)) {
                throw error;
            }

            // The first readings still stand, but the borderline ones were not
            // settled, and a run that swallows that reads like one that settled
            // them.
            report.unreachable(
                question.id,
                Text.of('report.resettle_failed', { detail: error.message }),
                Cause.of(error),
            );

            return out;
        }

        report.recordCall(again.usage.totalTokens());

        for (const { check } of borderline) {
            out.set(check.id, [again]);
        }

        return out;
    }

    private record(
        check: Check,
        keys: string[],
        field: string | null,
        responses: SystemOneResponse[],
        target: string,
        report: Report,
        question: ReviewedQuestion | null = null,
        locator = new Map<string, string>(),
    ): void {
        const probabilities: number[] = [];
        // Per call as well as pooled. Two wordings that disagree the same way
        // every run are an error bar on one verdict, not a verdict that moves.
        const perCall: number[] = [];

        for (const response of responses) {
            const thisCall: number[] = [];

            for (const key of keys) {
                const value = reading(response, key);

                if (value !== null) {
                    probabilities.push(value);
                    thisCall.push(value);
                }
            }

            if (thisCall.length > 0) {
                perCall.push(mean(thisCall));
            }
        }

        // No reading survived: every one was missing or outside 0..1. The check
        // reached no verdict, so it is a loss and not a clear.
        if (probabilities.length === 0) {
            report.unreachable(target, Text.of('report.no_reading_from', { id: check.id, questions: keys.length }));

            return;
        }

        const average = mean(probabilities);
        report.reached(check.id, target);

        if (check.scope === 'state-field' && field !== null) {
            const byField = this.fields.get(check.id) ?? new Map<string, Map<string, number>>();
            const byQuestion = byField.get(field) ?? new Map<string, number>();
            byQuestion.set(target, average);
            byField.set(field, byQuestion);
            this.fields.set(check.id, byField);

            return;
        }

        const fired = average > check.trigger;
        // Across calls, not across wordings: `undecided` says another run might
        // answer differently, so what has to straddle the trigger is what a run
        // produces, which is the mean of its wordings. The spread over the
        // wordings is reported either way.
        const unstable = perCall.length > 1
            && Math.min(...perCall) <= check.trigger
            && Math.max(...perCall) > check.trigger;

        // A cleared check within touching distance of its trigger is kept even
        // without `--all`, because the reading is already paid for and it is the
        // one a reader would otherwise re-run the whole query to see.
        const worthSeeing = Math.abs(average - check.trigger) <= ModelLinter.WORTH_SEEING;

        // An `inconclusive` check is reported either way: dropping it when it
        // clears would say the defect is absent, which is the one thing its
        // reading cannot tell you.
        if (!fired && !unstable && !worthSeeing && !check.inconclusive && !this.reportAll) {
            return;
        }

        const elements = fired && locator.size > 0 ? locate(locator, responses[0] as SystemOneResponse) : [];
        const element = elements.length === 1 ? elements[0] ?? null : null;

        report.add(new Finding({
            checkId: check.id,
            title: element !== null
                ? Text.of('finding.title_with_detail', { title: check.title, detail: describe(element, question) })
                : elements.length > 0
                    ? Text.of('finding.title_with_detail', {
                        title: check.title,
                        detail: elements.map((found) => describe(found, question)).join(', '),
                    })
                    : field !== null
                        ? Text.of('finding.title_with_field', { title: check.title, field })
                        : check.title,
            severity: Severity.fromName(check.severity),
            target,
            message: (check.message ?? check.title).split('{field}').join(field ?? ''),
            hint: check.hint,
            suggest: check.suggest.split('{target}').join(target).split('{field}').join(field ?? ''),
            advice: check.advice,
            mode: check.mode,
            action: check.action,
            path: check.path(target, field) + (element === null ? '' : `/${pointerFor(check, element)}`),
            paths: elements.map((found) => `${check.path(target, field)}/${pointerFor(check, found)}`),
            trigger: check.trigger,
            spread: probabilities.length > 1 ? Math.max(...probabilities) - Math.min(...probabilities) : null,
            nearTrigger: Math.abs(average - check.trigger) <= ModelLinter.NEAR,
            supersedes: check.supersedes,
            docs: check.docs,
            probability: average,
            fired,
            unstable,
            patch: this.removal(check, target, field),
            evidence: evidenceFor(field, check, question, element),
            readings: probabilities.length > 1 ? probabilities : [],
            readingsOf: probabilities.length > 1
                ? readingsOf(keys.length, responses.length, this.repeatCount)
                : null,
        }));
    }

    /**
     * The node a finding says to delete, where deleting one node is the fix.
     *
     * Rewording a question that asks Jev for arithmetic leaves the arithmetic
     * with Jev. The fix is to take the question out and do the work in code
     */
    private removal(check: Check, target: string, field: string | null): Patch | null {
        if (check.removes === 'question') {
            // Taking the last question out leaves a query that asks nothing,
            // which this tool reports as an error of its own. The suggestion
            // still stands - the work belongs in code - but it is not a change
            // anything can apply on its own, so no patch is offered.
            return this.questionCount > 1
                ? new Patch('remove', `/questions/${Check.escape(target)}`, null, Patch.DESTRUCTIVE)
                : null;
        }

        if (check.removes === 'field') {
            return field === null
                ? null
                : new Patch('remove', check.path('state', field), null, Patch.DESTRUCTIVE);
        }

        return null;
    }

    /**
     * The type check asks how the options in `criteria` relate to each other,
     * and picks the primitive that fits. The finding is the disagreement with
     * what the query declared
     */
    private recordTypeComparison(
        check: Check,
        key: string,
        response: SystemOneResponse,
        question: ReviewedQuestion,
        target: string,
        report: Report,
    ): void {
        report.reached(check.id, target);

        if (!response.has(key)) {
            return;
        }

        const answer = response.choice(key);
        const picked = answer.choice();

        // How strongly the declared type is read as the wrong one. Defined the
        // same way whichever type the check picks, so a run that agrees with the
        // query still produces a reading, and `--all` can report it. Taking the
        // picked type's own probability instead left the check with no reading at
        // all wherever it agreed, and a firing rate whose denominator was the
        // questions it had already disagreed about.
        const probability = 1.0 - (answer.probabilityOf(question.type) ?? 0.0);

        const setAside = picked !== question.type && this.suppressed(check, picked, question);
        const agrees = picked === question.type || setAside;

        const fired = !agrees && probability > check.trigger;

        if (!fired && !this.reportAll) {
            return;
        }

        const message = agrees
            ? Text.of('type.agrees', { declared: question.type })
            : picked === 'other'
                ? Text.of('type.none_fits', { declared: question.type })
                : Text.of('type.looks_like', { picked, declared: question.type });

        report.add(new Finding({
            checkId: check.id,
            title: check.title,
            severity: Severity.fromName(check.severity),
            target,
            message,
            hint: check.hint,
            suggest: check.suggest,
            advice: check.advice,
            mode: check.mode,
            action: check.action,
            path: check.path(target),
            clearedBecause: setAside ? Text.of('type.suppressed_catch_all', { picked }) : '',
            trigger: check.trigger,
            nearTrigger: Math.abs(probability - check.trigger) <= ModelLinter.NEAR,
            supersedes: check.supersedes,
            suggestedType: agrees || picked === 'other' ? null : picked,
            docs: check.docs,
            // Not a probability that anything is wrong, and not the weight on the
            // primitive this picked either: one minus the weight on the primitive
            // the question declares, so it covers every other primitive at once.
            // `evidence` carries the picked one's own weight.
            measure: 'weight',
            probability,
            fired,
            evidence: Text.of('type.evidence', {
                picked,
                picked_weight: answer.probabilityOf(picked) ?? 0.0,
                declared: question.type,
                declared_weight: answer.probabilityOf(question.type) ?? 0.0,
            }),
        }));
    }

    /**
     * Whether the catalogue says this answer does not count as a finding.
     *
     * The conditions live in `suppress` and not here, so an implementation in
     * another language reads the same rule out of the same file
     */
    private suppressed(check: Check, answer: string, question: ReviewedQuestion): boolean {
        for (const rule of check.suppress) {
            if (rule.answer !== answer) {
                continue;
            }

            if (rule.when === 'question_has_fallback_option' && question.hasFallbackOption()) {
                return true;
            }
        }

        return false;
    }
}

/**
 * An id as an answer key, without losing which id it was.
 *
 * Collapsing every run of punctuation to `_` made `a.b`, `a-b` and `a_b` the
 * same key, so one of them silently replaced the others on the request and the
 * reading that came back was reported against whichever name was asked last.
 * Each byte that cannot appear in a key becomes its own escape, so two different
 * ids cannot produce one key
 */
function slug(id: string): string {
    return [...Buffer.from(id, 'utf8')]
        .map((byte) => {
            const character = String.fromCharCode(byte);

            return /[a-zA-Z0-9]/.test(character) ? character : `_${byte.toString(16).padStart(2, '0')}`;
        })
        .join('');
}

/**
 * One reading, or null if it is not a probability.
 *
 * A calibrated answer is between 0 and 1. A response carrying anything else is
 * not a reading this can compare against a trigger, and reporting it verbatim
 * produced findings at 1.50 on a query with nothing wrong with it
 */
function reading(response: SystemOneResponse, key: string): number | null {
    if (!response.has(key)) {
        return null;
    }

    const value = response.noul(key).noul();

    return value >= 0.0 && value <= 1.0 ? value : null;
}

/** Every answer key a call carries, the locators among them */
function answerKeys(asked: Asked[]): string[] {
    return asked.flatMap(({ keys, locator }) => [...keys, ...locator.keys()]);
}

/** The answer keys one check was asked under */
function keysFor(asked: Asked[], checkId: string): string[] {
    return asked.find(({ check }) => check.id === checkId)?.keys ?? [];
}

function evidenceFor(
    field: string | null,
    check: Check,
    question: ReviewedQuestion | null,
    element: string | null,
): string | null {
    const parts: string[] = [];

    if (element !== null && question !== null) {
        const key = element.startsWith('level_') ? element.slice(6) : element;
        const found = question.entries().find(([label]) => label === key)?.[1];
        parts.push(Text.of('evidence.read', {
            what: typeof found === 'string' ? `"${shorten(found)}"` : element,
        }));
    } else if (field !== null) {
        parts.push(Text.of('evidence.field', { field }));
    } else if (question !== null) {
        const read = quote(check, question);

        if (read !== null) {
            parts.push(read);
        }
    }

    return parts.length === 0 ? null : parts.join(' ');
}

/**
 * What the readings behind a probability are.
 *
 * `calls` counts the answers; `asked` is what the caller asked for. A borderline
 * check is re-asked without `--repeats`, so a run of one can end with two
 * answers, and calling those "2 repeats" names a flag nobody passed
 */
function readingsOf(wordings: number, calls: number, asked: number): string {
    const settled = asked < 2 && calls > 1;

    if (wordings > 1 && settled) {
        return Text.of('readings.wordings_resettled', { wordings });
    }

    if (settled) {
        return Text.of('readings.one_and_a_resettle');
    }

    if (wordings > 1 && calls > 1) {
        return Text.of('readings.wordings_over_repeats', { wordings, repeats: calls });
    }

    if (wordings > 1) {
        return Text.of('readings.wordings', { wordings });
    }

    return Text.of('readings.repeats', { repeats: calls });
}

/**
 * Every level or option the check fires on.
 *
 * Reporting one of three broken levels sends a literal reader round the loop
 * twice more, so each is asked about and all of them are named
 */
function locate(locator: Map<string, string>, response: SystemOneResponse): string[] {
    const found: string[] = [];

    for (const [key, label] of locator) {
        if (!response.has(key)) {
            continue;
        }

        // An empty label marks the Choice form, which names one element.
        if (label === '') {
            const answer = response.choice(key);

            if ((answer.probabilityOf(answer.choice()) ?? 0.0) >= 0.5) {
                found.push(answer.choice());
            }

            continue;
        }

        if ((reading(response, key) ?? 0.0) >= 0.6) {
            found.push(label);
        }
    }

    return found;
}

/**
 * An element as a reader of their own query would name it.
 *
 * `level_2` is this module's own addressing, zero-based, and printing it at
 * somebody whose rubric starts at 1 names a different level from the one that is
 * wrong. A Choice option is already the label they wrote
 */
function describe(element: string, question: ReviewedQuestion | null): string {
    if (!element.startsWith('level_')) {
        return `\`${element}\``;
    }

    const index = Number.parseInt(element.slice(6), 10);
    const entries = question?.entries() ?? [];
    const levels = entries.length;
    const found = entries.find(([label]) => label === String(index))?.[1];
    const quoted = typeof found === 'string' && found !== ''
        ? Text.of('evidence.level_quoted', { text: shorten(found, 60) })
        : '';

    return levels > 0
        ? Text.of('evidence.level_of', { index: index + 1, levels, quoted })
        : Text.of('evidence.level', { index: index + 1, quoted });
}

/**
 * The pointer tail for one element a check located.
 *
 * `level_2` addresses index 2. A state field is a dotted path and splits into
 * segments, so `ticket.body` is `/ticket/body`. An option label is a key
 * somebody chose, so the `.` in `billing.invoices` belongs to the label, and
 * splitting it addresses a node that is not there or one that is the wrong one
 */
function pointerFor(check: Check, element: string): string {
    if (element.startsWith('level_')) {
        return element.slice(6);
    }

    return check.reads === 'field'
        ? Query.segments(element).map(Check.escape).join('/')
        : Check.escape(element);
}

/** What the check was looking at, quoted back from the query */
function quote(check: Check, question: ReviewedQuestion): string | null {
    const criteria = question.hasCriteria() ? Json.inline(question.criteria) : null;

    switch (check.reads) {
        case 'instructions':
            return Text.of('evidence.read_quoted', { what: shorten(question.instructionsText()) });
        case 'criteria':
            return criteria === null ? null : Text.of('evidence.read', { what: shorten(criteria) });
        case 'question':
        case 'type':
            return criteria === null
                ? Text.of('evidence.read_quoted', { what: shorten(question.instructionsText()) })
                : Text.of('evidence.read_with', {
                    instructions: shorten(question.instructionsText(), 80),
                    criteria: shorten(criteria, 80),
                });
        default:
            return null;
    }
}

/**
 * The text a check was shown, short enough to print.
 *
 * Cut from the middle, not the tail. A question that weighs several factors or
 * asks two things usually carries the second at the end, and a quote that stops
 * before it shows the reader everything except the reason
 */
function shorten(text: string, limit = 150): string {
    const characters = [...text];

    if (characters.length <= limit) {
        return text;
    }

    const head = Math.floor((limit - 3) * 0.6);
    const tail = limit - 3 - head;

    return `${characters.slice(0, head).join('')} … ${characters.slice(characters.length - tail).join('')}`;
}

function mean(values: number[]): number {
    return values.reduce((sum, value) => sum + value, 0) / values.length;
}
