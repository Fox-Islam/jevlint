/**
 * The library surface: the linter, what it reads, and what it hands back.
 *
 * `docs/library.md` covers what each of these is for. The console is not here -
 * reading the arguments, formatting the text report and turning a report into
 * an exit code belong to the CLI and to nothing else
 */
export { Catalogue } from './catalogue/catalogue.js';
export { Check } from './catalogue/check.js';
export { Wording } from './catalogue/wording.js';
export { Acceptance } from './config/acceptance.js';
export { Config } from './config/config.js';
export { JevLintError } from './exceptions/jevLintError.js';
export { ProbeFormatter } from './format/probeFormatter.js';
export { SelfTestFormatter } from './format/selfTestFormatter.js';
export { TextFormatter } from './format/textFormatter.js';
export { CheckText } from './i18n/checkText.js';
export { Text } from './i18n/text.js';
export { ClientFactory } from './lint/clientFactory.js';
export { Linter } from './lint/linter.js';
export { ModelLinter } from './lint/modelLinter.js';
export { StaticLinter } from './lint/staticLinter.js';
export { RULES } from './lint/rules.js';
export { Probe } from './probe/probe.js';
export { QuestionProbe } from './probe/questionProbe.js';
export { Reading } from './probe/reading.js';
export { Variant } from './probe/variant.js';
export * from './probe/variants.js';
export { Query } from './query/query.js';
export { PRIMITIVES, ReviewedQuestion } from './query/reviewedQuestion.js';
export { Finding } from './report/finding.js';
export { Note } from './report/note.js';
export { Patch } from './report/patch.js';
export { Report } from './report/report.js';
export { Severity } from './report/severity.js';
export { CheckScore } from './selftest/checkScore.js';
export { SelfTest } from './selftest/selfTest.js';
export { Cause } from './support/cause.js';
export { Env } from './support/env.js';
export { Json } from './support/json.js';

export { Application } from './console/application.js';

export { Client, SystemOne, type ClientOptions, type Provider } from './typesafe/client.js';
export {
    Answer,
    ChoiceAnswer,
    NoulAnswer,
    ScoreAnswer,
    SystemOneResponse,
    Usage,
} from './typesafe/answers.js';
export { Choice, Noul, Question, Score, type Content } from './typesafe/questions.js';

/** The SDK's own error classes, so a caller catches one import and not two */
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
} from './typesafe/errors.js';
