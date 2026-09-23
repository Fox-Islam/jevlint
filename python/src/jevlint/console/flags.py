"""What each command accepts, and what it does when given something else."""
from __future__ import annotations

from typing import ClassVar

from ..errors import JevLintError
from ..report import Severity
from ..text import Text
from .args import Args

_BY_COMMAND: dict[str, list[str]] = {
    'check': [
        'static-only', 'no-state', 'min', 'strict', 'max-state', 'timeout', 'brief',
        'repeats', 'question', 'only', 'all', 'config', 'show-accepted', 'jev',
    ],
    'probe': ['state', 'repeats', 'variants', 'strict', 'question'],
    'self-test': ['check', 'config', 'jev'],
    'checks': ['config', 'jev'],
}

_SWITCHES = [
    'no-color', 'openrouter', 'help', 'version', 'static-only', 'no-state',
    'strict', 'brief', 'all', 'show-accepted',
]

# How many arguments each command takes after its own name
_ARGUMENTS = {'check': 1, 'probe': 1, 'self-test': 0, 'checks': 1, 'help': 1, 'version': 0}

# Options that shape a call, and so do nothing in a run that makes none
_NEEDS_CALLS = ['repeats', 'timeout', 'no-state', 'all', 'model', 'openrouter']

# Options whose value is a count
_COUNTS = ['repeats', 'max-state']


class Flags:
    EVERYWHERE: ClassVar[list[str]] = [
        'no-color', 'env-file', 'lang', 'model', 'openrouter', 'format', 'help', 'version',
    ]

    @staticmethod
    def documented() -> dict[str, list[str]]:
        """
        Every option this tool takes, with the commands it belongs to. `help
        --format=json` prints it, so a caller can discover the interface.
        """
        return {'everywhere': Flags.EVERYWHERE, **_BY_COMMAND}

    @staticmethod
    def guard(command: str, args: Args) -> None:
        if len(args.malformed) > 0:
            raise JevLintError.of(JevLintError.USAGE, Text.of('flags.needs_two_dashes', {
                'options': ', '.join(
                    Text.of('flags.needs_two_dashes_item', {'given': given, 'fixed': given.lstrip('-')})
                    for given in args.malformed
                ),
            }))

        # Silently letting the last one win reports at a floor the caller wrote
        # twice and meant once.
        if len(args.repeated) > 0:
            raise JevLintError.of(JevLintError.USAGE, Text.of('flags.repeated', {
                'options': ', '.join(f'--{option}' for option in args.repeated),
                'count': len(args.repeated),
            }))

        # A second file is the shape of a caller who takes both as checked. Only
        # the first is.
        extra = args.positional[1 + _ARGUMENTS.get(command, 0):]

        if len(extra) > 0:
            raise JevLintError.of(JevLintError.USAGE, Text.of('flags.too_many_arguments', {
                'command': command,
                'takes': _ARGUMENTS.get(command, 0),
                'extra': ', '.join(extra),
            }))

        known = [*Flags.EVERYWHERE, *_BY_COMMAND.get(command, [])]
        unknown = args.unknown(known)

        if len(unknown) > 0:
            raise JevLintError(Text.of('flags.unknown_option', {
                'count': len(unknown),
                'options': ', '.join(f'--{option}' for option in unknown),
                'command': command,
                'accepts': ', '.join(f'--{option}' for option in known),
            }))

        # A value option written bare reads as `true`, and `value()` then hands
        # back its default, so `--jev` on its own ran the newest version's checks
        # while the caller believed they had pinned one.
        for option in known:
            if option in _SWITCHES or not args.has(option):
                continue

            if args.value(option) is None:
                raise JevLintError.of(
                    JevLintError.USAGE,
                    Text.of('flags.needs_a_value', {'option': option}),
                )

            # An empty value reaches the client as an empty model name, and the
            # report reads "asked through " with nothing after it.
            if args.value(option) == '':
                raise JevLintError.of(
                    JevLintError.USAGE,
                    Text.of('flags.empty_value', {'option': option}),
                )

        Flags.format(args)
        _allowed(args, 'min', [severity.value for severity in Severity.cases()])

        # Up front, before anything runs. A switch given a value reads as true
        # whatever the value is, so `--strict=false` would turn strict on, and
        # saying so after the report is printed is too late.
        for option in _SWITCHES:
            args.flag(option)

        # Read up front. A count this run never reads is a count nobody validated,
        # so `--static-only --repeats=abc` ran clean and reported nothing.
        for count in _COUNTS:
            if count in known and args.has(count):
                args.int(count, 1)

        if 'timeout' in known and args.has('timeout'):
            args.seconds('timeout', 10.0)

        # A flag that cannot do anything in this run is a flag the caller thinks
        # is doing something.
        if args.flag('static-only'):
            dead = [option for option in _NEEDS_CALLS if args.has(option)]

            if len(dead) > 0:
                raise JevLintError.of(JevLintError.USAGE, Text.of('flags.dead_with_static_only', {
                    'options': ', '.join(f'--{option}' for option in dead),
                    'count': len(dead),
                }))

        # `--brief` shapes the text report. Accepting it beside `--format=json`
        # and doing nothing is the silent no-op this tool refuses elsewhere.
        if args.flag('brief') and args.value('format') == 'json':
            raise JevLintError.of(JevLintError.USAGE, Text.of('flags.brief_with_json'))

        if args.flag('show-accepted') and args.value('format') == 'json':
            raise JevLintError.of(JevLintError.USAGE, Text.of('flags.show_accepted_with_json'))

    @staticmethod
    def format(args: Args) -> None:
        """
        The one option every command reads, including the ones that take no others.

        It decides how a caller parses the output, so an unrecognised value has to
        be refused on every command, `help` included.
        """
        _allowed(args, 'format', ['text', 'json'])


def _allowed(args: Args, name: str, values: list[str]) -> None:
    given = args.value(name)

    if given is not None and given not in values:
        raise JevLintError(Text.of('flags.value_not_allowed', {
            'option': name,
            'given': given,
            'allowed': ', '.join(values),
        }))
