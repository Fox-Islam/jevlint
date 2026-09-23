/**
 * Every rule the static linter can raise.
 *
 * A catalogue naming a rule that is not here claims a condition nobody tests:
 * the check loads, lists, documents itself and never fires. The opposite case
 * throws where the rule is raised
 *
 * This is its own module because the catalogue reads it at load, and the linter
 * that raises them reads the catalogue
 */
export const RULES = [
    'choice.criteriaShape',
    'choice.descriptionNotText',
    'choice.noCriteria',
    'choice.noFallback',
    'choice.tooFewOptions',
    'choice.undescribedOptions',
    'noul.criteriaShape',
    'noul.noCriteria',
    'query.duplicateInstructions',
    'query.floatingModel',
    'query.noQuestions',
    'query.unknownKey',
    'question.criteriaNotAStructure',
    'question.instructionIsId',
    'question.instructionsEmpty',
    'question.noInstructions',
    'question.typeNotLowercase',
    'question.unknownType',
    'score.criteriaShape',
    'score.levelsNotText',
    'score.noCriteria',
    'score.numericLevels',
    'score.tooFewLevels',
    'score.tooManyLevels',
    'state.missing',
    'state.oversized',
] as const;

/** A rule name, as a catalogue entry and the linter both write one */
export type Rule = (typeof RULES)[number];

export function isRule(name: string): name is Rule {
    return (RULES as readonly string[]).includes(name);
}
