<?php

declare(strict_types=1);

namespace Phox\JevLint\Probe;

use Phox\JevLint\Query\ReviewedQuestion;
use Phox\TypeSafe\Responses\ChoiceAnswer;
use Phox\TypeSafe\Responses\NoulAnswer;
use Phox\TypeSafe\Responses\ScoreAnswer;
use Phox\TypeSafe\Responses\SystemOneResponse;

/**
 * One meaning-preserving rewrite of a query, and how to read its answers back
 * onto the same scale as the original's.
 *
 * Every variant here is mechanical. A generated paraphrase would move both the
 * wording and whatever the generator took the question to mean, leaving the
 * spread attributable to neither
 */
abstract class Variant
{
    abstract public function name(): string;

    abstract public function describe(): string;

    /** Whether this variant changes anything about this question */
    public function applies(ReviewedQuestion $question): bool
    {
        return true;
    }

    public function apply(ReviewedQuestion $question): ReviewedQuestion
    {
        return $question;
    }

    /**
     * The answer as one number on [0, 1], comparable with the original's
     *
     * @param array{winner?: string, levels?: int} $baseline
     */
    public function read(SystemOneResponse $response, ReviewedQuestion $question, array $baseline): ?float
    {
        if (! $response->has($question->id)) {
            return null;
        }

        $answer = $response->answer($question->id);

        if ($answer instanceof NoulAnswer) {
            return $answer->noul();
        }

        if ($answer instanceof ChoiceAnswer) {
            $winner = $baseline['winner'] ?? $answer->choice();

            return $answer->probabilityOf($winner);
        }

        if ($answer instanceof ScoreAnswer) {
            $levels = max(1, ($baseline['levels'] ?? 2) - 1);

            return $answer->score() / $levels;
        }

        return null;
    }
}
