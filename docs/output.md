# Reading the output from a program

[`spec/report.schema.json`](../spec/report.schema.json) is the contract and documents every
field. This is what a caller needs to know beyond it.

The text report and the JSON carry the same information: a patch prints its `safety` in both,
a probability prints its trigger in both. What differs is shape, not substance - `action`,
`mode` and `suggest_kind` are enum words in the JSON and are said in prose to a reader, and the
JSON pointer in `path` is addressing a program needs and a person editing the file does not.

Three fields are spelled with some form of "asked" and mean different things: `summary.asked`
counts the checks this run evaluated, `catalogue.asked` is a digest over the questions the
checks put to Jev, and `asked_through` is the build `--model` pinned. Only the first is about
this run's coverage.

`--format=json` on every command, including errors, which come back as
`{"error": {"kind", "message", "command"}}` with exit 2. `kind` is one of `usage`, `not-found`,
`invalid-json`, `query`, `config`, `auth`, `catalogue`, `api` or `internal`, so a caller can tell
a mistyped flag from a missing file from a failure worth retrying without matching on English.

**Exit 2 carries three shapes, and only one of them has an `error` key.** A run that never
started returns `{"error": ...}`. A run that started and lost its calls returns a whole report
with `summary.complete: false`. A run narrowed until it asked nothing returns a whole report with
`summary.asked: 0`, `complete: true` and no findings, which is the shape a clean pass has. Read
all three before calling a run a pass:

```
exit 2 and `error`            the run never started
exit 2 and `complete: false`  it started and lost calls
exit 2 and `asked: 0`         it ran and asked nothing
```

[`spec/report.schema.json`](../spec/report.schema.json) is the shape of a report, and
[`corpus/README.md`](../corpus/README.md) covers the material the checks are measured against.

Read `summary.complete` before the findings. It is false when any check could not be asked, and
`notes` then carries `{kind: "unreachable", target, message}` entries saying what was lost.
`summary.unreachable` counts those entries, not calls and not checks: a call that failed outright
leaves one, and a call that came back having answered only some of what it carried leaves one
naming the rest. Read the notes for the scope of what went missing, and `summary.asked` for how
much did run.

Read `summary.narrowed` next. It is true when a flag, or the shape of your query, left checks
out of the run - `--only`, `--static-only`, `--no-state`, a state with no named fields, a query
too wide for the checks that compare questions. Each reason is a `{kind: "skipped", checks}`
note saying how many it left out. A narrowed run is not a failure and not coverage either, and
without this it is the same JSON as a full clean pass.

Each finding carries:

| field | |
| --- | --- |
| `check` | the check id, which is what to group or count by. `title` can carry the located detail, so it varies between two findings of the same check |
| `mode` | `static` for a rule, `model` for a judgement. Never infer this from a missing key |
| `action` | the kind of change: `rewrite` the text, `retype` the primitive, `restructure` into a different shape, `add` something, `remove` the node the `patch` names. A question that should not be put to Jev at all says `remove`; one that has to change shape and might go either way says `restructure` |
| `path` | a JSON pointer into your file, such as `/questions/urgency/criteria`. On an `add` it names where the node belongs, which is either a node that is not there yet or the one the patch adds into, so it may not resolve until the patch is applied |
| `target` | the question id, or `state`, or `query`. Always present, and a question id can be an empty string |
| `evidence` | what the check was shown, quoted back and elided in the middle where it is long. On a static rule it is the detail that tripped it; on a model check it is the part of the query the check reads, so two checks reading the same part quote the same text and neither isolates a span at fault |
| `trigger`, `probability`, `spread` | what the check needed, what it got, and how far its wordings or repeats disagreed. A check that reads one state field asks about it once per question and reports the weakest of those readings, so its `probability` is the smallest number in `readings`, not their mean |
| `measure`, `weight` | Read `mode` first: a `static` finding is a rule in code and carries no number at all. On a `model` finding, `measure` says which key holds it - `probability` on every check but `question/type-mismatch`, which asks which primitive fits rather than whether a defect is present, and reports `weight` with no `probability` key. The weight is how far Jev's answer sat from the primitive you declared, not how strongly `suggested_type` was picked - `evidence` carries that |
| `near_trigger` | the probability sits within 0.05 of the trigger, so it may not repeat. Always present, `true` or `false`, because an absent key and a `false` are different claims |
| `unstable` | separate calls answered on both sides of the trigger, so another run may decide differently. Wordings disagreeing inside one call is not this - that is `spread`. Always present |
| `supersedes`, `superseded_by` | acting on one finding can discard another. Changing a question's type drops the advice about the type it used to be |
| `patch` | an `{op, path, safety, value}` you can apply to the query file without reading it. `safety` is `lossless` (nothing you wrote is lost, apply it unattended), `lossy` (the content survives and something around it does not) or `destructive` (it takes a question or a field out, so a person decides). A `remove` is always destructive. `covered_by` names a check listed earlier whose patch already removes that node, so applying both leaves the query wrong |
| `fired` | `false`, on a check that ran and cleared. A cleared entry carries its check, target, path, probability, trigger, `near_trigger` and `unstable`, plus `readings` where more than one was taken, and none of the fields that tell you to do something - it is a measurement, not advice, and it never arrives in the same shape as a finding |
| `suggest_kind` | `patch` when `suggest` is backed by an appliable change, `guidance` when it is prose to read |
| `advice_caveat` | present only where `jevlint self-test` measured this check's own suggestion barely clearing it, or unable to clear it at all. The text report prints it as `Advice` |
| `accepted` | the reason from `.jevlint.json`, on a finding you have already decided about |

