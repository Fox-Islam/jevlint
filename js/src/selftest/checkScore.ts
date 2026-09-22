import type { Check } from '../catalogue/check.js';
import { SelfTest } from './selfTest.js';

/** What one check scored against its own clean and broken examples */
export class CheckScore {
    constructor(
        public readonly check: Check,
        public readonly clean: number | null,
        public readonly broken: number | null,
        public readonly fixed: number | null = null,
        public readonly domain = '',
        /**
         * Whether the fixture shipped a `fixed` example at all.
         *
         * Without it, a `fixed` call that failed and a check that ships no
         * rewrite are both `null`, and only the second is a pass
         */
        public readonly offersFixed = false,
    ) {}

    span(): number | null {
        if (this.clean === null || this.broken === null) {
            return null;
        }

        return this.broken - this.clean;
    }

    /**
     * `flat` and `inverted` mean the check is not measuring what it claims.
     * `fires-on-clean` and `misses-broken` mean it is, but the trigger is in
     * the wrong place
     */
    verdict(): string {
        const span = this.span();

        // Before anything about the readings: a run that lost a call did not
        // measure this check, and reporting a catalogue as wrong on the strength
        // of a call that never came back sends the reader to the wrong file.
        if (span === null || (this.offersFixed && this.fixed === null)) {
            return 'errored';
        }

        // A suggestion that leaves the check firing sends the reader in a circle
        if (this.fixed !== null && this.fixed > this.check.trigger) {
            return 'suggestion-fails';
        }

        if (span < 0) {
            return 'inverted';
        }

        if (span < SelfTest.FLAT) {
            return 'flat';
        }

        if (this.clean !== null && this.clean > this.check.trigger) {
            return 'fires-on-clean';
        }

        if (this.broken !== null && this.broken <= this.check.trigger) {
            return 'misses-broken';
        }

        return span < SelfTest.WEAK ? 'weak' : 'ok';
    }

    passed(): boolean {
        return ['ok', 'weak'].includes(this.verdict());
    }

    /** The check was never scored, because the call carrying it did not come back */
    errored(): boolean {
        return this.verdict() === 'errored';
    }

    toObject(): Record<string, unknown> {
        return {
            check: this.check.id,
            domain: this.domain === '' ? null : this.domain,
            trigger: this.check.trigger,
            clean: this.clean,
            broken: this.broken,
            fixed: this.fixed,
            span: this.span(),
            verdict: this.verdict(),
        };
    }
}
