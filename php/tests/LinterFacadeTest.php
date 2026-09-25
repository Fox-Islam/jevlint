<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\Lint\Linter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Report;
use Phox\JevLint\Report\Severity;
use Phox\TypeSafe\Testing\FakeAnswers;
use Phox\TypeSafe\Testing\FakeTypeSafe;
use PHPUnit\Framework\TestCase;

/** The documented library entry point, which the console commands also go through */
final class LinterFacadeTest extends TestCase
{
    public function test_the_rules_run_without_a_client(): void
    {
        $report = Linter::rulesOnly()->check($this->broken());

        $this->assertGreaterThan(0, $report->count(Severity::Error));
        $this->assertSame(0, $report->calls());
        $this->assertTrue($report->isComplete());
    }

    public function test_a_run_that_makes_no_calls_says_the_model_checks_did_not_run(): void
    {
        $report = Linter::rulesOnly()->check($this->broken());
        $model = count(array_filter(Catalogue::load()->all(), static fn ($c): bool => $c->isModel()));

        $this->assertSame(
            [$model],
            array_map(static fn ($note): ?int => $note->checks, $report->skippedNotes()),
        );
    }

    public function test_both_linters_run_and_the_report_stamps_the_catalogue(): void
    {
        $catalogue = Catalogue::load();
        $report = $this->linter(FakeAnswers::make()->noul('question_compound_judgment', 0.93)->only())
            ->check($this->query());

        $this->assertSame($catalogue->version, $report->catalogueVersion);
        $this->assertSame($catalogue->fingerprint, $report->fingerprint);
        $this->assertSame($catalogue->asked, $report->questionPrint);
        $this->assertSame($catalogue->model, $report->model);
        $this->assertContains('question/compound-judgment', $this->ids($report));
    }

    public function test_the_report_names_the_query_it_was_given(): void
    {
        $report = Linter::rulesOnly()->check(Query::fromArray($this->body(), 'inline.json'));

        $this->assertSame('inline.json', $report->source);
    }

    public function test_a_narrowing_runs_only_what_it_names(): void
    {
        $report = Linter::rulesOnly()->only(['choice/no-fallback'])->check($this->broken());

        $this->assertSame(['choice/no-fallback'], array_unique($this->ids($report)));
    }

    /**
     * A narrowing to an id the catalogue does not hold runs nothing, and a report
     * of nothing reads exactly like a clean one
     */
    public function test_a_narrowing_to_a_check_that_does_not_exist_is_refused(): void
    {
        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('There is no check called made/up');

        Linter::rulesOnly()->only(['made/up']);
    }

    public function test_the_version_a_run_uses_can_be_pinned(): void
    {
        $catalogue = Catalogue::load();
        $oldest = $catalogue->versions[0];

        $this->assertSame('jev-'.$oldest, Linter::rulesOnly()->forJev($oldest)->catalogue()->model);
    }

    public function test_narrowing_the_query_is_reported_as_a_narrowing(): void
    {
        $whole = $this->broken();
        $report = Linter::rulesOnly()->check($whole->only([$whole->questions[0]->id]), $whole);

        $this->assertNotSame([], array_filter(
            $report->skippedNotes(),
            static fn ($note): bool => str_contains($note->message, 'unchecked'),
        ));
    }

    public function test_a_lone_question_is_not_asked_whether_it_depends_on_a_sibling(): void
    {
        $report = $this->linter(FakeAnswers::make()->noul('question_refers_to_sibling', 0.95))
            ->only(['question/refers-to-sibling'])
            ->check($this->query());

        $this->assertSame([], $this->ids($report));
        $this->assertSame(0, $report->calls());
    }

