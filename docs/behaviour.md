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

The 18 question-scoped wordings come back with one finding, over 40 calls. It is
`question/type-mismatch` at 0.76, reading `question/arithmetic`'s own wording as better suited
to another primitive, which is an artefact of putting a check in the position of a query instead
of a defect in the catalogue. The run also notes that the checks comparing questions did not
run, because 18 questions make more pairs than one call carries - a limitation of this file, not
of the catalogue.

The six wordings in the state file come back with one finding, over 16 calls: a distractor field
planted so the state checks have something to read, which `state/irrelevant-field` reports at
0.86. Both call counts move with how many readings land near a trigger and are asked again.

`state/answer-absent` is the check that comes closest to firing on the catalogue without doing
so. Its highest reading over the question file is 0.56 against a 0.60 trigger, on one wording of
`choice/overlapping-options`. Which side of the trigger a reading that close lands on is
run-dependent, and this page has previously recorded the same file returning it as a finding
and returning it as undecided. Both are the report refusing to pick a side it cannot support.

## Asking a check more than one way

A check may carry several wordings. They go in one call, the mean is the answer, and the spread
is printed with the finding.

It does not widen the separation between a check's own examples. What it adds is an error bar:
the spread between the wordings is printed with the finding, so a reader can see when two ways of
asking the same thing disagreed. `question/generation` carries two because a question that asks
for text and then asks for a pick is caught by one wording and not the other, and neither alone
both catches that case and leaves the gold example above its trigger.

## What the linter finds in a query written to be bad

`examples/broken-triage.json` carries one planted defect per question. Four of the five come
back; the fifth is the interesting row:

| question | found |
| --- | --- |
| "Is this ticket free of spam and also written by a real customer?" | negated phrasing 0.90, two judgements in one question 0.92 |
| "Were more than two charges made before the account's renewal date?" | date comparison 0.85, reaches its subject through another thing 0.76, and the state cannot answer it 0.66. **`question/arithmetic` reads 0.46 against its 0.60 trigger and does not fire** |
| "Rate severity from 0 to 2", levels `["0","1","2"]` | degrees instead of situations 0.96, plus the static rule for numeric levels |
| "Which department?", options `billing` and `payments` | overlapping options 0.92, plus the static rules for an instruction that repeats its id and a missing fallback |
| "What is the order number the customer refers to?" | generation 0.70, and a type that fits the answer better, at the full weight |

**The arithmetic row is a check losing its own planted example.** "More than two charges" is a
tally, which is what `question/arithmetic` exists to find, and this page recorded 0.97 for it.
The question in the example file and the check's own wording are both unchanged between that
reading and this one. The check separates its own two examples in `self-test`, so what a move
of half a point on fixed inputs shows is the distance between a fixture and a query somebody
wrote.

One question comes back with a defect that was not planted in it. "the account's renewal date"
reaches its subject through another thing, and `question/indirection` is right to say so.

Six state fields are also flagged as read by no question, from 0.80 on `account.id` to 0.96 on
`routing.experiment_bucket`. `examples/support-triage.json`, written to be clean, comes back
with two advisory findings: the `plan` field at 0.90, which none of its four questions reads,
and `question/unsettled-case` at 0.47 on "Does the customer say they cannot carry on using the
product?" against a state saying the customer cannot place another order. Placing an order is
using the product on one reading and not on another, and the question settles neither.

| | calls | tokens | findings |
| --- | --- | --- | --- |
| `check` on the four-question clean example | 11 | 16,980 | 2 advice |
| `check` on the five-question broken example | 14 | 23,140 | 4 errors, 6 warnings, 11 advice |
| `probe`, four questions, five repeats | 9 | 5,275 | one question moved |
| `self-test`, whole catalogue | 124 | - | 21 checks, 42 example sets, all `ok` |

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
| blocked | 0.720 | 0.0158 | 0.690 stripped of criteria, **0.870 as a Choice** |
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
