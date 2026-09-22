import { Patch } from './patch.js';
import { Severity } from './severity.js';

export interface FindingFields {
    checkId: string;
    title: string;
    severity: Severity;
    target: string;
    message: string;
    hint?: string;
    suggest?: string;
    mode?: string;
    action?: string;
    path?: string;
    trigger?: number | null;
    spread?: number | null;
    nearTrigger?: boolean;
    supersedes?: string[];
    docs?: string | null;
    probability?: number | null;
    evidence?: string | null;
    readings?: number[];
    readingsOf?: string | null;
    suggestedType?: string | null;
    paths?: string[];
    patch?: Patch | null;
    /** What the self-test measured about this check's own suggestion, where it is weak */
    advice?: string;
    /**
     * Why a reading above the trigger is not a finding.
     *
     * A cleared entry carries a number and a trigger and nothing else, so a
     * reading the catalogue sets aside looks like a defect that got away
     */
    clearedBecause?: string;
    /**
     * What the number on this finding is. Every check but one reports a
     * calibrated probability that the defect is present; `question/type-mismatch`
     * asks which primitive fits and reports the weight on the one it picked,
     * which is not a probability of anything being wrong
     */
    measure?: string;
    fired?: boolean;
    accepted?: string | null;
    unstable?: boolean;
}

/** One change a query needs, and the evidence for it */
export class Finding {
    readonly checkId: string;

    readonly title: string;

    readonly severity: Severity;

    readonly target: string;

    readonly message: string;

    readonly hint: string;

    readonly suggest: string;

    readonly mode: string;

    readonly action: string;

    readonly path: string;

    readonly trigger: number | null;

    readonly spread: number | null;

    readonly nearTrigger: boolean;

    readonly supersedes: string[];

    readonly docs: string | null;

    readonly probability: number | null;

    readonly evidence: string | null;

    readonly readings: number[];

    readonly readingsOf: string | null;

    readonly suggestedType: string | null;

    readonly paths: string[];

    readonly patch: Patch | null;

    readonly advice: string;

    readonly clearedBecause: string;

    readonly measure: string;

    readonly fired: boolean;

    readonly accepted: string | null;

    readonly unstable: boolean;

    constructor(fields: FindingFields) {
        this.checkId = fields.checkId;
        this.title = fields.title;
        this.severity = fields.severity;
        this.target = fields.target;
        this.message = fields.message;
        this.hint = fields.hint ?? '';
        this.suggest = fields.suggest ?? '';
        this.mode = fields.mode ?? 'static';
        this.action = fields.action ?? 'rewrite';
        this.path = fields.path ?? '';
        this.trigger = fields.trigger ?? null;
        this.spread = fields.spread ?? null;
        this.nearTrigger = fields.nearTrigger ?? false;
        this.supersedes = fields.supersedes ?? [];
        this.docs = fields.docs ?? null;
        this.probability = fields.probability ?? null;
        this.evidence = fields.evidence ?? null;
        this.readings = fields.readings ?? [];
        this.readingsOf = fields.readingsOf ?? null;
        this.suggestedType = fields.suggestedType ?? null;
        this.paths = fields.paths ?? [];
        this.patch = fields.patch ?? null;
        this.advice = fields.advice ?? '';
        this.clearedBecause = fields.clearedBecause ?? '';
        this.measure = fields.measure ?? 'probability';
        this.fired = fields.fired ?? true;
        this.accepted = fields.accepted ?? null;
        this.unstable = fields.unstable ?? false;
    }

    /** The same finding, marked as one somebody has decided to live with */
    acceptedBecause(reason: string): Finding {
        return new Finding({ ...this, accepted: reason });
    }

    /** Whether a model decided this, instead of a rule in code */
    fromModel(): boolean {
        return this.probability !== null;
    }

    /**
     * A probability as it is reported.
     *
     * A mean over three readings comes out of the float as 0.07500000000000001,
     * and a consumer comparing two reports is reading noise the model never put
     * there. Four places is finer than anything the readings carry
     */
    private static reported(value: number | null): number | null {
        return value === null ? null : Math.round(value * 1e4) / 1e4;
    }

    toObject(): Record<string, unknown> {
        // A check that cleared is a measurement, not advice. Giving it the shape
        // of a finding invites a reader to act on an argument against acting.
        if (!this.fired) {
            return {
                ...present({
                    check: this.checkId,
                    path: this.path,
                    probability: Finding.reported(this.probability),
                    trigger: this.trigger,
                    readings: this.readings.length === 0 ? null : this.readings.map(Finding.reported),
                    cleared_because: this.clearedBecause === '' ? null : this.clearedBecause,
                    // A cleared entry carries none of the fields that tell you to
                    // act, but this one says what the reading cannot tell you,
                    // which is exactly what a clear reading needs beside it.
                    advice_caveat: this.advice === '' ? null : this.advice,
                }),
                target: this.target,
                near_trigger: this.nearTrigger,
                // Present on both shapes. An entry in `unstable` needs the key
                // most, so it cannot be the one shape that omits it.
                unstable: this.unstable,
                fired: false,
            };
        }

        return {
            ...present({
                check: this.checkId,
                title: this.title,
                severity: this.severity.value,
                mode: this.mode,
                action: this.action,
                path: this.path,
                message: this.message,
                hint: this.hint,
                suggest: this.suggest,
                suggest_kind: this.suggest === '' ? null : (this.patch === null ? 'guidance' : 'patch'),
                advice_caveat: this.advice === '' ? null : this.advice,
                docs: this.docs,
                probability: this.measure === 'probability' ? Finding.reported(this.probability) : null,
                weight: this.measure === 'weight' ? Finding.reported(this.probability) : null,
                trigger: this.trigger,
                spread: Finding.reported(this.spread),
                supersedes: this.supersedes.length === 0 ? null : this.supersedes,
                evidence: this.evidence,
                readings: this.readings.length === 0 ? null : this.readings.map(Finding.reported),
                readings_of: this.readingsOf,
                suggested_type: this.suggestedType,
                paths: this.paths.length === 0 ? null : this.paths,
                patch: this.patch?.toObject() ?? null,
                accepted: this.accepted,
            }),
            // Always present, both of them. `near_trigger: false` says the
            // reading is clear of its trigger; an absent key says nothing, and a
            // caller has no way to tell which was meant.
            // A question id is a key somebody chose, and "" is a key, so `target`
            // cannot go through the filter that drops an empty string.
            target: this.target,
            measure: this.measure,
            near_trigger: this.nearTrigger,
            unstable: this.unstable,
            fired: true,
        };
    }
}

/** Keys worth writing: everything the report has an answer for */
function present(row: Record<string, unknown>): Record<string, unknown> {
    return Object.fromEntries(
        Object.entries(row).filter(([, value]) => value !== null && value !== undefined && value !== ''),
    );
}
