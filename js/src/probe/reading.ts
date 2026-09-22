/** What one variant did to one question */
export class Reading {
    constructor(
        public readonly variant: string,
        public readonly describe: string,
        public readonly value: number | null,
        public readonly error: string | null = null,
    ) {}
}
