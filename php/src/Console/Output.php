<?php

declare(strict_types=1);

namespace Phox\JevLint\Console;

/** Writes to stdout and stderr, and knows whether a terminal is reading */
final class Output
{
    public function __construct(private readonly bool $colour) {}

    public static function make(bool $forceOff = false): self
    {
        $tty = function_exists('stream_isatty') && @stream_isatty(STDOUT);

        return new self(! $forceOff && $tty && getenv('NO_COLOR') === false);
    }

    public function colour(): bool
    {
        return $this->colour;
    }

    /** Silenced because a reader that closes the pipe, such as `head`, is not an error here */
    public function write(string $text): void
    {
        @fwrite(STDOUT, $text);
    }

    public function line(string $text = ''): void
    {
        $this->write($text.PHP_EOL);
    }

    public function error(string $text): void
    {
        fwrite(STDERR, ($this->colour ? "\033[31m".$text."\033[0m" : $text).PHP_EOL);
    }
}
