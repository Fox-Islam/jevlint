"""What one run of the linter found: the findings, the notes, and what it cost."""
from __future__ import annotations

import math
from typing import Any

from .support import Cause
from .text import Text

_WEIGHTS = {'error': 3, 'warning': 2, 'advice': 1}


class Severity:
    """Higher is worse. Used for sorting and for the minimum-severity filter."""

    Error: Severity

    Warning: Severity

    Advice: Severity

    def __init__(self, value: str) -> None:
        self.value = value

    @staticmethod
    def cases() -> list[Severity]:
        return [Severity.Error, Severity.Warning, Severity.Advice]

    @staticmethod
    def from_name(value: str) -> Severity:
        """An unknown name is a warning, so a report never loses a finding to a typo."""
        return next(
            (severity for severity in Severity.cases() if severity.value == value.lower()),
            Severity.Warning,
        )

    def weight(self) -> int:
        return _WEIGHTS[self.value]

    def at_least(self, floor: Severity) -> bool:
        return self.weight() >= floor.weight()

    def __repr__(self) -> str:
        return f'Severity({self.value!r})'


Severity.Error = Severity('error')
Severity.Warning = Severity('warning')
Severity.Advice = Severity('advice')


class Note:
    """
    Something about the run itself, as opposed to the query.

    `unreachable` is the one that matters: a call that could not be made means
    those checks never ran, and a report that cannot say so reads exactly like a
    report that ran them and found nothing.
    """

    def __init__(
        self,
        message: str,
        kind: str = 'note',
        target: str | None = None,
        checks: int | None = None,
        cause: str | None = None,
        findings: int | None = None,
    ) -> None:
        self.message = message
        self.kind = kind
        self.target = target
        self.checks = checks
        self.cause = cause
        self.findings = findings

    def is_unreachable(self) -> bool:
        return self.kind == 'unreachable'

    def is_skip(self) -> bool:
        """Checks this run did not carry, for a reason that is not a failure."""
        return self.kind == 'skipped'

    def to_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {'kind': self.kind, 'target': self.target, 'message': self.message}

        # Why it failed, as a word. A caller deciding between stopping and
        # retrying had to read the English the person reads.
        if self.cause is not None:
            row['cause'] = self.cause

        # How many findings a floor leaves out, as a number. `checks` carries the
        # same for a narrowing. A caller reads neither out of the message.
        if self.findings is not None:
            row['findings'] = self.findings

        # The count as a number, not only inside the sentence. A caller working
        # out whether a run covered anything had to regex the English.
        if self.checks is not None:
            row['checks'] = self.checks

        return row


class Patch:
    """
    A change to the query file that a program can apply without reading it.

    Only a defect that is purely a shape gets one: turning a Choice's criteria
    from a list into a map is a data transform, while rewriting a question is a
    judgement about a subject the linter has not seen.
    """

    # Nothing the author wrote is lost, so a loop can apply it unattended
    LOSSLESS = 'lossless'

    # It keeps the content and drops something around it, so read it first
    LOSSY = 'lossy'

    # It takes something out of the query, so a person decides
    DESTRUCTIVE = 'destructive'

    def __init__(self, op: str, path: str, value: Any = None, safety: str = LOSSLESS) -> None:
        self.op = op
        self.path = path
        self.value = value
        # Taking a node out is destructive whatever the caller passed, so the
        # classification a fixer gates on cannot be wrong by omission.
        self.safety = Patch.DESTRUCTIVE if op == 'remove' else safety

    def to_dict(self) -> dict[str, Any]:
        # What kind of change this is, as a field. `suggest_kind: "patch"` only
        # restates that a patch exists, so a loop applying patches unattended had
        # no way to tell a key rename from deleting somebody's question.
        row: dict[str, Any] = {'op': self.op, 'path': self.path, 'safety': self.safety}

        if self.op == 'remove':
            return row

        return {**row, 'value': self.value}

    def apply_to(self, query: dict[str, Any]) -> dict[str, Any]:
        """
        Apply this to a decoded query, so a caller can act on it and re-check.

        Objects stay objects: `questions` and `criteria` are keyed by names the
        caller chose, and writing them back as a JSON array is a request the API
        rejects.
        """
        parts = [part.replace('~1', '/').replace('~0', '~') for part in self.path.split('/')[1:]]
        applied = self._at(query, parts)

        return applied if isinstance(applied, dict) else query

    def _at(self, node: Any, parts: list[str]) -> Any:
        if not isinstance(node, (dict, list)):
            return node

        part = parts[0] if parts else ''

        if isinstance(node, list):
            copy = list(node)

            try:
                index = int(part)
            except ValueError:
                return node

            if index < 0 or index >= len(copy):
                return node

            if len(parts) == 1:
                if self.op == 'remove':
                    copy.pop(index)
                else:
                    copy[index] = self.value

                return copy

            copy[index] = self._at(copy[index], parts[1:])

            return copy

        copy = dict(node)

        if len(parts) == 1:
            if self.op == 'remove':
                copy.pop(part, None)
            else:
                copy[part] = self.value

            return copy

        child = copy.get(part)

        if not isinstance(child, (dict, list)):
            # Creating the path is right for `add`, which is putting something
            # where nothing is. For `remove` there is nothing to delete from.
            if self.op == 'remove':
                return node

            copy[part] = {}

        copy[part] = self._at(copy[part], parts[1:])

        return copy


