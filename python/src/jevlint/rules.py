"""
Every rule the static linter can raise.

A catalogue naming a rule that is not here claims a condition nobody tests: the
check loads, lists, documents itself and never fires. The opposite case raises
where the rule is raised.

This is its own module because the catalogue reads it at load, and the linter
that raises them reads the catalogue.
"""

RULES = (
    'choice.criteriaShape',
    'choice.descriptionNotText',
    'choice.indexLikeOptions',
    'choice.noCriteria',
    'choice.noFallback',
    'choice.tooFewOptions',
    'choice.tooManyOptions',
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
)


def is_rule(name: str) -> bool:
    """A rule name, as a catalogue entry and the linter both write one."""
    return name in RULES
