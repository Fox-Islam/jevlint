<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Catalogue\Check;
use PHPUnit\Framework\TestCase;

/**
 * The README names checks by id, and a renamed check would leave the name behind
 * as a pointer to nothing. This fails when they disagree
 */
final class DocumentationMatchesCatalogueTest extends TestCase
{
    public function test_every_jev_version_the_readme_writes_out_is_one_the_catalogue_covers(): void
    {
        $readme = (string) file_get_contents(__DIR__.'/../../README.md');

        // `--jev=1.13` in a sample and `"jev": "1.13"` in the config block are
        // both instructions somebody will paste, and a version the catalogue
        // stops covering turns them into a run that exits 2.
        preg_match_all('/--jev=([0-9.]+)|"jev": "([0-9.]+)"/', $readme, $matches, PREG_SET_ORDER);

        $named = [];

        foreach ($matches as $match) {
            $version = ($match[2] ?? '') !== '' ? $match[2] : ($match[1] ?? '');

            if ($version !== '') {
                $named[] = $version;
            }
        }

        $named = array_values(array_unique($named));
        $covered = Catalogue::load()->versions;

        self::assertNotSame([], $named, 'The README stopped naming a Jev version, so this pins nothing.');
        self::assertSame([], array_values(array_diff($named, $covered)), sprintf(
            'The README names Jev %s. The catalogue covers %s.',
            implode(', ', $named),
            implode(', ', $covered),
        ));
    }

    /**
     * The reverse direction. A check nobody documents still runs, still fires and
     * still has to be understood by whoever reads the finding, and the test that
     * only walks README-to-catalogue cannot fail that way.
     */
    public function test_every_model_check_is_named_in_the_readme(): void
    {
        // Outside the fenced blocks. A check named only in a pasted sample of the
        // tool's own output is not documented, and searching the whole file let
        // that satisfy this test.
        $readme = (string) preg_replace('/```.*?```/s', '', (string) file_get_contents(__DIR__.'/../../README.md'));
        $missing = [];

        foreach (Catalogue::load()->written() as $check) {
            if ($check->isModel() && ! str_contains($readme, $check->id)) {
                $missing[] = $check->id;
            }
        }

        self::assertSame([], $missing, sprintf(
            'These judgements are in the catalogue and described nowhere in the README: %s',
            implode(', ', $missing),
        ));
    }

    public function test_every_check_the_readme_names_exists(): void
    {
        $ids = array_map(static fn (Check $check): string => $check->id, Catalogue::load()->written());

        // Every page, not the README alone. Prose moved to docs/ took its check
        // names with it, and a guard that reads one file stops covering them.
        $pages = array_merge(
            [(string) file_get_contents(__DIR__.'/../../README.md')],
            array_map(
                static fn (string $path): string => (string) file_get_contents($path),
                glob(__DIR__.'/../../docs/*.md') ?: [],
            ),
        );

        // The namespaces a check id can have. A looser pattern reads a dataset
        // name such as `deepset/prompt-injections` as a check.
        preg_match_all(
            '/`((?:question|choice|score|noul|state|state-field|state-once|query)\/[a-z-]+)`/',
            implode("\n", $pages),
            $matches,
        );

        $named = array_values(array_unique($matches[1]));
        self::assertNotSame([], $named, 'The README names no checks, so this test is measuring nothing.');

        foreach ($named as $id) {
            self::assertContains($id, $ids, sprintf('The README names `%s`, which the catalogue does not hold.', $id));
        }
    }
}
