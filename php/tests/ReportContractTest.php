<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use PHPUnit\Framework\TestCase;
use Phox\JevLint\Report\Finding;
use Phox\JevLint\Report\Report;
use Phox\JevLint\Report\Severity;

/**
 * The machine-readable report is a contract, and the way it breaks is by
 * getting quieter: a false dropped by a null filter reads as a key nobody
 * wrote, and a caller cannot tell the two apart.
 */
final class ReportContractTest extends TestCase
{
    private function report(): Report
    {
        return new Report('q.json', '1', 'jev-1.13', 'abc');
    }

    private function finding(bool $fired = true, bool $near = false, bool $unstable = false): Finding
    {
        return new Finding(
            checkId: 'question/arithmetic',
            title: 'Answering needs arithmetic',
            severity: Severity::Error,
            target: 'q1',
            message: 'm',
            probability: 0.9,
            trigger: 0.7,
            nearTrigger: $near,
            fired: $fired,
            unstable: $unstable,
        );
    }

    public function test_the_schema_describes_every_key_the_report_emits(): void
    {
        // Nothing validates a produced report against the published schema, so
        // the two drift by a key at a time and the first reader to notice is a
        // consumer whose validator rejects a document the tool just wrote.
        $schema = json_decode((string) file_get_contents(__DIR__.'/../../spec/report.schema.json'), true);
        self::assertIsArray($schema);

        $report = $this->report();
        $report->add($this->finding());
        $report->add($this->finding(fired: false));
        $document = $report->toArray();

        $described = array_keys($schema['properties']);
        sort($described);
        $emitted = array_keys($document);
        sort($emitted);

        self::assertSame($described, $emitted, 'The report schema and the report disagree at the top level.');

        $summary = array_keys($schema['properties']['summary']['properties']);
        sort($summary);
        /** @var array<string, mixed> $emittedSummary */
        $emittedSummary = $document['summary'];
        $emittedSummaryKeys = array_keys($emittedSummary);
        sort($emittedSummaryKeys);

        self::assertSame($summary, $emittedSummaryKeys, 'The summary and its schema disagree.');

        /** @var list<array<string, mixed>> $findings */
        $findings = $document['findings'];
        $undescribed = array_diff(
            array_keys($findings[0]),
            array_keys($schema['$defs']['finding']['properties']),
        );

        self::assertSame([], array_values($undescribed), 'A finding carries keys the schema does not describe.');

        /** @var list<array<string, mixed>> $cleared */
        $cleared = $document['cleared'];
        $unclearedKeys = array_diff(
            array_keys($cleared[0]),
            array_keys($schema['$defs']['cleared']['properties']),
        );

        self::assertSame([], array_values($unclearedKeys), 'A cleared entry carries keys the schema does not describe.');
    }

    public function test_a_fired_finding_always_says_whether_it_was_near_its_trigger(): void
    {
        $row = $this->finding(near: false)->toArray();

        self::assertArrayHasKey('near_trigger', $row);
        self::assertFalse($row['near_trigger']);
        self::assertArrayHasKey('unstable', $row);
        self::assertTrue($row['fired']);
    }

    public function test_a_cleared_finding_says_the_same(): void
    {
        $row = $this->finding(fired: false)->toArray();

        self::assertArrayHasKey('near_trigger', $row);
        self::assertFalse($row['near_trigger']);
        self::assertFalse($row['fired']);
        self::assertArrayNotHasKey('suggest', $row, 'a cleared check must not read as advice');
    }

    public function test_a_run_that_asked_everything_says_it_is_complete(): void
    {
        $report = $this->report();

        self::assertTrue($report->isComplete());
        self::assertTrue($report->toArray()['summary']['complete']);
        self::assertSame(0, $report->toArray()['summary']['unreachable']);
    }

    public function test_a_call_that_could_not_be_made_makes_the_run_incomplete(): void
    {
        $report = $this->report();
        $report->unreachable('q1', '401 Cannot authenticate');

        self::assertFalse($report->isComplete());

        $summary = $report->toArray()['summary'];
        self::assertFalse($summary['complete']);
        self::assertSame(1, $summary['unreachable']);
    }

    public function test_every_note_carries_a_kind(): void
    {
        $report = $this->report();
        $report->note('a plain note');
        $report->unreachable('q1', 'boom');

        $kinds = array_column($report->toArray()['notes'], 'kind');

        self::assertSame(['note', 'unreachable'], $kinds);
    }

    public function test_a_finding_that_fired_is_not_also_listed_as_undecided(): void
    {
        $report = $this->report();
        $report->add($this->finding(fired: true, unstable: true));

        self::assertCount(1, $report->findings());
        self::assertSame([], $report->unstable(), 'a fired finding is reported once, as a finding');
    }

    public function test_a_check_that_could_not_decide_and_did_not_fire_is_listed_as_undecided(): void
    {
        $report = $this->report();
        $report->add($this->finding(fired: false, unstable: true));

        self::assertSame([], $report->findings());
        self::assertCount(1, $report->unstable());
    }
}
