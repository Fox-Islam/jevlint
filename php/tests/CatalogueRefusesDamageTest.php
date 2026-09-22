<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Exceptions\JevLintException;
use PHPUnit\Framework\TestCase;

/**
 * Each of these loaded without complaint and produced a report that read like a
 * clean one. The duplicate rule was the worst: the shadowing check's severity
 * was what got reported, so two checks on one rule took an exit 1 to an exit 0
 */
final class CatalogueRefusesDamageTest extends TestCase
{
    /**
     * @return iterable<string, array{callable(array<string, mixed>): array<string, mixed>, string}>
     */
    public static function damage(): iterable
    {
        yield 'two checks naming one rule' => [
            static function (array $data): array {
                $static = self::first($data, 'static');
                $shadow = $static;
                $shadow['id'] = $static['id'].'-copy';
                $shadow['severity'] = 'advice';
                array_unshift($data['checks'], $shadow);

                return $data;
            },
            'both name the rule',
        ];

        yield 'a model check carrying no question' => [
            static function (array $data): array {
                foreach ($data['checks'] as $at => $check) {
                    if (($check['mode'] ?? null) === 'model') {
                        unset($data['checks'][$at]['question'], $data['checks'][$at]['questions']);

                        break;
                    }
                }

                return $data;
            },
            'carries no `question`',
        ];

        yield 'applies_to naming no primitive' => [
            static function (array $data): array {
                foreach ($data['checks'] as $at => $check) {
                    if (($check['mode'] ?? null) === 'model') {
                        $data['checks'][$at]['applies_to'] = ['tarot'];

                        break;
                    }
                }

                return $data;
            },
            'is not a Jev primitive',
        ];

        yield 'two ids colliding under the answer key' => [
            static function (array $data): array {
                $model = self::first($data, 'model');
                $model['id'] = str_replace('/', '_', $model['id']);
                $data['checks'][] = $model;

                return $data;
            },
            'asked under the same key',
        ];

        yield 'a reads nothing can address' => [
            static function (array $data): array {
                $data['checks'][0]['reads'] = 'moon';

                return $data;
            },
            'is not a part of a query',
        ];

        yield 'no checks at all' => [
            static function (array $data): array {
                $data['checks'] = [];

                return $data;
            },
            'has no checks',
        ];

        yield 'a version that is not one' => [
            static function (array $data): array {
                $data['version'] = ['1'];

                return $data;
            },
            'writes its version as',
        ];

        yield 'a suppression nothing tests' => [
            static function (array $data): array {
                foreach ($data['checks'] as $at => $check) {
                    if (isset($check['suppress'])) {
                        $data['checks'][$at]['suppress'][0]['when'] = 'the_moon_is_full';

                        return $data;
                    }
                }

                self::fail('No check carries a suppression, so this case tests nothing.');
            },
            'which nothing tests',
        ];

        yield 'superseding a check that is not there' => [
            static function (array $data): array {
                $data['checks'][0]['supersedes'] = ['no/such-check'];

                return $data;
            },
            'is not a check in this catalogue',
        ];
    }

    /**
     * @param  callable(array<string, mixed>): array<string, mixed> $damage
     */
    #[\PHPUnit\Framework\Attributes\DataProvider('damage')]
    public function test_it_refuses_a_catalogue_that_could_never_report_correctly(callable $damage, string $expected): void
    {
        $path = $this->write($damage($this->catalogue()));

        $this->expectException(JevLintException::class);
        $this->expectExceptionMessageMatches('/'.preg_quote($expected, '/').'/');

        Catalogue::load($path);
    }

    public function test_the_shipped_catalogue_passes_all_of_them(): void
    {
        $this->assertNotSame([], Catalogue::load($this->write($this->catalogue()))->all());
    }

    /**
     * @param  array<string, mixed> $data
     * @return array<string, mixed>
     */
    private static function first(array $data, string $mode): array
    {
        foreach ($data['checks'] as $check) {
            if (($check['mode'] ?? null) === $mode) {
                return $check;
            }
        }

        self::fail('No '.$mode.' check in the catalogue, so this case tests nothing.');
    }

    /**
     * @return array<string, mixed>
     */
    private function catalogue(): array
    {
        /** @var array<string, mixed> $data */
        $data = json_decode((string) file_get_contents(__DIR__.'/../../checks/catalogue.json'), true);

        return $data;
    }

    /**
     * @param array<string, mixed> $data
     */
    private function write(array $data): string
    {
        $directory = sys_get_temp_dir().'/jevlint-damage-'.bin2hex(random_bytes(6));
        mkdir($directory);
        file_put_contents($directory.'/catalogue.json', json_encode($data));
        copy(__DIR__.'/../../checks/fixtures.json', $directory.'/fixtures.json');

        return $directory.'/catalogue.json';
    }
}
