/** One finding somebody has read and decided to live with */
export class Acceptance {
    constructor(
        public readonly check: string,
        public readonly question: string | null,
        public readonly reason: string,
    ) {}

    covers(check: string, target: string): boolean {
        if (this.check !== check) {
            return false;
        }

        return this.question === null || this.question === '*' || this.question === target;
    }
}
