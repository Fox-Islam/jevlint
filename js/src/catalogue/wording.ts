import type { Criteria } from '../query/reviewedQuestion.js';

/**
 * One way of asking a check.
 *
 * A check may carry several. They are meant to mean the same thing, so the
 * spread between their answers is reported with the finding as its error bar
 */
export class Wording {
    constructor(
        public readonly type: string,
        public readonly text: string,
        public readonly criteria: Criteria | null,
    ) {}

    static fromObject(data: Record<string, unknown>): Wording {
        const type = data['type'];
        const instructions = data['instructions'];
        const criteria = data['criteria'];

        return new Wording(
            typeof type === 'string' ? type : 'noul',
            typeof instructions === 'string' ? instructions : '',
            typeof criteria === 'object' && criteria !== null ? criteria as Criteria : null,
        );
    }

    /** The instructions with `{field}` filled in, where the check is asked per state field */
    instructions(field = ''): string {
        return this.text.split('{field}').join(field);
    }
}
