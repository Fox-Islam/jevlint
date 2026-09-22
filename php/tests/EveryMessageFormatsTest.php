<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use MessageFormatter;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

/**
 * A pattern ICU cannot parse comes back from the formatter as false, and the
 * message then prints with its arguments still in braces. Nothing else notices:
 * the run carries on and the text looks almost right
 */
final class EveryMessageFormatsTest extends TestCase
{
    /**
     * @return array<string, array{string, string}>
     */
    public static function patterns(): array
    {
        /** @var array<string, mixed> $bundle */
        $bundle = require __DIR__.'/../lang/en.php';
        $cases = [];

        foreach ($bundle as $key => $pattern) {
            if (is_string($pattern)) {
                $cases[$key] = [$key, $pattern];
            }
        }

        self::assertNotSame([], $cases, 'No patterns found, so this test pins nothing.');

        return $cases;
    }

    #[DataProvider('patterns')]
    public function test_a_pattern_parses_and_leaves_no_argument_behind(string $key, string $pattern): void
    {
        // `create` answers with null where the constructor throws, so a pattern
        // ICU refuses is a failing assertion and not an errored test.
        $formatter = MessageFormatter::create('en', $pattern);

        self::assertInstanceOf(
            MessageFormatter::class,
            $formatter,
            sprintf('%s is not a pattern ICU can parse: %s', $key, intl_get_error_message()),
        );

        $filled = $formatter->format(array_fill_keys($this->arguments($pattern), '1'));

        self::assertIsString($filled, sprintf('%s did not format: %s', $key, $formatter->getErrorMessage()));

        // A literal brace is written `'{'`, so one surviving here is an
        // argument the pattern names and this test did not supply.
        self::assertDoesNotMatchRegularExpression(
            '/(?<!\')\{[a-z_]+\}/',
            $filled,
            sprintf('%s left an argument unfilled: %s', $key, $filled),
        );
    }

    /**
     * Argument names, which are what `format` has to be given. A name inside a
     * plural or select branch is named again at the top, so the outer match is
     * enough
     *
     * @return list<string>
     */
    private function arguments(string $pattern): array
    {
        preg_match_all('/\{\s*([a-z_]+)\s*[,}]/', $pattern, $named);

        /** @var list<string> $names */
        $names = array_values(array_unique($named[1]));

        return $names;
    }
}
