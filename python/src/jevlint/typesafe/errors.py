"""
The errors the SDK raises, under the names the rest of this package uses.

jevlint catches one class - `TypeSafeError` - and turns the rest into the word
`Cause` reports, so this is the whole surface it needs. The SDK prefixes every
name with `TypeSafe`, which reads twice in `except TypeSafeAuthenticationError`
beside a `TypeSafe` import.
"""
from typesafe_sdk import (
    TypeSafeAPIConnectionError as APIConnectionError,
)
from typesafe_sdk import (
    TypeSafeAPIError as APIError,
)
from typesafe_sdk import (
    TypeSafeAPIResponseValidationError as ResponseValidationError,
)
from typesafe_sdk import (
    TypeSafeAPITimeoutError as APITimeoutError,
)
from typesafe_sdk import (
    TypeSafeAuthenticationError as AuthenticationError,
)
from typesafe_sdk import (
    TypeSafeBadRequestError as BadRequestError,
)
from typesafe_sdk import (
    TypeSafeError as TypeSafeError,
)
from typesafe_sdk import (
    TypeSafeInternalServerError as InternalServerError,
)
from typesafe_sdk import (
    TypeSafeNotFoundError as NotFoundError,
)
from typesafe_sdk import (
    TypeSafePermissionDeniedError as PermissionDeniedError,
)
from typesafe_sdk import (
    TypeSafeRateLimitError as RateLimitError,
)
from typesafe_sdk import (
    TypeSafeUnprocessableEntityError as UnprocessableEntityError,
)

__all__ = [
    'APIConnectionError',
    'APIError',
    'APITimeoutError',
    'AuthenticationError',
    'BadRequestError',
    'InternalServerError',
    'NotFoundError',
    'PermissionDeniedError',
    'RateLimitError',
    'ResponseValidationError',
    'TypeSafeError',
    'UnprocessableEntityError',
]
