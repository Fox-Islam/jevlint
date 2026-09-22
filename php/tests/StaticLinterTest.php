<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Lint\StaticLinter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Finding;
use Phox\JevLint\Report\Report;
use PHPUnit\Framework\TestCase;

final class StaticLinterTest extends TestCase
{
    public function test_a_well_formed_query_reports_nothing(): void
    {
        $this->assertSame([], $this->check([
            'state' => ['ticket' => 'I was charged twice. Please refund the duplicate.'],
            'questions' => [
                'refund_requested' => [
                    'type' => 'noul',
                    'instructions' => 'Does the customer ask for a refund?',
                    'criteria' => ['true' => 'They ask for money back.', 'false' => 'They do not.'],
                ],
            ],
        ]));
    }

    public function test_it_catches_the_shapes_the_api_rejects(): void
    {
        $this->assertContains('choice/criteria-shape', $this->check([
            'state' => 'a ticket',
            'questions' => ['category' => ['type' => 'choice', 'instructions' => 'What is this ticket about?', 'criteria' => ['billing', 'technical']]],
        ]));

        $this->assertContains('score/criteria-shape', $this->check([
            'state' => 'a ticket',
            'questions' => ['urgency' => ['type' => 'score', 'instructions' => 'How urgent is this ticket?', 'criteria' => ['low' => 'Can wait', 'high' => 'Now']]],
        ]));
    }

    public function test_it_catches_a_rubric_made_of_numbers(): void
    {
        $this->assertContains('score/numeric-levels', $this->check([
            'state' => 'a ticket',
            'questions' => ['severity' => ['type' => 'score', 'instructions' => 'Rate severity from 0 to 2', 'criteria' => ['0', '1', '2']]],
        ]));
    }

    public function test_a_described_rubric_is_left_alone(): void
    {
        $this->assertNotContains('score/numeric-levels', $this->check([
            'state' => 'a ticket',
            'questions' => ['severity' => [
                'type' => 'score',
                'instructions' => 'How severe is this bug report?',
                'criteria' => ['Nobody is affected', 'A workaround exists', 'The work has stopped'],
            ]],
        ]));
    }

    public function test_it_catches_an_instruction_that_only_repeats_the_id(): void
    {
        $this->assertContains('question/instruction-is-id', $this->check([
            'state' => 'a ticket',
            'questions' => ['refund_requested' => ['type' => 'noul', 'instructions' => 'Refund requested?']],
        ]));
    }

    public function test_a_short_whole_question_is_not_an_id_in_disguise(): void
    {
        // Four words, contains the id, and a complete question. The rule fires on
        // an instruction that adds nothing to the id, not on a short one.
        $this->assertNotContains('question/instruction-is-id', $this->check([
            'state' => 'a ticket',
            'questions' => ['blocked' => ['type' => 'noul', 'instructions' => 'Is the customer blocked?']],
        ]));
    }

    public function test_it_leaves_a_full_question_alone(): void
    {
        $this->assertNotContains('question/instruction-is-id', $this->check([
            'state' => 'a ticket',
            'questions' => ['refund_requested' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?']],
        ]));
    }

    public function test_it_catches_noul_criteria_that_are_not_true_and_false(): void
    {
        $this->assertContains('noul/criteria-shape', $this->check([
            'state' => 'a ticket',
            'questions' => ['refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?', 'criteria' => ['yes' => 'They do', 'no' => 'They do not']]],
        ]));
    }

    public function test_it_notices_a_choice_with_nowhere_to_put_the_rest(): void
    {
        $findings = $this->check([
            'state' => 'a ticket',
            'questions' => ['category' => ['type' => 'choice', 'instructions' => 'What is this ticket about?', 'criteria' => ['billing' => 'Money', 'technical' => 'Broken things']]],
        ]);

        $this->assertContains('choice/no-fallback', $findings);
    }

    public function test_it_notices_two_questions_that_ask_the_same_thing(): void
    {
        $this->assertContains('query/duplicate-instructions', $this->check([
            'state' => 'a ticket',
            'questions' => [
                'refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?'],
                'wants_money_back' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?'],
            ],
        ]));
    }

    public function test_it_says_when_there_is_no_state_to_check_against(): void
    {
        $this->assertContains('state/missing', $this->check([
            'questions' => ['refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?']],
        ]));
    }

    public function test_it_says_when_the_state_is_large(): void
    {
        $this->assertContains('state/oversized', $this->check([
            'state' => ['log' => str_repeat('nothing to do with the question. ', 800)],
            'questions' => ['refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?']],
        ]));
    }

    /**
     * @param  array<string, mixed> $query
     * @return list<string>
     */
    private function check(array $query): array
    {
        $catalogue = Catalogue::load();
        $report = new Report('test', $catalogue->version);

        (new StaticLinter($catalogue))->run(Query::fromArray($query), $report);

        return array_map(static fn (Finding $finding): string => $finding->checkId, $report->findings());
    }
}
