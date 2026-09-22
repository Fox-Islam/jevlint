import { readFileSync, statSync } from 'node:fs';
import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';
import { parse, stringify } from './ordered.js';

/** A decoded JSON object, as the files this reads all are */
export type JsonObject = Record<string, unknown>;

export const Json = {
    /**
     * The file's text, or an error naming why it could not be read.
     *
     * A directory is named as one. Reading it otherwise fails deeper in with a
     * message about the file's contents, which is a file nobody wrote
     */
    contents(path: string): string {
        let stats;

        try {
            stats = statSync(path);
        } catch {
            throw JevLintError.of(JevLintError.NOT_FOUND, Text.of('file.unreadable', { path }));
        }

        if (stats.isDirectory()) {
            throw JevLintError.of(JevLintError.NOT_FOUND, Text.of('file.is_a_directory', { path }));
        }

        try {
            return readFileSync(path, 'utf8');
        } catch {
            throw JevLintError.of(JevLintError.NOT_FOUND, Text.of('file.unreadable', { path }));
        }
    },

    readFile(path: string): JsonObject {
        return Json.decode(Json.contents(path), path);
    },

    decode(contents: string, what = 'input'): JsonObject {
        let decoded: unknown;

        try {
            decoded = parse(contents);
        } catch (error) {
            throw JevLintError.of(JevLintError.INVALID_JSON, Text.of('json.invalid', {
                what,
                detail: error instanceof Error ? error.message : String(error),
            }));
        }

        if (typeof decoded !== 'object' || decoded === null) {
            throw JevLintError.of(JevLintError.INVALID_JSON, Text.of('json.not_an_object', { what }));
        }

        return decoded as JsonObject;
    },

    /**
     * Whether the text was written as a JSON array.
     *
     * `{"0":"a"}` and `["a"]` decode to the same thing once the keys are
     * counting numbers, and the API treats the two differently, so which one
     * was written is read from the text and not from the value
     */
    isList(contents: string): boolean {
        return /^\s*\[/.test(contents);
    },

    encode(value: unknown): string {
        const encoded = stringify(value, 4);

        if (encoded === undefined) {
            throw JevLintError.of(JevLintError.INVALID_JSON, Text.of('json.report_unencodable', {
                detail: 'the value holds nothing that can be written',
            }));
        }

        return encoded;
    },

    /**
     * The same, for the error document.
     *
     * The handler cannot fail: a throw here leaves the run with no output at
     * all, and `command` is required by spec/error.schema.json, so the one
     * document written without going through the encoder carries it too
     */
    encodeSafely(value: unknown): string {
        try {
            return Json.encode(value);
        } catch {
            return '{"error":{"kind":"internal","message":"The error could not be written as JSON.","command":"check"}}';
        }
    },

    /** A stable, readable rendering of a state or criteria value */
    inline(value: unknown): string {
        if (typeof value === 'string') {
            return value;
        }

        return stringify(value);
    },
};
