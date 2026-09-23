<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Catalogue\Check;
use PHPUnit\Framework\TestCase;

/**
 * docs/behaviour.md states what the tool costs on itself. Most of those figures
 * come from a run and can only be checked by paying for another one, but four
 * are counted off the catalogue and the fixtures, and those drifted silently:
 * the page said five state-scoped wordings against a catalogue holding six, and
 * a self-test of 118 calls against one costing 124
 */
final class BehaviourCountsMatchTheCatalogueTest extends TestCase
{
    private const WORDS = [7 => 'seven', 18 => '18', 21 => '21', 42 => '42', 124 => '124'];

    /**
     * Each figure with the words the page sets it in, so a constant changed to
     * another number the page happens to print somewhere is still caught.
     *
     * @return iterable<string, array{int, string}>
     */
    public static function figures(): iterable
    {
        yield 'question-scoped wordings' => [self::wordings('question'), 'The %s question-scoped wordings'];
        yield 'state-scoped wordings' => [self::wordings('state'), 'The %s wordings in the state file'];
        yield 'self-test calls' => [self::selfTestCalls(), '| `self-test`, whole catalogue | %s |'];
        yield 'checks scored' => [self::scored(), '| %s checks,'];
        yield 'example sets' => [self::sets(), '%s example sets, all `ok`'];
    }

    #[\PHPUnit\Framework\Attributes\DataProvider('figures')]
    public function test_the_page_prints_the_figure_the_catalogue_holds(int $value, string $sentence): void
    {
        self::assertStringContainsString(
            sprintf($sentence, self::WORDS[$value] ?? (string) $value),
            (string) file_get_contents(__DIR__.'/../../docs/behaviour.md'),
            'docs/behaviour.md states a figure the catalogue no longer holds.',
        );
    }

    /**
     * Wordings, not checks: the dogfood files ask each way of asking
     * separately. `corpus/dogfood.py` splits them on `question` scope against
     * everything else, so the state file holds the query-scoped check too
     */
    private static function wordings(string $half): int
    {
        $total = 0;

        foreach (Catalogue::load()->all() as $check) {
            if ($check->isModel() && ($check->scope === 'question') === ($half === 'question')) {
                $total += count($check->wordings);
            }
        }

        return $total;
    }

    /** One call per example, and a set with no `fixed` example is two and not three */
    private static function selfTestCalls(): int
    {
        $calls = 0;

        foreach (self::fixtures() as $fixture) {
            $calls += isset($fixture['fixed']) ? 3 : 2;
        }

        return $calls;
    }

    private static function scored(): int
    {
        return count(array_unique(array_column(self::fixtures(), 'check')));
    }

    private static function sets(): int
    {
        return count(self::fixtures());
    }

    /**
     * @return list<array<string, mixed>>
     */
    private static function fixtures(): array
    {
        /** @var array{fixtures?: list<array<string, mixed>>} $data */
        $data = json_decode((string) file_get_contents(Catalogue::locate('fixtures.json')), true);

        return $data['fixtures'] ?? [];
    }
}
