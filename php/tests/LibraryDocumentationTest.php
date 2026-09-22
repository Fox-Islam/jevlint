<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Lint\Linter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Report;
use PHPUnit\Framework\TestCase;

/**
 * The library pages name methods by hand, and a renamed one leaves a page that
 * reads correctly and does not run
 */
final class LibraryDocumentationTest extends TestCase
{
    /** The receiver a page writes, and the class it is */
    private const RECEIVERS = [
        'Linter::' => Linter::class,
        '$linter->' => Linter::class,
        '`->' => Linter::class,
        'Query::' => Query::class,
        '$report->' => Report::class,
    ];

    public function test_every_method_the_pages_name_exists(): void
    {
        $missing = [];
        $found = 0;

        foreach (['docs/library.md', 'README.md'] as $page) {
            $text = (string) file_get_contents(__DIR__.'/../../'.$page);

            // A bare `->` is only a Linter call where it is written as one, in a
            // code span with nothing before it. Elsewhere it follows its receiver.
            preg_match_all('/(Linter::|Query::|\$report->|\$linter->|`->)(\w+)\(/', $text, $named, PREG_SET_ORDER);

            foreach ($named as [$whole, $receiver, $method]) {
                $found++;
                $class = self::RECEIVERS[$receiver];

                if (! method_exists($class, $method)) {
                    $missing[] = sprintf('%s: %s) is not on %s', $page, $whole, $class);
                }
            }
        }

        self::assertGreaterThan(0, $found, 'No method names found, so this test pins nothing.');
        self::assertSame([], $missing, implode("\n", $missing));
    }
}
