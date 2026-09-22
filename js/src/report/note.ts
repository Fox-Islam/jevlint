/**
 * Something about the run itself, as opposed to the query.
 *
 * `unreachable` is the one that matters: a call that could not be made means
 * those checks never ran, and a report that cannot say so reads exactly like a
 * report that ran them and found nothing.
 */
export class Note {
    constructor(
        public readonly message: string,
        public readonly kind: string = 'note',
        public readonly target: string | null = null,
        public readonly checks: number | null = null,
        public readonly cause: string | null = null,
        public readonly findings: number | null = null,
    ) {}

    isUnreachable(): boolean {
        return this.kind === 'unreachable';
    }

    /** Checks this run did not carry, for a reason that is not a failure */
    isSkip(): boolean {
        return this.kind === 'skipped';
    }

    toObject(): Record<string, unknown> {
        const row: Record<string, unknown> = { kind: this.kind, target: this.target, message: this.message };

        // Why it failed, as a word. A caller deciding between stopping and
        // retrying had to read the English the person reads.
        if (this.cause !== null) {
            row['cause'] = this.cause;
        }

        // How many findings a floor leaves out, as a number. `checks` carries
        // the same for a narrowing. A caller reads neither out of the message.
        if (this.findings !== null) {
            row['findings'] = this.findings;
        }

        // The count as a number, not only inside the sentence. A caller working
        // out whether a run covered anything had to regex the English.
        if (this.checks !== null) {
            row['checks'] = this.checks;
        }

        return row;
    }
}
