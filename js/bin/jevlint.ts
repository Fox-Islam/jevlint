#!/usr/bin/env -S node --

// The `--` is load-bearing. Node scans the whole command line for its own
// `--env-file` wherever it appears, and exits 9 with its own message when the
// path does not exist - before this file runs, so jevlint's `--env-file` could
// not report a mistyped path as the usage error it is. `--` ends Node's option
// scanning, and everything after it reaches the parser below.

import { Application } from '../src/console/application.js';

// A write to a pipe is asynchronous, so a reader that goes away - `jevlint checks
// | head -2` - arrives as an error event and never as a throw. Node's default
// handler for it rethrows, which prints a stack trace over output the reader
// already has and exits 1 where the PHP package exits 0.
process.stdout.on('error', (error: NodeJS.ErrnoException) => {
    if (error.code !== 'EPIPE') {
        throw error;
    }
});

process.exitCode = await new Application().run(['jevlint', ...process.argv.slice(2)]);
