<?php

declare(strict_types=1);

namespace Phox\JevLint\Report;

enum Severity: string
{
    case Error = 'error';
    case Warning = 'warning';
    case Advice = 'advice';

    public static function fromName(string $value): self
    {
        return self::tryFrom(strtolower($value)) ?? self::Warning;
    }

    /** Higher is worse. Used for sorting and for the minimum-severity filter */
    public function weight(): int
    {
        return match ($this) {
            self::Error => 3,
            self::Warning => 2,
            self::Advice => 1,
        };
    }

    public function atLeast(self $floor): bool
    {
        return $this->weight() >= $floor->weight();
    }
}
