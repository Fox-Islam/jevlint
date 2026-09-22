<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use PHPUnit\Framework\TestCase;

/**
 * The corpus keeps its readings against this digest and treats them as still
 * valid while it holds. A field that changes the call and not the digest makes
 * a stale harvest look current, which is the one thing the digest exists to stop
 */
final class AskedDigestTest extends TestCase
{
    /**
     * @return iterable<string, array{callable(array<string, mixed>): array<string, mixed>, bool}>
     */
    public static function edits(): iterable
    {
        yield 'rewording a check question' => [
            static fn (array $c): array => self::onModel($c, static function (array $check): array {
                $check['question']['instructions'] = 'Something else entirely.';

                return $check;
            }),
            true,
        ];

        yield 'changing a scope' => [
            static fn (array $c): array => self::onModel($c, static function (array $check): array {
                $check['scope'] = $check['scope'] === 'state' ? 'question' : 'state';

                return $check;
            }),
            true,
        ];

        yield 'changing a trigger' => [
            static fn (array $c): array => self::onModel($c, static function (array $check): array {
                $check['trigger'] = 0.55;

                return $check;
            }),
            true,
        ];

        yield 'narrowing applies_to' => [
            static fn (array $c): array => self::onModel($c, static function (array $check): array {
                $check['applies_to'] = ['noul'];

                return $check;
            }),
            true,
        ];

        yield 'flipping a locate_mode' => [
            static function (array $c): array {
                foreach ($c['checks'] as $at => $check) {
                    if (isset($check['locate_mode'])) {
                        $c['checks'][$at]['locate_mode'] = $check['locate_mode'] === 'each' ? 'pick' : 'each';

                        return $c;
                    }
                }

                self::fail('No check carries locate_mode, so this case tests nothing.');
            },
            true,
        ];

        yield 'rewording a hint' => [
            static fn (array $c): array => self::onModel($c, static function (array $check): array {
                $check['hint'] = 'Different words, the same question asked.';

                return $check;
            }),
            false,
        ];

        yield 'rewording a suggestion' => [
            static fn (array $c): array => self::onModel($c, static function (array $check): array {
                $check['suggest'] = 'Different words again.';

                return $check;
            }),
            false,
        ];
    }

    /**
     * @param callable(array<string, mixed>): array<string, mixed> $edit
     */
    #[\PHPUnit\Framework\Attributes\DataProvider('edits')]
    public function test_the_digest_moves_when_the_call_changes_and_not_otherwise(callable $edit, bool $shouldMove): void
    {
        $before = Catalogue::load($this->write($this->catalogue()))->asked;
        $after = Catalogue::load($this->write($edit($this->catalogue())))->asked;

        $shouldMove
            ? $this->assertNotSame($before, $after, 'The edit changed what is asked and the digest did not move.')
            : $this->assertSame($before, $after, 'The edit changed no question and the digest moved anyway.');
    }

    /**
     * @param  array<string, mixed>                                 $catalogue
     * @param  callable(array<string, mixed>): array<string, mixed> $edit
     * @return array<string, mixed>
     */
    private static function onModel(array $catalogue, callable $edit): array
    {
        foreach ($catalogue['checks'] as $at => $check) {
            if (($check['mode'] ?? null) === 'model') {
                $catalogue['checks'][$at] = $edit($check);

                return $catalogue;
            }
        }

        self::fail('No model check in the catalogue, so this case tests nothing.');
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
        $directory = sys_get_temp_dir().'/jevlint-asked-'.bin2hex(random_bytes(6));
        mkdir($directory);
        file_put_contents($directory.'/catalogue.json', json_encode($data));
        copy(__DIR__.'/../../checks/fixtures.json', $directory.'/fixtures.json');

        return $directory.'/catalogue.json';
    }
}
