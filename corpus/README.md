# The corpus

What the checks are measured against, beyond the two examples each one ships.

| file | what it is | how it is labelled |
| --- | --- | --- |
| `gold.json` | 22 questions the TypeSafe docs discuss in prose | by the docs, with the quotation and the defect named |
| `docs-examples.json` | 76 entries, 52 distinct, from the docs' cookbooks, patterns and demos | correct by publication: TypeSafe wrote them as how to do it |
| `field.json` | 62 questions from `jev-bias-bench` and the Atarim API | unlabelled |
| `scores.json` | what every check put on every one of them | runs of `harvest.py`, 959 calls so far |
| `build.py` | the three above, as query files jevlint can read | - |
| `answers.py` | asking Jev one question and scoring the answer against its label, for the scripts that do both | - |
| `dogfood.py` | the catalogue's own check wordings, as query files | - |
| `squad.py` | `state/answer-absent` against SQuAD 2.0, fetched on demand | by the SQuAD annotators |
| `decision.py` | `state/answer-absent` against decision-v7, whose states carry a policy that can be taken away | by decision-v7 |
| `advice.py` | whether following `choice/no-fallback` improves the answer, not just the report | by decision-v7 |
| `position.py` | whether where the catch-all is listed changes the answer `advice.py` measures | by decision-v7 |
| `locators.py` | whether the order of a question's levels changes which one a `locate_mode: pick` check names | none needed |
| `sibling.py` | what it costs to put what a question needs into another question instead of the state | by decision-v7 |
| `mechanical.py` | whether Jev answers a question code could answer, over states generated here | computed, not judged |
| `undetermined.py` | `choice/undetermined-outcome` and `state/answer-absent` over the hidden draws `jev-does-not-play-dice` recorded, fetched on demand | the draw is hidden by construction |
| `rewrite.py` | the same for `question/double-negative`, with the rewriting done blind by a panel | by decision-v7 |
| `wording.py` | three wording checks at once, on material the model does not already answer perfectly | by decision-v7 |
| `families.py` | whether the two date and arithmetic checks fire where decision-v7's answers fail | by decision-v7 |
| `levels.py` | whether rewriting a Score's levels as situations puts reviews where they belong | by decision-v7 |
| `contradiction.py` | what inverted criteria cost, against criteria that agree with the instruction | by decision-v7 |
| `external.py` | `query/overlapping-questions` against Quora's duplicate questions | by that dataset |
| `planted.py` | `state/adversarial-content` on documents with a line planted in them | by the injection being known |
| `unread.py` | `state/irrelevant-field` on states with a field nothing reads | by the field being known |
| `fields.py` | how often the state-scoped checks fire on states nobody changed | by decision-v7, whose fields the question needs |
| `boundary.py` | what a vague boundary costs in how steadily the answer repeats | none needed |
| `borderline.py` | `question/unsettled-case`, on paragraphs with an edge planted in them | planted, the edge being known |
| `encoded.py` | whether a value written as hex costs an answer | computed, not judged |
| `flores.py` | what a spare field costs by the language it is written in | the language each FLORES-200 file holds |
| `drift.py` | how far a re-harvest moved the readings, and which verdicts changed | - |
| `arms/` | the samples and the blind rewrites the four arm experiments run over | - |
| `pages.py` | mirrors the documentation pages the docs tier was lifted from | - |
| `states.py` | puts back the state each docs example was run against | - |

```sh
python3 corpus/build.py                # the three source files into the query files in local/corpus
python3 corpus/harvest.py [path/to/.env]   # score them, 250 calls
python3 corpus/measure.py              # recall on the gold negatives, firing rate on the rest
python3 corpus/drift.py                # this harvest against the one it replaced
```

```sh
python3 corpus/squad.py --items=40    # one call per item, balanced across the two labels
```

