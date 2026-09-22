<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Report\Report;
use PHPUnit\Framework\TestCase;

/**
 * A check that goes into a call and produces nothing leaves a report that reads
 * as clean and complete. The reconciliation compares what was asked against what
 * came back, so a path that loses a check is caught wherever it is
 */
final class EveryCheckIsAccountedForTest extends TestCase
{
    public function test_a_check_that_reaches_no_verdict_makes_the_run_incomplete(): void
    {
        $report = new Report('test', '1');
        $report->expecting('question/arithmetic', 'refund');
        $report->expecting('question/generation', 'refund');
        $report->reached('question/arithmetic', 'refund');

        $report->reconcile();

        self::assertFalse($report->isComplete());
        self::assertStringContainsString('question/generation', $report->unreachableNotes()[0]->message);
    }

    public function test_a_run_where_every_check_reached_a_verdict_is_complete(): void
    {
        $report = new Report('test', '1');
        $report->expecting('question/arithmetic', 'refund');
        $report->reached('question/arithmetic', 'refund');

        $report->reconcile();

        self::assertTrue($report->isComplete());
        self::assertSame([], $report->unreachableNotes());
    }

    public function test_a_target_that_already_reported_a_loss_is_not_reported_twice(): void
    {
        $report = new Report('test', '1');
        $report->expecting('question/arithmetic', 'refund');
        $report->expecting('question/generation', 'refund');
        $report->unreachable('refund', 'the call failed');

        $report->reconcile();

        self::assertCount(1, $report->unreachableNotes(), 'One failed call should report one loss, not one per check as well.');
    }
}
