"""
The rules that need no call: shapes the API rejects, and defects visible in the
structure instead of in the wording.

These run first and always. A query that fails one of them either cannot be sent
or is broken in a way no amount of rephrasing fixes, and finding that out should
not cost a round trip.
"""
from __future__ import annotations

import re
from typing import Any

from .catalogue import Catalogue, Check
from .errors import JevLintError
from .query import Query, ReviewedQuestion
from .report import Finding, Patch, Report, Severity
from .rules import RULES
from .support import Json, has_letter, is_invisible, is_letter_or_number
from .text import Text

_PINNED_BUILD = re.compile(r'^jev-\d+(?:\.\d+)*$')

_WHOLE_NUMBER = re.compile(r'^-?\d+$')

# What the API takes, as `Too many choices. Must have at most 255 choices.` on a 400.
_MOST_OPTIONS = 255

# The largest number a JavaScript object treats as an array index.
_LARGEST_INDEX = 4294967294

_INDEX_LIKE = re.compile(r'^(0|[1-9][0-9]*)$')


def _is_index(label: str) -> bool:
    return _INDEX_LIKE.match(label) is not None and int(label) <= _LARGEST_INDEX


def _as_javascript_sends(labels: list[str]) -> list[str]:
    """The options in the order a JavaScript object would list them.

    A key holding the plain decimal form of a number up to 2^32 - 2 is an array
    index, and an object lists every one of those first, in ascending order,
    before the keys it was written with.
    """
    indexes = sorted((label for label in labels if _is_index(label)), key=int)

    return indexes + [label for label in labels if not _is_index(label)]


