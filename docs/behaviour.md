# What the tool does on itself

The measurements here are about jevlint rather than about the checks: what it costs, whether it
repeats, what it reports on a query written to be bad, and what happens when it is pointed at its
own catalogue. [evidence.md](evidence.md) has how good each check is.

## What a self-test verdict means

`ok` and `weak` pass; `flat`, `inverted`, `fires-on-clean`, `misses-broken` and
`suggestion-fails` mean the check is not measuring what it claims and exit 1; `errored` means it
was never scored and exits 2. `weak` is a span between 0.15 and 0.30 - it passes, and it is a
check worth rewriting.

## The shapes the API rejects, checked against the API

Three checks are `error` severity and say the request will be rejected. The claim is not
reproducible through this tool: the SDK rewrites a list of labels into a map before the request
goes out, so `jevlint probe` on a list-shaped Choice gets an answer rather than a rejection.
Sending the body by hand settles it. All three are rejected, and the two checks that quote the
API quote it exactly:

| what was sent | HTTP | what came back |
| --- | --- | --- |
| Choice criteria as a list | 422 | `Input should be a valid dictionary` |
| Score criteria as a map | 422 | `Input should be a valid list` |
| Noul criteria as a list | 422 | `Input should be a valid dictionary or object to extract fields from` |
| Choice criteria as a map | 200 | answered, `model: jev-1.13.0` |

The control also settles a second thing: `jev-latest` resolved to `jev-1.13.0` on the day this
ran, which is what the self-test comparison against the pinned build inferred from readings.

## The catalogue passes its own checks

The checks are Jev questions, so the linter runs on them, every wording of every one:

The 18 question-scoped wordings come back with one or two findings, over 38 to 40 calls depending
on how many readings land near a trigger and are asked again. What comes back is
`state/answer-absent` on the synthetic state the file carries, a hair over its trigger, and
`question/type-mismatch` reading a check's own wording as better suited to another primitive.
Both are artefacts of putting a check in the position of a query, not defects in the catalogue.
The run also notes that the checks comparing questions did not run, because 18 questions make
more pairs than one call carries - a limitation of this file, not of the catalogue.

The five wordings in the state file, over 13 or 14 calls depending on how many readings land near
a trigger, return two findings, and both are artefacts of how the file that
holds them is built instead of defects in the catalogue: a distractor field planted so the
state checks have something to read, which `state/irrelevant-field` correctly flags, and the
two wordings of `state/answer-absent`, which `query/overlapping-questions` reads as two
questions asking the same judgement. In a real run those two wordings are one check in one
call.

`state/answer-absent` is the check that most often cannot decide about the catalogue. Asked
about several of these wordings its readings fall on both sides of its 0.60 trigger. Which way
that lands is run-dependent: where the mean clears the trigger the finding is reported and says
on its own line that its readings disagreed, and where it does not the check is listed as
undecided instead. Both are the report refusing to pick a side it cannot support.

## Asking a check more than one way

A check may carry several wordings. They go in one call, the mean is the answer, and the spread
is printed with the finding.

It does not widen the separation between a check's own examples. What it adds is an error bar:
the spread between the wordings is printed with the finding, so a reader can see when two ways of
asking the same thing disagreed. `question/generation` carries two because a question that asks
for text and then asks for a pick is caught by one wording and not the other, and neither alone
both catches that case and leaves the gold example above its trigger.

## What the linter finds in a query written to be bad

`examples/broken-triage.json` carries one planted defect per question. Every one comes back:

| question | found |
| --- | --- |
| "Is this ticket free of spam and also written by a real customer?" | negated phrasing 0.88, two judgements in one question 0.90 |
| "Were more than two charges made before the account's renewal date?" | arithmetic 0.97, date comparison 0.81, reaches its subject through another thing 0.81, and the state cannot answer it 0.65 |
| "Rate severity from 0 to 2", levels `["0","1","2"]` | degrees instead of situations 0.96, plus the static rule for numeric levels |
| "Which department?", options `billing` and `payments` | options do not cover every input 0.88, overlapping options 0.93, plus the static rules for an instruction that repeats its id and a missing fallback |
| "What is the order number the customer refers to?" | generation 0.73, and a type that fits the answer better 0.89 |

