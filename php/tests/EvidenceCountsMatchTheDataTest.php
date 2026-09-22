<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use PHPUnit\Framework\TestCase;

/**
 * docs/evidence.md counts the model checks and how many have a labelled defect
 * to catch. Both are claims about files beside it, and a check added or a gold
 * entry relabelled moves them without touching the prose
 */
final class EvidenceCountsMatchTheDataTest extends TestCase
{
    public function test_the_counts_the_evidence_quotes_are_the_counts_in_the_catalogue_and_the_gold_set(): void
    {
        $model = array_values(array_filter(
            Catalogue::load()->written(),
            static fn ($check): bool => $check->isModel(),
        ));

        /** @var array<string, array{defects?: list<string>}> $gold */
        $gold = json_decode((string) file_get_contents(__DIR__.'/../../corpus/gold.json'), true);
        $named = [];

        foreach ($gold as $entry) {
            foreach ($entry['defects'] ?? [] as $defect) {
                $named[$defect] = true;
            }
        }

        $covered = array_values(array_filter(
            $model,
            static fn ($check): bool => isset($named[$check->id]),
        ));

        $words = [9 => 'nine', 11 => 'eleven', 20 => 'twenty'];
        $evidence = (string) file_get_contents(__DIR__.'/../../docs/evidence.md');

        self::assertStringContainsString(
            sprintf(
                'readings for all %s model checks, and a labelled defect to catch for %s of them; the other %s',
                $words[count($model)] ?? count($model),
                $words[count($covered)] ?? count($covered),
                $words[count($model) - count($covered)] ?? count($model) - count($covered),
            ),
            preg_replace('/\s+/', ' ', $evidence) ?? '',
        );

        self::assertStringContainsString(
            sprintf('%s model checks have no gold negative', ucfirst($words[count($model) - count($covered)] ?? '')),
            $evidence,
        );
    }
}
