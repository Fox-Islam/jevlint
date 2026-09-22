<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Lint\StaticLinter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Report;
use PHPUnit\Framework\TestCase;

/**
 * A static rule is dispatched by primitive in code, so `applies_to` describes
 * that dispatch instead of constraining it. Editing the field changes nothing,
 * which means the two can drift apart in silence and the catalogue ends up
 * describing a tool that does something else
 */
final class StaticChecksApplyWhereTheySayTest extends TestCase
{
    public function test_no_static_check_fires_on_a_primitive_it_says_it_does_not_cover(): void
    {
        $catalogue = Catalogue::load();
        $wrong = [];

        foreach (['noul', 'choice', 'score'] as $type) {
            $report = new Report('t', $catalogue->version, $catalogue->jev, $catalogue->fingerprint, $catalogue->asked, null);

            (new StaticLinter($catalogue, 20000))->run($this->everythingWrong($type), $report);

            // Without this the whole test passes on a query that trips nothing,
            // which is how its first version reported clean.
            self::assertNotSame([], $report->findings(), sprintf(
                'The %s fixture trips no static rule, so it cannot show one firing on the wrong primitive.',
                $type,
            ));

            foreach ($report->findings() as $finding) {
                $check = $catalogue->find($finding->checkId);

                if ($check === null || $finding->target !== 'q') {
                    continue;
                }

                if (! $check->covers($type)) {
                    $wrong[] = sprintf('%s fired on a %s and says it covers %s', $check->id, $type, implode(', ', $check->appliesTo));
                }
            }
        }

        self::assertSame([], $wrong, implode("\n", $wrong));
    }

    /**
     * One question of the given primitive, written to trip as many rules as it
     * can, so a check that covers the wrong primitive has something to fire on.
     */
    private function everythingWrong(string $type): Query
    {
        // Each primitive takes its criteria in its own shape, so one shape for
        // all three trips the shape rule and nothing past it.
        $criteria = match ($type) {
            // No criteria at all on the Noul, numeric levels on the Score, and
            // two options meaning the same thing on the Choice: one rule each
            // that only its own primitive's branch raises.
            'noul' => null,
            'choice' => ['billing' => 'Money things', 'payments' => 'Anything to do with money'],
            default => ['0', '1', '2'],
        };

        return Query::fromArray([
            'state' => ['ticket' => 'I was charged twice and want it back.'],
            'questions' => [
                'q' => [
                    'type' => $type,
                    'instructions' => 'Levels: 0, 1, 2. Is this not un-urgent, and how bad is it?',
                    ...($criteria === null ? [] : ['criteria' => $criteria]),
                ],
            ],
        ], 't');
    }
}
