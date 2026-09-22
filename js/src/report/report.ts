import type { Config } from '../config/config.js';
import { Text } from '../i18n/text.js';
import { Cause } from '../support/cause.js';
import { Finding } from './finding.js';
import { Note } from './note.js';
import { Patch } from './patch.js';
import { Severity } from './severity.js';

export interface ReportFields {
    source: string;
    catalogueVersion: string;
    model?: string;
    fingerprint?: string;
    /** A fingerprint over what the checks ask, which a reworded message does not move */
    questionPrint?: string;
    /** The build `--model` pinned, where one was pinned */
    askedThrough?: string | null;
}

/** What one run of the linter found, and what it cost */
export class Report {
    readonly source: string;

    readonly catalogueVersion: string;

    readonly model: string;

    readonly fingerprint: string;

    readonly questionPrint: string;

    readonly askedThrough: string | null;

    private readonly foundFindings: Finding[] = [];

    private readonly foundNotes: Note[] = [];

    private config: Config | null = null;

    private order = new Map<string, number>();

    private callCount = 0;

    private callsWithoutUsageCount = 0;

    private readonly answeredByModels = new Set<string>();

    /** Checks this run put to a query or to the model */
    private askedChecks = 0;

    private readonly expected = new Map<string, Set<string>>();

    private readonly reachedChecks = new Map<string, Set<string>>();

    private tokenCount = 0;

    constructor(fields: ReportFields) {
        this.source = fields.source;
        this.catalogueVersion = fields.catalogueVersion;
        this.model = fields.model ?? 'jev-1.13';
        this.fingerprint = fields.fingerprint ?? '';
        this.questionPrint = fields.questionPrint ?? '';
        this.askedThrough = fields.askedThrough ?? null;
    }

    acceptFrom(config: Config): void {
        this.config = config;
    }

    /** The file the acceptances were read from, where there was one */
    acceptedFrom(): string {
        return this.configSource() ?? '.jevlint.json';
    }

    /** The config this run read, or null where it found none */
    configSource(): string | null {
        return this.config?.source ?? null;
    }

    add(finding: Finding): void {
        const reason = this.config?.reasonFor(finding.checkId, finding.target) ?? null;

        this.foundFindings.push(reason === null ? finding : finding.acceptedBecause(reason));
    }

    /**
     * The order the query wrote its questions in, so the report reads down the
     * file instead of down the alphabet
     */
    orderBy(targets: string[]): void {
        this.order = new Map(targets.map((target, index) => [target, index]));
    }

    private orderOf(target: string): number {
        return this.order.get(target) ?? Number.MAX_SAFE_INTEGER;
    }

    /** Record that this many checks were evaluated, so a run that asked nothing can say so */
    asked(checks: number): void {
        this.askedChecks += checks;
    }

    askedCount(): number {
        return this.askedChecks;
    }

    note(note: string, findings: number | null = null): void {
        this.foundNotes.push(new Note(note, 'note', null, null, null, findings));
    }

    /**
     * A call that could not be made, so the checks it carried never ran.
     *
     * Recorded apart from an ordinary note because the run is now incomplete,
     * and a caller gating on the exit code has to be able to tell.
     */
    unreachable(target: string, message: string, cause: string | null = null): void {
        this.foundNotes.push(new Note(
            Text.of('report.unreachable', { target, detail: message }),
            'unreachable',
            target,
            null,
            cause ?? Cause.ANSWER,
        ));
    }

    /**
     * A check this run put into a call, and the question or state it was asked
     * about. Paired with `reached`, this is what `reconcile()` compares
     */
    expecting(checkId: string, target: string): void {
        const checks = this.expected.get(target) ?? new Set<string>();
        checks.add(checkId);
        this.expected.set(target, checks);
    }

    /** A check that got as far as a verdict, whether or not it fired */
    reached(checkId: string, target: string): void {
        const checks = this.reachedChecks.get(target) ?? new Set<string>();
        checks.add(checkId);
        this.reachedChecks.set(target, checks);
    }

    /**
     * Every check that went into a call has to come back as a finding, as a
     * cleared reading, or as a loss somebody can see.
     *
     * A check that produces nothing on some path and is never mentioned leaves a
     * report that reads as clean and complete. Reconciling what was asked
     * against what came back catches that wherever it happens, instead of each
     * path having to notice for itself.
     */
    reconcile(): void {
        for (const [target, checks] of this.expected) {
            // A target that already carries a loss has said so; adding a second
            // note per check would inflate the count without adding a fact.
            if (this.unreachableNotes().some((note) => note.target === target)) {
                continue;
            }

            const reached = this.reachedChecks.get(target) ?? new Set<string>();
            const missing = [...checks].filter((check) => !reached.has(check)).sort();

            if (missing.length === 0) {
                continue;
            }

            this.unreachable(target, Text.of('report.no_verdict', {
                first: missing[0] ?? '',
                more: missing.length - 1,
            }));
        }
    }

