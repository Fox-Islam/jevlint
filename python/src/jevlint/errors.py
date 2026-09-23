"""
Everything this package raises.

The kind is for a caller deciding what to do next. A missing file and a
mistyped flag are both the caller's fault and neither is worth retrying; an
`api` failure might be. Collapsing them all into one label leaves a program
matching on English.
"""


class JevLintError(Exception):
    USAGE = 'usage'

    NOT_FOUND = 'not-found'

    INVALID_JSON = 'invalid-json'

    QUERY = 'query'

    CONFIG = 'config'

    AUTH = 'auth'

    CATALOGUE = 'catalogue'

    def __init__(self, message: str, kind: str = USAGE) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind

    @classmethod
    def of(cls, kind: str, message: str) -> 'JevLintError':
        return cls(message, kind)

    def __str__(self) -> str:
        return self.message
