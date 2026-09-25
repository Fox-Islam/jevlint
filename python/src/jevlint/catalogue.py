"""
The check catalogue, read from `checks/catalogue.json`.

The file sits at the root of the repository instead of inside this package, so an
implementation in another language reads the same one. Nothing in it is
Python-specific: a static check names a rule the implementation owns, and a model
check is a Jev question, which is data in any language.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from .errors import JevLintError
from .paths import HERE
from .query import PRIMITIVES, Query
from .report import Severity
from .rules import is_rule
from .support import Json, encode_like_php
from .text import CheckText, Text

# A Jev version, as the catalogue and the command line write one
VERSION = re.compile(r'^\d+(\.\d+)*$')


def compare_versions(a: str, b: str) -> int:
    """
    Compare two Jev versions, oldest first.

    Each dot-separated part is a number, so 1.9 comes before 1.13. Comparing them
    as text puts 1.13 first and runs a query against the wrong build's rules.
    """
    left = [int(part) for part in a.split('.')]
    right = [int(part) for part in b.split('.')]

    for index in range(max(len(left), len(right))):
        difference = (left[index] if index < len(left) else 0) - (right[index] if index < len(right) else 0)

        if difference != 0:
            return -1 if difference < 0 else 1

    return 0


def _version_key(version: str) -> list[int]:
    return [int(part) for part in version.split('.')]


class SecondQuestion:
    """
    A question asked beside a check that overrules its verdict, and the reading it
    takes. It asks something different from the check, so it decides on its own
    instead of being averaged in with the check's wordings.
    """

    def __init__(self, wording: Wording, trigger: float) -> None:
        self.wording = wording
        self.trigger = trigger


class Wording:
    """
    One way of asking a check.

    A check may carry several. They are meant to mean the same thing, so the
    spread between their answers is reported with the finding as its error bar.
    """

    def __init__(self, type: str, text: str, criteria: dict[str, Any] | list[Any] | None) -> None:
        self.type = type
        self.text = text
        self.criteria = criteria

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Wording:
        type = data.get('type')
        instructions = data.get('instructions')
        criteria = data.get('criteria')

        return Wording(
            type if isinstance(type, str) else 'noul',
            instructions if isinstance(instructions, str) else '',
            criteria if isinstance(criteria, (dict, list)) else None,
        )

    def instructions(self, field: str = '') -> str:
        """The instructions with `{field}` filled in, where the check is asked per state field."""
        return self.text.replace('{field}', field)


class Check:
    """
    One entry from `checks/catalogue.json`.

    A static check names a rule implemented in code. A model check carries the Jev
    question that decides it, and the probability above which that question's
    answer becomes a finding.
    """

    # Conditions a `suppress` entry may name
    SUPPRESSIONS = ('question_has_fallback_option',)

    # The parts of a query `path()` can address
    READS = ('query', 'state', 'field', 'instructions', 'criteria', 'type', 'question')

    def __init__(self, **fields: Any) -> None:
        self.id: str = fields['id']
        self.title: str = fields['title']
        self.mode: str = fields['mode']
        self.scope: str = fields['scope']
        self.applies_to: list[str] = fields['applies_to']
        self.severity: str = fields['severity']
        self.rule: str | None = fields['rule']
        self.message: str | None = fields['message']
        self.question: dict[str, Any] | None = fields['question']
        self.wordings: list[Wording] = fields['wordings']
        self.trigger: float = fields['trigger']
        self.requires: str | None = fields['requires']
        self.compare: str | None = fields['compare']
        self.hint: str = fields['hint']
        self.suggest: str = fields['suggest']
        self.reads: str = fields['reads']
        self.action: str = fields['action']
        self.locate: str | None = fields['locate']
        self.removes: str | None = fields['removes']
        self.locate_mode: str = fields['locate_mode']
        self.supersedes: list[str] = fields['supersedes']
        # The documented failure modes this check is written against
        self.jaggedness: list[str] = fields['jaggedness']
        self.suppress: list[dict[str, str]] = fields['suppress']
        # Reading above its own trigger, one sets a finding aside and the other
        # raises one the check's own reading did not
        self.cleared_by: SecondQuestion | None = fields['cleared_by']
        self.fired_by: SecondQuestion | None = fields['fired_by']
        # Whether a reading under the trigger says nothing. A check whose clean
        # and defective readings overlap is reported either way, because silence
        # from it would read as a clean bill of health.
        self.inconclusive: bool = fields['inconclusive']
        self.docs: str | None = fields['docs']
        self.advice: str = fields['advice']
        self.since: str | None = fields['since']
        self.until: str | None = fields['until']

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Check:
        check_id = data['id'] if isinstance(data.get('id'), str) else '?'
        trigger = data.get('trigger')

        if trigger is not None and (
            isinstance(trigger, bool) or not isinstance(trigger, (int, float)) or not 0.3 <= trigger <= 0.95
        ):
            raise JevLintError.of(JevLintError.CATALOGUE, Text.of('check.trigger_out_of_range', {
                'id': check_id,
                'trigger': _type_name(trigger) if isinstance(trigger, (dict, list)) else _js_string(trigger),
            }))

        for required in ('id', 'title', 'mode', 'scope', 'severity'):
            if not isinstance(data.get(required), str):
                raise JevLintError.of(
                    JevLintError.CATALOGUE,
                    Text.of('check.missing_field', {'field': required}),
                )

        # A severity nobody recognises cannot fall back to `warning`: one typo in
        # the catalogue would demote an error and a failing run would pass.
        severities = [severity.value for severity in Severity.cases()]

        if data['severity'] not in severities:
            raise JevLintError.of(JevLintError.CATALOGUE, Text.of('check.bad_severity', {
                'id': check_id,
                'given': str(data['severity']),
                'allowed': ', '.join(severities),
            }))

        modes = ['static', 'model']

        if data['mode'] not in modes:
            raise JevLintError.of(JevLintError.CATALOGUE, Text.of('check.bad_mode', {
                'id': check_id,
                'given': str(data['mode']),
                'allowed': ', '.join(modes),
            }))

        if data['mode'] == 'model' and trigger is None:
            raise JevLintError.of(
                JevLintError.CATALOGUE,
                Text.of('check.model_without_trigger', {'id': check_id}),
            )

        # Every one of these is asked by name in the model linter. A check under a
        # scope it does not ask never runs.
        scopes = ['question', 'state', 'state-field', 'state-once', 'query']

        if data['scope'] not in scopes:
            raise JevLintError.of(JevLintError.CATALOGUE, Text.of('check.bad_scope', {
                'id': check_id,
                'given': str(data['scope']),
                'allowed': ', '.join(scopes),
            }))

        declared = data.get('applies_to', ['*'])
        applies_to = [value for value in declared if isinstance(value, str)] if isinstance(declared, list) else []

        if len(applies_to) == 0:
            raise JevLintError.of(
                JevLintError.CATALOGUE,
                Text.of('check.applies_to_nothing', {'id': check_id}),
            )

        since = _bound(data, 'since', check_id)
        until = _bound(data, 'until', check_id)

        if since is not None and until is not None and compare_versions(since, until) > 0:
            raise JevLintError.of(JevLintError.CATALOGUE, Text.of('check.empty_version_span', {
                'id': check_id,
                'since': since,
                'until': until,
            }))

        translated = CheckText.for_check(check_id)

        return Check(
            id=check_id,
            title=translated.get('title', str(data['title'])),
            mode=str(data['mode']),
            scope=str(data['scope']),
            applies_to=applies_to,
            severity=str(data['severity']),
            rule=_text(data.get('rule')),
            message=translated.get('message', _text(data.get('message'))),
            question=data['question'] if isinstance(data.get('question'), dict) else None,
            wordings=_read_wordings(data),
            trigger=float(trigger) if isinstance(trigger, (int, float)) else 0.7,
            requires=_text(data.get('requires')),
            compare=_text(data.get('compare')),
            hint=translated.get('hint', _text(data.get('hint')) or ''),
            suggest=translated.get('suggest', _text(data.get('suggest')) or ''),
            reads=_reads_of(data, check_id),
            action=_text(data.get('action')) or 'rewrite',
            locate=_text(data.get('locate')),
            removes=_text(data.get('removes')),
            locate_mode=_text(data.get('locate_mode')) or 'pick',
            supersedes=_strings(data.get('supersedes')),
            jaggedness=_strings(data.get('jaggedness')),
            suppress=_suppressions(data, check_id),
            cleared_by=_second_question(data, 'cleared_by', check_id),
            fired_by=_second_question(data, 'fired_by', check_id),
            inconclusive=data.get('inconclusive') is True,
            docs=_text(data.get('docs')),
            advice=_text(data.get('advice')) or '',
            since=since,
            until=until,
        )

    def covers_jev(self, version: str) -> bool:
        """
        Whether this check is one of the rules for this Jev version.

        A defect one build reads past is a defect the next one may not have, so a
        check retired by `until` keeps working for the versions it was written for.
        """
        if self.since is not None and compare_versions(version, self.since) < 0:
            return False

        return self.until is None or compare_versions(version, self.until) <= 0

    def is_composite(self) -> bool:
        """Whether this check is asked more than one way."""
        return len(self.wordings) > 1

    def path(self, target: str, field: str | None = None) -> str:
        """
        Where in the query file the finding points, as a JSON pointer.

        An agent patching a query needs the node, not the question id.
        """
        if self.reads == 'query':
            return ''

        if self.reads == 'state':
            return '/state'

        if self.reads == 'field':
            return f'/state{_pointer(field or "")}'

        if self.reads in ('instructions', 'criteria', 'type'):
            return f'/questions/{Check.escape(target)}/{self.reads}'

        # `reads` is checked against READS at load, so this is `question` and not
        # a typo that fell through.
        return f'/questions/{Check.escape(target)}'

    @staticmethod
    def escape(segment: str) -> str:
        """
        One segment of an RFC 6901 pointer.

        A question id is a key somebody chose, so it can hold a `/` or a `~`, and
        an unescaped one addresses a different node or none at all.
        """
        return segment.replace('~', '~0').replace('/', '~1')

    def is_static(self) -> bool:
        return self.mode == 'static'

    def is_model(self) -> bool:
        return self.mode == 'model'

    def covers(self, type: str) -> bool:
        """Whether this check has anything to say about a question of this type."""
        return '*' in self.applies_to or type in self.applies_to

    def answer_key(self) -> str:
        """The key this check's answer comes back under, with `/` and `-` mapped to `_`."""
        return self.id.replace('/', '_').replace('-', '_')

    def question_type(self) -> str:
        """The question type this check asks, for a model check."""
        return self.wordings[0].type if self.wordings else 'noul'

    def instructions(self, field: str = '') -> str:
        """
        The check's own instructions, with `{field}` replaced where the check is
        asked once per state field.
        """
        return self.wordings[0].instructions(field) if self.wordings else ''

    def criteria(self) -> dict[str, Any] | list[Any] | None:
        return self.wordings[0].criteria if self.wordings else None