    /**
     * Checks this run did not carry: a flag narrowed it, or the query is a shape
     * a check cannot run on. Not a failure, but not coverage either, and a
     * report that cannot say so reads like a full clean pass.
     */
    skipped(message: string, checks: number | null = null): void {
        this.foundNotes.push(new Note(message, 'skipped', null, checks));
    }

    skippedNotes(): Note[] {
        return this.foundNotes.filter((note) => note.isSkip());
    }

    unreachableNotes(): Note[] {
        return this.foundNotes.filter((note) => note.isUnreachable());
    }

    /** Whether every check that was meant to run got an answer */
    isComplete(): boolean {
        return this.unreachableNotes().length === 0;
    }

    /** The build the answers say they came from, whatever was asked for */
    answeredBy(model: string): void {
        this.answeredByModels.add(model);
    }

    /**
     * The builds that answered, as the API named them.
     *
     * `--model` and `--openrouter` say what was asked for. This says what
     * replied, which is what makes two reports comparable or not.
     */
    answeringModels(): string[] {
        return [...this.answeredByModels].sort();
    }

    /**
     * A call that left the machine.
     *
     * `tokens` is null where the answer carried no usage, which is not a call
     * that cost nothing; counting it as zero prints the two the same way
     */
    recordCall(tokens: number | null): void {
        this.callCount++;

        if (tokens === null) {
            this.callsWithoutUsageCount++;

            return;
        }

        this.tokenCount += tokens;
    }

    /** Calls whose answer carried no token count */
    callsWithoutUsage(): number {
        return this.callsWithoutUsageCount;
    }

    findings(floor: Severity | null = null): Finding[] {
        const fired = this.foundFindings.filter((finding) => finding.fired && finding.accepted === null);
        const findings = floor === null
            ? fired
            : fired.filter((finding) => finding.severity.atLeast(floor));

        const rank = (finding: Finding): number => (this.supersededBy(finding) === null ? 0 : 1);

        return [...findings].sort((a, b) => compare(
            [this.orderOf(a.target), rank(a), b.severity.weight(), a.checkId],
            [this.orderOf(b.target), rank(b), a.severity.weight(), b.checkId],
        ));
    }

    /**
     * The finding that makes this one moot, where one does.
     *
     * Changing a question's type discards the advice about the type it had, so
     * an agent applying findings in order would otherwise write criteria it
     * immediately throws away
     */
    supersededBy(finding: Finding): string | null {
        for (const other of this.foundFindings) {
            // Only something the reader was told to do. A check that ran and
            // cleared, or one already accepted, is nothing to act on, so it
            // cannot make another finding moot - and naming it points the reader
            // at a line that is not in the report.
            if (!other.fired || other.accepted !== null) {
                continue;
            }

            if (other.target !== finding.target || !other.supersedes.includes(finding.checkId)) {
                continue;
            }

            // No severity test. The catalogue declares these edges because acting
            // on one finding makes the other moot, which is a fact about the two
            // changes and not about how much either costs.
            return other.checkId;
        }

        return null;
    }

    /** The findings this one makes moot, of those reported */
    superseding(finding: Finding): string[] {
        return this.foundFindings
            .filter((other) => other.target === finding.target
                && finding.supersedes.includes(other.checkId)
                && finding.severity.atLeast(other.severity))
            .map((other) => other.checkId);
    }

    /** Checks that ran and cleared, when the caller asked to see them */
    cleared(): Finding[] {
        return this.foundFindings.filter((finding) => !finding.fired);
    }

    notes(): Note[] {
        return this.foundNotes;
    }

    calls(): number {
        return this.callCount;
    }

    tokens(): number {
        return this.tokenCount;
    }

    count(severity: Severity): number {
        return this.foundFindings.filter(
            (finding) => finding.fired && finding.accepted === null && finding.severity === severity,
        ).length;
    }

    /**
     * Checks whose readings straddled their trigger and did not fire.
     *
     * One whose mean clears the trigger is reported as the finding it is, with
     * the disagreement noted on it. Listing it here as well would count it twice
     * and leave a reader unable to tell which of the two the tool meant.
     */
    unstable(): Finding[] {
        return this.foundFindings.filter(
            (finding) => finding.unstable && !finding.fired && finding.accepted === null,
        );
    }

    /**
     * Findings somebody has read and decided to live with.
     *
     * They are reported and they count for nothing. A tool that deletes them
     * from its own output teaches you to distrust the output.
     */
    accepted(): Finding[] {
        return this.foundFindings.filter((finding) => finding.fired && finding.accepted !== null);
    }