One question comes back with a defect that was not planted in it. "the account's renewal date"
reaches its subject through another thing, and `question/indirection` is right to say so. The
reading on that question's `state/answer-absent` straddles its trigger, and the report marks it
undecided, or reports it with the disagreement noted, depending on where the mean of those
readings lands. It is never counted as both.

Six state fields are also flagged as read by no question. `examples/support-triage.json`, written
to be clean, comes back with one advisory finding: the `plan` field, which none of its four
questions reads.

| | calls | tokens | findings |
| --- | --- | --- | --- |
| `check` on the four-question clean example | 10 | 15,433 | 1 advice |
| `check` on the five-question broken example | 12 | 20,932 | 4 errors, 6 warnings, 11 advice |
| `probe`, four questions, five repeats | 9 | 5,275 | one question moved |
| `self-test`, whole catalogue | 118 | - | 20 checks, two example sets each |

TypeSafe reports no cost on a call, so these are token counts. `--no-state` removes the second
call per question. The call counts move between runs: a reading that lands within 0.05 of its
trigger is asked again, so the broken example costs 12 to 14 depending on how many do.

Two calls per question plus two for the query is the floor, not the price. A check whose reading
lands within 0.05 of its trigger is asked again, and those re-asks ride in one extra call per
question that has any. The same file can therefore cost 12 calls on one run and 13 on the next,
and it is the borderline readings that decide which.

## What a rewrite does to a clean query

`jevlint probe examples/support-triage.json`, five repeats:

| question | unchanged | repeat spread | rewritten |
| --- | --- | --- | --- |
| refund_requested | 0.990 | 0.0000 | 0.990 stripped of criteria, 1.000 as a Choice |
| blocked | 0.714 | 0.0152 | 0.730 stripped of criteria, **0.870 as a Choice** |
| category | 1.000 | 0.0000 | 1.000 with the options reversed |
| urgency | 0.995 | 0.0000 | 0.990 with the levels reversed |

The three questions with one defensible answer against this state are pinned, and reversing a
Choice's options or a Score's levels does not move them. `blocked` - "Does the customer say they
cannot carry on using the product?" against a ticket saying "I cannot place another order until
this is sorted" - is the only question with room in it, and the only one that moves.

**Read the size of the move, not the multiple.** The multiple is the move divided by the spread
over five back-to-back repeats, and that spread is small enough that a small change in it moves
the multiple a long way. It is what makes a move a finding instead of noise; it is not a
measurement of anything.

A threshold at 0.8 on that question means one thing as a Noul and another as a Choice.

## What the report says about itself

A report carries the catalogue that produced it, as a version, a fingerprint over the whole
catalogue file, and the model. Two reports from different catalogues are distinguishable
without reading either, and a trigger outside 0.3 to 0.95 is refused at load, because a
catalogue that fires on everything and one that works produce reports of the same shape.

Under `--all` the report also carries every model check that ran and cleared, with its
probability and its trigger. Without it, a check that ran and cleared and a check that never
applied are indistinguishable.

Where a check reads `criteria`, it asks one more question in the same call, a Choice over the
reviewed question's own levels or options. The finding then points at the one it read:
`/questions/risk/criteria/1`, quoting that level. It costs a question and not a round trip.

## Repeatability

A model check asked twice about the same text does not return the same number. `probe` prints the
spread it measures over its repeats, and `check --repeats=n` prints the spread over n asks, so
the size of the jitter on your own query is something you can read rather than take on trust.
TypeSafe's consistency cookbook publishes 0.0102 as the mean per-question deviation over 15
repeats per condition; this tool's floor of 0.0085 is lower and where it came from is not
recorded here.

A finding whose probability sits within about 0.1 of its trigger may not survive the next run, so
`check` marks any finding within 0.05 of its trigger and re-asks it.

The repeats a probe sends go back to back, and nothing here sends them spaced out, so the spread
it prints is a floor and the multiples of it are an overstatement.
