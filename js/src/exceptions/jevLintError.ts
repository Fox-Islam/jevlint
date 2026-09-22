/**
 * Everything this package throws.
 *
 * The kind is for a caller deciding what to do next. A missing file and a
 * mistyped flag are both the caller's fault and neither is worth retrying; an
 * `api` failure might be. Collapsing them all into one label leaves a program
 * matching on English.
 */
export class JevLintError extends Error {
    static readonly USAGE = 'usage';

    static readonly NOT_FOUND = 'not-found';

    static readonly INVALID_JSON = 'invalid-json';

    static readonly QUERY = 'query';

    static readonly CONFIG = 'config';

    static readonly AUTH = 'auth';

    static readonly CATALOGUE = 'catalogue';

    public kind: string = JevLintError.USAGE;

    constructor(message: string) {
        super(message);
        this.name = 'JevLintError';
    }

    static of(kind: string, message: string): JevLintError {
        const error = new JevLintError(message);
        error.kind = kind;

        return error;
    }
}
