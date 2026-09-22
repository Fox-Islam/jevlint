/** Writes to stdout and stderr, and knows whether a terminal is reading */
export class Output {
    constructor(private readonly coloured: boolean) {}

    static make(forceOff = false): Output {
        return new Output(!forceOff && process.stdout.isTTY === true && process.env['NO_COLOR'] === undefined);
    }

    colour(): boolean {
        return this.coloured;
    }

    /** A reader that closes the pipe, such as `head`, is not an error here */
    write(text: string): void {
        try {
            process.stdout.write(text);
        } catch {
            // Nothing to do: the reader has gone.
        }
    }

    line(text = ''): void {
        this.write(`${text}\n`);
    }

    error(text: string): void {
        process.stderr.write(`${this.coloured ? `\u001b[31m${text}\u001b[0m` : text}\n`);
    }
}
