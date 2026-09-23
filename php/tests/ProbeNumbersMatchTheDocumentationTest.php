<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Probe\Probe;
use Phox\JevLint\Probe\QuestionProbe;
use PHPUnit\Framework\TestCase;

/**
 * The README states the probe's thresholds as figures a reader takes on trust.
 * A constant moved without the page moving leaves the page describing a run
 * nobody can get.
 *
 * Each figure is matched inside the sentence that explains it, because the
 * README holds enough numbers that a bare search finds one somewhere whatever
 * the constant is set to
 */
final class ProbeNumbersMatchTheDocumentationTest extends TestCase
{
    /**
     * @return iterable<string, array{float, int, string}>
     */
    public static function figures(): iterable
    {
        yield 'the band a yes/no answer is undecided inside' => [QuestionProbe::UNDECIDED, 2, 'within %s of the middle'];
        yield 'the movement too small to cross a threshold' => [QuestionProbe::NEGLIGIBLE, 2, 'three times that spread and %s'];
        yield 'the floor used where a run cannot measure its own' => [Probe::PUBLISHED_NOISE, 4, 'or %s where'];
    }

    #[\PHPUnit\Framework\Attributes\DataProvider('figures')]
    public function test_the_readme_prints_the_figure_the_code_uses(float $value, int $places, string $sentence): void
    {
        // The README wraps, so the sentence is matched without its line breaks.
        $readme = (string) preg_replace('/\s+/', ' ', (string) file_get_contents(__DIR__.'/../../README.md'));
        $printed = rtrim(rtrim(number_format($value, $places, '.', ''), '0'), '.');

        self::assertStringContainsString(
            sprintf($sentence, $printed),
            $readme,
            'The README explains this threshold with a figure the code does not use.',
        );
    }
}
