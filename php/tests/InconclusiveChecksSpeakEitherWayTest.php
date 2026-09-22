<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Catalogue\Check;
use Phox\JevLint\Lint\ModelLinter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Report;
use Phox\TypeSafe\Testing\FakeAnswers;
use Phox\TypeSafe\Testing\FakeTypeSafe;
use PHPUnit\Framework\TestCase;

/**
 * A check whose clean and defective readings overlap cannot say the defect is
 * absent. Leaving it out of a run it cleared says exactly that, to a reader who
 * has no way to know otherwise without opening the catalogue
 */
final class InconclusiveChecksSpeakEitherWayTest extends TestCase
{
    public function test_a_check_that_cannot_clear_a_query_is_reported_when_it_clears(): void
    {
        $inconclusive = $this->inconclusive();
        $report = $this->lint($inconclusive, 0.10);

        $cleared = array_values(array_filter(
            $report->cleared(),
            static fn ($f): bool => $f->checkId === $inconclusive->id,
        ));

        self::assertCount(1, $cleared, sprintf(
            '%s read far below its trigger and said nothing, which reads as the defect being absent.',
            $inconclusive->id,
        ));
        self::assertNotSame('', $cleared[0]->advice, 'The reading is reported without the caveat that explains it.');
    }

    public function test_every_inconclusive_check_carries_the_caveat_that_explains_it(): void
    {
        $silent = [];

        foreach (Catalogue::load()->written() as $check) {
            if ($check->inconclusive && $check->advice === '') {
                $silent[] = $check->id;
            }
        }

        self::assertSame([], $silent, 'An inconclusive check with no caveat reports a number and no reason to doubt it.');
    }

    private function inconclusive(): Check
    {
        foreach (Catalogue::load()->written() as $check) {
            if ($check->inconclusive) {
                return $check;
            }
        }

        self::fail('No check is marked inconclusive, so this test pins nothing.');
    }

    private function lint(Check $check, float $reading): Report
    {
        $catalogue = Catalogue::load();
        $report = new Report('test', $catalogue->version);

        $fake = FakeTypeSafe::make();
        $fake->alwaysReply(FakeAnswers::make()->noul($check->answerKey(), $reading)->only());

        (new ModelLinter($catalogue, $fake->client(), only: [$check->id]))->run(
            Query::fromArray(['questions' => ['q' => [
                'type' => 'score',
                'instructions' => 'How urgent is this?',
                'criteria' => ['Not urgent', 'Somewhat urgent', 'Very urgent'],
            ]]]),
            $report,
        );

        return $report;
    }
}
