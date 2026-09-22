<?php

declare(strict_types=1);

namespace Phox\JevLint\Probe\Variants;

use Phox\JevLint\Probe\Variant;
use Phox\JevLint\Query\ReviewedQuestion;

/**
 * The same Choice with its options listed back to front.
 *
 * Nothing about the question changes, so any movement comes from the order the
 * options were listed in, which the calling code has no way to see
 */
final class OptionsReversed extends Variant
{
    public function name(): string
    {
        return 'options-reversed';
    }

    public function describe(): string
    {
        return 'the same options in the opposite order';
    }

    public function applies(ReviewedQuestion $question): bool
    {
        return $question->type === 'choice' && is_array($question->criteria) && count($question->criteria) > 1;
    }

    public function apply(ReviewedQuestion $question): ReviewedQuestion
    {
        return $question->withCriteria(array_reverse($question->criteria ?? [], true));
    }
}