class StaticLinter:
    RULES = RULES

    def __init__(
        self,
        catalogue: Catalogue,
        max_state_chars: int = 20000,
        only: list[str] | None = None,
    ) -> None:
        self._catalogue = catalogue
        self._max_state_chars = max_state_chars
        # check ids to run, or all of them when empty
        self._only = only or []

    def run(self, query: Query, report: Report) -> None:
        report.asked(self._applicable(query))
        self._query_rules(query, report)

        for question in query.questions:
            self._question_rules(question, report)

    def _applicable(self, query: Query) -> int:
        """
        How many static checks have anything to look at in this query.

        A question-scoped rule needs a question of a type it covers; a
        query-scoped one always has the query.
        """
        types = list(dict.fromkeys(question.type for question in query.questions))
        applicable = 0

        for check in self._catalogue.static():
            if len(self._only) > 0 and check.id not in self._only:
                continue

            if check.scope == 'query' or any(check.covers(type) for type in types):
                applicable += 1

        return applicable

    def _query_rules(self, query: Query, report: Report) -> None:
        if len(query.questions) == 0:
            self._raise('query.noQuestions', 'query', report)

            return

        seen: dict[str, str] = {}

        for question in query.questions:
            text = question.instructions_text().strip()

            if text == '':
                continue

            other = seen.get(text)

            if other is not None:
                self._raise(
                    'query.duplicateInstructions',
                    question.id,
                    report,
                    Text.of('evidence.identical_to', {'other': other}),
                )

                continue

            seen[text] = question.id

        # A request naming no build at all makes no claim about one, and the
        # report names the build it ran against. An alias claims a build and
        # resolves to a different one the day a newer lands.
        if isinstance(query.model, str) and _PINNED_BUILD.match(query.model) is None:
            self._raise(
                'query.floatingModel',
                'query',
                report,
                Text.of('evidence.found_quoted', {'what': query.model}),
            )

        extra = [key for key in query.raw if key not in ('state', 'questions', 'model')]

        if len(extra) > 0:
            # The keys as pointers, not only inside the sentence. An error whose
            # fix is "delete this key" gave a fixer nothing but prose to parse.
            self._raise(
                'query.unknownKey',
                'query',
                report,
                Text.of('evidence.found', {'what': ', '.join(f'`{key}`' for key in extra)}),
                Patch('remove', f'/{Check.escape(extra[0])}') if len(extra) == 1 else None,
                [f'/{Check.escape(key)}' for key in extra],
            )

        if not query.has_state():
            self._raise('state.missing', 'query', report)

            return

        size = query.state_size()

        if size > self._max_state_chars:
            self._raise(
                'state.oversized',
                'state',
                report,
                Text.of('evidence.state_size', {'size': size, 'threshold': self._max_state_chars}),
            )

    def _question_rules(self, question: ReviewedQuestion, report: Report) -> None:
        if not question.is_known_type():
            self._raise(
                'question.unknownType',
                question.id,
                report,
                Text.of('evidence.found_quoted', {'what': question.type}),
            )

            return

        declared = question.raw.get('type')

        if isinstance(declared, str) and declared != declared.lower():
            # The whole fix is one call to lower-case, so it is a patch and not
            # advice, and it addresses `type` and not the question around it.
            self._raise(
                'question.typeNotLowercase',
                question.id,
                report,
                Text.of('evidence.found_quoted', {'what': declared}),
                Patch(
                    'replace',
                    f'/questions/{Check.escape(question.id)}/type',
                    declared.lower(),
                    Patch.LOSSLESS,
                ),
            )

        # `criteria` present but neither a list nor a map: a comma-separated
        # string reads as options to a person and is one value to the API.
        if 'criteria' in question.raw and not isinstance(question.raw['criteria'], (dict, list)):
            self._raise(
                'question.criteriaNotAStructure',
                question.id,
                report,
                Text.of('evidence.found', {'what': Json.inline(question.raw['criteria'])}),
            )

        if all(is_invisible(character) for character in question.instructions_text()):
            self._raise('question.noInstructions', question.id, report)
        elif isinstance(question.instructions, (dict, list)) and _words(question.instructions).strip() == '':
            self._raise('question.instructionsEmpty', question.id, report)
        elif _instruction_is_id(question):
            self._raise(
                'question.instructionIsId',
                question.id,
                report,
                Text.of('evidence.instructions', {'text': question.instructions_text()}),
            )

        if question.type == 'noul':
            self._noul_rules(question, report)
        elif question.type == 'choice':
            self._choice_rules(question, report)
        elif question.type == 'score':
            self._score_rules(question, report)

    def _noul_rules(self, question: ReviewedQuestion, report: Report) -> None:
        if not question.has_criteria():
            self._raise('noul.noCriteria', question.id, report)

            return

        entries = question.entries()
        keys = [key.lower() for key, _ in entries]

        if question.criteria_is_list() or any(key not in ('true', 'false') for key in keys):
            renamed: dict[str, Any] | None = None

            # Two keys that differ only in case - `yes` beside `YES` - collapse
            # onto one renamed key, and the second description overwrites the
            # first. Nothing may be lost under a lossless patch, so where the keys
            # collide the advice stands without one.
            if (not question.criteria_is_list()
                    and all(key in ('yes', 'no') for key in keys)
                    and len(set(keys)) == len(keys)):
                renamed = {
                    'true' if key.lower() == 'yes' else 'false': value for key, value in entries
                }

            self._raise(
                'noul.criteriaShape',
                question.id,
                report,
                Text.of('evidence.keys', {
                    'keys': Text.of('evidence.none') if len(keys) == 0 else ', '.join(keys),
                }),
                None if renamed is None else Patch(
                    'replace',
                    f'/questions/{Check.escape(question.id)}/criteria',
                    renamed,
                    Patch.LOSSLESS,
                ),
            )

    def _choice_rules(self, question: ReviewedQuestion, report: Report) -> None:
        criteria = question.criteria

        # `criteria` absent altogether, as opposed to the wrong shape, left every
        # Choice rule unreached and the query reported clean.
        if criteria is None:
            if 'criteria' not in question.raw:
                self._raise('choice.noCriteria', question.id, report)

            return

        if isinstance(criteria, list):
            labels = [value for value in criteria if isinstance(value, str)]

            # Only where every entry is a label this can keep, and every label is
            # distinct. An entry that is a number or a nested object has no label
            # to carry over, and two entries spelled the same collapse onto one
            # key, so either way a patch here removes an option the caller wrote.
            whole = len(labels) == len(criteria) and len(set(labels)) == len(labels)

            # Numeric-looking labels would be written back as a JSON array - the
            # very shape this check exists to refuse, so the patch would not clear
            # its own finding.
            keyed = all(label != '' and _parsed_int(label) != label for label in labels)

            self._raise(
                'choice.criteriaShape',
                question.id,
                report,
                None,
                Patch(
                    'replace',
                    f'/questions/{Check.escape(question.id)}/criteria',
                    dict.fromkeys(labels, ''),
                    Patch.LOSSY,
                ) if whole and keyed and len(labels) >= 2 else None,
            )

            return

        entries = question.entries()
        labels = [label for label, _ in entries]

        if len(labels) < 2:
            self._raise(
                'choice.tooFewOptions',
                question.id,
                report,
                Text.of('evidence.option_count', {'count': len(labels)}),
            )

        if len(labels) > _MOST_OPTIONS:
            self._raise(
                'choice.tooManyOptions',
                question.id,
                report,
                Text.of('evidence.option_count', {'count': len(labels)}),
            )

        not_text = [value for _, value in entries if value is not None and not isinstance(value, str)]

        if len(not_text) > 0:
            self._raise(
                'choice.descriptionNotText',
                question.id,
                report,
                Text.of('evidence.found', {'what': Json.inline(not_text[0])}),
            )

            return

        described = [
            (label, value) for label, value in entries
            if value is not None and value != '' and not _is_empty_list(value)
        ]

        # One definition of a catch-all, on the question that owns it, so the rule
        # cannot offer to add a second one beside a catch-all it failed to
        # recognise by name.
        if not question.has_fallback_option():
            self._raise(
                'choice.noFallback',
                question.id,
                report,
                Text.of('evidence.options', {'options': ', '.join(labels)}),
                # Adding a fallback to options that carry no descriptions leaves
                # the criteria in a shape the next check rejects, so no patch.
                None if len(described) == 0 else Patch(
                    'add',
                    f'/questions/{Check.escape(question.id)}/criteria',
                    {**dict(question.entries()), 'other': Text.of('patch.fallback_option')},
                    Patch.LOSSY,
                ),
            )

        if len(described) == 0:
            self._raise('choice.undescribedOptions', question.id, report)

        sent = _as_javascript_sends(labels)

        if sent != labels:
            self._raise(
                'choice.indexLikeOptions',
                question.id,
                report,
                Text.of('evidence.reordered_options', {
                    'written': ', '.join(labels),
                    'sent': ', '.join(sent),
                }),
            )

    def _score_rules(self, question: ReviewedQuestion, report: Report) -> None:
        criteria = question.criteria

        if criteria is None:
            if 'criteria' not in question.raw:
                self._raise('score.noCriteria', question.id, report)

            return

        values = [value for _, value in question.entries()]
        structured = [value for value in values if isinstance(value, (dict, list))]

        if len(structured) > 0:
            self._raise(
                'score.levelsNotText',
                question.id,
                report,
                Text.of('evidence.found', {'what': Json.inline(structured[0])}),
            )

            return

        if not isinstance(criteria, list):
            entries = question.entries()

            # A Score is an ordered rubric, so the order of the list this becomes
            # is the meaning. Keys that are all numbers say what the order is, and
            # taking them in the order they happened to be written ships a
            # reversed scale that clears this check and is wrong.
            numeric = len(entries) > 0 and all(_WHOLE_NUMBER.match(key) for key, _ in entries)
            in_order = sorted(entries, key=lambda entry: int(entry[0])) if numeric else entries

            levels = [
                value if isinstance(value, str) and value != '' else key for key, value in in_order
            ]

            # Every level has to survive as the text somebody wrote. Where a value
            # is empty or is not text, the line above puts the key in its place,
            # and a rubric level replaced by its own index is content lost under a
            # patch that says nothing is.
            describes = all(isinstance(value, str) and value != '' for _, value in in_order)

            # A map of one is not a rubric, and a map of more than ten is past
            # what a Score takes, so reshaping either produces a file that fails
            # the query schema.
            sized = 2 <= len(in_order) <= 10

            self._raise(
                'score.criteriaShape',
                question.id,
                report,
                Text.of('evidence.keys_are_numbers') if numeric else Text.of('evidence.keys_are_names'),
                # Only where the keys say what the order is. With names, the order
                # of a map is the order it happened to be written in, and a patch
                # built from that ships a scrambled rubric that clears this check.
                # A caller applying patches unattended cannot read the line above.
                Patch(
                    'replace',
                    f'/questions/{Check.escape(question.id)}/criteria',
                    levels,
                    Patch.LOSSLESS,
                ) if numeric and describes and sized else None,
            )

            return

        levels = criteria

        if len(levels) < 2:
            self._raise(
                'score.tooFewLevels',
                question.id,
                report,
                Text.of('evidence.level_count', {'count': len(levels)}),
            )

            return

        if len(levels) > 10:
            self._raise(
                'score.tooManyLevels',
                question.id,
                report,
                Text.of('evidence.level_count', {'count': len(levels)}),
            )

        wordless = [
            level for level in levels
            if not isinstance(level, (dict, list)) and not has_letter(_scalar(level))
        ]

        if len(wordless) == len(levels):
            self._raise(
                'score.numericLevels',
                question.id,
                report,
                Text.of('evidence.levels', {'levels': ', '.join(_scalar(level) for level in levels)}),
            )

    def _raise(
        self,
        rule: str,
        target: str,
        report: Report,
        evidence: str | None = None,
        patch: Patch | None = None,
        paths: list[str] | None = None,
    ) -> None:
        """`paths` names every node at fault, where a finding names more than one."""
        paths = paths or []
        check = self._catalogue.rule(rule)

        # A rule the catalogue does not name is a typo, not a condition. Returning
        # quietly drops the finding, turns a failing run green, and leaves every
        # test passing, so it is raised as the programming error it is.
        if check is None:
            raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.rule_unclaimed', {'rule': rule}))

        if len(self._only) > 0 and check.id not in self._only:
            return

        report.add(Finding(
            check_id=check.id,
            title=check.title,
            severity=Severity.from_name(check.severity),
            target=target,
            message=check.message or check.title,
            hint=check.hint,
            suggest=check.suggest.replace('{target}', target),
            advice=check.advice,
            mode=check.mode,
            action=check.action,
            path=check.path(target) if len(paths) == 0 else paths[0],
            supersedes=check.supersedes,
            docs=check.docs,
            evidence=evidence,
            patch=patch,
            paths=paths,
        ))