A check that cleared within 0.1 of its trigger is reported without asking, under `Cleared, and
worth a look`. The reading is already paid for, and it is the one that would otherwise cost a
second run to see.

**A check that cannot clear your query says so in the run.** Where a check's readings for clean
and defective material overlap, a reading under its trigger is not evidence the defect is absent.
The catalogue marks such a check `inconclusive`, and it is reported whether it fires or not,
carrying the caveat in `advice_caveat`. `score/multi-dimension` is one: published-correct rubrics
read 0.62 to 0.76 and two-axis rubrics read 0.72 to 0.80, so nothing separates them. A silent
check would read as a clean bill of health, and that is the one thing its reading cannot give
you.

`--all` fills the `cleared` array with every model check that ran without firing, with its
probability and trigger. Without it the array is present but holds only the checks that could
not decide, so a check that ran and cleared and a check that never applied otherwise look the
same.

Where a check reads `criteria`, it asks about the elements in the same call and names the ones
at fault. A fault every element can carry at once, such as levels written as degrees, is asked
one element at a time and `paths` lists all of them. A fault one element carries relative to the
others is asked as a single choice across them, because asked in isolation every level that
describes a situation reads as naming several things.
Where more than one element carries that fault, the choice
names one of them, and which one it names follows the order they are listed in, so a located
level is where to start and not the only one.

A finding whose fix is deleting one node carries a `remove` patch: `question/arithmetic` on a
question that asks for a tally emits `{"op":"remove","path":"/questions/charge_count"}`, and
`state/irrelevant-field` emits the pointer to the field. `question/type-mismatch` carries
`suggested_type`, so the primitive it picked is a field and not a phrase to pull out of prose.
It is absent when the check judged that none of the three fits, which is a finding worth
acting on and not a type to retype to.

`probe --format=json` carries `moved` on every reading and a `summary` naming which
questions moved and the rule that decided it. Each question also carries `undecided`, true
where the unchanged answer landed near the middle of a yes/no question, and `flips`, true where
its repeats fell on both sides of that middle. `summary.undecided_questions` lists them and
`summary.undecided_rule` states the band. Neither changes the exit code: a probe is not a gate,
and an answer near the middle can be the right answer to material that is ambiguous.

## Versions, in full

A version the catalogue holds nothing for is refused, because the alternative is a query
checked against a different build's rules and reported as clean. Where the resolved version
leaves checks out, the report carries a skipped note, the same as `--only` does, and the header
and `catalogue.model` name the version that ran.

In the catalogue a check carries `since`, `until`, both or neither. A check with neither is a
rule for every version the file covers, and one written for no version it covers fails the load.

## Which checks emit a patch

The shape rules, because the right shape is arithmetic on what you wrote:
`noul/criteria-shape`, `choice/criteria-shape`, `score/criteria-shape` and
`choice/no-fallback`. So do `question/type-not-lowercase` and `query/unknown-key`, and the three
whose answer is to delete a node: `question/arithmetic`, `question/date-comparison` and
`state/irrelevant-field`.

A patch is withheld where reshaping would lose something or produce a file this tool would
refuse: levels keyed by words, because ordering them is a judgement about your rubric and not
arithmetic on it; a level with no text, which has nothing to carry over but its own index;
options written as numbers, which reshape into the list the rule exists to refuse; `yes` beside
`YES`, which collapse onto one key; and removing the only question in a query, which leaves
nothing to ask. In each case the advice stands without a patch. `suggest_kind` says which of the
two a finding carries, and a test applies each patch to a query written to break it and asserts
the finding is gone.

Applying a patch can raise a finding the old shape hid: filling in option labels leaves them
undescribed, and removing the last field of a state object leaves the object itself unread.
Neither is a mistake in the patch; both are the next thing to look at.

## Pointing the loader elsewhere

`JEVLINT_CHECKS_DIR` points the loader at another directory holding `catalogue.json` and
`fixtures.json`, for trying a rule set without editing the installed one. It is an override and
not a preference: a directory missing `catalogue.json` is an error rather than a fall back to
the bundled copy, because a run against half a rule set reports like a clean one.
`fixtures.json` is read only by `self-test`, which is the command that fails without it.

Everything the catalogue can get wrong is refused at load - a check naming a rule no code
raises, two checks naming one rule, a model check with no question, an `applies_to` or a `reads`
naming something that does not exist - so a damaged file cannot produce a report that reads as a
pass.
