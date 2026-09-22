<?php

declare(strict_types=1);

namespace Phox\JevLint\Probe\Variants;

use Phox\JevLint\Probe\Variant;

/**
 * The query exactly as written. Sent several times, it gives the spread every
 * other variant's movement is measured against
 */
final class Unchanged extends Variant
{
    public function name(): string
    {
        return 'unchanged';
    }

    public function describe(): string
    {
        return 'the query as written';
    }
}
