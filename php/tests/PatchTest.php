<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Lint\StaticLinter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Finding;
use Phox\JevLint\Report\Patch;
use Phox\JevLint\Report\Report;
use PHPUnit\Framework\TestCase;

/**
 * A patch is only emitted where applying it clears the finding behind it. Each
 * case here is a broken query, patched by the tool's own output and checked
 * again
 */
final class PatchTest extends TestCase
{
    /**
     * @return array<string, array{array<string, mixed>, string}>
     */
    public static function brokenQueries(): array
    {
        return [
            'a Choice sent as a list' => [[
                'state' => 'a ticket',
                'questions' => ['category' => [
                    'type' => 'choice',
                    'instructions' => 'What is this support ticket about?',
                    'criteria' => ['billing', 'technical', 'other'],
                ]],
            ], 'choice/criteria-shape'],

            // Keys out of order: the shape is wrong and the keys say what the
            // order should be, which is the one case a patch can be built from.
            'a Score sent as a map with keys that say the order' => [[
                'state' => 'a ticket',
                'questions' => ['urgency' => [
                    'type' => 'score',
                    'instructions' => 'How urgent is this ticket?',
                    'criteria' => ['2' => 'The customer is blocked', '0' => 'Can wait until next week', '1' => 'Needs an answer today'],
                ]],
            ], 'score/criteria-shape'],

            'a Noul with yes and no keys' => [[
                'state' => 'a ticket',
                'questions' => ['refund' => [
                    'type' => 'noul',
                    'instructions' => 'Does the customer ask for a refund?',
                    'criteria' => ['yes' => 'They ask for money back.', 'no' => 'They do not.'],
                ]],
            ], 'noul/criteria-shape'],

            'a Choice with no fallback' => [[
                'state' => 'a ticket',
                'questions' => ['category' => [
                    'type' => 'choice',
                    'instructions' => 'What is this support ticket about?',
                    'criteria' => ['billing' => 'Charges and invoices', 'technical' => 'Something is broken'],
                ]],
            ], 'choice/no-fallback'],
        ];
    }

    /**
     * A Score is an ordered rubric. Where the keys are names, the order of the
     * map is the order somebody happened to type it, and a patch built from that
     * would ship a scrambled scale and clear this very check. So the check still
     * fires and says what is wrong, and offers no patch to apply blindly.
     */
    public function test_a_score_map_with_named_keys_fires_without_a_patch(): void
    {
        $finding = $this->find([
            'state' => 'a ticket',
            'questions' => ['severity' => [
                'type' => 'score',
                'instructions' => 'How severe is this?',
                'criteria' => [
                    'critical' => 'Service has stopped',
                    'minor' => 'Cosmetic only',
                    'major' => 'Service is degraded',
                ],
            ]],
        ], 'score/criteria-shape');

        self::assertNotNull($finding, 'a Score sent as a map should still be reported');
        self::assertNull($finding->patch, 'the order is unknowable, so there is nothing safe to apply');
        self::assertNotSame('', $finding->suggest, 'withholding the patch must not withhold the advice');
    }

    /**
     * The `remove` patches come from model checks, so they cannot be driven
     * through the linter offline. What is testable without a call is that the
     * patch a check declares removes the node it names, and nothing else.
     *
     * @return array<string, array{string, array<string, mixed>, string}>
     */
    public static function removals(): array
    {
        $query = [
            'state' => ['ticket' => 'a ticket', 'plan' => 'pro'],
            'questions' => [
                'charge_count' => ['type' => 'noul', 'instructions' => 'Were there more than two charges?'],
                'keep_me' => ['type' => 'noul', 'instructions' => 'Does the customer ask for a refund?'],
            ],
        ];

        return [
            'question/arithmetic removes the question' => ['/questions/charge_count', $query, 'questions'],
            'question/date-comparison removes the question' => ['/questions/charge_count', $query, 'questions'],
            'state/irrelevant-field removes the field' => ['/state/plan', $query, 'state'],
        ];
    }

    /**
     * @param array<string, mixed> $query
     */
    #[\PHPUnit\Framework\Attributes\DataProvider('removals')]
    public function test_a_remove_patch_takes_out_the_node_it_names_and_no_other(string $path, array $query, string $branch): void
    {
        $patch = new Patch('remove', $path);
        $patched = $patch->applyTo($query);

        $leaf = substr($path, strrpos($path, '/') + 1);

        self::assertIsArray($patched[$branch]);
        self::assertArrayNotHasKey($leaf, $patched[$branch], 'the patch did not remove what it named');

        $before = is_array($query[$branch]) ? count($query[$branch]) : 0;
        self::assertCount($before - 1, $patched[$branch], 'the patch removed more than it named');
    }

    public function test_a_remove_patch_through_a_node_that_is_not_there_changes_nothing(): void
    {
        $query = ['state' => ['ticket' => 'x', 'a.b' => 'y']];

        // `/state/a/b` walks through a node that does not exist. Creating it and
        // removing nothing left junk behind in the caller's query.
        self::assertSame($query, (new Patch('remove', '/state/a/b'))->applyTo($query));
    }

    /**
     * A `remove` takes something out of the query, so it can never be lossless
     * however it is declared. This is the classification an unattended fixer
     * gates on, so it must not be possible to get it wrong by omission.
     */
    public function test_a_removal_is_always_classified_destructive(): void
    {
        foreach ([new Patch('remove', '/questions/x'), new Patch('remove', '/state/y')] as $patch) {
            self::assertSame(Patch::DESTRUCTIVE, $patch->safety, 'the default hid a destructive patch');
        }
    }

    public function test_every_check_that_declares_a_removal_is_a_model_check_that_names_a_node(): void
    {
        foreach (Catalogue::load()->written() as $check) {
            if ($check->removes === null) {
                continue;
            }

            self::assertContains($check->removes, ['question', 'field'], $check->id.' removes something unrecognised');
            self::assertTrue($check->isModel(), $check->id.' declares a removal but is a rule');
        }
    }

    /**
     * @param array<string, mixed> $query
     */
    #[\PHPUnit\Framework\Attributes\DataProvider('brokenQueries')]
    public function test_applying_the_patch_clears_the_finding(array $query, string $checkId): void
    {
        $finding = $this->find($query, $checkId);

        self::assertNotNull($finding, $checkId.' did not fire on the query written to break it');
        self::assertNotNull($finding->patch, $checkId.' fired without offering a patch');

        $patched = $finding->patch->applyTo($query);

        self::assertNull(
            $this->find($patched, $checkId),
            $checkId.' still fires after its own patch is applied',
        );
    }

    /**
     * @param array<string, mixed> $query
     */
    private function find(array $query, string $checkId): ?Finding
    {
        $catalogue = Catalogue::load();
        $report = new Report('test', $catalogue->version);

        (new StaticLinter($catalogue))->run(Query::fromArray($query), $report);

        foreach ($report->findings() as $finding) {
            if ($finding->checkId === $checkId) {
                return $finding;
            }
        }

        return null;
    }
}
