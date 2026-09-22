<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Lint\StaticLinter;
use Phox\JevLint\Catalogue\Check;
use Phox\JevLint\Config\Config;
use Phox\JevLint\Exceptions\JevLintException;
use PHPUnit\Framework\TestCase;

final class CatalogueVersionsTest extends TestCase
{
    /** @var list<string> */
    private array $written = [];

    protected function tearDown(): void
    {
        foreach ($this->written as $path) {
            @unlink($path);
        }

        $this->written = [];
    }

    /**
     * @param list<string>              $versions
     * @param list<array<string, mixed>> $checks
     */
    private function catalogue(array $versions, array $checks): string
    {
        $path = (string) tempnam(sys_get_temp_dir(), 'jevlint-catalogue-');
        $this->written[] = $path;

        file_put_contents($path, (string) json_encode([
            'version' => '1',
            'jev' => $versions,
            'checks' => $checks,
        ]));

        return $path;
    }

    /**
     * Each check gets its own rule. Two checks naming one rule under the same
     * version is refused at load, because the second could only shadow the first.
     *
     * @param  array<string, mixed> $extra
     * @return array<string, mixed>
     */
    private function check(string $id, array $extra = []): array
    {
        return [
            'id' => $id,
            'title' => 'A title',
            'mode' => 'static',
            'scope' => 'question',
            'severity' => 'warning',
            'rule' => StaticLinter::RULES[$this->rule++ % count(StaticLinter::RULES)],
            ...$extra,
        ];
    }

    private int $rule = 0;

    /**
     * @param  list<Check> $checks
     * @return list<string>
     */
    private function ids(array $checks): array
    {
        return array_map(static fn (Check $check): string => $check->id, $checks);
    }

    public function test_the_shipped_catalogue_names_the_versions_it_covers(): void
    {
        $catalogue = Catalogue::load();

        $this->assertNotSame([], $catalogue->versions);
        $this->assertSame($catalogue->versions[count($catalogue->versions) - 1], $catalogue->jev);
        $this->assertSame('jev-'.$catalogue->jev, $catalogue->model);
        $this->assertSame(0, $catalogue->withheld());
    }

    public function test_latest_is_the_newest_version_the_catalogue_covers(): void
    {
        // Written oldest first would read 1.9 as the newest of the three.
        $path = $this->catalogue(['1.13', '1.9', '1.12'], [$this->check('a/b')]);
        $catalogue = Catalogue::load($path);

        $this->assertSame(['1.9', '1.12', '1.13'], $catalogue->versions);
        $this->assertSame('1.13', $catalogue->jev);
        $this->assertSame('1.13', $catalogue->forJev('latest')->jev);
    }

    public function test_a_version_carries_the_checks_written_for_it(): void
    {
        $path = $this->catalogue(['1.12', '1.13'], [
            $this->check('always/here'),
            $this->check('new/in-13', ['since' => '1.13']),
            $this->check('gone/after-12', ['until' => '1.12']),
        ]);
        $catalogue = Catalogue::load($path);

        $this->assertSame(['always/here', 'new/in-13'], $this->ids($catalogue->forJev('1.13')->all()));
        $this->assertSame(['always/here', 'gone/after-12'], $this->ids($catalogue->forJev('1.12')->all()));
        $this->assertSame(1, $catalogue->forJev('1.12')->withheld());
        $this->assertCount(3, $catalogue->forJev('1.12')->written());
        $this->assertInstanceOf(Check::class, $catalogue->forJev('1.12')->findWritten('new/in-13'));
        $this->assertNull($catalogue->forJev('1.12')->find('new/in-13'));
    }

    public function test_it_refuses_a_version_it_holds_no_checks_for(): void
    {
        $catalogue = Catalogue::load($this->catalogue(['1.13'], [$this->check('a/b')]));

        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('Jev 1.9 is not a version this catalogue is written for. It covers 1.13.');

        $catalogue->forJev('1.9');
    }

    public function test_it_refuses_a_version_that_is_not_one(): void
    {
        $catalogue = Catalogue::load($this->catalogue(['1.13'], [$this->check('a/b')]));

        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('--jev=newest is not a Jev version.');

        $catalogue->forJev('newest');
    }

    public function test_it_refuses_a_check_written_for_no_version_it_covers(): void
    {
        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('can never run');

        Catalogue::load($this->catalogue(['1.13'], [$this->check('a/b', ['since' => '1.14'])]));
    }

    public function test_it_refuses_a_range_that_ends_before_it_starts(): void
    {
        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('no versions at all');

        Catalogue::load($this->catalogue(['1.12', '1.13'], [
            $this->check('a/b', ['since' => '1.13', 'until' => '1.12']),
        ]));
    }

    public function test_it_refuses_a_catalogue_that_names_no_version(): void
    {
        $path = (string) tempnam(sys_get_temp_dir(), 'jevlint-catalogue-');
        $this->written[] = $path;
        file_put_contents($path, (string) json_encode(['version' => '1', 'checks' => [$this->check('a/b')]]));

        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('does not name the Jev versions it covers');

        Catalogue::load($path);
    }

    public function test_a_config_pins_the_version(): void
    {
        $path = (string) tempnam(sys_get_temp_dir(), 'jevlint-config-');
        $this->written[] = $path;
        file_put_contents($path, (string) json_encode(['jev' => '1.12']));

        $this->assertSame('1.12', Config::load($path)->jev);
        $this->assertNull(Config::empty()->jev);
    }

    public function test_a_config_refuses_a_version_that_is_not_a_string(): void
    {
        $path = (string) tempnam(sys_get_temp_dir(), 'jevlint-config-');
        $this->written[] = $path;
        file_put_contents($path, (string) json_encode(['jev' => 1.12]));

        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('"jev" should be a version');

        Config::load($path);
    }
}