def _pointer(dotted: str) -> str:
    """
    A dotted field path as an RFC 6901 pointer.

    `application.role` addresses `/application/role`, and a `/` or `~` inside a
    key is escaped so a key containing one still resolves.
    """
    if dotted == '':
        return ''

    return '/' + '/'.join(Check.escape(segment) for segment in Query.segments(dotted))


def _bound(data: dict[str, Any], key: str, check_id: str) -> str | None:
    """One end of the range of Jev versions a check is written for."""
    value = data.get(key)

    if value is None:
        return None

    if not isinstance(value, str) or VERSION.match(value) is None:
        raise JevLintError.of(JevLintError.CATALOGUE, Text.of('check.bad_version', {
            'id': check_id,
            'field': key,
            'given': _type_name(value) if isinstance(value, (dict, list)) else f'"{_js_string(value)}"',
        }))

    return value


def _read_wordings(data: dict[str, Any]) -> list[Wording]:
    """
    Every way this check can be asked.

    `question` holds one wording, `questions` holds several. Several go in the
    same call, so they cost the questions but not a round trip, and their answers
    are combined.
    """
    questions = data.get('questions')

    if isinstance(questions, list) and len(questions) > 0:
        return [Wording.from_dict(wording if isinstance(wording, dict) else {}) for wording in questions]

    question = data.get('question')

    return [Wording.from_dict(question)] if isinstance(question, dict) else []


