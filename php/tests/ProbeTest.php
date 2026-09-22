<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Probe\Probe;
use Phox\JevLint\Probe\QuestionProbe;
use Phox\JevLint\Probe\Reading;
use Phox\JevLint\Query\Query;
use Phox\TypeSafe\Testing\FakeAnswers;
use Phox\TypeSafe\Testing\FakeTypeSafe;
use PHPUnit\Framework\TestCase;

final class ProbeTest extends TestCase
{
    public function test_it_measures_each_rewrite_against_the_unchanged_query(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->reply(FakeAnswers::make()->noul('refund', 0.70)->only(), times: 5);
        $fake->reply(FakeAnswers::make()->noul('refund', 0.40)->only());
        $fake->reply(FakeAnswers::make()->choice('refund', 'yes', ['yes' => 0.95, 'no' => 0.05])->only());

        $probe = (new Probe($fake->client()))->run($this->noulQuery(), repeats: 5)['refund'];

        $this->assertSame(0.70, $probe->baseline());
        $this->assertEqualsWithDelta(-0.30, $probe->delta($this->reading($probe, 'criteria-stripped')), 0.0001);
        $this->assertEqualsWithDelta(0.25, $probe->delta($this->reading($probe, 'asked-as-choice')), 0.0001);
    }

    public function test_a_query_that_never_moves_reports_the_published_noise_floor(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->reply(FakeAnswers::make()->noul('refund', 0.70)->only(), times: 6);
        $fake->reply(FakeAnswers::make()->choice('refund', 'yes', ['yes' => 0.70, 'no' => 0.30])->only());

        $probe = (new Probe($fake->client()))->run($this->noulQuery(), repeats: 5)['refund'];

        $this->assertSame(0.0, $probe->noise());
        $this->assertSame(Probe::PUBLISHED_NOISE, $probe->floor());
    }

    public function test_the_movement_is_reported_in_multiples_of_that_floor(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->reply(FakeAnswers::make()->noul('refund', 0.70)->only(), times: 5);
        $fake->reply(FakeAnswers::make()->noul('refund', 0.61)->only());
        $fake->reply(FakeAnswers::make()->choice('refund', 'yes', ['yes' => 0.70, 'no' => 0.30])->only());

        $probe = (new Probe($fake->client()))->run($this->noulQuery(), repeats: 5)['refund'];

        $this->assertEqualsWithDelta(0.09 / Probe::PUBLISHED_NOISE, $probe->ratio($this->reading($probe, 'criteria-stripped')), 0.01);
    }

    public function test_a_score_is_read_on_the_same_scale_whichever_way_the_rubric_runs(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->reply(FakeAnswers::make()->score('urgency', 1.4)->only(), times: 5);
        $fake->reply(FakeAnswers::make()->score('urgency', 0.6)->only());

        $probe = (new Probe($fake->client()))->run($this->scoreQuery(), repeats: 5)['urgency'];

        $this->assertEqualsWithDelta(0.70, $probe->baseline(), 0.0001);
        $this->assertEqualsWithDelta(0.0, $probe->delta($this->reading($probe, 'levels-reversed')), 0.0001);
    }

    public function test_a_rubric_the_model_reads_as_an_ordering_shows_up_as_movement(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->reply(FakeAnswers::make()->score('urgency', 1.4)->only(), times: 5);
        $fake->reply(FakeAnswers::make()->score('urgency', 1.4)->only());

        $probe = (new Probe($fake->client()))->run($this->scoreQuery(), repeats: 5)['urgency'];

        $this->assertEqualsWithDelta(-0.40, $probe->delta($this->reading($probe, 'levels-reversed')), 0.0001);
    }

    public function test_a_rewording_of_your_own_is_probed_like_any_other_variant(): void
    {
        $fake = FakeTypeSafe::make();
        $fake->reply(FakeAnswers::make()->noul('refund', 0.70)->only(), times: 5);
        $fake->reply(FakeAnswers::make()->noul('refund', 0.20)->only());
        $fake->reply(FakeAnswers::make()->choice('refund', 'no', ['yes' => 0.20, 'no' => 0.80])->only());
        $fake->reply(FakeAnswers::make()->noul('refund', 0.20)->only());

        $variants = Probe::rewordings(['as-a-statement' => ['refund' => 'The customer is asking for a refund.']]);
        $probe = (new Probe($fake->client()))->run($this->noulQuery(), repeats: 5, extra: $variants)['refund'];

        $this->assertEqualsWithDelta(-0.50, $probe->delta($this->reading($probe, 'as-a-statement')), 0.0001);
    }

    public function test_it_refuses_to_probe_without_state(): void
    {
        $this->expectExceptionMessage('needs state');

        (new Probe(FakeTypeSafe::make()->client()))->run(Query::fromArray([
            'questions' => ['refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?']],
        ]));
    }

    private function reading(QuestionProbe $probe, string $variant): Reading
    {
        foreach ($probe->readings as $reading) {
            if ($reading->variant === $variant) {
                return $reading;
            }
        }

        self::fail(sprintf('The probe took no reading for "%s".', $variant));
    }

    private function noulQuery(): Query
    {
        return Query::fromArray([
            'state' => ['ticket' => 'I was charged twice. Please refund the duplicate.'],
            'questions' => [
                'refund' => [
                    'type' => 'noul',
                    'instructions' => 'Does the customer ask for a refund?',
                    'criteria' => ['true' => 'They ask for money back.', 'false' => 'They do not.'],
                ],
            ],
        ]);
    }

    private function scoreQuery(): Query
    {
        return Query::fromArray([
            'state' => ['ticket' => 'I was charged twice. Please refund the duplicate.'],
            'questions' => [
                'urgency' => [
                    'type' => 'score',
                    'instructions' => 'How urgent is this ticket?',
                    'criteria' => ['Can wait until next week', 'Should be handled today', 'The customer is blocked right now'],
                ],
            ],
        ]);
    }
}
