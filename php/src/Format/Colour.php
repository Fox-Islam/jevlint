<?php

declare(strict_types=1);

namespace Phox\JevLint\Format;

/**
 * ANSI escapes for a formatter, or plain text where the caller asked for none.
 *
 * Every formatter needs both and none of them needs anything else from the
 * others, so this is a trait and not a base class
 */
trait Colour
{
    private function paint(string $text, string $code): string
    {
        return $this->colour ? sprintf("\033[%sm%s\033[0m", $code, $text) : $text;
    }

    private function dim(string $text): string
    {
        return $this->paint($text, '2');
    }
}
