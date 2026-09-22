export type SeverityName = 'error' | 'warning' | 'advice';

/** Higher is worse. Used for sorting and for the minimum-severity filter */
const weights: Record<SeverityName, number> = { error: 3, warning: 2, advice: 1 };

export class Severity {
    static readonly Error = new Severity('error');

    static readonly Warning = new Severity('warning');

    static readonly Advice = new Severity('advice');

    private constructor(public readonly value: SeverityName) {}

    static cases(): Severity[] {
        return [Severity.Error, Severity.Warning, Severity.Advice];
    }

    /** An unknown name is a warning, so a report never loses a finding to a typo */
    static fromName(value: string): Severity {
        return Severity.cases().find((severity) => severity.value === value.toLowerCase()) ?? Severity.Warning;
    }

    weight(): number {
        return weights[this.value];
    }

    atLeast(floor: Severity): boolean {
        return this.weight() >= floor.weight();
    }
}