def _words(node: Any) -> str:
    """Every string anywhere inside a structured instruction."""
    values = node.values() if isinstance(node, dict) else node

    return ''.join(
        _words(value) if isinstance(value, (dict, list)) else (value if isinstance(value, str) else '')
        for value in values
    )


def _normalise(value: str) -> str:
    """
    Letters and digits in any script, so an accented word survives instead of
    being cut into the pieces between its accents.
    """
    return ''.join(
        character if is_letter_or_number(character) or character == ' ' else ' '
        for character in value.lower()
    ).strip()


def _instruction_is_id(question: ReviewedQuestion) -> bool:
    """
    An instruction that says no more than the id does. Ids are never sent, so the
    model sees nothing.
    """
    question_id = _normalise(re.sub(r'[_\-.]', ' ', question.id))
    instructions = _normalise(question.instructions_text())

    if question_id == '' or instructions == '':
        return False

    instruction_words = instructions.split()

    if len(instruction_words) > 4:
        return False

    id_words = question_id.split()

    # "Is the customer blocked?" is four words and contains the id, and it is a
    # whole question. What makes an instruction lean on its id is that it adds
    # nothing to it: "Refund requested?" beside `refund_requested` does, and the
    # grammar around it is not content.
    grammar = Text.list('words.grammar')
    content = [word for word in instruction_words if word not in grammar]

    if any(word not in id_words for word in content):
        return False

    return all(word in instruction_words for word in id_words)


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return '1' if value else ''

    if value is None:
        return ''

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value)


def _parsed_int(label: str) -> str:
    """`String(Number.parseInt(label, 10))`, which is how a numeric label is spotted."""
    found = re.match(r'^[+-]?\d+', label.strip())

    return str(int(found.group())) if found else 'NaN'


def _is_empty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 0
