<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Lint\StaticLinter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Patch;
use Phox\JevLint\Report\Report;
use PHPUnit\Framework\TestCase;

/**
 * A `lossless` patch keeps every word the caller wrote, and a patch of any
 * safety leaves a file this tool can still read. A shape rule that rebuilds
 * criteria from their keys meets neither condition, so it offers no patch
 */
final class PatchesKeepWhatTheyClaimTest extends TestCase
{
    /**
     * The questions are written as JSON, not as PHP arrays: `{"0": ...}` decodes
     * to a PHP list, and whether the caller wrote an object is read from the
     * text, so a PHP fixture cannot express the case.
     *
     * @return iterable<string, array{string, bool}>
     */
    public static function criteria(): iterable
    {
        yield 'a score level with no text' => [
            '{"type":"score","instructions":"How urgent?","criteria":{"0":"","1":"Inconvenient","2":"Blocked"}}',
            false,
        ];
        yield 'score levels that are numbers' => [
            '{"type":"score","instructions":"How urgent?","criteria":{"0":10,"1":20}}',
            false,
        ];
        yield 'a score map of one' => [
            '{"type":"score","instructions":"How urgent?","criteria":{"0":"Only one"}}',
            false,
        ];
        yield 'score levels that are all text' => [
            '{"type":"score","instructions":"How urgent?","criteria":{"0":"Fine","1":"Bad"}}',
            true,
        ];
        yield 'choice options that are numbers' => [
            '{"type":"choice","instructions":"Which?","criteria":["0","1","2"]}',
            false,
        ];
        yield 'a choice list holding a nested option' => [
            '{"type":"choice","instructions":"Which?","criteria":["billing",{"technical":"broken"}]}',
            false,
        ];
        yield 'a choice list of labels' => [
            '{"type":"choice","instructions":"Which?","criteria":["billing","technical","other"]}',
            true,
        ];
        yield 'noul keys that differ only in case' => [
            '{"type":"noul","instructions":"Refund?","criteria":{"yes":"Money back","YES":"Chargeback","no":"No"}}',
            false,
        ];
        yield 'noul keys written as yes and no' => [
            '{"type":"noul","instructions":"Refund?","criteria":{"yes":"Money back","no":"No"}}',
            true,
        ];
    }

    #[\PHPUnit\Framework\Attributes\DataProvider('criteria')]
    public function test_a_shape_patch_is_offered_only_where_it_keeps_everything(string $question, bool $expected): void
    {
        $patch = $this->shapePatch($question);

        $expected
            ? self::assertInstanceOf(Patch::class, $patch, 'A patch that loses nothing should be offered.')
            : self::assertNull($patch, 'This patch would drop or rewrite content the caller wrote.');
    }

    public function test_removing_a_question_leaves_questions_an_object(): void
    {
        $query = ['state' => ['t' => 'x'], 'questions' => [
            '0' => ['type' => 'noul', 'instructions' => 'A?'],
            '1' => ['type' => 'noul', 'instructions' => 'B?'],
        ]];

        $after = (new Patch('remove', '/questions/1', null, Patch::DESTRUCTIVE))->applyTo($query);

        self::assertStringContainsString('"questions":{"0"', (string) json_encode($after));
    }

    private function shapePatch(string $question): ?Patch
    {
        $report = new Report('test', '1');
        $path = tempnam(sys_get_temp_dir(), 'jevlint').'.json';
        file_put_contents($path, sprintf('{"state":{"t":"x"},"questions":{"q":%s}}', $question));

        (new StaticLinter(Catalogue::load(), 20000))->run(Query::fromFile($path), $report);
        unlink($path);

        foreach ($report->findings() as $finding) {
            if (str_ends_with($finding->checkId, '/criteria-shape')) {
                return $finding->patch;
            }
        }

        self::fail('No shape finding was raised, so this case tests nothing.');
    }
}
