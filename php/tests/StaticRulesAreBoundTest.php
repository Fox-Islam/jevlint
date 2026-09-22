<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use PHPUnit\Framework\TestCase;
use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Lint\StaticLinter;

/**
 * A static check is a name in the catalogue bound to a branch in StaticLinter.
 * Nothing in the language ties the two together, so a rename on either side is
 * a silent no-op: the check still lists, still documents itself, and never
 * fires. These pin the binding in both directions.
 */
final class StaticRulesAreBoundTest extends TestCase
{
    /** @return list<string> */
    private function rulesRaisedInCode(): array
    {
        $source = file_get_contents(__DIR__.'/../src/Lint/StaticLinter.php');
        self::assertIsString($source);

        preg_match_all("/raise\(\s*'([^']+)'/", $source, $matches);

        return array_values(array_unique($matches[1]));
    }

    public function test_the_declared_rule_list_matches_the_rules_the_code_raises(): void
    {
        // The catalogue is validated against this list at load, so a name missing
        // from it makes a working check unloadable, and a name left in it after a
        // rename lets an unbound check load.
        $raised = $this->rulesRaisedInCode();
        $declared = StaticLinter::RULES;
        sort($raised);
        sort($declared);

        self::assertNotSame([], $raised, 'Found no raised rules, so this pins nothing.');
        self::assertSame($raised, $declared, 'StaticLinter::RULES and the raise() calls disagree.');
    }

    /** @return list<string> */
    private function rulesNamedInCatalogue(): array
    {
        $rules = [];

        foreach (Catalogue::load()->written() as $check) {
            if ($check->isStatic() && $check->rule !== null) {
                $rules[] = $check->rule;
            }
        }

        return array_values(array_unique($rules));
    }

    public function test_the_detector_finds_the_rules_that_are_there(): void
    {
        // Believing an empty result would make both tests below pass vacuously.
        self::assertContains('question.noInstructions', $this->rulesRaisedInCode());
        self::assertGreaterThan(10, count($this->rulesRaisedInCode()));
    }

    public function test_every_rule_the_catalogue_names_is_raised_somewhere(): void
    {
        $unraised = array_diff($this->rulesNamedInCatalogue(), $this->rulesRaisedInCode());

        self::assertSame([], array_values($unraised), sprintf(
            'These checks can never fire, because no code raises their rule: %s',
            implode(', ', $unraised),
        ));
    }

    public function test_every_rule_the_code_raises_is_named_by_a_check(): void
    {
        $unclaimed = array_diff($this->rulesRaisedInCode(), $this->rulesNamedInCatalogue());

        self::assertSame([], array_values($unclaimed), sprintf(
            'These rules raise a finding no check claims, so it is dropped: %s',
            implode(', ', $unclaimed),
        ));
    }

    /**
     * Which method raises each rule, so the catalogue's `applies_to` can be
     * checked against where the rule runs.
     *
     * @return array<string, string>
     */
    private function raisedIn(): array
    {
        $source = (string) file_get_contents(__DIR__.'/../src/Lint/StaticLinter.php');

        // By offset, not line by line: a `raise(` and the rule it names are
        // usually on different lines, so a per-line scan matched neither and the
        // check below passed on every catalogue.
        preg_match_all('/function (\w+)\(/', $source, $methods, PREG_OFFSET_CAPTURE);
        preg_match_all("/raise\(\s*'([^']+)'/", $source, $raises, PREG_OFFSET_CAPTURE);

        $where = [];

        foreach ($raises[1] as $raise) {
            $method = '';

            foreach ($methods[1] as $candidate) {
                if ($candidate[1] < $raise[1]) {
                    $method = $candidate[0];
                }
            }

            $where[$raise[0]] = $method;
        }

        return $where;
    }

    /**
     * `StaticLinter` dispatches by primitive and never consults `applies_to`, so
     * the field is documentation: `jevlint checks` prints it and nothing makes it
     * true. A rule raised inside `scoreRules` covers scores, and saying otherwise
     * in the catalogue is a claim about behaviour that is wrong.
     */
    public function test_a_static_check_applies_to_the_primitive_whose_rules_raise_it(): void
    {
        $expected = ['noulRules' => 'noul', 'choiceRules' => 'choice', 'scoreRules' => 'score'];
        $where = $this->raisedIn();
        $wrong = [];

        foreach (Catalogue::load()->written() as $check) {
            if (! $check->isStatic() || $check->rule === null) {
                continue;
            }

            $type = $expected[$where[$check->rule] ?? ''] ?? null;

            if ($type === null) {
                continue;
            }

            if ($check->appliesTo !== [$type]) {
                $wrong[] = sprintf('%s says [%s] but is raised in %s', $check->id, implode(',', $check->appliesTo), $where[$check->rule]);
            }
        }

        self::assertSame([], $wrong, implode('; ', $wrong));
    }

    public function test_every_static_check_names_a_rule(): void
    {
        foreach (Catalogue::load()->written() as $check) {
            if ($check->isStatic()) {
                self::assertIsString($check->rule, $check->id.' is static but names no rule');
            }
        }
    }

    public function test_a_check_id_and_its_rule_are_not_confused(): void
    {
        foreach (Catalogue::load()->written() as $check) {
            if ($check->isStatic()) {
                self::assertStringNotContainsString('/', (string) $check->rule, $check->id.' names a rule that looks like a check id');
            }
        }
    }
}
