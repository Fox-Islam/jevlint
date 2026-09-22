<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Report\Finding;
use PHPUnit\Framework\TestCase;

/**
 * `acceptedBecause` rebuilds the finding by listing every property, because a
 * readonly one cannot be reassigned on a clone. A property added and not listed
 * falls back to its default, which is how an accepted `question/type-mismatch`
 * came to report its weight under `probability`
 */
final class FindingCarriesEveryFieldTest extends TestCase
{
    public function test_accepting_a_finding_changes_nothing_but_the_reason(): void
    {
        $finding = $this->distinctive();
        $accepted = $finding->acceptedBecause('we know');

        $before = $this->properties($finding);
        $after = $this->properties($accepted);

        self::assertSame('we know', $after['accepted']);

        unset($before['accepted'], $after['accepted']);
        self::assertEquals($before, $after, 'Accepting a finding dropped a field back to its default.');
    }

    /**
     * Every property set away from its default, so a field the rebuild forgets
     * shows up as a difference instead of matching by luck.
     */
    private function distinctive(): Finding
    {
        $reflection = new \ReflectionClass(Finding::class);
        $arguments = [];

        foreach ($reflection->getConstructor()?->getParameters() ?? [] as $parameter) {
            // The exact type, not a substring of it: `JevLint` contains `int`.
            $type = ltrim((string) $parameter->getType(), '?');
            $name = $parameter->getName();

            $arguments[$name] = match (true) {
                $name === 'measure' => 'weight',
                is_a($type, \BackedEnum::class, true) => $this->anyCase($type),
                $type === 'bool' => ! ($parameter->isDefaultValueAvailable() && $parameter->getDefaultValue() === true),
                $type === 'float' => 0.4242,
                $type === 'int' => 7,
                $type === 'array' => ['a-value'],
                $type === 'string' => 'a-'.$name,
                default => null,
            };
        }

        self::assertNotSame([], $arguments, 'No constructor parameters found, so this test pins nothing.');

        /** @var Finding */
        return $reflection->newInstanceArgs($arguments);
    }

    /**
     * @param class-string<\BackedEnum> $enum
     */
    private function anyCase(string $enum): \BackedEnum
    {
        return $enum::cases()[0];
    }

    /**
     * @return array<string, mixed>
     */
    private function properties(Finding $finding): array
    {
        $values = [];

        foreach ((new \ReflectionClass(Finding::class))->getProperties() as $property) {
            $values[$property->getName()] = $property->getValue($finding);
        }

        return $values;
    }
}
