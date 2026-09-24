<?php

declare(strict_types=1);

namespace Phox\JevLint\Probe\Variants;

use Phox\JevLint\Probe\Variant;
use Phox\JevLint\Query\ReviewedQuestion;
use Phox\TypeSafe\Responses\ChoiceAnswer;
use Phox\TypeSafe\Responses\SystemOneResponse;

/**
 * The same Choice with each label replaced by its position, `option_1` and on.
 *
 * Jev reads a label as part of what an option means, not as an id, so this
 * leaves the descriptions to carry the meaning alone. Where the answer moves,
 * the labels were deciding it, which on a clear input they do not. A label
 * with no description would be left meaning nothing, so a Choice with one is
 * left alone
 */
final class KeysHidden extends Variant
{
    public function name(): string
    {
        return 'keys-hidden';
    }

    public function describe(): string
    {
        return 'the same options with each label replaced by option_1, option_2 and on, read back by position';
    }

    public function applies(ReviewedQuestion $question): bool
    {
        if ($question->type !== 'choice' || ! is_array($question->criteria) || count($question->criteria) < 2 || $question->criteriaIsList()) {
            return false;
        }

        foreach ($question->criteria as $value) {
            if (is_string($value) ? trim($value) === '' : ! is_array($value)) {
                return false;
            }
        }

        return true;
    }

    public function apply(ReviewedQuestion $question): ReviewedQuestion
    {
        $hidden = [];

        foreach (array_values($question->criteria ?? []) as $index => $value) {
            $hidden['option_'.($index + 1)] = $value;
        }

        return $question->withCriteria($hidden);
    }

    /**
     * @param array{winner?: string, levels?: int} $baseline
     */
    public function read(SystemOneResponse $response, ReviewedQuestion $question, array $baseline): ?float
    {
        $answer = $response->has($question->id) ? $response->answer($question->id) : null;

        if (! $answer instanceof ChoiceAnswer) {
            return null;
        }

        // The question here is the rewritten one; `raw` still holds the labels as written.
        $criteria = $question->raw['criteria'] ?? [];
        $labels = array_map('strval', array_keys(is_array($criteria) ? $criteria : []));
        $position = array_search($baseline['winner'] ?? '', $labels, true);

        return $position === false ? null : $answer->probabilityOf('option_'.($position + 1));
    }
}
