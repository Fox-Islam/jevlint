# jevlint

A linter for [Jev](https://docs.typesafe.ai) queries. It takes the request you would send
to System One - a state and the questions asked about it - and reports where the query is
written in a way the model is documented to handle badly.

These pages are on the web at
[fox-islam.github.io/jevlint](https://fox-islam.github.io/jevlint/), which also has
[worked examples](https://fox-islam.github.io/jevlint/examples.html): three queries with a
defect in each, the report, and the same query rewritten.

**Start:** [Quickstart](#quickstart) · [Install](#install) ·
[What a query file looks like](#what-a-query-file-looks-like) · [What it checks](#what-it-checks)

**Reading the output:** [Is it any good?](#is-it-any-good) ·
[Severity and probability](#severity-and-probability-say-different-things) ·
[Reading a finding](#reading-a-finding) · [Exit codes](#exit-codes) ·
[For a program reading the output](#for-a-program-reading-the-output) ·
[What this cannot tell you](#what-this-cannot-tell-you)

**Going further:** [The probe](#the-probe) · [Accepting a finding](#accepting-a-finding) ·
[Which Jev build the rules are for](#which-jev-build-the-rules-are-for) ·
[The catalogue is not PHP](#the-catalogue-is-not-php)

**Beyond this page:** [docs/evidence.md](docs/evidence.md), how good each check is ·
[docs/output.md](docs/output.md), reading the output from a program ·
[docs/library.md](docs/library.md), calling it from PHP ·
[docs/javascript.md](docs/javascript.md), calling it from JavaScript ·
[docs/languages.md](docs/languages.md), how to add a language ·
[docs/behaviour.md](docs/behaviour.md), what the tool does on itself

## Quickstart

```sh
composer install                                          # or: npm install
./jevlint check examples/broken-triage.json --static-only
```

That reads a query written to be bad, costs nothing and makes no calls. It reports one error,
two warnings and three advisories, each naming the defect, where it is and what to change.

To check your own query, point it at the request body you would send:

```sh
./jevlint check your-query.json --static-only    # the rules that need no key
./jevlint check your-query.json                  # and the ones that ask Jev
```

The second needs `TYPESAFE_API_KEY` in the environment or in a `.env` in the working directory,
and costs two calls per question plus two for the query. `./jevlint help` lists the rest.

Called as a library, `Linter` hands the report back instead of printing it:
[from PHP](docs/library.md), [from JavaScript](docs/javascript.md).

## Install

As a dependency, which puts `jevlint` on your `PATH`:

```sh
composer require --dev phox/jevlint    # PHP 8.3+
./vendor/bin/jevlint help
```

```sh
npm install --save-dev @phox-js/jevlint  # Node 20.19+
npx jevlint help
```

Or from a clone, where `./jevlint` at the root runs it from anywhere:

```sh
composer install
./jevlint help
```

The commands below are written from the repository root, where `examples/` sits. The PHP source
is under `php/` and the JavaScript under `js/`; `checks/` sits beside them because both read the
same catalogue.

Put `TYPESAFE_API_KEY` in the environment or in a `.env` in the working directory, or pass
`--env-file`. `check --static-only` needs no key and makes no calls. `--openrouter` sends the
checks through OpenRouter instead and reads `OPENROUTER_API_KEY`.

## What a query file looks like

The request body, so what you already send is what you check:

```json
{
  "state": {"ticket": {"body": "I was charged twice for order A-104. Please refund the duplicate."}},
  "questions": {
    "refund_requested": {
      "type": "noul",
      "instructions": "Does the customer ask for a refund?",
      "criteria": {
        "true": "The customer asks for money back, a refund, or a charge to be reversed.",
        "false": "The customer reports a problem without asking for money back."
      }
    }
  }
}
```

Jev answers three kinds of question, and the checks differ by kind:

| | |
| --- | --- |
| `noul` | yes or no, answered with the probability of yes. Its `criteria` describe what a yes and a no mean |
| `choice` | one of a set of labels with no order between them. Its `criteria` map each label to a description |
| `score` | a position on an ordered rubric. Its `criteria` are the levels, in order, each describing a situation |

`examples/` has a query written well and one written badly. `spec/query.schema.json` is the
schema.

## What it checks

Two kinds of check, both reported the same way.

**Static checks** run in code and cost nothing. They catch the shapes the API rejects - a
Choice whose criteria are a list, a Score whose criteria are a map, the two 422s that are
exactly inverse - and the structural defects: a rubric made of bare numbers, a Choice with
nowhere to put an input the options do not cover, an instruction that says no more than the
question id does.

**Model checks** put the question under review to Jev as state, and ask one calibrated
question per documented failure mode. Every check is phrased so that a high probability
means the defect is present, and the probability is reported with the finding. What enforces
the direction is `self-test`: a check written backwards scores high on its clean example and
low on its broken one, which is the `inverted` verdict, and the run fails.

| Failure mode | Checks |
| --- | --- |
| [Literal reading](https://docs.typesafe.ai/model-jaggedness/jev-1.13#literal-reading) | `question/undefined-boundary` |
| [Math and numbers](https://docs.typesafe.ai/model-jaggedness/jev-1.13#math-and-numbers) | `question/arithmetic`, `question/numeric-representation` |
| [Date and time](https://docs.typesafe.ai/model-jaggedness/jev-1.13#date-and-time-comparison) | `question/date-comparison` |
| [Indirection](https://docs.typesafe.ai/model-jaggedness/jev-1.13#indirection) | `question/indirection`, `question/double-negative` |
| [Large state](https://docs.typesafe.ai/model-jaggedness/jev-1.13#large-state-full-of-irrelevant-detail) | `state/irrelevant-field` |
| [Adversarial content](https://docs.typesafe.ai/model-jaggedness/jev-1.13#adversarial-content) | `state/adversarial-content` |
| [Contradictory criteria](https://docs.typesafe.ai/model-jaggedness/jev-1.13#contradictory-instructions-and-criteria) | `question/criteria-contradiction`, `question/criteria-off-topic`, `noul/negated-phrasing` |
| [Generation](https://docs.typesafe.ai/model-jaggedness/jev-1.13#generation) | `question/generation` |
| [One snap judgment per question](https://docs.typesafe.ai/primitives#ask-for-one-snap-judgment-per-question) | `question/compound-judgment`, `score/multi-dimension` |
| [Writing good levels](https://docs.typesafe.ai/primitives/score#writing-good-levels) | `score/degree-levels`, `score/overlapping-levels` |
| [Choosing a question type](https://docs.typesafe.ai/primitives#choose-a-question-type) | `choice/overlapping-options`, `question/type-mismatch` |
| [The state has to hold the answer](https://docs.typesafe.ai/concepts/state) | `state/answer-absent` |
| [Ask multiple questions together](https://docs.typesafe.ai/primitives#ask-multiple-questions-together) | `query/overlapping-questions` |

Some checks are asked more than one way. A catalogue entry with `questions` instead of
`question` carries several wordings that mean the same thing; they go in the same call, the
mean is the finding's probability, and the spread between them is printed with it. A criterion
held by one sentence is held by that sentence's accidents as much as by its meaning, and where
two wordings of the same check disagree, the finding reports both instead of picking one.

**`jevlint checks` is the fastest way to learn what a good query looks like.** Every check
carries the failure, the fix, the measurement behind its severity and the case where accepting
it is right, so the catalogue reads as a guide to writing queries and not only as a list of
rules. It lists the whole catalogue, including the static rules this table leaves out.
`jevlint checks <id>` prints one check in full: its trigger, what it reads, and the Jev
question it asks. A test pins every model check named above to one that exists, and every model
check in the catalogue to a mention here.

A question costs two calls: one carrying every check that reads the question itself, and one
carrying the checks that read your state. Two more calls are spent on the query as a whole: one
for the checks that read the state on its own, and one for the checks that compare questions
against each other. Each call holds a dozen or so questions, because a call costs its round trip
and not its question count. So a four-question query with a state is ten calls, and `--no-state`
drops the per-question state call and the state-only call.

That figure is a floor, and two things move it. A query with one question, or with more than a
dozen, has no pair to compare, so the pair call is not made and a `skipped` note says so. And a
question-scoped check whose reading lands within 0.05 of its trigger is asked again in a
follow-up call, so a run with borderline readings costs up to twice the per-question calls:
between `2n + 2` and `4n + 2`. The checks that read your state are not re-asked; they carry
`near_trigger` and nothing more. `summary.calls` is what the run spent, including calls that
failed.

A check that compares questions, such as `query/overlapping-questions`, has no single question
to blame, so it names both and its finding is attached to the second.

## Is it any good?

Measured, and the measurements are in the repository. The short version:

- **The checks separate a well-written question from a badly written one.** Each ships two
  example sets in unrelated domains; taking whichever it does worse on, the clean example
  scores a median 0.08 and the broken one 0.90.
- **Every defect the TypeSafe documentation gives an example for is caught**, 14 of 14. On
  material the documentation publishes as correct, firing rates run from 0 to 8%.
- **Severity is what the defect costs, measured.** Joining a second condition to a question
  that every case already satisfies takes the answers from 15 of 20 to 11 of 20 and doubles the
  Brier score, so `question/compound-judgment` is an error. Three checks are advice because
  their defect was detected and cost nothing on the hardest material to hand.
- **Acting on a finding can be worth more than the finding.** Following
  `question/date-comparison` - extract the date parts as a Choice over enumerated options and
  subtract in code - took a returns-window query from 21 of 40 correct to 40 of 40 on held-out
  labelled cases.

And what it cannot tell you:

- A check passing does not mean your question is right. It means the ways this tool knows how to
  be wrong were not found.
- One check, `score/multi-dimension`, cannot separate its clean and defective readings at all.
  It says so in its own output rather than leaving you to find out.
- The corpus tests firing rates, not correctness. A check that fires on 0 of 52 published
  examples may still be wrong about yours.

Read a model finding as an argument with a number attached, not as a verdict. `jevlint
self-test` shows each check separates its own examples, which catches a wording change that
breaks a check and proves nothing about whether the check is right; that takes material
somebody else labelled, which is what `corpus/` holds.

[docs/evidence.md](docs/evidence.md) has the per-check measurements and the material behind them.
[docs/behaviour.md](docs/behaviour.md) has what the tool does on itself: cost, repeatability, and
what it reports on a query written to be bad.

## Severity and probability say different things

**Severity is what the defect costs if it is real. Probability is how sure the check is that it
is.** They move independently, and the report shows both because neither answers for the other.

`question/type-mismatch` can report `advice` at a probability of 1.00: the check is certain the
answers would fit a Score better, and the query works either way, so the cost of ignoring it is
small. `question/arithmetic` is an `error` at 0.97 because a question that asks Jev to count
returns a wrong number.

This matters for `--min`. Filtering to `warning` hides advice whatever its probability, so a
run gated that way can pass while carrying the most confident finding in the report.

## Reading a finding

```
  error    Score levels are bare numbers
           score/numeric-levels
           The levels are bare numbers, so there is nothing in the state for the model to
           match them against.
           Likelihood  certain, because this rule either matches or does not
           Found       Levels: 0, 1, 2.
           Suggested   Replace each number with the situation it stands for. For example, a
                       three-level severity rubric becomes "Cosmetic, and nobody's work is
                       affected", "Broken or degraded, but a workaround exists", "No
                       workaround, and the work has stopped".
           Why         The model never sees a level's number or its neighbours, so a bare
                       number gives it nothing to match against. The documented example
                       scores 0.55 at confidence 0.33 with numeric levels and 0.0 at
                       confidence 1.0 with described ones.
           Docs        https://docs.typesafe.ai/primitives/score#writing-good-levels
```

The first line says what is wrong without needing to know the catalogue. The second names the
check, which you can look up with `jevlint checks <id>`, grep for, or narrow a run to with
`--only`. `Likelihood` is how the finding was reached: a static rule is certain, and a model
check carries the probability that produced it and the trigger it cleared. `Found` quotes your
file, `Suggested` is the change to make, and `Why` is what goes wrong if you do not.

Where the defect is purely a shape, the finding also carries a `Patch`: the exact change, built
from your own file, ready to apply.

```
           Patch       lossless · replace /questions/urgency/criteria = ["Can wait until next
                       week","The customer is blocked right now"]
```

In JSON that is `{"op": "replace", "path": ..., "value": [...]}`, which a program can apply
without reading the file, and `safety` says whether it can be applied unattended. A patch is
offered only where it keeps every word you wrote, so a reshape that would drop something ships
the advice alone. **Re-run after applying one:** a reshape can raise a finding the old shape hid.
[docs/output.md](docs/output.md) lists which checks emit patches and when they withhold them.

Everywhere else `Suggested` is guidance. A model check has read your instruction, not your
subject, so its suggestion holds for any query the check fires on, and any example in it is
marked as one.

A model check's probability reads in one direction: it is how strongly the check reads the
defect as present, so higher is worse. The report says so once at the top, and each finding
puts the number in words - `0.97, almost certain`, `0.67, likely` - because a bare 0.67 does
not say which way it points.

`--brief` collapses each finding to its id, its message and the suggestion.

## The probe

`check` can tell you a question is vague. Only `probe` can tell you that your question,
against your state, answers 0.72 one way and 0.87 the other.

**Point it at the inputs you are least sure about.** `check` reads the state you gave it and
nothing else, so a question the material cannot settle looks fine against a state that happens to
settle it. `probe --state=hard-case.json` runs the same query against another state, and a
question with nothing to answer from shows up as one that moves when you reword it. That is the
failure worth finding, and `check` on a comfortable state will not find it.

It sends the query unchanged several times, and the spread of those repeats is what counts
as movement. Then it sends rewrites:

| Variant | What changes |
| --- | --- |
| `criteria-stripped` | the instructions alone, with the criteria removed |
| `asked-as-choice` | the same yes/no question as a two-option Choice |
| `options-reversed` | the same Choice options in the opposite order |
| `levels-reversed` | the same Score levels in the opposite order, read back flipped |
| your own | `--variants=file.json`, holding `{"name": {"question_id": "the rewording"}}` |

Every built-in variant is mechanical. Nothing generates a paraphrase, because a generated
one moves the wording and whatever the generator decided the question meant at the same
time, and the spread cannot then be attributed to either. That is what `--variants` is for:
a rewording you wrote, so that when the answer moves, the disagreement is between you and
the model.

Movement is reported in multiples of the repeat spread, and counted when it clears both three
times that spread and 0.05. The spread is the sample deviation of the repeats, or 0.0085 where
that is smaller. The repeats are sent back to back, which understates the variability of requests
spread out over time, so the figure is a floor.

**A probe is not a gate.** The unchanged query is sent `--repeats` times; every rewrite is sent
once. So a variant's reading is one draw compared against a mean, and the bar it has to clear is
three times a deviation estimated from five. Both move between runs, and a variant sitting near
the bar is starred on some runs and not others - on a query measured ten times, the same rewrite
was reported as moving eight times and not moving twice. Read the size of the move and the
readings behind it. `--strict` is for a rewrite that moves far more than the bar, not for one
near it, and a CI job that fails on `probe --strict` will fail intermittently.

## Exit codes

| code | `check` | `probe` | `self-test` |
| --- | --- | --- | --- |
| `0` | no findings at error severity | ran, whether or not anything moved | every check separated its examples |
| `1` | an error, or `--strict` with any finding | `--strict` and something moved | a check failed its own examples |
| `2` | could not run | could not run | could not run |
| `3` | no errors, but a check could not decide | - | - |

**`0` does not mean no findings.** Warnings and advice exit 0 on their own, which is what
`--strict` is for; a gate written as `jevlint check q.json && deploy` ships a query carrying
both. Read `summary`, or pass `--strict`.

`--min` sets one floor for both the listing and `--strict`, so `--min=warning --strict` fails
on a warning and passes on advice. The counts in `summary` are always the whole run, and the
report carries a note saying how many findings the floor left out.

**`2` means could not run, on every command**, including a run where any call to the API
failed or came back without answering what it was asked.

**A run that could not ask its checks is not a run that passed.** If any call fails - a bad key,
a network fault - the checks it carried never ran, and reporting that as a clean query would
tell a gate to deploy something nobody looked at. Those calls are recorded as `unreachable`
notes, `summary.complete` goes false, and the exit code is 2 whatever the findings say.

**Exit 3 is a check that could not decide.** A reading landing within 0.05 of its trigger is
asked again, and where separate calls answer on both sides of it the run says so instead of
picking. A gate that treats 3 as a pass is flipping a coin.

```sh
jevlint check query.json --static-only            # no key, no calls, no cost
jevlint check query.json --min=warning --strict   # for CI
jevlint check query.json --question=urgency       # re-check one question while iterating
jevlint check query.json --repeats=5              # ask the per-question checks five times
jevlint check query.json --all                    # also show the checks that ran and cleared
jevlint check query.json --show-accepted          # and the ones your config accepts
jevlint check query.json --brief                  # one line per finding
jevlint check query.json --format=json            # the report as JSON
jevlint check query.json --jev=1.13               # the rules written for that Jev build
jevlint --version                                 # the tool and the catalogue it loads
jevlint probe query.json --strict                 # fail when a rewrite moves an answer
```

An unknown option or an unknown `--min` value is an error, not a shrug: a mistyped
`--static-only` would otherwise spend money on a run you believed was free. A trigger outside
0.3 to 0.95 is refused at load for the same reason - a catalogue that fires on everything and
one that works produce reports of the same shape.

Every `check` report carries the catalogue that produced it, as `catalogue v1 <fingerprint>
for jev-1.13`. The fingerprint is a hash of the whole catalogue file, so two reports can be
compared and an edited rule set is visible instead of inferred. It moves when a hint is reworded
too, which is a difference that changes no finding: `jevlint --version --format=json` also
carries `asked`, a digest over what the checks put to Jev, and that is the one to compare when
what matters is whether the answers would be the same. `asked_through` carries the build
`--model` pinned, and `answered_by` carries the builds the answers came back naming, so a run
through another provider is distinguishable even where both were asked for the same thing. More
than one entry in `answered_by` means one run was not answered by one build. `probe` reads no
checks, so its output carries no catalogue.

## Which Jev build the rules are for

A defect belongs to a build, so the checks are versioned with Jev. Every run resolves one
version: `--jev`, then `jev` in the config, then `latest`. `jevlint --version` lists what the
catalogue covers, and a version it holds nothing for is refused.

```sh
jevlint check query.json --jev=1.13   # the rules written for that build
```

```json
{ "jev": "1.13" }
```

A query pinning its own build with `"model": "jev-1.13"` gets a note where the run resolved a
different one. The pin does not change the version. [docs/output.md](docs/output.md) has the
rest: what a skipped note carries, and how `since` and `until` narrow a check to a range.

## Accepting a finding

A finding you have read and disagree with goes in `.jevlint.json`, beside the query or in the
working directory:

```json
{
  "accept": [
    {
      "check": "choice/no-fallback",
      "question": "department",
      "reason": "The three departments are the whole set; a ticket cannot be about anything else."
    }
  ]
}
```

- **A reason is required.** Without one the run fails, because accepting a finding is a
  judgement somebody made and switching a check off is not.
- `jev` belongs in the same file, and pins the Jev build every command checks against.
- `question` is optional and takes `*`, for a check you accept across the whole query.
- A check id the catalogue does not hold fails the run, so a renamed check cannot leave an
  acceptance quietly covering nothing.
- No file is an empty config, not an error.

Accepted findings are **counted and named, not deleted**. They come out of the severity counts
and the exit code, and the report says `1 accepted by .jevlint.json` with `--show-accepted` for
the reasons and `"accepted": "<reason>"` in the JSON. A run whose only findings are accepted
prints `Nothing to report` above that line: nothing is outstanding, and the line below says what
was set aside and where to read why.

The config lives beside the query instead of inside it because the API rejects an unknown key
at the top of a request, and a query file that cannot be sent is no longer the thing you are
checking.

## For a program reading the output

`--format=json` on every command, including errors, which come back as
`{"error": {"kind", "message", "command"}}` with exit 2.
[`spec/report.schema.json`](spec/report.schema.json) documents every field, and
[docs/output.md](docs/output.md) covers what a caller needs beyond it.

One trap is worth stating here. **Exit 2 carries three shapes, and only one has an `error`
key**, so branching on that key alone reads two failures as a pass:

```
exit 2 and `error`            the run never started
exit 2 and `complete: false`  it started and lost calls
exit 2 and `asked: 0`         it ran and asked nothing
```

## The catalogue is not PHP

`checks/catalogue.json` holds every check: its id, severity, which primitives it applies to,
and for a model check the Jev question that decides it. It mentions no language, so both
implementations read the same file and neither writes checks of its own. A harness runs every
command through each and diffs what comes back, so the report, the text and the exit code are
one document; [docs/javascript.md](docs/javascript.md) names where the platform's own wording
shows through.

## What this cannot tell you

A model check has read your instruction and your criteria. It has not seen your subject, and it
is not calibrated against human judgement, so a finding is an argument you can weigh and not a
verdict. A query can pass every check and still be the wrong question to ask.
