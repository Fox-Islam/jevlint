<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Lint\ModelLinter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Finding;
use Phox\JevLint\Report\Report;
use Phox\JevLint\Report\Severity;
use Phox\TypeSafe\Testing\FakeAnswers;
use Phox\TypeSafe\Testing\FakeTypeSafe;
use PHPUnit\Framework\TestCase;

final class ModelLinterTest extends TestCase
{
    public function test_a_probability_above_the_trigger_becomes_a_finding(): void
    {
        $report = $this->lint(FakeAnswers::make()->noul('question_compound_judgment', 0.93)->only());

        $finding = $this->find($report, 'question/compound-judgment');

        $this->assertNotNull($finding);
        $this->assertSame(0.93, $finding->probability);
        $this->assertSame('refund', $finding->target);

        // From the catalogue, not a literal: a severity re-ranked on evidence is
        // a change to the catalogue and should not be a failing test.
        $check = Catalogue::load()->find('question/compound-judgment');
        $this->assertNotNull($check);
        $this->assertSame(Severity::fromName($check->severity), $finding->severity);
    }

    public function test_a_probability_below_the_trigger_is_not_a_finding(): void
    {
        $report = $this->lint(FakeAnswers::make()->noul('question_compound_judgment', 0.12)->only());

        $this->assertNull($this->find($report, 'question/compound-judgment'));
    }

    public function test_the_probability_that_produced_a_finding_is_reported_with_it(): void
    {
        $report = $this->lint(FakeAnswers::make()->noul('question_arithmetic', 0.88)->only());

        $this->assertTrue($this->find($report, 'question/arithmetic')?->fromModel());
    }

    public function test_the_type_check_reports_the_primitive_it_would_have_picked(): void
    {
        $report = $this->lint(
            FakeAnswers::make()
                ->choice('question_type_mismatch', 'score', ['score' => 0.9, 'noul' => 0.05, 'choice' => 0.05])
                ->only(),
        );

        $finding = $this->find($report, 'question/type-mismatch');

        $this->assertNotNull($finding);
        $this->assertStringContainsString('`score`', $finding->message);
    }

    public function test_the_type_check_stays_quiet_when_it_agrees(): void
    {
        $report = $this->lint(
            FakeAnswers::make()
                ->choice('question_type_mismatch', 'noul', ['noul' => 0.9, 'score' => 0.05, 'choice' => 0.05])
                ->only(),
        );

        $this->assertNull($this->find($report, 'question/type-mismatch'));
    }

    public function test_every_check_for_one_question_goes_in_one_call(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->alwaysReply(FakeAnswers::make()->noul('question_arithmetic', 0.1)->only());

        $this->lintWith($fake, $this->query());

        // One call for the question itself, one for the state in front of it,
        // and one for the checks that read the state alone.
        $this->assertSame(3, $fake->callCount());
    }

    public function test_the_state_checks_are_skipped_when_there_is_no_state(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->alwaysReply(FakeAnswers::make()->noul('question_arithmetic', 0.1)->only());

        $this->lintWith($fake, Query::fromArray([
            'questions' => ['refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?']],
        ]));

