<?php

declare(strict_types=1);

namespace Phox\JevLint\Probe\Variants;

use Phox\JevLint\Probe\Variant;
use Phox\JevLint\Query\ReviewedQuestion;
use Phox\TypeSafe\Responses\ScoreAnswer;
use Phox\TypeSafe\Responses\SystemOneResponse;

/**
 * The same rubric with its levels in the opposite order, read back flipped.
 *
 * The rubric describes the same situations either way, and each level is
 * evaluated on its own, so the flipped reading should fall where the original
 * did. Where it does not, the scale is being read as an ordering instead of as
 * the descriptions it is made of
 */
final class LevelsReversed extends Variant
{
    public function name(): string
    {
        return 'levels-reversed';
    }

    public function describe(): string
    {
        return 'the same levels in the opposite order, with the reading flipped back';
    }

    public function applies(ReviewedQuestion $question): bool
    {
        return $question->type === 'score' && is_array($question->criteria) && count($question->criteria) > 1;
    }

    public function apply(ReviewedQuestion $question): ReviewedQuestion
    {
        return $question->withCriteria(array_values(array_reverse($question->criteria ?? [])));
    }

    /**
     * @param array{winner?: string, levels?: int} $baseline
     */
    public function read(SystemOneResponse $response, ReviewedQuestion $question, array $baseline): ?float
    {
        $answer = $response->has($question->id) ? $response->answer($question->id) : null;

        if (! $answer instanceof ScoreAnswer) {
            return null;
        }

        $levels = max(1, ($baseline['levels'] ?? 2) - 1);

        return 1.0 - ($answer->score() / $levels);
    }
}
