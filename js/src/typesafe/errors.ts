/**
 * The errors the SDK raises, re-exported so nothing here imports it twice.
 *
 * jevlint catches one class - `TypeSafeError` - and turns the rest into the
 * word `Cause` reports, so this is the whole surface it needs
 */
export {
    APIConnectionError,
    APIError,
    APITimeoutError,
    APIUserAbortError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    TypeSafeError,
    UnprocessableEntityError,
} from '@typesafe-ai/sdk';
