import { existsSync, readFileSync, statSync } from 'node:fs';
import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';

/**
 * Reads a key from the environment, falling back to a `.env` in the working
 * directory or the one `--env-file` names. The client reads the environment
 * itself; this exists so a `.env` in the directory you run from is enough
 */
export const Env = {
    get(name: string): string | null {
        // A named file is where the key comes from, whether or not it holds one.
        // Falling back to the shell sent a run whose caller had pointed at one
        // account to whichever account the environment happened to carry.
        if (named !== null) {
            return fromFile()[name] ?? null;
        }

        const value = process.env[name];

        if (typeof value === 'string' && value !== '') {
            return value;
        }

        return fromFile()[name] ?? null;
    },

    /** The file `--env-file` named, for an error message that can say so */
    file(): string | null {
        return named;
    },

    /** Put what a `.env` holds into the environment, without overwriting it */
    hydrate(): void {
        for (const [name, value] of Object.entries(fromFile())) {
            // The client reads the environment, so a named file has to reach it
            // there or the call goes out with whatever the shell held.
            if (named !== null || process.env[name] === undefined) {
                process.env[name] = value;
            }
        }
    },

    useFile(path: string | null): void {
        loaded = null;
        named = null;

        if (path === null) {
            return;
        }

        // Somebody who passed --env-file wants that file. Falling back to the
        // ambient environment sends them looking for a variable when what they
        // mistyped is a path.
        if (!existsSync(path)) {
            throw JevLintError.of(JevLintError.NOT_FOUND, Text.of('env.no_such_file', { path }));
        }

        if (!statSync(path).isFile()) {
            throw JevLintError.of(JevLintError.NOT_FOUND, Text.of('env.not_a_file', { path }));
        }

        let contents: string;

        try {
            contents = readFileSync(path, 'utf8');
        } catch {
            throw JevLintError.of(JevLintError.NOT_FOUND, Text.of('env.unreadable', { path }));
        }

        named = path;
        loaded = parse(contents);
    },

    /** Forget what is loaded, so a test can point at another file inside one process */
    reset(): void {
        loaded = null;
        named = null;
    },
};

let loaded: Record<string, string> | null = null;

let named: string | null = null;

function fromFile(): Record<string, string> {
    if (loaded !== null) {
        return loaded;
    }

    const path = `${process.cwd()}/.env`;
    loaded = existsSync(path) && statSync(path).isFile() ? parse(readFileSync(path, 'utf8')) : {};

    return loaded;
}

function parse(contents: string): Record<string, string> {
    const values: Record<string, string> = {};

    for (const raw of contents.split(/\r?\n/)) {
        const line = raw.trim();

        if (line === '' || line.startsWith('#') || !line.includes('=')) {
            continue;
        }

        const at = line.indexOf('=');
        const name = line.slice(0, at).trim();
        values[name] = line.slice(at + 1).trim().replace(/^["']+/, '').replace(/["']+$/, '');
    }

    return values;
}
