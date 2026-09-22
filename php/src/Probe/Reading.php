<?php

declare(strict_types=1);

namespace Phox\JevLint\Probe;

/** What one variant did to one question */
final class Reading
{
    public function __construct(
        public readonly string $variant,
        public readonly string $describe,
        public readonly ?float $value,
        public readonly ?string $error = null,
    ) {}
}
