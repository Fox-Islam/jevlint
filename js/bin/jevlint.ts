#!/usr/bin/env -S node --

// The `--` is load-bearing. Node scans the whole command line for its own
// `--env-file` wherever it appears, and exits 9 with its own message when the
// path does not exist - before this file runs, so jevlint's `--env-file` could
// not report a mistyped path as the usage error it is. `--` ends Node's option
// scanning, and everything after it reaches the parser below.

import { Application } from '../src/console/application.js';

process.exitCode = await new Application().run(['jevlint', ...process.argv.slice(2)]);
