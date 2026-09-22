<?php

declare(strict_types=1);

namespace Phox\JevLint\Probe\Variants;

use Phox\JevLint\Probe\Variant;
use Phox\JevLint\Query\ReviewedQuestion;
use Phox\TypeSafe\Responses\ChoiceAnswer;
use Phox\TypeSafe\Responses\SystemOneResponse;

/**
 * The same yes/no question asked as a two-option Choice.
 *
 * The documented example has a Noul at 0.22 and the same question as a Choice
 * at 0.01 on the same ticket. Nothing guarantees the two agree, so a threshold
 * tuned on one does not carry to the other, and this measures the gap on your
 * question
 */
final class NoulAsChoice extends Variant
{
    public function name(): string
    {
        return 'asked-as-choice';
    }

    public function describe(): string
    {
        return 'the same yes/no question asked as a two-option Choice';
    }

    public function applies(ReviewedQuestion $question): bool
    {
        return $question->type === 'noul';
    }

    public function apply(ReviewedQuestion $question): ReviewedQuestion
    {
        $criteria = $question->criteria ?? [];

        // A criterion written as a list of bullets is a shape the request takes.
        // Requiring a string here would replace it with a placeholder, and the
        // row would measure the criteria going missing as well as the primitive
        // changing.
        $describes = static fn (mixed $value, string $fallback): string|array => is_string($value) || is_array($value)
            ? $value
            : $fallback;

        $options = [
            'yes' => $describes($criteria['true'] ?? null, 'The answer to the question is yes.'),
            'no' => $describes($criteria['false'] ?? null, 'The answer to the question is no.'),
        ];

        return new ReviewedQuestion($question->id, 'choice', $question->instructions, $options, $question->raw);
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

        return $answer->probabilityOf('yes');
    }
}
