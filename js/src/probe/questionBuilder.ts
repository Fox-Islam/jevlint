import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';
import type { ReviewedQuestion } from '../query/reviewedQuestion.js';
import { ordered } from '../support/ordered.js';
import { Choice, Noul, Question, Score, type Content } from '../typesafe/questions.js';

/** Turns a question from the file under test back into one that can be sent */
export const QuestionBuilder = {
    build(question: ReviewedQuestion): Question {
        switch (question.type) {
            case 'noul':
                return noul(question);
            case 'choice':
                return Choice.ask(question.instructions).options(options(question));
            case 'score':
                return Score.ask(question.instructions).levels(
                    question.entries().map(([, value]) => value as Content),
                );
            default:
                throw new JevLintError(Text.of('probe.question_has_no_type', { id: question.id }));
        }
    },
};

function noul(question: ReviewedQuestion): Noul {
    const built = Noul.ask(question.instructions);
    const criteria = (question.criteria ?? {}) as Record<string, unknown>;

    if (criteria['true'] !== undefined) {
        built.yes(content(criteria['true']));
    }

    if (criteria['false'] !== undefined) {
        built.no(content(criteria['false']));
    }

    return built;
}

function options(question: ReviewedQuestion): Record<string, Content> {
    return ordered(
        question.entries().map(([label, description]) => [label, content(description)]),
    ) as Record<string, Content>;
}

function content(value: unknown): Content {
    return typeof value === 'string' || (typeof value === 'object' && value !== null)
        ? value as Content
        : null;
}
