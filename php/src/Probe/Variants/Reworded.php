<?php

declare(strict_types=1);

namespace Phox\JevLint\Probe\Variants;

use Phox\JevLint\Probe\Variant;
use Phox\JevLint\Query\ReviewedQuestion;

/**
 * A rewording you wrote yourself, read from `--variants`.
 *
 * A paraphrase belongs here, where you have judged it to mean the same thing.
 * When the answer then moves, the disagreement is between you and the model,
 * with no generator in between
 */
final class Reworded extends Variant
{
    /**
     * @param array<string, string> $instructions question id to its rewording
     */
    public function __construct(
        private readonly string $name,
        private readonly array $instructions,
    ) {}

    public function name(): string
    {
        return $this->name;
    }

    public function describe(): string
    {
        return 'your rewording';
    }

    public function applies(ReviewedQuestion $question): bool
    {
        return isset($this->instructions[$question->id]);
    }

    public function apply(ReviewedQuestion $question): ReviewedQuestion
    {
        // `applies()` has already found the id, so there is nothing to fall back to.
        return $question->withInstructions($this->instructions[$question->id]);
    }
}
