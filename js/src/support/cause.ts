import {
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
    TypeSafeError,
    UnprocessableEntityError,
} from '../typesafe/errors.js';

/**
 * Why a call did not come back, as a word.
 *
 * A caller deciding whether to retry has to tell a wrong key from a dropped
 * connection, and the message is English written for a person
 */
export const Cause = {
    /** Nothing failed; the answer that came back was unusable */
    ANSWER: 'answer',

    /**
     * Whether a second call would fail the same way.
     *
     * A wrong key or a denied account answers every call identically, so a run
     * that keeps going spends the rest of its calls learning what the first one
     * already said.
     */
    isSettled(error: TypeSafeError): boolean {
        return error instanceof AuthenticationError || error instanceof PermissionDeniedError;
    },

    of(error: TypeSafeError): string {
        if (error instanceof AuthenticationError) return 'auth';
        if (error instanceof PermissionDeniedError) return 'permission';
        if (error instanceof RateLimitError) return 'rate-limit';
        if (error instanceof APITimeoutError) return 'timeout';
        if (error instanceof APIConnectionError) return 'connection';
        if (error instanceof BadRequestError || error instanceof UnprocessableEntityError) return 'request';
        if (error instanceof InternalServerError) return 'server';
        if (error instanceof APIError) return 'api';

        return 'api';
    },
};
