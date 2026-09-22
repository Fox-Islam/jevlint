<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Catalogue\Check;
use Phox\JevLint\Lint\StaticLinter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Finding;
use Phox\JevLint\Report\Report;
use Phox\JevLint\Report\Severity;
use PHPUnit\Framework\TestCase;

/**
 * The checks are themselves Jev questions, so they have to survive the rules
 * they enforce. A linter that breaks its own rules is arguing against itself
 */
final class CatalogueLintsCleanTest extends TestCase
{
    public function test_the_checks_pass_their_own_static_rules(): void
    {
        $catalogue = Catalogue::load();
        $questions = [];

        foreach ($catalogue->all() as $check) {
            if (! $check->isModel()) {
                continue;
            }

            $questions[$check->answerKey()] = array_filter([
                'type' => $check->questionType(),
                'instructions' => $check->instructions('a_field'),
                'criteria' => $check->criteria(),
            ], static fn (mixed $value): bool => $value !== null);
        }

        $report = new Report('catalogue', $catalogue->version);

        (new StaticLinter($catalogue))->run(
            Query::fromArray(['state' => ['question' => 'a question under review'], 'questions' => $questions]),
            $report,
        );

        $serious = array_filter(
            $report->findings(),
            static fn (Finding $finding): bool => $finding->severity->atLeast(Severity::Warning),
        );

        $this->assertSame([], array_map(
            static fn (Finding $finding): string => $finding->target.': '.$finding->checkId,
            array_values($serious),
        ));
    }

    public function test_every_noul_check_says_what_a_yes_means(): void
    {
        foreach (Catalogue::load()->written() as $check) {
            if (! $check->isModel() || $check->questionType() !== 'noul') {
                continue;
            }

            $criteria = $check->criteria() ?? [];
            $true = is_string($criteria['true'] ?? null) ? $criteria['true'] : '';

            $this->assertNotSame('', $true, $check->id.' does not say what a yes means');
        }
    }

    public function test_a_check_that_needs_criteria_says_so(): void
    {
        $contradiction = Catalogue::load()->find('question/criteria-contradiction');

        $this->assertInstanceOf(Check::class, $contradiction);
        $this->assertSame('criteria', $contradiction->requires);
    }
}
