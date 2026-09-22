<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use PHPUnit\Framework\TestCase;

/**
 * An extension the code calls and composer.json does not name installs fine and
 * fatals on first use. `mb_strlen` on the --static-only path did exactly that
 */
final class DeclaredExtensionsTest extends TestCase
{
    /**
     * Functions whose extension can be missing from a PHP build. `preg_` is left
     * out because PCRE cannot be.
     *
     * @var array<string, string>
     */
    private const PREFIXES = [
        'mb_' => 'ext-mbstring',
        'json_' => 'ext-json',
        'curl_' => 'ext-curl',
        'iconv' => 'ext-iconv',
        'openssl_' => 'ext-openssl',
        'bc' => 'ext-bcmath',
        'gmp_' => 'ext-gmp',
        'simplexml_' => 'ext-simplexml',
        'intl' => 'ext-intl',
        'sodium_' => 'ext-sodium',
        'imagick' => 'ext-imagick',
        'zip_' => 'ext-zip',
    ];

    /**
     * Classes an extension brings. The prefix list above finds a function and
     * not a class, so `MessageFormatter::formatMessage` looked like core PHP
     *
     * @var array<string, string>
     */
    private const CLASSES = [
        'MessageFormatter' => 'ext-intl',
        'NumberFormatter' => 'ext-intl',
        'IntlDateFormatter' => 'ext-intl',
        'Collator' => 'ext-intl',
        'Transliterator' => 'ext-intl',
        'IntlChar' => 'ext-intl',
        'ZipArchive' => 'ext-zip',
        'SimpleXMLElement' => 'ext-simplexml',
        'Imagick' => 'ext-imagick',
    ];

    public function test_every_extension_the_shipped_source_calls_is_declared(): void
    {
        $composer = json_decode((string) file_get_contents(__DIR__.'/../../composer.json'), true);

        self::assertIsArray($composer);
        self::assertIsArray($composer['require'] ?? null);

        $declared = array_keys($composer['require']);
        $undeclared = [];

        foreach ($this->sources() as $file) {
            $source = (string) file_get_contents($file);

            foreach (self::PREFIXES as $prefix => $extension) {
                if (in_array($extension, $declared, true)) {
                    continue;
                }

                // A call, not a mention: `mb_strlen(` and not the word in a comment.
                if (preg_match('/(?<![\w$>])'.preg_quote($prefix, '/').'\w*\s*\(/', $source, $match) === 1) {
                    $undeclared[$extension] = sprintf('%s calls %s', basename($file), rtrim($match[0], " \t("));
                }
            }

            foreach (self::CLASSES as $class => $extension) {
                if (in_array($extension, $declared, true)) {
                    continue;
                }

                // Constructed, called statically, or imported. A `use` counts:
                // nothing imports a class it never reaches for.
                if (preg_match('/(?<![\w\\$>])'.$class.'\s*(?:::|\()|^use\s+'.$class.'\s*;/m', $source) === 1) {
                    $undeclared[$extension] = sprintf('%s uses %s', basename($file), $class);
                }
            }
        }

        self::assertSame([], $undeclared, sprintf(
            "composer.json does not require:\n  %s",
            implode("\n  ", array_map(
                static fn (string $extension, string $why): string => $extension.' - '.$why,
                array_keys($undeclared),
                $undeclared,
            )),
        ));
    }

    /**
     * @return list<string>
     */
    private function sources(): array
    {
        $files = [];

        /** @var iterable<\SplFileInfo> $found */
        $found = new \RecursiveIteratorIterator(
            new \RecursiveDirectoryIterator(__DIR__.'/../src', \FilesystemIterator::SKIP_DOTS),
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
