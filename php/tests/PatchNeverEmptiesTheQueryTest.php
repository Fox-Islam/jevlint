<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Lint\ModelLinter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Report;
use Phox\TypeSafe\Testing\FakeAnswers;
use Phox\TypeSafe\Testing\FakeTypeSafe;
use PHPUnit\Framework\TestCase;

/**
 * A check that says a question should not be asked at all offers a patch that
 * removes it. On a query holding one question that leaves nothing to ask, so an
 * agent applying patches unattended would empty the file
 */
final class PatchNeverEmptiesTheQueryTest extends TestCase
{
    public function test_the_only_question_is_not_offered_for_removal(): void
    {
        $finding = $this->lint(['decision' => 'Was the refund issued within 30 days of 3 March 2026?']);

        self::assertNotNull($finding, 'The check did not fire, so this test pins nothing.');
        self::assertNull($finding->patch, 'Applying this patch would leave the query with no questions.');
        self::assertNotSame('', $finding->suggest, 'Withholding the patch must not withhold the advice.');
    }

    public function test_one_of_several_questions_still_offers_the_patch(): void
    {
        $finding = $this->lint([
            'decision' => 'Was the refund issued within 30 days of 3 March 2026?',
            'tone' => 'Is the customer polite?',
        ]);

        self::assertNotNull($finding);
        self::assertNotNull($finding->patch, 'A query with other questions can lose this one.');
        self::assertSame('/questions/decision', $finding->patch->path);
    }

    /**
     * @param array<string, string> $questions
     */
    private function lint(array $questions): ?\Phox\JevLint\Report\Finding
    {
        $catalogue = Catalogue::load();
        $report = new Report('test', $catalogue->version);

        $fake = FakeTypeSafe::make();
        $fake->alwaysReply(FakeAnswers::make()->noul('question_date_comparison', 0.95)->only());

        (new ModelLinter($catalogue, $fake->client(), only: ['question/date-comparison']))->run(
            Query::fromArray(['questions' => array_map(
                static fn (string $text): array => ['type' => 'noul', 'instructions' => $text],
                $questions,
            )]),
            $report,
        );

        foreach ($report->findings() as $finding) {
            if ($finding->checkId === 'question/date-comparison') {
                return $finding;
            }
        }

        return null;
    }
}
