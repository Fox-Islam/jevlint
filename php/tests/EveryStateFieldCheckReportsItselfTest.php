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
 * A state-field check is asked once per field, and the readings are held by
 * field so one finding can speak for every question. Held by field alone, a
 * second such check overwrites the first's readings and is reported under the
 * first's id, which is a wrong answer wearing a check's name
 */
final class EveryStateFieldCheckReportsItselfTest extends TestCase
{
    public function test_a_second_state_field_check_reports_under_its_own_id(): void
    {
        $path = tempnam(sys_get_temp_dir(), 'catalogue').'.json';
        $catalogue = json_decode((string) file_get_contents(__DIR__.'/../../checks/catalogue.json'), true);
        self::assertIsArray($catalogue);

        $first = null;

        foreach ($catalogue['checks'] as $check) {
            if (($check['id'] ?? '') === 'state/irrelevant-field') {
                $first = $check;
            }
        }

        self::assertIsArray($first, 'the catalogue no longer ships a state-field check to copy');

        $second = $first;
        $second['id'] = 'state/second-opinion';
        $second['trigger'] = 0.7;
        $catalogue['checks'][] = $second;

        file_put_contents($path, json_encode($catalogue, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));

        $fake = FakeTypeSafe::make();
        $fake->alwaysReply(FakeAnswers::make()
            ->noul('state_irrelevant_field__ticket', 0.95)
            ->noul('state_second_opinion__ticket', 0.80)
            ->only());

        $loaded = Catalogue::load($path);
        $report = new Report('test', $loaded->version);
        (new ModelLinter($loaded, $fake->client()))->run(Query::fromArray([
            'state' => ['ticket' => 'I was charged twice.'],
            'questions' => ['refund' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?']],
        ]), $report);

        unlink($path);

        $read = [];

        foreach ($report->findings() as $finding) {
            $read[$finding->checkId] = $finding->probability;
        }

        self::assertSame(0.95, $read['state/irrelevant-field'] ?? null);
        self::assertSame(0.80, $read['state/second-opinion'] ?? null);
    }
}
