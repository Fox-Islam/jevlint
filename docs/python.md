# Calling jevlint from Python

```sh
pip install jevlint
jevlint check your-query.json --static-only
```

Python 3.10 or newer. Two dependencies:
[`typesafe-sdk`](https://pypi.org/project/typesafe-sdk/), which is how the model checks are
asked, and [`babel`](https://pypi.org/project/babel/), which supplies the CLDR plural rules and
number formats the messages are written against.

The commands and the options are the ones on the front page. This page is the library.

## The library

`Linter` runs the catalogue over a query and hands back a `Report`. The `check` command goes
through it, so a caller here gets the report the CLI prints instead of a second implementation
of it.

```python
from jevlint import Linter, Query

report = Linter.from_environment().check(Query.from_dict({
    'state': {'ticket': 'I was charged twice for order A-104.'},
    'questions': {
        'refund': {'type': 'noul', 'instructions': 'Does the customer ask for a refund?'},
    },
}))

for finding in report.findings():
    print(finding.severity.value, finding.check_id, finding.message)
```

`check()` blocks while the model checks are asked. The JavaScript package is asynchronous and
this one is not, so a caller here writes no `await` and gets no event loop.

The query is the request body you would send, so a query built in memory is checked without
going to disk first. `Query.from_file` reads one, `Query.from_json` takes the body as a string,
and `Query.from_dict` takes it decoded.

**All three keep the order the file wrote.** A `dict` lists its keys in the order they went in,
and `json.loads` fills one in the order the text holds, so a Choice written
`{"30": "A month", "7": "A week"}` reaches the request that way round. Option order changes
answers, and in JavaScript it is the entry point that decides whether it survives; here it is
not something you have to think about.

## Starting one

| | |
| --- | --- |
| `Linter.make(client)` | asks its model checks through a client you supply |
| `Linter.from_environment()` | reads `TYPESAFE_API_KEY` from the environment or a `.env` in the working directory and builds its own |
| `Linter.rules_only()` | runs the rules, makes no calls and needs no key |

`make` takes a `Client` from this package, which wraps the SDK. The SDK takes an
`httpx2` transport, so the model path runs in a test against a function instead of a network:

```python
import httpx2
from jevlint import Client, Linter

def handle(request):
    return httpx2.Response(200, json={
        'model': 'jev-1.13.0',
        'answers': {'question_compound_judgment': {'type': 'noul', 'noul': 0.93}},
        'usage': {'input_tokens': 10, 'output_tokens': 2},
    })

client = Client(api_key='not-used', transport=httpx2.MockTransport(handle))
report = Linter.make(client).only(['question/compound-judgment']).check(query)
```

A client is built when the run reaches a check that needs one, so `from_environment()` narrowed
to rules asks for no key.

## Narrowing a run

Each of these returns a new linter, so one can be configured once and reused:

| | |
| --- | --- |
| `.only([...])` | run these checks. An id the catalogue does not hold raises, instead of narrowing to nothing and reporting a clean query |
| `.for_jev('1.13')` | the rules for one Jev build. Without it the run uses the newest version the catalogue covers |
| `.accepting(Config.load('.jevlint.json'))` | the acceptances that set findings aside. The CLI discovers this file beside the query; nothing here does it for you |
| `.without_state()` | leave out the checks that read the query's state |
| `.repeats(3)` | ask each model check this many times, so the report has the spread |
| `.reporting_cleared()` | report every model check that ran and cleared, not only the readings near a trigger |
| `.max_state_chars(20000)` | where a state stops being state and starts being a document |

Where you narrow the query itself with `Query.only()`, pass the whole query as the second
argument to `check()`. The checks that judge a state field against the whole query cannot answer
from part of it, so they are left out and the report records it:

```python
report = linter.check(whole.only(['refund']), whole)
```

## Reading the report

`report.to_dict()` is the document in [`spec/report.schema.json`](../spec/report.schema.json),
and [output.md](output.md) covers what every field means. Read as objects instead:

| | |
| --- | --- |
| `report.findings(floor)` | the findings, ordered as the query wrote its questions |
| `report.count(Severity.Error)` | how many at one severity, counted whole even where a floor hid them from the list |
| `report.cleared()`, `report.unstable()`, `report.accepted()` | checks that ran without firing, could not decide, or were set aside by the config |
| `report.notes()`, `report.skipped_notes()`, `report.unreachable_notes()` | what the run could not ask, and what it left out |
| `report.is_complete()`, `report.asked_count()` | whether every check was asked, and how many were |
| `report.calls()`, `report.tokens()` | what it cost |

**A run that lost its calls is not a run that passed, and neither is one that asked nothing.**
The exit codes belong to the CLI; a caller gating on a report writes the same three conditions:

```python
if not report.is_complete() or report.asked_count() == 0:
    ...  # the run did not check the query

if report.has_errors():
    ...  # the query has a defect the API is documented to reject

if len(report.unstable()) > 0:
    ...  # a check answered on both sides of its trigger, so another run may differ
```

## Where the implementations part

All three are held to the same output by a harness that runs every command through each and
diffs what comes back, so the report, the text, the exit code and the request body are the same
document. What is left is the platform's own and cannot be:

| | |
| --- | --- |
| the detail on an invalid query file | `Syntax error` against `Expecting property name enclosed in double quotes: line 1 column 2 (char 1)`. The `kind` a program reads is `invalid-json` either way |
| the detail on a call that never connected | cURL names the host it could not resolve and the URL it was asking for; `httpx2` reports the resolver error alone. The `cause` is `connection` either way |
| a `--lang` tag no locale data exists for | ICU falls back to the root locale, whose plurals have one form; Babel falls back to English. A tag anybody has, translated or not, behaves the same in all three |

These are worth knowing instead of comparing:

- **A locale file is `<locale>.json` here and in the JavaScript package, and `<locale>.php` in
  the PHP one.** All three read `JEVLINT_LANG_DIR`, and `checks/lang/<locale>.json`, which is
  where what a check reports about your query is translated, is the same file for every
  implementation. A file dropped into a directory at run time is data here, not a module, so it
  is JSON and importing it never runs it. See [languages.md](languages.md).
- **The methods carry Python names.** `reportingCleared` is `reporting_cleared`,
  `fromEnvironment` is `from_environment`, `toObject` is `to_dict`. The catalogue, the report
  fields and the check ids are the same words everywhere, because they are data and not an API.
- **`python -m jevlint` runs the same command line as the `jevlint` script**, for a checkout
  with nothing installed on the `PATH`.

## What the CLI does that this does not

Reading the arguments, discovering `.jevlint.json` beside the query, formatting the text report
and turning a report into an exit code all live in the console layer. The catalogue, the
narrowing, the order of the two linters, the notes saying what was left out and the reconciling
that makes a lost check visible are all in `Linter` and run wherever it does.
