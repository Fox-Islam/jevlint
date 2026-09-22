<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Lint\StaticLinter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Report;
use Phox\JevLint\Report\Severity;
use PHPUnit\Framework\TestCase;

/**
 * The README's first command is the first thing anybody runs, and it states what
 * they will see. A count that drifts is wrong in the thirty seconds a reader
 * spends deciding whether to trust the rest
 */
final class QuickstartWorksTest extends TestCase
{
    public function test_the_quickstart_reports_what_the_readme_says_it_does(): void
    {
        $catalogue = Catalogue::load();
        $report = new Report('examples/broken-triage.json', $catalogue->version);

        (new StaticLinter($catalogue, 20000))->run(
            Query::fromFile(__DIR__.'/../../examples/broken-triage.json'),
            $report,
        );

        $said = sprintf(
            'reports %s error, %s warnings and %s advisories',
            $this->word($report->count(Severity::Error)),
            $this->word($report->count(Severity::Warning)),
            $this->word($report->count(Severity::Advice)),
        );

        // The README wraps, so the sentence is compared without its line breaks.
        $readme = preg_replace('/\s+/', ' ', (string) file_get_contents(__DIR__.'/../../README.md'));

        self::assertStringContainsString(
            $said,
            (string) $readme,
            'The quickstart describes a run that no longer produces those counts.',
        );
    }

    private function word(int $n): string
    {
        return ['zero', 'one', 'two', 'three', 'four', 'five', 'six'][$n] ?? (string) $n;
    }
}
