# Calling jevlint from JavaScript

```sh
npm install --save-dev @phox-js/jevlint
npx jevlint check your-query.json --static-only
```

Node 20.19 or newer. The one dependency is
[`@typesafe-ai/sdk`](https://www.npmjs.com/package/@typesafe-ai/sdk), which is how the model
checks are asked.

The commands and the options are the ones on the front page. This page is the library.

## The library

`Linter` runs the catalogue over a query and hands back a `Report`. The `check` command goes
through it, so a caller here gets the report the CLI prints instead of a second implementation
of it.

```ts
import { Linter, Query } from '@phox-js/jevlint';

const report = await Linter.fromEnvironment().check(Query.fromObject({
    state: { ticket: 'I was charged twice for order A-104.' },
    questions: {
        refund: { type: 'noul', instructions: 'Does the customer ask for a refund?' },
    },
}));

for (const finding of report.findings()) {
    console.log(finding.severity.value, finding.checkId, finding.message);
}
```

`check()` is async because a model check is a call. `Linter.rulesOnly()` makes none and still
returns a promise, so a caller writes `await` once and does not have to know which half ran.

The query is the request body you would send, so a query built in memory is checked without
going to disk first. `Query.fromFile` reads one, `Query.fromJson` takes the body as a string,
and `Query.fromObject` takes it decoded.

**Prefer `fromFile` or `fromJson` where you have the text.** A JavaScript object lists a key
that looks like an array index before every other key, and lists those in ascending numeric
order however they were written, so a Choice you decoded yourself as
`{"30": "A month", "7": "A week"}` has already been reordered before jevlint sees it. Option
order changes answers. `fromJson` reads the text with a parser that records what the file
wrote, and everything downstream — the request that goes out, the probe's `options-reversed`,
a patch that rebuilds `criteria` — keeps it. `choice/index-like-options` reports a Choice whose
keys the reordering would move, whichever way the query reached jevlint.

## Starting one

| | |
| --- | --- |
| `Linter.make(client)` | asks its model checks through a client you supply |
| `Linter.fromEnvironment()` | reads `TYPESAFE_API_KEY` from the environment or a `.env` in the working directory and builds its own |
| `Linter.rulesOnly()` | runs the rules, makes no calls and needs no key |

`make` takes a `Client` from this package, which wraps the SDK. The SDK takes a `fetch`, so the
model path runs in a test against a function instead of a network:

```ts
import { Client, Linter } from '@phox-js/jevlint';

const client = Client.make({
    apiKey: 'not-used',
    fetch: async () => new Response(JSON.stringify({
        model: 'jev-1.13.0',
        answers: { question_compound_judgment: { type: 'noul', noul: 0.93 } },
        usage: { input_tokens: 10, output_tokens: 2 },
    })),
});

const report = await Linter.make(client).only(['question/compound-judgment']).check(query);
```

A client is built when the run reaches a check that needs one, so `fromEnvironment()` narrowed
to rules asks for no key.

## Narrowing a run

Each of these returns a new linter, so one can be configured once and reused:

| | |
| --- | --- |
| `.only([...])` | run these checks. An id the catalogue does not hold throws, instead of narrowing to nothing and reporting a clean query |
| `.forJev('1.13')` | the rules for one Jev build. Without it the run uses the newest version the catalogue covers |
| `.accepting(Config.load('.jevlint.json'))` | the acceptances that set findings aside. The CLI discovers this file beside the query; nothing here does it for you |
| `.withoutState()` | leave out the checks that read the query's state |
| `.repeats(3)` | ask each model check this many times, so the report has the spread |
| `.reportingCleared()` | report every model check that ran and cleared, not only the readings near a trigger |
| `.maxStateChars(20000)` | where a state stops being state and starts being a document |

Where you narrow the query itself with `Query.only()`, pass the whole query as the second
argument to `check()`. The checks that judge a state field against the whole query cannot answer
from part of it, so they are left out and the report records it:

```ts
const report = await linter.check(whole.only(['refund']), whole);
```

## Reading the report

`report.toObject()` is the document in [`spec/report.schema.json`](../spec/report.schema.json),
and [output.md](output.md) covers what every field means. Read as objects instead:

| | |
| --- | --- |
| `report.findings(floor)` | the findings, ordered as the query wrote its questions |
| `report.count(Severity.Error)` | how many at one severity, counted whole even where a floor hid them from the list |
| `report.cleared()`, `report.unstable()`, `report.accepted()` | checks that ran without firing, could not decide, or were set aside by the config |
| `report.notes()`, `report.skippedNotes()`, `report.unreachableNotes()` | what the run could not ask, and what it left out |
| `report.isComplete()`, `report.askedCount()` | whether every check was asked, and how many were |
| `report.calls()`, `report.tokens()` | what it cost |

**A run that lost its calls is not a run that passed, and neither is one that asked nothing.**
The exit codes belong to the CLI; a caller gating on a report writes the same three conditions:

```ts
if (!report.isComplete() || report.askedCount() === 0) {
    // the run did not check the query
}

if (report.hasErrors()) {
    // the query has a defect the API is documented to reject
}

if (report.unstable().length > 0) {
    // a check answered on both sides of its trigger, so another run may differ
}
```

## Where the two implementations part

Both are held to the same output by a harness that runs every command through each and diffs
what comes back, so the report, the text, the exit code and the request body are the same
document. What is left is the platform's own and cannot be:

| | |
| --- | --- |
| the detail on an invalid query file | `Syntax error` against `Expected property name or '}' at position 1`. The `kind` a program reads is `invalid-json` either way |
| the detail on a call that never connected | cURL names the host and port; `fetch` reports only that it failed. The `cause` is `connection` either way |
| a `--lang` tag no locale data exists for | ICU falls back to the root locale, whose plurals have one form; `Intl` falls back to the runtime's. A tag anybody has, translated or not, behaves the same in both |

These two are worth knowing instead of comparing:

- **A locale file is `<locale>.json` here and `<locale>.php` in the PHP package.** Both are read
  from `JEVLINT_LANG_DIR`, and `checks/lang/<locale>.json`, which is where what a check reports
  about your query is translated, is the same file for both. See [languages.md](languages.md).
- **The shebang on the published binary is `#!/usr/bin/env -S node --`.** Node reads its own
  `--env-file` wherever it appears on the command line and exits before the script runs, so
  without the `--` jevlint's `--env-file` could not report a mistyped path as the usage error it
  is.

## What the CLI does that this does not

Reading the arguments, discovering `.jevlint.json` beside the query, formatting the text report
and turning a report into an exit code all live in the console layer. The catalogue, the
narrowing, the order of the two linters, the notes saying what was left out and the reconciling
that makes a lost check visible are all in `Linter` and run wherever it does.
