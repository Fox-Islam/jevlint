<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use PHPUnit\Framework\TestCase;
use RecursiveDirectoryIterator;
use RecursiveIteratorIterator;
use SplFileInfo;

/**
 * A key with no pattern prints as itself, which is a run that works and prints
 * `check.no_query_file` where a sentence belongs.
 *
 * Both directions are read from the source by eye, so a key has to be a plain
 * string at the call. A key built from a variable is invisible here
 */
final class EveryMessageKeyExistsTest extends TestCase
{
    public function test_every_key_the_source_asks_for_is_in_the_english_bundle(): void
    {
        /** @var array<string, mixed> $bundle */
        $bundle = require __DIR__.'/../lang/en.php';
        $missing = [];
        $asked = 0;

        foreach ($this->sources() as $file) {
            preg_match_all(
                "/Text::(?:of|list)\(\s*'([^']+)'/",
                (string) file_get_contents($file),
                $keys,
            );

            foreach ($keys[1] as $key) {
                $asked++;

                if (! array_key_exists($key, $bundle)) {
                    $missing[] = sprintf('%s asks for %s', basename($file), $key);
                }
            }
        }

        self::assertGreaterThan(0, $asked, 'No keys found, so this test pins nothing.');
        self::assertSame([], $missing, implode("\n", $missing));
    }

    /** Patterns nothing asks for, which are a message the code stopped printing */
    public function test_the_english_bundle_holds_nothing_the_source_never_asks_for(): void
    {
        /** @var array<string, mixed> $bundle */
        $bundle = require __DIR__.'/../lang/en.php';
        $asked = [];

        foreach ($this->sources() as $file) {
            preg_match_all("/Text::(?:of|list)\(\s*'([^']+)'/", (string) file_get_contents($file), $keys);
            $asked = [...$asked, ...$keys[1]];
        }

        self::assertSame([], array_values(array_diff(array_keys($bundle), $asked)));
    }

    /**
     * @return list<string>
     */
    private function sources(): array
    {
        $files = [];

        /** @var iterable<SplFileInfo> $found */
        $found = new RecursiveIteratorIterator(
            new RecursiveDirectoryIterator(__DIR__.'/../src', \FilesystemIterator::SKIP_DOTS),
        );

        foreach ($found as $file) {
            if ($file->getExtension() === 'php') {
                $files[] = $file->getPathname();
            }
        }

        self::assertNotSame([], $files, 'No source files found, so this test pins nothing.');

        return $files;
    }
}
