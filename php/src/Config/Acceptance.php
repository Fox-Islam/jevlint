<?php

declare(strict_types=1);

namespace Phox\JevLint\Config;

/** One finding somebody has read and decided to live with */
final class Acceptance
{
    public function __construct(
        public readonly string $check,
        public readonly ?string $question,
        public readonly string $reason,
    ) {}

    public function covers(string $check, string $target): bool
    {
        if ($this->check !== $check) {
            return false;
        }

        return $this->question === null || $this->question === '*' || $this->question === $target;
    }
}