```sh
python3 corpus/pages.py               # mirror the pages into local/docs
python3 corpus/states.py --write      # recover each docs example's state from its page
python3 corpus/decision.py --items=40 # the policy ablation, three calls per case
python3 corpus/advice.py --items=30   # does the advice improve the answer, two calls per arm
python3 corpus/position.py --items=24 # the catch-all where it was, listed first, listed last
python3 corpus/sibling.py --items=30  # the policy in the state, in a sibling question, and nowhere
python3 corpus/rewrite.py             # the same for a wording check, five arms
python3 corpus/wording.py --items=20  # three wording checks, seven arms
python3 corpus/families.py --items=6  # do the error-severity checks fire where answers fail
python3 corpus/levels.py              # does a Score check's advice improve where reviews land
python3 corpus/levels.py --check=score/multi-dimension   # with the arms in local/score-arms.json
```

`decision.py` fetches decision-v7 into `local/` on first run, and `advice.py`, `boundary.py`,
`families.py`, `fields.py`, `planted.py` and `unread.py` read it from there, so run `decision.py`
before them.
The arm experiments - `contradiction.py`, `rewrite.py`, `levels.py`, `wording.py` - read their
sample and their rewrites from `corpus/arms/`, which is committed because those files are the
experiment's inputs rather than its output: the rewrites were written blind by a panel and cannot
be regenerated by running anything. A copy in `local/` takes precedence, which is how a different
rewrite is tried without touching the committed one.

The checks with no gold negative are measured by planting the defect in material somebody else
wrote, or by fetching a dataset that is the defect:

```sh
python3 corpus/planted.py --items=20  # a line addressed to the reviewer, put into a document
python3 corpus/unread.py --items=20   # a field added to a state that no question reads
python3 corpus/fields.py --items=20   # the same checks over states with nothing to find
python3 corpus/external.py --check=query/overlapping-questions --items=30   # Quora's pairs
python3 corpus/contradiction.py       # criteria inverted against the instruction they belong to
python3 corpus/boundary.py            # a boundary taken out of the policy that defines it
python3 corpus/encoded.py             # the same comparison over a value written plainly and as hex
python3 corpus/mechanical.py          # eight rules over generated states, one call per state
python3 corpus/dogfood.py             # the catalogue's own wordings, as queries jevlint can read
python3 corpus/locators.py            # each pick locator over its own broken example, both ways round
python3 corpus/undetermined.py        # a Choice over a hidden draw, against the Choice questions the corpus holds
python3 corpus/borderline.py --items=12   # an edge planted in a paragraph, six arms over each
python3 corpus/flores.py --items=12   # one spare field per arm, the same sentences in another language
```

`flores.py` fetches FLORES-200 into `local/` on first run and unpacks it there, 25 MB
compressed and 77 MB on disk. It is the only measurement here whose spare field can be written
in a chosen language while its content is held still, because FLORES-200 translates one set of
sentences into 204 languages line for line. [docs/evidence.md](../docs/evidence.md) carries the
result.

`borderline.py` measures `question/unsettled-case`, which reads the reviewed question's
`criteria` beside the state. That is what `scope: state` shows a check, and it is the reason it
can work at all: shown the instruction line alone it reads 0.31 on a defect and 0.49 on the
repair for it, because the repair is in the criteria; shown the whole question the same two read
0.63 and 0.08.

`decision.py` is the strongest evidence here about a state-scoped check. decision-v7 ships states
holding a `policy` and a `case`, the question asked about them, and the answer it should get, so
removing the policy makes the state unable to answer the question and changes nothing else. It
also records what Jev answers as written, scored against the label, which is the baseline
`advice.py`, `rewrite.py`, `wording.py` and `levels.py` measure their repaired arms against.

`squad.py` is the only other measurement here whose labels come from outside this repository for a
state-scoped check. It fetches SQuAD 2.0 into `local/` on first run, samples a seeded balanced
set so two runs measure the same material, sends each paragraph as the state and its question as
the question, and records what `state/answer-absent` read. [docs/evidence.md](../docs/evidence.md)
carries
the result.

