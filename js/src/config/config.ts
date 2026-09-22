import { existsSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';
import { Json } from '../support/json.js';
import { Acceptance } from './acceptance.js';

/**
 * What a repository has decided about its own findings.
 *
 * The acceptances live beside the query and not inside it: the API rejects an
 * unknown key at the top of a request, and a query file that cannot be sent is
 * no longer the thing being checked.
 *
 * An absent file is an empty config. A repository that has never accepted
 * anything should not have to say so.
 */
export class Config {
    static readonly FILE = '.jevlint.json';

    private constructor(
        public readonly accept: Acceptance[],
        public readonly source: string | null,
        public readonly jev: string | null = null,
    ) {}

    static empty(): Config {
        return new Config([], null);
    }

    /** Find the config beside the query, then in the working directory */
    static discover(explicit: string | null, queryPath: string): Config {
        if (explicit !== null) {
            if (!isFile(explicit)) {
                throw JevLintError.of(JevLintError.CONFIG, Text.of('config.not_found', { path: explicit }));
            }

            return Config.load(explicit);
        }

        for (const candidate of [
            `${dirname(queryPath)}/${Config.FILE}`,
            `${resolve('.')}/${Config.FILE}`,
        ]) {
            if (isFile(candidate)) {
                return Config.load(candidate);
            }
        }

        return Config.empty();
    }

    static load(path: string): Config {
        const data = Json.readFile(path);

        // A misspelled `accept` leaves the whole block covering nothing, which
        // is the failure this file exists to make visible.
        const unknown = Object.keys(data).filter((key) => key !== 'accept' && key !== 'jev');

        if (unknown.length > 0) {
            throw JevLintError.of(JevLintError.CONFIG, Text.of('config.unknown_setting', {
                path,
                names: unknown.join('", "'),
            }));
        }

        const accept = data['accept'] ?? [];

        if (typeof accept !== 'object' || accept === null) {
            throw JevLintError.of(JevLintError.CONFIG, Text.of('config.accept_not_a_list', { path }));
        }

        const accepted: Acceptance[] = [];

        for (const [index, entry] of Object.entries(accept as Record<string, unknown>)) {
            if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) {
                throw JevLintError.of(JevLintError.CONFIG, Text.of('config.entry_not_an_object', { path, entry: index }));
            }

            const row = entry as Record<string, unknown>;
            const check = row['check'];
            const reason = row['reason'];
            const question = row['question'];

            if (typeof check !== 'string' || check === '') {
                throw JevLintError.of(JevLintError.CONFIG, Text.of('config.entry_names_no_check', { path, entry: index }));
            }

            // An acceptance is a judgement somebody made. Recording why is what
            // separates it from switching the check off.
            if (typeof reason !== 'string' || reason.trim() === '') {
                throw JevLintError.of(JevLintError.CONFIG, Text.of('config.acceptance_needs_a_reason', { path, check }));
            }

            accepted.push(new Acceptance(check, typeof question === 'string' ? question : null, reason));
        }

        return new Config(accepted, path, jevOf(data, path));
    }

    reasonFor(check: string, target: string): string | null {
        return this.accept.find((acceptance) => acceptance.covers(check, target))?.reason ?? null;
    }

    /** Check ids named in the config that the catalogue does not hold */
    unknown(known: string[]): string[] {
        return [...new Set(
            this.accept.filter((acceptance) => !known.includes(acceptance.check)).map((acceptance) => acceptance.check),
        )];
    }
}

/**
 * The Jev version this repository writes its queries for.
 *
 * A query file carries no record of the build it will be sent to, so the
 * version a run checks against comes from here
 */
function jevOf(data: Record<string, unknown>, path: string): string | null {
    const jev = data['jev'] ?? null;

    if (jev === null) {
        return null;
    }

    if (typeof jev !== 'string' || jev === '') {
        throw JevLintError.of(JevLintError.CONFIG, Text.of('config.jev_not_a_version', { path }));
    }

    return jev;
}

function isFile(path: string): boolean {
    return existsSync(path) && statSync(path).isFile();
}
