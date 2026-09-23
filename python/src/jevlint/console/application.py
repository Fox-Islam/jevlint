"""Reads the arguments, runs one command, and turns what happened into an exit code."""
from __future__ import annotations

import os
import sys

from ..catalogue import Catalogue
from ..errors import JevLintError
from ..support import Env, Json
from ..text import Text
from ..typesafe.errors import TypeSafeError
from .args import Args
from .commands import CheckCommand, ChecksCommand, ProbeCommand, SelfTestCommand
from .flags import Flags
from .output import Output

VERSION = '1.2.0'


class Application:
    VERSION = VERSION

    def run(self, argv: list[str]) -> int:
        args = Args.parse(argv[1:])
        # Read without validating. `args.flag()` raises on `--no-color=x`, and one
        # line above the try that raised before anything could report it.
        output = Output.make(args.has('no-color'))

        command = args.argument(0) or 'help'

        try:
            args.flag('no-color')

            # Before the first message. A usage error raised while reading the
            # options is the earliest thing this can print, and it is printed in
            # the reader's language like everything after it.
            if args.value('lang') is not None:
                Text.use(args.value('lang'))
            else:
                Text.from_environment()

            # Inside the try: a missing env file is a usage error and gets the
            # same reporting as any other, instead of an uncaught raise.
            if args.value('env-file') is not None:
                Env.use_file(args.value('env-file'))

            Flags.format(args)

            # `--version` is accepted everywhere and answers the same question
            # wherever it is written, so it is handled before the command runs.
            if args.has('version'):
                Flags.guard('version', args)

                return self._version(output, args.value('format') == 'json')

            if command in ('check', 'probe', 'self-test', 'checks'):
                if args.flag('help'):
                    Flags.guard(command, args)

                    return self._help(output, args.value('format') == 'json')

                Flags.guard(command, args)

            if command == 'check':
                return CheckCommand().run(args, output)

            if command == 'probe':
                return ProbeCommand().run(args, output)

            if command == 'self-test':
                return SelfTestCommand().run(args, output)

            if command == 'checks':
                return ChecksCommand().run(args, output)

            # An unknown option is an error on the four commands, so it is one
            # here too, instead of answering as though the flag were right.
            if command == 'help':
                Flags.guard('help', args)

                return self._help(output, args.value('format') == 'json')

            return self._unknown(command)
        except (JevLintError, TypeSafeError) as error:
            if args.value('format') == 'json':
                output.line(Json.encode_safely({
                    'error': {
                        'kind': 'api' if isinstance(error, TypeSafeError) else error.kind,
                        'message': str(error),
                        'command': command,
                    },
                }))

                return 2

            output.error(str(error))

            return 2

    def _help(self, output: Output, json: bool = False) -> int:
        if json:
            output.line(Json.encode_safely({
                'usage': Text.of('help.usage'),
                'commands': {
                    'check': Text.of('help.command_check'),
                    'probe': Text.of('help.command_probe'),
                    'self-test': Text.of('help.command_self_test'),
                    'checks': Text.of('help.command_checks'),
                },
                'options': Flags.documented(),
            }))

            return 0

        output.write(Text.of('help.page'))

        return 0

    def _version(self, output: Output, json: bool = False) -> int:
        catalogue = Catalogue.load()

        if json:
            output.line(Json.encode({
                'jevlint': VERSION,
                'catalogue': {
                    'version': catalogue.version,
                    'fingerprint': catalogue.fingerprint,
                    'asked': catalogue.asked,
                    'model': catalogue.model,
                    'jev': catalogue.versions,
                },
            }))

            return 0

        output.line(Text.of('version.line', {
            'jevlint': VERSION,
            'version': catalogue.version,
            'fingerprint': catalogue.fingerprint,
            'model': catalogue.model,
        }))
        output.line(Text.of('version.covers', {
            'versions': ', '.join(catalogue.versions),
            'latest': catalogue.jev,
        }))

        return 0

    def _unknown(self, command: str) -> int:
        """
        Raised, not printed, so it leaves through the same path as every other
        usage error. Printing it here made it the one failure a caller reading
        `--format=json` got as English on stderr and nothing on stdout.
        """
        raise JevLintError.of(JevLintError.USAGE, Text.of('cli.no_such_command', {'command': command}))


def main() -> int:
    """The console entry point, which is what `jevlint` on your PATH runs."""
    code = Application().run(['jevlint', *sys.argv[1:]])

    # A reader that goes away - `jevlint checks | head -2` - leaves the
    # interpreter's own final flush to fail, which prints a traceback over output
    # the reader already has and exits non-zero. Pointing the descriptor at
    # nowhere lets that flush succeed.
    try:
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())

    return code


if __name__ == '__main__':
    raise SystemExit(main())