`harvest.py --only=<check ids>` scores those checks and merges them into the readings already
recorded, leaving every other check's numbers where they were and adding what the run paid to
the cost the file carries. A check added to the catalogue is folded in for the price of itself,
instead of buying the whole corpus again and moving every published figure.

`harvest.py` uses `TYPESAFE_API_KEY` from the environment. Pass an env file as its
argument, or set `JEVLINT_ENV_FILE`, if the key lives somewhere else; it refuses to start
instead of running every check against a file that is not there.

The three source files hold one question per entry with its label attached, which is the shape
a label is easiest to read and write in. `build.py` turns them into the query files jevlint
takes, grouped as they were asked, with the labels stripped and the ids normalised so that
`measure.py` can split a score id back into its file and its question. It refuses a source
entry whose primitive and criteria do not agree, naming the entry.

`harvest.py` runs `jevlint check --all`, which reports the model checks that ran and cleared
alongside the ones that fired. That records a probability whether or not it would have been
reported, without touching the catalogue other processes are reading.

Query files that carry a state are asked with it. `states.py` recovers the state each docs
example was run against from its own page, so 32 of the 76 entries carry one and the
state-scoped checks are measured on material somebody else wrote. The other 44 belong to
cookbook pages that fetch or loop over their state at run time, so the page holds none to
recover, and `gold.json` is questions quoted from prose with no material anywhere upstream.
Those files carry no state and the run says which checks that left out.

## What the gold set is for

A check's own two examples show it can tell an obvious defect from an obvious non-defect.
They cannot show it fires on the right things, because the person who wrote the check wrote
them both. The gold set is labelled by somebody else: each entry quotes the documentation
saying this question is right, or is wrong and why.

Fourteen are wrong with the defect named, so a check that claims to find that defect either
finds it or does not. Eight are right.

A positive carries `clears`: the checks its citation speaks to. The docs call "Does
this message convey urgency?" a good question in a passage about snap judgements, which clears
`question/compound-judgment` and says nothing about where the question's boundary falls. A
blanket good label would have scored every check against a claim the citation does not make.

Six entries are `tier: derived` instead of `quoted`: the documentation defines the failure but
gives no example, so the example is written from the definition. They are weaker evidence than
the quoted ones and are marked so.

## Reading the numbers

**Some docs examples carry no criteria.** They are extracted from code where the options and
levels are built from variables, so 34 of the 76 kept theirs and the rest are instruction only.
A check that reads `criteria` is asked about criteria that are not there on those, which is one
source of the firing rates on this tier.

**The docs repeat examples across pages.** 76 entries hold 52 distinct questions, so `measure.py`
counts each question once. Reading the raw entry count inflates every rate.

**The clean-material column is the docs tier plus the gold positives.** `measure.py` counts a
gold positive for a check only where that entry's `clears` names it, and no check is named by
more than two of the eight, so the column adds at most two to a denominator: 52 distinct docs
questions plus two gold positives is the 54 the widest checks are out of. The two tiers are
labelled clean by the same standard, and the column is a rate over everything labelled clean.

**The field tier has no labels.** A firing rate on it is a rate, not an error rate. Where a
finding there has been checked by hand, [docs/evidence.md](../docs/evidence.md) says so.

**A denominator is the questions the check was asked about.** A check that applies only to
Choice questions is asked about the Choice questions and no others, so its rate is out of
those, not out of the tier. Counting a question the check never saw as a question it cleared
would turn silence into a clean bill of health, and `measure.py` prints the checks that were
never asked at all instead of scoring them 0.

**Twenty-two gold entries is a small set**, fourteen of them negatives. It is enough to show
whether a check finds the example the documentation uses to define its own failure mode. It is
not enough to put an interval on a recall figure.