class Finding:
    """One change a query needs, and the evidence for it."""

    def __init__(
        self,
        check_id: str,
        title: str,
        severity: Severity,
        target: str,
        message: str,
        hint: str = '',
        suggest: str = '',
        mode: str = 'static',
        action: str = 'rewrite',
        path: str = '',
        trigger: float | None = None,
        spread: float | None = None,
        near_trigger: bool = False,
        supersedes: list[str] | None = None,
        docs: str | None = None,
        probability: float | None = None,
        evidence: str | None = None,
        readings: list[float] | None = None,
        readings_of: str | None = None,
        suggested_type: str | None = None,
        paths: list[str] | None = None,
        patch: Patch | None = None,
        advice: str = '',
        cleared_because: str = '',
        measure: str = 'probability',
        fired: bool = True,
        accepted: str | None = None,
        unstable: bool = False,
    ) -> None:
        self.check_id = check_id
        self.title = title
        self.severity = severity
        self.target = target
        self.message = message
        self.hint = hint
        self.suggest = suggest
        self.mode = mode
        self.action = action
        self.path = path
        self.trigger = trigger
        self.spread = spread
        self.near_trigger = near_trigger
        self.supersedes = supersedes or []
        self.docs = docs
        self.probability = probability
        self.evidence = evidence
        self.readings = readings or []
        self.readings_of = readings_of
        self.suggested_type = suggested_type
        self.paths = paths or []
        self.patch = patch
        # What the self-test measured about this check's own suggestion, where it is weak
        self.advice = advice
        # Why a reading above the trigger is not a finding. A cleared entry
        # carries a number and a trigger and nothing else, so a reading the
        # catalogue sets aside looks like a defect that got away.
        self.cleared_because = cleared_because
        # What the number on this finding is. Every check but one reports a
        # calibrated probability that the defect is present; `question/type-mismatch`
        # asks which primitive fits and reports the weight on the one it picked,
        # which is not a probability of anything being wrong.
        self.measure = measure
        self.fired = fired
        self.accepted = accepted
        self.unstable = unstable

    def accepted_because(self, reason: str) -> Finding:
        """The same finding, marked as one somebody has decided to live with."""
        copy = Finding(self.check_id, self.title, self.severity, self.target, self.message)
        copy.__dict__.update(self.__dict__)
        copy.accepted = reason

        return copy

    def from_model(self) -> bool:
        """Whether a model decided this, instead of a rule in code."""
        return self.probability is not None

    @staticmethod
    def _reported(value: float | None) -> float | None:
        """
        A probability as it is reported.

        A mean over three readings comes out of the float as 0.07500000000000001,
        and a consumer comparing two reports is reading noise the model never put
        there. Four places is finer than anything the readings carry.
        """
        if value is None:
            return None

        scaled = value * 1e4

        return (math.floor(scaled + 0.5) if scaled >= 0 else math.ceil(scaled - 0.5)) / 1e4

    def to_dict(self) -> dict[str, Any]:
        # A check that cleared is a measurement, not advice. Giving it the shape
        # of a finding invites a reader to act on an argument against acting.
        if not self.fired:
            return {
                **_present({
                    'check': self.check_id,
                    'path': self.path,
                    'probability': Finding._reported(self.probability),
                    'trigger': self.trigger,
                    'readings': None if len(self.readings) == 0
                    else [Finding._reported(value) for value in self.readings],
                    'cleared_because': self.cleared_because or None,
                    # A cleared entry carries none of the fields that tell you to
                    # act, but this one says what the reading cannot tell you,
                    # which is exactly what a clear reading needs beside it.
                    'advice_caveat': self.advice or None,
                }),
                'target': self.target,
                'near_trigger': self.near_trigger,
                # Present on both shapes. An entry in `unstable` needs the key
                # most, so it cannot be the one shape that omits it.
                'unstable': self.unstable,
                'fired': False,
            }

        return {
            **_present({
                'check': self.check_id,
                'title': self.title,
                'severity': self.severity.value,
                'mode': self.mode,
                'action': self.action,
                'path': self.path,
                'message': self.message,
                'hint': self.hint,
                'suggest': self.suggest,
                'suggest_kind': None if self.suggest == '' else ('guidance' if self.patch is None else 'patch'),
                'advice_caveat': self.advice or None,
                'docs': self.docs,
                'probability': Finding._reported(self.probability) if self.measure == 'probability' else None,
                'weight': Finding._reported(self.probability) if self.measure == 'weight' else None,
                'trigger': self.trigger,
                'spread': Finding._reported(self.spread),
                'supersedes': None if len(self.supersedes) == 0 else self.supersedes,
                'evidence': self.evidence,
                'readings': None if len(self.readings) == 0
                else [Finding._reported(value) for value in self.readings],
                'readings_of': self.readings_of,
                'suggested_type': self.suggested_type,
                'paths': None if len(self.paths) == 0 else self.paths,
                'patch': self.patch.to_dict() if self.patch is not None else None,
                'accepted': self.accepted,
            }),
            # Always present, both of them. `near_trigger: false` says the reading
            # is clear of its trigger; an absent key says nothing, and a caller
            # has no way to tell which was meant.
            # A question id is a key somebody chose, and "" is a key, so `target`
            # cannot go through the filter that drops an empty string.
            'target': self.target,
            'measure': self.measure,
            'near_trigger': self.near_trigger,
            'unstable': self.unstable,
            'fired': True,
        }


