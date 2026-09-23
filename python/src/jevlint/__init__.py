"""
The library surface: the linter, what it reads, and what it hands back.

`docs/python.md` covers what each of these is for. The console is not here -
reading the arguments, formatting the text report and turning a report into an
exit code belong to the CLI and to nothing else.
"""
from .catalogue import Catalogue, Check, Wording
from .config import Acceptance, Config
from .console.application import Application
from .errors import JevLintError
from .linter import ClientFactory, Linter
from .model_linter import ModelLinter
from .probe import Probe, QuestionBuilder, QuestionProbe, Reading
from .probe_formatter import ProbeFormatter
from .query import PRIMITIVES, Query, ReviewedQuestion
from .report import Finding, Note, Patch, Report, Severity
from .rules import RULES
from .self_test_formatter import SelfTestFormatter
from .selftest import CheckScore, SelfTest
from .static_linter import StaticLinter
from .support import Cause, Env, Json
from .text import CheckText, Text
from .text_formatter import TextFormatter
from .typesafe import (
    Answer,
    Choice,
    ChoiceAnswer,
    Client,
    Noul,
    NoulAnswer,
    Question,
    Score,
    ScoreAnswer,
    SystemOne,
    SystemOneResponse,
    Usage,
)

# The SDK's own error classes, so a caller catches one import and not two
from .typesafe.errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ResponseValidationError,
    TypeSafeError,
    UnprocessableEntityError,
)
from .variants import (
    CriteriaStripped,
    LevelsReversed,
    NoulAsChoice,
    OptionsReversed,
    Reworded,
    Unchanged,
    Variant,
)

__version__ = Application.VERSION

__all__ = [
    'PRIMITIVES',
    'RULES',
    'APIConnectionError',
    'APIError',
    'APITimeoutError',
    'Acceptance',
    'Answer',
    'Application',
    'AuthenticationError',
    'BadRequestError',
    'Catalogue',
    'Cause',
    'Check',
    'CheckScore',
    'CheckText',
    'Choice',
    'ChoiceAnswer',
    'Client',
    'ClientFactory',
    'Config',
    'CriteriaStripped',
    'Env',
    'Finding',
    'InternalServerError',
    'JevLintError',
    'Json',
    'LevelsReversed',
    'Linter',
    'ModelLinter',
    'NotFoundError',
    'Note',
    'Noul',
    'NoulAnswer',
    'NoulAsChoice',
    'OptionsReversed',
    'Patch',
    'PermissionDeniedError',
    'Probe',
    'ProbeFormatter',
    'Query',
    'Question',
    'QuestionBuilder',
    'QuestionProbe',
    'RateLimitError',
    'Reading',
    'Report',
    'ResponseValidationError',
    'ReviewedQuestion',
    'Reworded',
    'Score',
    'ScoreAnswer',
    'SelfTest',
    'SelfTestFormatter',
    'Severity',
    'StaticLinter',
    'SystemOne',
    'SystemOneResponse',
    'Text',
    'TextFormatter',
    'TypeSafeError',
    'Unchanged',
    'UnprocessableEntityError',
    'Usage',
    'Variant',
    'Wording',
    '__version__',
]