def _second_question(data: dict[str, Any], name: str, check_id: str) -> SecondQuestion | None:
    declared = data.get(name)

    if declared is None:
        return None

    question = declared.get('question') if isinstance(declared, dict) else None
    trigger = declared.get('trigger') if isinstance(declared, dict) else None

    if (not isinstance(question, dict)
            or question.get('type', 'noul') != 'noul'
            or not isinstance(question.get('instructions'), str)
            or isinstance(trigger, bool)
            or not isinstance(trigger, (int, float))
            or not 0 < trigger < 1):
        raise JevLintError.of(JevLintError.CATALOGUE, Text.of('check.bad_second_question', {
            'id': check_id,
            'name': name,
        }))

    return SecondQuestion(Wording.from_dict(question), float(trigger))


def _suppressions(data: dict[str, Any], check_id: str) -> list[dict[str, str]]:
    declared = data.get('suppress')
    rules: list[dict[str, str]] = []

    for rule in declared if isinstance(declared, list) else []:
        if (not isinstance(rule, dict)
                or not isinstance(rule.get('answer'), str)
                or not isinstance(rule.get('when'), str)):
            raise JevLintError.of(
                JevLintError.CATALOGUE,
                Text.of('check.bad_suppress_entry', {'id': check_id}),
            )

        if rule['when'] not in Check.SUPPRESSIONS:
            raise JevLintError.of(JevLintError.CATALOGUE, Text.of('check.unknown_suppression', {
                'id': check_id,
                'given': rule['when'],
                'allowed': ', '.join(Check.SUPPRESSIONS),
            }))

        rules.append({'answer': rule['answer'], 'when': rule['when']})

    return rules