def _present(row: dict[str, Any]) -> dict[str, Any]:
    """Keys worth writing: everything the report has an answer for."""
    return {key: value for key, value in row.items() if value is not None and value != ''}


class Report:
    def __init__(
        self,
        source: str,
        catalogue_version: str,
        model: str = 'jev-1.13',
        fingerprint: str = '',
        question_print: str = '',
        asked_through: str | None = None,
    ) -> None:
        self.source = source
        self.catalogue_version = catalogue_version
        self.model = model
        self.fingerprint = fingerprint
        # A fingerprint over what the checks ask, which a reworded message does not move
        self.question_print = question_print
        # The build `--model` pinned, where one was pinned
        self.asked_through = asked_through
        self._findings: list[Finding] = []
        self._notes: list[Note] = []
        self._config: Any = None
        self._order: dict[str, int] = {}
        self._calls = 0
        self._calls_without_usage = 0
        self._answered_by: set[str] = set()
        # Checks this run put to a query or to the model
        self._asked = 0
        self._expected: dict[str, set[str]] = {}
        self._reached: dict[str, set[str]] = {}
        self._tokens = 0

    def accept_from(self, config: Any) -> None:
        self._config = config

    def accepted_from(self) -> str:
        """The file the acceptances were read from, where there was one."""
        return self.config_source() or '.jevlint.json'

    def config_source(self) -> str | None:
        """The config this run read, or None where it found none."""
        return None if self._config is None else self._config.source

    def add(self, finding: Finding) -> None:
        reason = None if self._config is None else self._config.reason_for(finding.check_id, finding.target)

        self._findings.append(finding if reason is None else finding.accepted_because(reason))

    def order_by(self, targets: list[str]) -> None:
        """
        The order the query wrote its questions in, so the report reads down the
        file instead of down the alphabet.
        """
        self._order = {target: index for index, target in enumerate(targets)}

    def asked(self, checks: int) -> None:
        """Record that this many checks were evaluated, so a run that asked nothing can say so."""
        self._asked += checks

    def asked_count(self) -> int:
        return self._asked

    def note(self, note: str, findings: int | None = None) -> None:
        self._notes.append(Note(note, 'note', None, None, None, findings))

    def unreachable(self, target: str, message: str, cause: str | None = None) -> None:
        """
        A call that could not be made, so the checks it carried never ran.

        Recorded apart from an ordinary note because the run is now incomplete,
        and a caller gating on the exit code has to be able to tell.
        """
        self._notes.append(Note(
            Text.of('report.unreachable', {'target': target, 'detail': message}),
            'unreachable',
            target,
            None,
            cause or Cause.ANSWER,
        ))

    def expecting(self, check_id: str, target: str) -> None:
        """
        A check this run put into a call, and the question or state it was asked
        about. Paired with `reached`, this is what `reconcile()` compares.
        """
        self._expected.setdefault(target, set()).add(check_id)

    def reached(self, check_id: str, target: str) -> None:
        """A check that got as far as a verdict, whether or not it fired."""
        self._reached.setdefault(target, set()).add(check_id)

    def reconcile(self) -> None:
        """
        Every check that went into a call has to come back as a finding, as a
        cleared reading, or as a loss somebody can see.

        A check that produces nothing on some path and is never mentioned leaves a
        report that reads as clean and complete. Reconciling what was asked
        against what came back catches that wherever it happens, instead of each
        path having to notice for itself.
        """
        for target, checks in list(self._expected.items()):
            # A target that already carries a loss has said so; adding a second
            # note per check would inflate the count without adding a fact.
            if any(note.target == target for note in self.unreachable_notes()):
                continue

            reached = self._reached.get(target, set())
            missing = sorted(check for check in checks if check not in reached)

            if len(missing) == 0:
                continue

            self.unreachable(target, Text.of('report.no_verdict', {
                'first': missing[0],
                'more': len(missing) - 1,
            }))

    def skipped(self, message: str, checks: int | None = None) -> None:
        """
        Checks this run did not carry: a flag narrowed it, or the query is a shape
        a check cannot run on. Not a failure, but not coverage either, and a
        report that cannot say so reads like a full clean pass.
        """
        self._notes.append(Note(message, 'skipped', None, checks))

    def skipped_notes(self) -> list[Note]:
        return [note for note in self._notes if note.is_skip()]

    def unreachable_notes(self) -> list[Note]:
        return [note for note in self._notes if note.is_unreachable()]

    def is_complete(self) -> bool:
        """Whether every check that was meant to run got an answer."""
        return len(self.unreachable_notes()) == 0

    def answered_by(self, model: str) -> None:
        """The build the answers say they came from, whatever was asked for."""
        self._answered_by.add(model)

    def answering_models(self) -> list[str]:
        """
        The builds that answered, as the API named them.

        `--model` and `--openrouter` say what was asked for. This says what
        replied, which is what makes two reports comparable or not.
        """
        return sorted(self._answered_by)

    def record_call(self, tokens: int | None) -> None:
        """
        A call that left the machine.

        `tokens` is None where the answer carried no usage, which is not a call
        that cost nothing; counting it as zero prints the two the same way.
        """
        self._calls += 1

        if tokens is None:
            self._calls_without_usage += 1

            return

        self._tokens += tokens

    def calls_without_usage(self) -> int:
        """Calls whose answer carried no token count."""
        return self._calls_without_usage

    def findings(self, floor: Severity | None = None) -> list[Finding]:
        fired = [finding for finding in self._findings if finding.fired and finding.accepted is None]
        found = fired if floor is None else [finding for finding in fired if finding.severity.at_least(floor)]

        return sorted(found, key=lambda finding: (
            self._order.get(finding.target, len(self._order) + 1_000_000),
            0 if self.superseded_by(finding) is None else 1,
            -finding.severity.weight(),
            finding.check_id,
        ))

    def superseded_by(self, finding: Finding) -> str | None:
        """
        The finding that makes this one moot, where one does.

        Changing a question's type discards the advice about the type it had, so
        an agent applying findings in order would otherwise write criteria it
        immediately throws away.
        """
        for other in self._findings:
            # Only something the reader was told to do. A check that ran and
            # cleared, or one already accepted, is nothing to act on, so it cannot
            # make another finding moot - and naming it points the reader at a
            # line that is not in the report.
            if not other.fired or other.accepted is not None:
                continue

            if other.target != finding.target or finding.check_id not in other.supersedes:
                continue

            # No severity test. The catalogue declares these edges because acting
            # on one finding makes the other moot, which is a fact about the two
            # changes and not about how much either costs.
            return other.check_id

        return None

    def superseding(self, finding: Finding) -> list[str]:
        """The findings this one makes moot, of those reported."""
        return [
            other.check_id for other in self._findings
            if other.target == finding.target
            and other.check_id in finding.supersedes
            and finding.severity.at_least(other.severity)
        ]

    def cleared(self) -> list[Finding]:
        """Checks that ran and cleared, when the caller asked to see them."""
        return [finding for finding in self._findings if not finding.fired]

    def notes(self) -> list[Note]:
        return self._notes

    def calls(self) -> int:
        return self._calls

    def tokens(self) -> int:
        return self._tokens

    def count(self, severity: Severity) -> int:
        return len([
            finding for finding in self._findings
            if finding.fired and finding.accepted is None and finding.severity.value == severity.value
        ])

    def unstable(self) -> list[Finding]:
        """
        Checks whose readings straddled their trigger and did not fire.

        One whose mean clears the trigger is reported as the finding it is, with
        the disagreement noted on it. Listing it here as well would count it twice
        and leave a reader unable to tell which of the two the tool meant.
        """
        return [
            finding for finding in self._findings
            if finding.unstable and not finding.fired and finding.accepted is None
        ]

    def accepted(self) -> list[Finding]:
        """
        Findings somebody has read and decided to live with.

        They are reported and they count for nothing. A tool that deletes them
        from its own output teaches you to distrust the output.
        """
        return [finding for finding in self._findings if finding.fired and finding.accepted is not None]

    def patch_covered_by(self, finding: Finding) -> str | None:
        """
        The finding whose patch already settles the node this one's patch writes.

        Two checks can want the same question gone, and a third can want a key
        added inside it. Applied in order the second delete fails and the add puts
        the deleted question back as a stub the API rejects, so each patch is
        right and the set is not. Replacing a node settles it the same way: what
        the replacement holds is what is there, whatever a patch inside it wanted.
        """
        if finding.patch is None:
            return None

        seen_self = False

        for other in self.findings():
            if other is finding:
                seen_self = True

                continue

            patch = other.patch

            if patch is None:
                continue

            # A patch writing inside a node another finding removes or replaces is
            # void wherever the two sort, because a caller may apply either first
            # and the node it wrote into is then gone or overwritten.
            if finding.patch.path.startswith(f'{patch.path}/'):
                return other.check_id

            # Two patches on the same node make each other moot, so only the later
            # one is marked; marking both would name a cycle.
            if patch.path == finding.patch.path and not seen_self:
                return other.check_id

        return None

    def has_errors(self) -> bool:
        return self.count(Severity.Error) > 0

    def is_empty(self, floor: Severity | None = None) -> bool:
        return len(self.findings(floor)) == 0

    def to_dict(self, floor: Severity | None = None) -> dict[str, Any]:
        return {
            'source': self.source,
            'catalogue': {
                'version': self.catalogue_version,
                'fingerprint': self.fingerprint,
                'asked': self.question_print,
                'model': self.model,
            },
            # Which build answered, against the build the checks are written for.
            # Without it, two runs through different models are one document.
            'asked_through': self.asked_through,
            # What answered, not what was asked for: two providers serving the
            # same build, or one serving a different one, are only visible here.
            'answered_by': self.answering_models(),
            'summary': {
                'error': self.count(Severity.Error),
                'warning': self.count(Severity.Warning),
                'advice': self.count(Severity.Advice),
                'calls': self._calls,
                'tokens': self._tokens,
                # Calls the answer carried no usage for. Without it a run whose
                # provider reported no usage prints the same figure as a run that
                # cost nothing.
                'tokens_unreported_for': self._calls_without_usage,
                'accepted': len(self.accepted()),
                'unstable': len(self.unstable()),
                'unreachable': len(self.unreachable_notes()),
                # Checks evaluated. A narrowed run that left nothing to do
                # produced the same empty report as a query with nothing wrong.
                'asked': self._asked,
                'complete': self.is_complete(),
                # Not a total: two reasons can leave out the same check, so the
                # count that means anything is the one on each note.
                'narrowed': len(self.skipped_notes()) > 0,
            },
            # Which config was read. A query copied to another directory loses its
            # acceptances, and this is what says so instead of the findings
            # reappearing with no reason given.
            'accepted_from': self.config_source(),
            'notes': [note.to_dict() for note in self._notes],
            'cleared': [finding.to_dict() for finding in self.cleared()],
            # Accepted findings go through the same resolution. Left raw, their
            # `supersedes` is the catalogue's whole list and not the checks this
            # report holds, and one field means two things in one document.
            'accepted': [self._resolved(finding) for finding in self.accepted()],
            'unstable': [self._resolved(finding) for finding in self.unstable()],
            'findings': [self._resolved(finding) for finding in self.findings(floor)],
        }

    def _resolved(self, finding: Finding) -> dict[str, Any]:
        """
        A finding with its relationships answered against this report, instead of
        against the catalogue the check was written in.
        """
        row = finding.to_dict()
        superseded = self.superseded_by(finding)
        supersedes = self.superseding(finding)

        if superseded is not None:
            row['superseded_by'] = superseded

        row['supersedes'] = None if len(supersedes) == 0 else supersedes
        covered = self.patch_covered_by(finding)
        patch = row.get('patch')

        if covered is not None and isinstance(patch, dict):
            patch['covered_by'] = covered

        return {key: value for key, value in row.items() if value is not None}