        $this->assertSame(1, $fake->callCount());
    }

    public function test_a_state_field_is_asked_about_by_name(): void
    {
        $report = $this->lint(FakeAnswers::make()->noul('state_irrelevant_field__routing_2ecdn_5fpop', 0.95)->only());

        $finding = $this->find($report, 'state/irrelevant-field');

        $this->assertNotNull($finding);
        $this->assertStringContainsString('routing.cdn_pop', $finding->title);
        $this->assertStringContainsString('routing.cdn_pop', $finding->message);
    }

    public function test_a_field_no_question_needs_is_reported_once_for_the_whole_query(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->alwaysReply(FakeAnswers::make()->noul('state_irrelevant_field__routing_2ecdn_5fpop', 0.95)->only());

        $report = $this->lintWith($fake, Query::fromArray([
            'state' => ['ticket' => 'I was charged twice.', 'routing' => ['cdn_pop' => 'lhr-3']],
            'questions' => [
                'refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?'],
                'blocked' => ['type' => 'noul', 'instructions' => 'Does the customer say they cannot carry on?'],
                'angry' => ['type' => 'noul', 'instructions' => 'Is the customer angry?'],
            ],
        ]));

        $found = array_filter(
            $report->findings(),
            static fn (Finding $finding): bool => $finding->checkId === 'state/irrelevant-field',
        );

        $this->assertCount(1, $found, 'A field is asked about once per question and should be reported once.');

        $finding = array_values($found)[0];

        $this->assertSame('state', $finding->target);
        $this->assertStringContainsString('None of refund, blocked, angry reads `routing.cdn_pop`', $finding->evidence ?? '');
    }

    public function test_every_model_finding_says_it_came_from_a_model(): void
    {
        $report = $this->lint(
            FakeAnswers::make()
                ->noul('question_arithmetic', 0.95)
                ->noul('state_irrelevant_field__routing_2ecdn_5fpop', 0.95)
                ->choice('question_type_mismatch', 'score', ['score' => 0.95, 'noul' => 0.02, 'choice' => 0.02, 'other' => 0.01])
                ->only(),
        );

        $checks = array_map(static fn (Finding $f): string => $f->checkId, $report->findings());
        $this->assertContains('state/irrelevant-field', $checks, 'the state-field path is not being exercised');

        $this->assertNotSame([], $report->findings());

        foreach ($report->findings() as $finding) {
            $this->assertSame('model', $finding->mode, $finding->checkId.' does not report its mode');
            $this->assertNotSame('', $finding->path, $finding->checkId.' does not report where it points');
            $this->assertNotNull($finding->trigger, $finding->checkId.' does not report its trigger');
        }
    }

    public function test_a_field_one_question_still_reads_is_not_reported_as_unread(): void
    {
        $fake = FakeTypeSafe::make();
        // The field is beside the point of two questions and needed by the third
        $fake->reply(FakeAnswers::make()->noul('state_irrelevant_field__ticket', 0.95)->only(), times: 2);
        $fake->reply(FakeAnswers::make()->noul('state_irrelevant_field__ticket', 0.95)->only(), times: 2);
        $fake->alwaysReply(FakeAnswers::make()->noul('state_irrelevant_field__ticket', 0.05)->only());

        $report = $this->lintWith($fake, Query::fromArray([
            'state' => ['ticket' => 'I was charged twice.'],
            'questions' => [
                'refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?'],
                'blocked' => ['type' => 'noul', 'instructions' => 'Does the customer say they cannot carry on?'],
                'angry' => ['type' => 'noul', 'instructions' => 'Is the customer angry?'],
            ],
        ]));

        $found = array_filter(
            $report->findings(),
            static fn (Finding $finding): bool => $finding->checkId === 'state/irrelevant-field',
        );

        $this->assertSame([], $found, 'A field one question reads is not a field no question reads.');
    }

    public function test_a_criteria_finding_points_at_the_level_that_caused_it(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->alwaysReply(
            FakeAnswers::make()
                ->noul('score_multi_dimension', 0.95)
                ->choice('score_multi_dimension__where', 'level_1', ['level_0' => 0.05, 'level_1' => 0.90, 'level_2' => 0.05])
                ->only(),
        );

        $report = $this->lintWith($fake, Query::fromArray([
            'questions' => ['risk' => [
                'type' => 'score',
                'instructions' => 'How risky is this change?',
                'criteria' => ['Easy to revert', 'Touches shared code and the author is new', 'Cannot be reverted'],
            ]],
        ]));

        $found = null;

        foreach ($report->findings() as $finding) {
            if ($finding->checkId === 'score/multi-dimension') {
                $found = $finding;
            }
        }

        $this->assertNotNull($found);
        $this->assertSame('/questions/risk/criteria/1', $found->path, 'the finding points at the container, not the level');
        $this->assertStringContainsString('Touches shared code', $found->evidence ?? '');
    }

    public function test_a_choice_with_a_catch_all_is_not_reported_as_a_score(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->alwaysReply(
            FakeAnswers::make()
                ->choice('question_type_mismatch', 'score', ['score' => 0.97, 'choice' => 0.01, 'noul' => 0.01, 'other' => 0.01])
                ->only(),
        );

        $report = $this->lintWith($fake, Query::fromArray([
            'questions' => ['lifetime' => [
                'type' => 'choice',
                'instructions' => 'How long does the reset token stay valid?',
                'criteria' => [
                    'under_15_minutes' => 'Under fifteen minutes',
                    'over_60_minutes' => 'More than an hour',
                    'not_stated' => 'The report does not say',
                ],
            ]],
        ]));

        $checks = array_map(static fn (Finding $f): string => $f->checkId, $report->findings());

        $this->assertNotContains(
            'question/type-mismatch',
            $checks,
            'a catch-all option cannot sit on an ordered scale, so this is a Choice',
        );
    }

    public function test_a_reading_on_the_trigger_is_asked_again(): void
    {
        $fake = FakeTypeSafe::make();
        // 0.72 sits within 0.05 of the 0.70 trigger, so the check is re-asked.
        $fake->reply(FakeAnswers::make()->noul('question_compound_judgment', 0.72)->only());
        $fake->alwaysReply(FakeAnswers::make()->noul('question_compound_judgment', 0.74)->only());

        $report = $this->lintWith($fake, $this->noStateQuery());

        $this->assertSame(2, $fake->callCount(), 'a borderline reading was not settled with a second call');
    }

    public function test_readings_that_straddle_the_trigger_cannot_decide(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->reply(FakeAnswers::make()->noul('question_compound_judgment', 0.72)->only());
        $fake->alwaysReply(FakeAnswers::make()->noul('question_compound_judgment', 0.66)->only());

        $report = $this->lintWith($fake, $this->noStateQuery());
        $unstable = array_map(static fn (Finding $f): string => $f->checkId, $report->unstable());

        $this->assertContains('question/compound-judgment', $unstable);
    }

    public function test_readings_on_one_side_of_the_trigger_decide(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->reply(FakeAnswers::make()->noul('question_compound_judgment', 0.72)->only());
        $fake->alwaysReply(FakeAnswers::make()->noul('question_compound_judgment', 0.80)->only());

        $report = $this->lintWith($fake, $this->noStateQuery());

        $this->assertSame([], $report->unstable());
        $this->assertNotSame([], $report->findings());
    }

    private function noStateQuery(): Query
    {
        return Query::fromArray([
            'questions' => ['refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?']],
        ]);
    }

    public function test_a_failed_call_is_reported_rather_than_thrown(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->fail(429, ['error' => ['message' => 'slow down']], times: 3);

        $report = $this->lintWith($fake, $this->query());

        $this->assertSame([], $report->findings());
        $this->assertNotSame([], $report->notes());
    }

    private function lint(FakeAnswers $answers): Report
    {
        $fake = FakeTypeSafe::make();
        $fake->alwaysReply($answers);

        return $this->lintWith($fake, $this->query());
    }

    /**
     * The re-ask has to show the check the same material the first call did.
     * A state-scoped check reads `question` and `state`; rebuilding the follow-up
     * from the question alone showed it `instructions` and `criteria`, so it
     * answered about a state it had never been given and that answer was
     * averaged into the reported probability.
     */
    public function test_a_borderline_state_check_is_asked_again_against_the_same_state(): void
    {
        $fake = FakeTypeSafe::make();
        // 0.62 sits within 0.05 of state/answer-absent's 0.60 trigger.
        $fake->reply(FakeAnswers::make()->noul('state_answer_absent__w0', 0.62)->only());
        $fake->alwaysReply(FakeAnswers::make()->noul('state_answer_absent__w0', 0.64)->only());

        $this->lintWith($fake, $this->query());

        $shown = [];

        foreach ($fake->systemOneCalls() as $call) {
            $body = $call->body();
            $asked = is_array($body['questions'] ?? null) ? array_keys($body['questions']) : [];

            if (! in_array('state_answer_absent__w0', $asked, true)) {
                continue;
            }

            $state = $call->state();
            $shown[] = is_array($state) ? array_keys($state) : [];
        }

        self::assertGreaterThanOrEqual(2, count($shown), 'the borderline state check was not re-asked');

        foreach ($shown as $keys) {
            self::assertContains('question', $keys, 'a call showed the state check a state with no `question` in it');
            self::assertContains('state', $keys, 'a call showed the state check a state with no `state` in it');
        }
    }

    private function lintWith(FakeTypeSafe $fake, Query $query): Report
    {
        $catalogue = Catalogue::load();
        $report = new Report('test', $catalogue->version);

        (new ModelLinter($catalogue, $fake->client()))->run($query, $report);

        return $report;
    }

    private function query(): Query
    {
        return Query::fromArray([
            'state' => [
                'ticket' => 'I was charged twice for order A-104. Please refund the duplicate.',
                'routing' => ['cdn_pop' => 'lhr-3'],
            ],
            'questions' => [
                'refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?'],
            ],
        ]);
    }

    private function find(Report $report, string $checkId): ?Finding
    {
        foreach ($report->findings() as $finding) {
            if ($finding->checkId === $checkId) {
                return $finding;
            }
        }

        return null;
    }
}