    /**
     * The finding whose patch already settles the node this one's patch writes.
     *
     * Two checks can want the same question gone, and a third can want a key
     * added inside it. Applied in order the second delete fails and the add puts
     * the deleted question back as a stub the API rejects, so each patch is
     * right and the set is not. Replacing a node settles it the same way: what
     * the replacement holds is what is there, whatever a patch inside it wanted
     */
    patchCoveredBy(finding: Finding): string | null {
        if (finding.patch === null) {
            return null;
        }

        let seenSelf = false;

        for (const other of this.findings()) {
            if (other === finding) {
                seenSelf = true;

                continue;
            }

            const patch = other.patch;

            if (patch === null) {
                continue;
            }

            // A patch writing inside a node another finding removes or replaces
            // is void wherever the two sort, because a caller may apply either
            // first and the node it wrote into is then gone or overwritten.
            if (finding.patch.path.startsWith(`${patch.path}/`)) {
                return other.checkId;
            }

            // Two patches on the same node make each other moot, so only the
            // later one is marked; marking both would name a cycle.
            if (patch.path === finding.patch.path && !seenSelf) {
                return other.checkId;
            }
        }

        return null;
    }

    hasErrors(): boolean {
        return this.count(Severity.Error) > 0;
    }

    isEmpty(floor: Severity | null = null): boolean {
        return this.findings(floor).length === 0;
    }

    toObject(floor: Severity | null = null): Record<string, unknown> {
        return {
            source: this.source,
            catalogue: {
                version: this.catalogueVersion,
                fingerprint: this.fingerprint,
                asked: this.questionPrint,
                model: this.model,
            },
            // Which build answered, against the build the checks are written for.
            // Without it, two runs through different models are one document.
            asked_through: this.askedThrough,
            // What answered, not what was asked for: two providers serving the
            // same build, or one serving a different one, are only visible here.
            answered_by: this.answeringModels(),
            summary: {
                error: this.count(Severity.Error),
                warning: this.count(Severity.Warning),
                advice: this.count(Severity.Advice),
                calls: this.callCount,
                tokens: this.tokenCount,
                // Calls the answer carried no usage for. Without it a run whose
                // provider reported no usage prints the same figure as a run
                // that cost nothing.
                tokens_unreported_for: this.callsWithoutUsageCount,
                accepted: this.accepted().length,
                unstable: this.unstable().length,
                unreachable: this.unreachableNotes().length,
                // Checks evaluated. A narrowed run that left nothing to do
                // produced the same empty report as a query with nothing wrong.
                asked: this.askedChecks,
                complete: this.isComplete(),
                // Not a total: two reasons can leave out the same check, so the
                // count that means anything is the one on each note.
                narrowed: this.skippedNotes().length > 0,
            },
            // Which config was read. A query copied to another directory loses its
            // acceptances, and this is what says so instead of the findings
            // reappearing with no reason given.
            accepted_from: this.configSource(),
            notes: this.foundNotes.map((note) => note.toObject()),
            cleared: this.cleared().map((finding) => finding.toObject()),
            // Accepted findings go through the same resolution. Left raw, their
            // `supersedes` is the catalogue's whole list and not the checks
            // this report holds, and one field means two things in one document.
            accepted: this.accepted().map((finding) => this.resolved(finding)),
            unstable: this.unstable().map((finding) => this.resolved(finding)),
            findings: this.findings(floor).map((finding) => this.resolved(finding)),
        };
    }

    /**
     * A finding with its relationships answered against this report, instead of
     * against the catalogue the check was written in
     */
    private resolved(finding: Finding): Record<string, unknown> {
        const row = finding.toObject();
        const superseded = this.supersededBy(finding);
        const supersedes = this.superseding(finding);

        if (superseded !== null) {
            row['superseded_by'] = superseded;
        }

        row['supersedes'] = supersedes.length === 0 ? null : supersedes;
        const covered = this.patchCoveredBy(finding);
        const patch = row['patch'];

        if (covered !== null && typeof patch === 'object' && patch !== null) {
            (patch as Record<string, unknown>)['covered_by'] = covered;
        }

        return Object.fromEntries(Object.entries(row).filter(([, value]) => value !== null));
    }
}

/** PHP's array comparison, which is what the findings are sorted with */
function compare(a: (string | number)[], b: (string | number)[]): number {
    for (const [index, left] of a.entries()) {
        const right = b[index];

        if (right === undefined) {
            return 1;
        }

        if (left < right) {
            return -1;
        }

        if (left > right) {
            return 1;
        }
    }

    return 0;
}

export { Patch };
