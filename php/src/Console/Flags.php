<?php

declare(strict_types=1);

namespace Phox\JevLint\Console;

use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Report\Severity;

/** What each command accepts, and what it does when given something else */
final class Flags
{
    /** @var list<string> */
    public const EVERYWHERE = ['no-color', 'env-file', 'lang', 'model', 'openrouter', 'format', 'help', 'version'];

    /** @var array<string, list<string>> */
    private const BY_COMMAND = [
        'check' => ['static-only', 'no-state', 'min', 'strict', 'max-state', 'timeout', 'brief', 'repeats', 'question', 'only', 'all', 'config', 'show-accepted', 'jev'],
        'probe' => ['state', 'repeats', 'variants', 'strict', 'question'],
        'self-test' => ['check', 'config', 'jev'],
        'checks' => ['config', 'jev'],
    ];

    /**
     * Every option this tool takes, with the commands it belongs to. `help
     * --format=json` prints it, so a caller can discover the interface
     *
     * @return array<string, list<string>>
     */
    public static function documented(): array
    {
        $options = ['everywhere' => self::EVERYWHERE];

        foreach (self::BY_COMMAND as $command => $flags) {
            $options[$command] = $flags;
        }

        return $options;
    }

    /** @var list<string> */
    private const SWITCHES = ['no-color', 'openrouter', 'help', 'version', 'static-only', 'no-state', 'strict', 'brief', 'all', 'show-accepted'];

    /** How many arguments each command takes after its own name */
    private const ARGUMENTS = ['check' => 1, 'probe' => 1, 'self-test' => 0, 'checks' => 1, 'help' => 1, 'version' => 0];

    /** Options that shape a call, and so do nothing in a run that makes none */
    private const NEEDS_CALLS = ['repeats', 'timeout', 'no-state', 'all', 'model', 'openrouter'];

    /** Options whose value is a count */
    private const COUNTS = ['repeats', 'max-state'];

    public static function guard(string $command, Args $args): void
    {
        if ($args->malformed !== []) {
            throw JevLintException::of(JevLintException::USAGE, Text::of('flags.needs_two_dashes', [
                'options' => implode(', ', array_map(
                    static fn (string $f): string => Text::of('flags.needs_two_dashes_item', ['given' => $f, 'fixed' => ltrim($f, '-')]),
                    $args->malformed,
                )),
            ]));
        }

        // Silently letting the last one win reports at a floor the caller wrote
        // twice and meant once.
        if ($args->repeated !== []) {
            throw JevLintException::of(JevLintException::USAGE, Text::of('flags.repeated', [
                'options' => implode(', ', array_map(static fn (string $f): string => '--'.$f, $args->repeated)),
                'count' => count($args->repeated),
            ]));
        }

        // A second file is the shape of a caller who takes both as checked.
        // Only the first is.
        $extra = array_slice($args->positional, 1 + (self::ARGUMENTS[$command] ?? 0));

        if ($extra !== []) {
            throw JevLintException::of(JevLintException::USAGE, Text::of('flags.too_many_arguments', [
                'command' => $command,
                'takes' => self::ARGUMENTS[$command] ?? 0,
                'extra' => implode(', ', $extra),
            ]));
        }

        $known = [...self::EVERYWHERE, ...(self::BY_COMMAND[$command] ?? [])];
        $unknown = $args->unknown($known);

        if ($unknown !== []) {
            throw new JevLintException(Text::of('flags.unknown_option', [
                'count' => count($unknown),
                'options' => implode(', ', array_map(static fn (string $f): string => '--'.$f, $unknown)),
                'command' => $command,
                'accepts' => implode(', ', array_map(static fn (string $f): string => '--'.$f, $known)),
            ]));
        }

        // A value option written bare reads as `true`, and `value()` then hands
        // back its default, so `--jev` on its own ran the newest version's checks
        // while the caller believed they had pinned one.
        foreach ($known as $option) {
            if (in_array($option, self::SWITCHES, true) || ! $args->has($option)) {
                continue;
            }

            if ($args->value($option) === null) {
                throw JevLintException::of(JevLintException::USAGE, Text::of('flags.needs_a_value', ['option' => $option]));
            }

            // An empty value reaches the client as an empty model name, and the
            // report reads "asked through " with nothing after it.
            if ($args->value($option) === '') {
                throw JevLintException::of(JevLintException::USAGE, Text::of('flags.empty_value', ['option' => $option]));
            }
        }

        self::format($args);
        self::value($args, 'min', array_map(static fn (Severity $s): string => $s->value, Severity::cases()));

        // Up front, before anything runs. A switch given a value reads as true
        // whatever the value is, so `--strict=false` would turn strict on, and
        // saying so after the report is printed is too late.
        foreach (self::SWITCHES as $switch) {
            $args->flag($switch);
        }

        // Read up front. A count this run never reads is a count nobody validated,
        // so `--static-only --repeats=abc` ran clean and reported nothing.
        foreach (self::COUNTS as $count) {
            if (in_array($count, $known, true) && $args->has($count)) {
                $args->int($count, 1);
            }
        }

        if (in_array('timeout', $known, true) && $args->has('timeout')) {
            $args->seconds('timeout', 10.0);
        }

        // A flag that cannot do anything in this run is a flag the caller thinks
        // is doing something.
        if ($args->flag('static-only')) {
            $dead = array_values(array_filter(self::NEEDS_CALLS, static fn (string $f): bool => $args->has($f)));

            if ($dead !== []) {
                throw JevLintException::of(JevLintException::USAGE, Text::of('flags.dead_with_static_only', [
                    'options' => implode(', ', array_map(static fn (string $f): string => '--'.$f, $dead)),
                    'count' => count($dead),
                ]));
            }
        }

        // `--brief` shapes the text report. Accepting it beside `--format=json`
        // and doing nothing is the silent no-op this tool refuses elsewhere.
        if ($args->flag('brief') && $args->value('format') === 'json') {
            throw JevLintException::of(JevLintException::USAGE, Text::of('flags.brief_with_json'));
        }

        if ($args->flag('show-accepted') && $args->value('format') === 'json') {
            throw JevLintException::of(JevLintException::USAGE, Text::of('flags.show_accepted_with_json'));
        }
    }

    /**
     * The one option every command reads, including the ones that take no others.
     *
     * It decides how a caller parses the output, so an unrecognised value has to
     * be refused on every command, `help` included
     */
    public static function format(Args $args): void
    {
        self::value($args, 'format', ['text', 'json']);
    }

    /**
     * @param list<string> $allowed
     */
    private static function value(Args $args, string $name, array $allowed): void
    {
        $given = $args->value($name);

        if ($given !== null && ! in_array($given, $allowed, true)) {
            throw new JevLintException(Text::of('flags.value_not_allowed', [
                'option' => $name,
                'given' => $given,
                'allowed' => implode(', ', $allowed),
            ]));
        }
    }
}
