<?php

declare(strict_types=1);

namespace Phox\JevLint\Probe\Variants;

use Phox\JevLint\Probe\Variant;
use Phox\JevLint\Query\ReviewedQuestion;

/**
 * The same instructions with the criteria removed.
 *
 * This variant changes the question, which the others do not. The gap it opens
 * is how much of the answer the criteria are carrying
 */
final class CriteriaStripped extends Variant
{
    public function name(): string
    {
        return 'criteria-stripped';
    }

    public function describe(): string
    {
        return 'the instructions alone, with the criteria removed - the one rewrite here that changes the question';
    }

    public function applies(ReviewedQuestion $question): bool
    {
        // The criteria that reach the request, not the ones in the file. A Noul
        // is sent with `true` and `false` and nothing else, so criteria under any
        // other key never leave, and stripping them would send the baseline again
        // under the name of a rewrite.
        $criteria = $question->criteria ?? [];

        return $question->type === 'noul'
            && (isset($criteria['true']) || isset($criteria['false']));
    }

    public function apply(ReviewedQuestion $question): ReviewedQuestion
    {
        return $question->withCriteria(null);
    }
}