def _reads_of(data: dict[str, Any], check_id: str) -> str:
    """
    Which part of the query a check looks at, checked against what `path()` knows
    how to address. A typo would fall through to the default arm and report a
    pointer to the question instead of the node, which reads as a real value.
    """
    reads = data.get('reads', 'question')

    if not isinstance(reads, str) or reads not in Check.READS:
        raise JevLintError.of(JevLintError.CATALOGUE, Text.of('check.unknown_reads', {
            'id': check_id,
            'given': _type_name(reads) if isinstance(reads, (dict, list)) else _js_string(reads),
            'allowed': ', '.join(Check.READS),
        }))

    return reads


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _type_name(value: Any) -> str:
    if value is None:
        return 'null'

    if isinstance(value, list):
        return 'array'

    if isinstance(value, bool):
        return 'boolean'

    if isinstance(value, (int, float)):
        return 'number'

    if isinstance(value, str):
        return 'string'

    return 'object'


def _js_string(value: Any) -> str:
    """A scalar as the other two implementations put it into a message."""
    if value is None:
        return 'null'

    if isinstance(value, bool):
        return 'true' if value else 'false'

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value)


class Catalogue:
    # What `--jev` is given when nobody pins a version
    LATEST = 'latest'

    def __init__(
        self,
        version: str,
        jev: str,
        versions: list[str],
        fingerprint: str,
        asked: str,
        checks: list[Check],
        written: list[Check],
    ) -> None:
        self.version = version
        self.jev = jev
        # the Jev versions the file covers, oldest first
        self.versions = versions
        self.fingerprint = fingerprint
        self.asked = asked
        # The Jev build the carried checks are the rules for, as the report names it
        self.model = f'jev-{jev}'
        self._checks = checks
        self._written = written

    @staticmethod
    def load(path: str | None = None) -> Catalogue:
        file = path or Catalogue.locate('catalogue.json')
        contents = Path(file).read_bytes()
        data = Json.decode(contents.decode('utf-8'), file)

        if not isinstance(data.get('checks'), list) or len(data['checks']) == 0:
            raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.no_checks', {'path': file}))

        declared = data['checks']

        # The version is what two reports are compared on, so an invented one is
        # worse than none.
        version = data.get('version')

        if version is not None and (isinstance(version, bool) or not isinstance(version, (str, int, float))):
            raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.version_wrong_type', {
                'path': file,
                'type': _type_name(version),
            }))

        # Two checks under one id behave as one or the other depending on which
        # lookup you go through: `--only` narrows to both, `find()` answers with
        # whichever comes first.
        ids: set[str] = set()

        for check in declared:
            check_id = check.get('id') if isinstance(check, dict) else None

            if not isinstance(check_id, str):
                continue

            if check_id in ids:
                raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.duplicate_id', {
                    'path': file,
                    'id': check_id,
                }))

            ids.add(check_id)

        versions = _read_versions(data, file)

        for position, check in enumerate(declared):
            # A null or a number reaching Check.from_dict is a crash and a stack
            # trace, where a caller was promised a message.
            if not isinstance(check, dict):
                raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.check_not_an_object', {
                    'path': file,
                    'type': _type_name(check),
                    'position': f'#{position + 1}',
                }))

        checks = [Check.from_dict(check) for check in declared]

        # A static check naming a rule no code raises can never fire, and the
        # report that leaves it out reads exactly like a clean one. The opposite
        # case raises where the rule is raised.
        for check in checks:
            if check.is_static() and (check.rule is None or not is_rule(check.rule)):
                raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.unknown_rule', {
                    'id': check.id,
                    'rule': Text.of('catalogue.rule_nothing') if check.rule is None else f'"{check.rule}"',
                }))

        # Both of these are collisions only among the checks one version runs. A
        # rule whose severity changed between Jev versions is two checks naming
        # it, separated by `since` and `until`, and they never meet.
        for version_run in versions:
            rules: dict[str, str] = {}
            keys: dict[str, str] = {}

            for check in checks:
                if not check.covers_jev(version_run):
                    continue

                # Two checks naming one rule is worse than two sharing an id:
                # `rule()` answers with the first, and the finding is reported
                # under its id and its severity. A second check demoting the first
                # to advice takes a run that exited 1 down to 0, and the report
                # reads as a pass.
                if check.is_static() and check.rule is not None:
                    first = rules.get(check.rule)

                    if first is not None:
                        raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.rule_shadowed', {
                            'first': first,
                            'second': check.id,
                            'rule': check.rule,
                            'jev': version_run,
                        }))

                    rules[check.rule] = check.id

                # Two ids differing only in `/` against `-` collide once
                # `answer_key()` has replaced both, so the second overwrites the
                # first in the request and is reported carrying its answer.
                if check.is_model():
                    key = check.answer_key()
                    first = keys.get(key)

                    if first is not None:
                        raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.key_collision', {
                            'first': first,
                            'second': check.id,
                            'key': key,
                            'jev': version_run,
                        }))

                    keys[key] = check.id

        # The model half of the rule guard above. A model check is its question,
        # so one carrying none is counted among the checks that ask, listed by
        # `checks`, and never asked.
        for check in checks:
            if check.is_model() and len(check.wordings) == 0:
                raise JevLintError.of(
                    JevLintError.CATALOGUE,
                    Text.of('catalogue.model_without_question', {'id': check.id}),
                )

        # `applies_to` is matched against a question's type, so a primitive that
        # does not exist narrows the check to nothing.
        for check in checks:
            allowed = [*PRIMITIVES, '*']
            unknown = [primitive for primitive in check.applies_to if primitive not in allowed]

            if len(unknown) > 0:
                raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.unknown_primitive', {
                    'id': check.id,
                    'primitive': unknown[0],
                    'primitives': ', '.join(PRIMITIVES),
                }))

        # A `supersedes` naming nothing drops the suppression it was written for,
        # and the finding it should have discarded is reported beside the one that
        # replaces it.
        known = {check.id for check in checks}

        for check in checks:
            for superseded in check.supersedes:
                if superseded not in known:
                    raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.supersedes_unknown', {
                        'id': check.id,
                        'other': superseded,
                    }))

        # A check written for no version the file covers can never run: a `since`
        # a release ahead of the catalogue does that.
        for check in checks:
            if not any(check.covers_jev(version_run) for version_run in versions):
                raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.covers_no_version', {
                    'id': check.id,
                    'versions': ', '.join(versions),
                }))

        latest = versions[-1] if versions else ''

        # A second fingerprint over what the checks ask, and nothing else. The
        # whole-file one moves when a message is reworded, which tells a corpus
        # its readings are stale when nothing it measured has changed.
        asked: list[dict[str, Any]] = []

        for check in declared:
            if check.get('mode') != 'model':
                continue

            # `scope` decides whether the state goes in front of the check and
            # `locate_mode` decides whether a locator is one Choice or one
            # question per level, so both change the calls without touching a word
            # of the question. `since` and `until` decide whether the check is
            # asked at all.
            asked.append({
                'id': check.get('id'),
                'scope': check.get('scope'),
                'trigger': check.get('trigger'),
                'questions': check.get('questions', check.get('question')),
                'requires': check.get('requires'),
                'cleared_by': check.get('cleared_by'),
                'fired_by': check.get('fired_by'),
                'compare': check.get('compare'),
                'locate': check.get('locate'),
                'locate_mode': check.get('locate_mode'),
                'applies_to': check.get('applies_to'),
                'since': check.get('since'),
                'until': check.get('until'),
            })

        return Catalogue(
            str(version if version is not None else '0'),
            latest,
            versions,
            # The version moves when somebody remembers. This moves whenever the
            # file does, which is what decides whether two reports compare; the
            # `asked` digest beside it moves only when a call would change.
            _digest(contents),
            _digest(encode_like_php(asked).encode('utf-8')),
            [check for check in checks if check.covers_jev(latest)],
            checks,
        )

    @staticmethod
    def for_run(flag: str | None, config: Any) -> Catalogue:
        """
        The catalogue for the version this run resolves, which every command needs
        before it does anything else.

        The command line pins the version, then the config, then the newest the
        catalogue covers.
        """
        return Catalogue.load().for_jev(
            flag or config.jev or Catalogue.LATEST,
            None if flag is not None or config.jev is None else config.source,
        )

    def for_jev(self, requested: str, source: str | None = None) -> Catalogue:
        """
        The same catalogue narrowed to the rules for one Jev version.

        A query is sent to one build, and a build has the defects it has. Checking
        it against a later build's rules reports a defect the run will not hit.
        `source` is the file a version was pinned in, where one was, so a version
        this catalogue cannot run names that file and not a flag nobody passed.
        """
        version = self.resolve(requested, source)

        return Catalogue(
            self.version,
            version,
            self.versions,
            self.fingerprint,
            self.asked,
            [check for check in self._written if check.covers_jev(version)],
            self._written,
        )

    def resolve(self, requested: str, source: str | None = None) -> str:
        """The version a request names, with `latest` resolved."""
        if requested == Catalogue.LATEST:
            return self.versions[-1] if self.versions else ''

        named = {
            'from': 'flag' if source is None else 'config',
            'source': source or '',
            'requested': requested,
        }
        kind = JevLintError.USAGE if source is None else JevLintError.CONFIG

        if VERSION.match(requested) is None:
            raise JevLintError.of(kind, Text.of('catalogue.not_a_version', named))

        # Running 1.13's rules against a 1.9 query would report defects nobody
        # measured on 1.9 and miss the ones somebody did.
        if requested not in self.versions:
            raise JevLintError.of(kind, Text.of('catalogue.version_not_covered', {
                **named,
                'versions': ', '.join(self.versions),
            }))

        return requested

    def withheld(self) -> int:
        """How many of the file's checks this version does not carry."""
        return len(self._written) - len(self._checks)

    @staticmethod
    def locate(file: str) -> str:
        """
        Find a file in `checks/`, whether this package is the repository or is
        installed into someone else's site-packages.
        """
        directory = os.environ.get('JEVLINT_CHECKS_DIR')

        # An override, not a preference. Falling through to the bundled copy ran a
        # CI job against a different check set than the one it had mounted.
        if directory:
            named = Path(directory.rstrip('/')) / file

            if not named.is_file():
                raise JevLintError.of(JevLintError.NOT_FOUND, Text.of('catalogue.checks_dir_missing_file', {
                    'dir': directory,
                    'file': file,
                }))

            return str(named)

        for candidate in (HERE / 'checks' / file, HERE.parents[2] / 'checks' / file):
            if candidate.is_file():
                return str(candidate)

        raise JevLintError.of(
            JevLintError.NOT_FOUND,
            Text.of('catalogue.checks_not_found', {'file': file}),
        )

    def all(self) -> list[Check]:
        return self._checks

    def written(self) -> list[Check]:
        """Every check in the file, including the ones this version does not carry."""
        return self._written

    def find_written(self, check_id: str) -> Check | None:
        """A check by id, wherever in the file it is."""
        return next((check for check in self._written if check.id == check_id), None)

    def static(self) -> list[Check]:
        return [check for check in self._checks if check.is_static()]

    def model_checks(self, scope: str, type: str | None = None) -> list[Check]:
        """Model checks in one scope, applicable to a question of this type."""
        return [
            check for check in self._checks
            if check.is_model() and check.scope == scope and (type is None or check.covers(type))
        ]

    def find(self, check_id: str) -> Check | None:
        return next((check for check in self._checks if check.id == check_id), None)

    def rule(self, rule: str) -> Check | None:
        return next((check for check in self._checks if check.rule == rule), None)


def _read_versions(data: dict[str, Any], path: str) -> list[str]:
    """The Jev versions the file names, oldest first."""
    declared = data.get('jev')
    versions = list(dict.fromkeys(
        version for version in declared if isinstance(version, str)
    )) if isinstance(declared, list) else []

    if len(versions) == 0:
        raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.no_versions', {'path': path}))

    for version in versions:
        if VERSION.match(version) is None:
            raise JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.version_malformed', {
                'path': path,
                'version': version,
            }))

    return sorted(versions, key=_version_key)


def _digest(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()[:12]
