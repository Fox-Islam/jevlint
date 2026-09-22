<?php

declare(strict_types=1);

namespace Phox\JevLint\Probe;

use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Query\ReviewedQuestion;
use Phox\TypeSafe\Questions\Choice;
use Phox\TypeSafe\Questions\Noul;
use Phox\TypeSafe\Questions\Question;
use Phox\TypeSafe\Questions\Score;

/** Turns a question from the file under test back into one the SDK can send */
final class QuestionBuilder
{
    public static function build(ReviewedQuestion $question): Question
    {
        $criteria = $question->criteria;

        return match ($question->type) {
            'noul' => self::noul($question),
            'choice' => Choice::ask($question->instructions)->options(self::options($criteria ?? [])),
            'score' => Score::ask($question->instructions)->levels(array_values($criteria ?? [])),
            default => throw new JevLintException(Text::of('probe.question_has_no_type', ['id' => $question->id])),
        };
    }

    private static function noul(ReviewedQuestion $question): Noul
    {
        $noul = Noul::ask($question->instructions);
        $criteria = $question->criteria ?? [];

        if (isset($criteria['true'])) {
            $noul->yes(is_string($criteria['true']) || is_array($criteria['true']) ? $criteria['true'] : null);
        }

        if (isset($criteria['false'])) {
            $noul->no(is_string($criteria['false']) || is_array($criteria['false']) ? $criteria['false'] : null);
        }

        return $noul;
    }

    /**
     * @param  array<array-key, mixed>       $criteria
     * @return array<string, string|array<array-key, mixed>|null>
     */
    private static function options(array $criteria): array
    {
        $options = [];

        foreach ($criteria as $label => $description) {
            $options[(string) $label] = is_string($description) || is_array($description) ? $description : null;
        }

        return $options;
    }
}
