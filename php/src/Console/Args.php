<?php

declare(strict_types=1);

namespace Phox\JevLint\Console;

use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;

/** The bare minimum that reads `--name=value`, `--flag` and positionals */
final class Args
{
    /**
     * @param list<string>               $positional
     * @param array<string, string|bool> $options
     * @param list<string>               $malformed options written with one dash
     * @param list<string>               $repeated  options given more than once
     */
    private function __construct(
        public readonly array $positional,
        private readonly array $options,
        public readonly array $malformed = [],
        public readonly array $repeated = [],
    ) {}

    /**
     * @param list<string> $argv
     */
    public static function parse(array $argv): self
    {
        $positional = [];
        $options = [];
        $malformed = [];
        $repeated = [];

        foreach ($argv as $argument) {
            if (! str_starts_with($argument, '--')) {
                // `-static-only`, written with one dash, parsed as a positional,
                // so the option guard never saw it and the run paid for the calls
                // the caller believed they had switched off.
                if (str_starts_with($argument, '-') && strlen($argument) > 1) {
                    $malformed[] = $argument;

                    continue;
                }

                $positional[] = $argument;

                continue;
            }

            $argument = substr($argument, 2);

            if (str_contains($argument, '=')) {
                [$name, $value] = explode('=', $argument, 2);

                if (array_key_exists($name, $options)) {
                    $repeated[$name] = true;
                }

                $options[$name] = $value;

                continue;
            }

            if (array_key_exists($argument, $options)) {
                $repeated[$argument] = true;
            }

            $options[$argument] = true;
        }

        return new self($positional, $options, $malformed, array_keys($repeated));
    }

    public function has(string $name): bool
    {
        return array_key_exists($name, $this->options);
    }

    public function flag(string $name): bool
    {
        $value = $this->options[$name] ?? false;

        if ($value === false) {
            return false;
        }

        // `--strict=false` read as true, which is the opposite of what anybody
        // typing it means. A switch takes no value.
        if ($value !== true && $value !== '') {
            throw JevLintException::of(JevLintException::USAGE, Text::of('args.switch_takes_no_value', ['option' => $name]));
        }

        return true;
    }

    public function value(string $name, ?string $default = null): ?string
    {
        $value = $this->options[$name] ?? null;

        return is_string($value) ? $value : $default;
    }

    /**
     * A count, with a ceiling.
     *
     * Every count here multiplies calls, and a typed `--repeats=50` is a bill
     * nobody meant to run. The limit is refused out loud, naming what the most is.
     */
    public function int(string $name, int $default, int $most = 20): int
    {
        $value = $this->value($name);

        if ($value === null) {
            return $default;
        }

        // Falling back to the default here runs a threshold the caller believes
        // they raised, and says nothing about it.
        if (! is_numeric($value)) {
            throw JevLintException::of(JevLintException::USAGE, Text::of('args.not_a_number', ['option' => $name, 'given' => $value]));
        }

        // `1.9` truncates to 1 and `9e99` saturates at PHP_INT_MAX, both in
        // silence, so the threshold that runs is not the one the caller wrote.
        if ((string) (int) $value !== ltrim($value, '+')) {
            throw JevLintException::of(JevLintException::USAGE, Text::of('args.not_a_whole_number', ['option' => $name, 'given' => $value]));
        }

        if ((int) $value < 1) {
            throw JevLintException::of(JevLintException::USAGE, Text::of('args.not_a_count', ['option' => $name, 'given' => $value]));
        }

        if ((int) $value > $most) {
            throw JevLintException::of(JevLintException::USAGE, Text::of('args.above_the_most', ['option' => $name, 'given' => $value, 'most' => $most]));
        }

        return (int) $value;
    }

    /**
     * A duration in seconds, which can carry a fraction.
     *
     * The count reader calls `--timeout=0.5` "not a count", which is a message
     * about the wrong kind of number
     */
    public function seconds(string $name, float $default): float
    {
        $value = $this->value($name);

        if ($value === null) {
            return $default;
        }

        if (! is_numeric($value) || (float) $value <= 0.0) {
            throw JevLintException::of(JevLintException::USAGE, Text::of('args.not_seconds', ['option' => $name, 'given' => $value]));
        }

        return (float) $value;
    }

    public function argument(int $index): ?string
    {
        return $this->positional[$index] ?? null;
    }

    /**
     * Options the caller did not list.
     *
     * A mistyped flag is otherwise indistinguishable from one left out, so
     * `--static-onlyy` spends money on a run the caller takes for free
     *
     * @param  list<string>  $known
     * @return list<string>
     */
    public function unknown(array $known): array
    {
        return array_values(array_diff(array_keys($this->options), $known));
    }
}