    public function test_a_question_is_asked_about_a_sibling_the_narrowing_left_out(): void
    {
        $body = $this->body();
        $body['questions']['urgent'] = ['type' => 'noul', 'instructions' => 'Given the refund answer, is this urgent?'];
        $whole = Query::fromArray($body);
        $report = $this->linter(FakeAnswers::make()->noul('question_refers_to_sibling', 0.95))
            ->only(['question/refers-to-sibling'])
            ->check($whole->only(['urgent']), $whole);

        $this->assertSame(['question/refers-to-sibling'], $this->ids($report));
    }

    public function test_a_finding_its_clearing_question_does_not_set_aside_is_reported(): void
    {
        $report = $this->linter(FakeAnswers::make()
            ->noul('choice_undetermined_outcome', 0.95)
            ->noul('choice_undetermined_outcome__clear', 0.05)
            ->only())
            ->only(['choice/undetermined-outcome'])
            ->check($this->draw());

        $this->assertSame(['choice/undetermined-outcome'], $this->ids($report));
    }

    public function test_a_finding_is_set_aside_where_its_clearing_question_reads_above_its_trigger(): void
    {
        $report = $this->linter(FakeAnswers::make()
            ->noul('choice_undetermined_outcome', 0.95)
            ->noul('choice_undetermined_outcome__clear', 0.9)
            ->only())
            ->only(['choice/undetermined-outcome'])
            ->reportingCleared()
            ->check($this->draw());

        $this->assertSame([], $this->ids($report));
        $this->assertSame(['choice/undetermined-outcome'], array_map(static fn ($f): string => $f->checkId, $report->cleared()));
        $this->assertStringContainsString('clearing question read 0.90', $report->cleared()[0]->clearedBecause);
    }

    public function test_a_finding_is_raised_where_its_second_question_reads_above_its_trigger(): void
    {
        $report = $this->linter(FakeAnswers::make()
            ->noul('question_arithmetic', 0.1)
            ->noul('question_arithmetic__fire', 0.9)
            ->noul('question_arithmetic__clear', 0.05)
            ->only())
            ->only(['question/arithmetic'])
            ->check($this->query());

        $this->assertSame(['question/arithmetic'], $this->ids($report));
        $this->assertSame(0.9, $report->findings()[0]->probability);
        $this->assertSame(0.5, $report->findings()[0]->trigger);
        $this->assertStringContainsString('own question read 0.10 against its 0.60 trigger', (string) $report->findings()[0]->evidence);
    }

    public function test_nothing_is_raised_where_neither_question_reads_above_its_trigger(): void
    {
        $report = $this->linter(FakeAnswers::make()
            ->noul('question_arithmetic', 0.1)
            ->noul('question_arithmetic__fire', 0.3)
            ->noul('question_arithmetic__clear', 0.05)
            ->only())
            ->only(['question/arithmetic'])
            ->check($this->query());

        $this->assertSame([], $this->ids($report));
    }

    private function draw(): Query
    {
        return Query::fromArray([
            'state' => 'A die was rolled inside a closed box and nobody has looked.',
            'questions' => [
                'face' => [
                    'type' => 'choice',
                    'instructions' => 'Which face came up?',
                    'criteria' => ['low' => 'One to three', 'high' => 'Four to six'],
                ],
            ],
        ]);
    }

    /** @return list<string> */
    private function ids(Report $report): array
    {
        return array_map(static fn ($finding): string => $finding->checkId, $report->findings());
    }

    private function linter(FakeAnswers $answers): Linter
    {
        $fake = FakeTypeSafe::make();
        $fake->alwaysReply($answers);

        return Linter::make($fake->client());
    }

    /** @return array<string, mixed> */
    private function body(): array
    {
        return [
            'state' => ['ticket' => 'I was charged twice for order A-104. Please refund the duplicate.'],
            'questions' => [
                'refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?'],
            ],
        ];
    }

    private function query(): Query
    {
        return Query::fromArray($this->body());
    }

    private function broken(): Query
    {
        return Query::fromFile(dirname(__DIR__, 2).'/examples/broken-triage.json');
    }
}
