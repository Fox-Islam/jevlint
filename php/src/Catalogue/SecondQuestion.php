<?php

declare(strict_types=1);

namespace Phox\JevLint\Catalogue;

/**
 * A question asked beside a check that overrules its verdict, and the reading it
 * takes. It asks something different from the check, so it decides on its own
 * instead of being averaged in with the check's wordings
 */
final class SecondQuestion
{
    public function __construct(
        public readonly Wording $wording,
        public readonly float $trigger,
    ) {}
}
