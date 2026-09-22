<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Catalogue\Check;
use Phox\JevLint\Support\Json;
use PHPUnit\Framework\TestCase;

final class CatalogueTest extends TestCase
{
    public function test_it_loads_the_shipped_catalogue(): void
    {
        $catalogue = Catalogue::load();

        $this->assertNotSame([], $catalogue->all());
        $this->assertNotSame([], $catalogue->static());
        $this->assertNotSame([], $catalogue->modelChecks('question', 'noul'));
    }

    public function test_every_scope_the_catalogue_accepts_is_one_the_linter_asks(): void
    {
        // A scope nothing asks is the model half of what StaticRulesAreBound
        // covers for rules: a check that loads and never runs.
        $linter = (string) file_get_contents(__DIR__.'/../src/Lint/ModelLinter.php');
        preg_match_all("/modelChecks\(\s*'([a-z-]+)'/", $linter, $asked);
        $asked = array_values(array_unique($asked[1]));

        $check = (string) file_get_contents(__DIR__.'/../src/Catalogue/Check.php');
        preg_match('/\$scopes = \[([^\]]+)\]/', $check, $declared);
        $list = $declared[1] ?? '';

        self::assertNotSame([], $asked, 'Found no scopes in the linter, so this pins nothing.');
        self::assertNotSame('', $list, 'Found no scope list in Check, so this pins nothing.');

        preg_match_all("/'([a-z-]+)'/", $list, $names);
        sort($asked);
        $accepted = $names[1];
        sort($accepted);

        self::assertSame($accepted, $asked, sprintf(
            'The catalogue accepts scopes %s and the linter asks %s.',
            implode(', ', $accepted),
            implode(', ', $asked),
        ));
    }

    public function test_every_check_has_a_unique_id(): void
    {
        $ids = array_map(static fn (Check $check): string => $check->id, Catalogue::load()->written());

        $this->assertSame($ids, array_values(array_unique($ids)));
    }

    public function test_every_severity_is_one_the_report_understands(): void
    {
        foreach (Catalogue::load()->written() as $check) {
            $this->assertContains($check->severity, ['error', 'warning', 'advice'], $check->id);
        }
    }

    public function test_every_static_check_names_a_rule_and_every_model_check_carries_a_question(): void
    {
        foreach (Catalogue::load()->written() as $check) {
            if ($check->isStatic()) {
                $this->assertNotNull($check->rule, $check->id);
                $this->assertNotNull($check->message, $check->id);

                continue;
            }

            $this->assertNotSame([], $check->wordings, $check->id);
            $this->assertNotSame('', $check->instructions(), $check->id);
            $this->assertContains($check->questionType(), ['noul', 'choice'], $check->id);

            foreach ($check->wordings as $wording) {
                $this->assertNotSame('', $wording->instructions, $check->id);
            }
        }
    }

    public function test_every_noul_wording_says_what_true_and_false_mean(): void
    {
        foreach (Catalogue::load()->written() as $check) {
            foreach ($check->isModel() ? $check->wordings : [] as $wording) {
                if ($wording->type !== 'noul') {
                    continue;
                }

                $criteria = $wording->criteria ?? [];

                $this->assertArrayHasKey('true', $criteria, $check->id);
                $this->assertArrayHasKey('false', $criteria, $check->id);
            }
        }
    }

    public function test_a_composite_check_asks_every_wording_the_same_way(): void
    {
        foreach (Catalogue::load()->written() as $check) {
            if (! $check->isComposite()) {
                continue;
            }

            $types = array_map(static fn ($wording): string => $wording->type, $check->wordings);

            $this->assertSame([$types[0]], array_values(array_unique($types)), $check->id);
        }
    }

    public function test_every_check_tells_the_reader_what_to_write_instead(): void
    {
        foreach (Catalogue::load()->written() as $check) {
            $this->assertNotSame('', $check->suggest, $check->id.' reports a defect without suggesting a change');
            $this->assertNotSame('', $check->title, $check->id.' has no title for somebody who does not know the catalogue');
        }
    }

    public function test_a_nested_state_field_addresses_a_real_pointer(): void
    {
        $check = Catalogue::load()->find('state/irrelevant-field');

        $this->assertInstanceOf(Check::class, $check);
        $this->assertSame('/state/application/role', $check->path('state', 'application.role'));
        $this->assertSame('/state/plan', $check->path('state', 'plan'));
        $this->assertSame('/state/a~1b', $check->path('state', 'a/b'));
    }

    public function test_every_model_check_ships_a_fixture(): void
    {
        /** @var array{fixtures: list<array{check: string}>} $fixtures */
        $fixtures = Json::readFile(Catalogue::locate('fixtures.json'));
        $covered = array_column($fixtures['fixtures'], 'check');

        foreach (Catalogue::load()->written() as $check) {
            if ($check->isModel()) {
                $this->assertContains($check->id, $covered, $check->id.' has no fixture to prove it measures anything');
            }
        }
    }

    /**
     * `advice_clears: false` is the reason a fixture ships no rewrite, and the
     * only record of it. A fixture that loses its `fixed` by accident reads as
     * one whose advice cannot clear its own check
     */
    public function test_a_fixture_without_a_fix_says_why_and_no_other_does(): void
    {
        /** @var array{fixtures: list<array<string, mixed>>} $data */
        $data = json_decode((string) file_get_contents(__DIR__.'/../../checks/fixtures.json'), true);
        $wrong = [];

        foreach ($data['fixtures'] as $fixture) {
            $offersFix = isset($fixture['fixed']);
            $saysWhy = ($fixture['advice_clears'] ?? null) === false;

            if ($offersFix !== $saysWhy) {
                continue;
            }

            $wrong[] = sprintf(
                '%s (%s) %s',
                (string) $fixture['check'],
                (string) ($fixture['domain'] ?? 'support'),
                $offersFix ? 'ships a fix and says its advice does not clear' : 'ships no fix and does not say why',
            );
        }

        self::assertSame([], $wrong, implode("\n", $wrong));
    }

    /**
     * The `fixed` example exists to show the check's own advice clears it. A
     * `fixed` that is the clean example again measures the clean question twice
     * and proves nothing about the advice.
     */
    public function test_no_fixture_offers_its_clean_example_as_the_fix(): void
    {
        $fixtures = json_decode((string) file_get_contents(__DIR__.'/../../checks/fixtures.json'), true);
        self::assertIsArray($fixtures);

        $duplicates = [];

        foreach ($fixtures['fixtures'] as $fixture) {
            if (! isset($fixture['fixed'])) {
                continue;
            }

            if ($fixture['fixed'] === $fixture['clean']) {
                $duplicates[] = $fixture['check'].' ('.($fixture['domain'] ?? 'first').')';
            }
        }

        self::assertSame([], $duplicates, sprintf(
            'These ship the clean example as the fix, so the advice is untested: %s',
            implode(', ', $duplicates),
        ));
    }

    public function test_an_answer_key_survives_the_round_trip(): void
    {
        $catalogue = Catalogue::load();
        $keys = [];

        foreach ($catalogue->all() as $check) {
            if ($check->isModel()) {
                $keys[] = $check->answerKey();
            }
        }

        $this->assertSame($keys, array_values(array_unique($keys)));
    }
}
