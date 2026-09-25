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
 * A repeat that comes back without the answer keys contributes nothing, so the
 * guard runs against every response. Checking only the first lets a run lose
 * every repeat but that one, rest its verdict on a single reading, and report
 * itself complete
 */
final class LostCallsAreNotAPassTest extends TestCase
{
    public function test_a_repeat_that_answers_nothing_makes_the_run_incomplete(): void
    {
        $fake = FakeTypeSafe::make();
        $answered = FakeAnswers::make()->noul('question_arithmetic', 0.05)->noul('question_arithmetic__fire', 0.05)->noul('question_arithmetic__clear', 0.05)->only();

        // The first call answers; the repeats come back with nothing in them.
        $fake->reply($answered);
        $fake->reply(FakeAnswers::make()->only());
        $fake->reply(FakeAnswers::make()->only());

        $report = $this->lint($fake, 3);

        self::assertFalse($report->isComplete(), 'Two of three calls answered nothing and the run called itself complete.');
        self::assertNotSame([], $report->unreachableNotes());
    }

    public function test_a_run_whose_calls_all_answer_is_complete(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->alwaysReply(FakeAnswers::make()->noul('question_arithmetic', 0.05)->noul('question_arithmetic__fire', 0.05)->noul('question_arithmetic__clear', 0.05)->only());

        self::assertTrue($this->lint($fake, 3)->isComplete());
    }

    public function test_a_failed_call_is_counted_and_its_tokens_are_not_claimed_as_zero(): void
    {
        $report = new Report('test', '1');
        $report->recordCall(null);
        $report->recordCall(120);

        self::assertSame(2, $report->calls(), 'A call that failed still left the machine.');
        self::assertSame(120, $report->tokens());
        self::assertSame(1, $report->callsWithoutUsage());
    }

    private function lint(FakeTypeSafe $fake, int $repeats): Report
    {
        $catalogue = Catalogue::load();
        $report = new Report('test', $catalogue->version);

        // One check, so the call carries one answer key and a complete reply
        // really is complete.
        (new ModelLinter(
            $catalogue,
            $fake->client(),
            repeats: $repeats,
            only: ['question/arithmetic'],
        ))->run($this->query(), $report);

        return $report;
    }

    private function query(): Query
    {
        return Query::fromArray([
            'questions' => [
                'refund' => ['type' => 'noul', 'instructions' => 'How many separate charges are on the account?'],
            ],
        ]);
    }
}
