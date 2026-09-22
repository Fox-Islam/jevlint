# Calling jevlint from PHP

`Phox\JevLint\Lint\Linter` runs the catalogue over a query and hands back a `Report`. The
`check` command goes through it, so a caller here gets the report the CLI prints instead of a
second implementation of it.

```php
use Phox\JevLint\Lint\Linter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Severity;

$report = Linter::fromEnvironment()->check(Query::fromArray([
    'state' => ['ticket' => 'I was charged twice for order A-104.'],
    'questions' => [
        'refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?'],
    ],
]));

foreach ($report->findings() as $finding) {
    printf("%s %s %s\n", $finding->severity->value, $finding->checkId, $finding->message);
}
```

The query is the request body you would send, so a query built in memory is checked without
going to disk first. `Query::fromFile` reads one, `Query::fromJson` takes the body as a string,
and `Query::fromArray` takes it decoded. Prefer one of the first two where you have the JSON:
`criteria` written as a JSON object and as a JSON array are different requests and the API
rejects the wrong one, and `json_decode` to an associative array loses which one it was.

## Starting one

| | |
| --- | --- |
| `Linter::make($client)` | asks its model checks through an SDK client you supply |
| `Linter::fromEnvironment()` | reads `TYPESAFE_API_KEY` from the environment or a `.env` in the working directory and builds its own |
| `Linter::rulesOnly()` | runs the rules, makes no calls and needs no key |

`make` takes any `Phox\TypeSafe\Client`, including the one `FakeTypeSafe` hands out, which is
how the tests here run the model path without calling anything:

```php
$fake = FakeTypeSafe::make();
$fake->alwaysReply(FakeAnswers::make()->noul('question_compound_judgment', 0.93)->only());

$report = Linter::make($fake->client())->check($query);
```

A client is built when the run reaches a check that needs one, so `fromEnvironment()` narrowed
to rules asks for no key.

## Narrowing a run

Each of these returns a new linter, so one can be configured once and reused:

| | |
| --- | --- |
| `->only([...])` | run these checks. An id the catalogue does not hold throws, instead of narrowing to nothing and reporting a clean query |
| `->forJev('1.13')` | the rules for one Jev build. Without it the run uses the newest version the catalogue covers |
| `->accepting(Config::load('.jevlint.json'))` | the acceptances that set findings aside. The CLI discovers this file beside the query; nothing here does it for you |
| `->withoutState()` | leave out the checks that read the query's state |
| `->repeats(3)` | ask each model check this many times, so the report has the spread |
| `->reportingCleared()` | report every model check that ran and cleared, not only the readings near a trigger |
| `->maxStateChars(20000)` | where a state stops being state and starts being a document |

Where you narrow the query itself with `Query::only()`, pass the whole query as the second
argument to `check()`. The checks that judge a state field against the whole query cannot answer
from part of it, so they are left out and the report records it:

```php
$report = $linter->check($whole->only(['refund']), $whole);
```

## Reading the report

`$report->toArray()` is the document in [`spec/report.schema.json`](../spec/report.schema.json),
and [output.md](output.md) covers what every field means. Read as objects instead:

| | |
| --- | --- |
| `$report->findings($floor)` | the findings, ordered as the query wrote its questions |
| `$report->count(Severity::Error)` | how many at one severity, counted whole even where a floor hid them from the list |
| `$report->cleared()`, `$report->unstable()`, `$report->accepted()` | checks that ran without firing, could not decide, or were set aside by the config |
| `$report->notes()`, `$report->skippedNotes()`, `$report->unreachableNotes()` | what the run could not ask, and what it left out |
| `$report->isComplete()`, `$report->askedCount()` | whether every check was asked, and how many were |
| `$report->calls()`, `$report->tokens()` | what it cost |

**A run that lost its calls is not a run that passed, and neither is one that asked nothing.**
The exit codes belong to the CLI; a caller gating on a report writes the same three conditions:

```php
if (! $report->isComplete() || $report->askedCount() === 0) {
    // the run did not check the query
}

if ($report->hasErrors()) {
    // the query has a defect the API is documented to reject
}

if ($report->unstable() !== []) {
    // a check answered on both sides of its trigger, so another run may differ
}
```

A report with no findings and `askedCount() === 0` is the same object as a clean pass. Nothing
distinguishes them but that count.

## What the CLI does that this does not

Reading the arguments, discovering `.jevlint.json` beside the query, formatting the text report
and turning a report into an exit code all live in `Phox\JevLint\Console`. The catalogue, the
narrowing, the order of the two linters, the notes saying what was left out and the reconciling
that makes a lost check visible are all in `Linter` and run wherever it does.
