<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use PHPUnit\Framework\TestCase;

/**
 * The README groups the checks by the failure mode they are written against, and
 * the catalogue carries the same grouping as `jaggedness`. The table is written
 * by hand, so nothing but this stops the two describing different catalogues
 */
final class JaggednessMatchesDocumentationTest extends TestCase
{
    public function test_every_check_the_readme_files_under_a_failure_mode_names_it_in_the_catalogue(): void
    {
        $catalogue = [];

        foreach (Catalogue::load()->written() as $check) {
            foreach ($check->jaggedness as $mode) {
                $catalogue[$mode][] = $check->id;
            }
        }

        self::assertNotSame([], $catalogue, 'No check carries a jaggedness, so this test pins nothing.');

        $rows = $this->rows();
        self::assertNotSame([], $rows, 'The README stopped listing failure modes, so this test pins nothing.');

        $wrong = [];

        foreach ($rows as $anchor => $ids) {
            $mode = $this->modeFor($anchor, array_keys($catalogue));

            if ($mode === null) {
                $wrong[] = sprintf('the README links to #%s, which no check names', $anchor);

                continue;
            }

            foreach (array_diff($ids, $catalogue[$mode]) as $id) {
                $wrong[] = sprintf('the README files %s under #%s and the catalogue does not', $id, $anchor);
            }
        }

        self::assertSame([], $wrong, implode("\n", $wrong));
    }

    /**
     * The anchors are longer than the values, so `#date-and-time-comparison` is
     * the mode `date-and-time`.
     *
     * @param list<string> $modes
     */
    private function modeFor(string $anchor, array $modes): ?string
    {
        foreach ($modes as $mode) {
            if (str_starts_with($anchor, $mode)) {
                return $mode;
            }
        }

        return null;
    }

    /**
     * The failure-mode rows of the README's table, as anchor to check ids. Only
     * the model-jaggedness ones: the other rows link to guidance pages that the
     * `jaggedness` field does not cover.
     *
     * @return array<string, list<string>>
     */
    private function rows(): array
    {
        $readme = (string) file_get_contents(__DIR__.'/../../README.md');

        preg_match_all(
            '/^\| \[[^\]]+\]\([^)]*model-jaggedness[^#)]*#([a-z-]+)\) \| (.+) \|$/m',
            $readme,
            $matches,
            PREG_SET_ORDER,
        );

        $rows = [];

        foreach ($matches as $match) {
            $rows[$match[1]] = array_map(
                static fn (string $id): string => trim($id, " \t`"),
                explode(',', $match[2]),
            );
        }

        return $rows;
    }
}
