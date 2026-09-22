<?php

declare(strict_types=1);

namespace Phox\JevLint\Config;

use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Support\Json;

/**
 * What a repository has decided about its own findings.
 *
 * The acceptances live beside the query and not inside it: the API rejects an
 * unknown key at the top of a request, and a query file that cannot be sent is
 * no longer the thing being checked.
 *
 * An absent file is an empty config. A repository that has never accepted
 * anything should not have to say so.
 */
final class Config
{
    public const FILE = '.jevlint.json';

    /**
     * @param list<Acceptance> $accept
     */
    private function __construct(
        public readonly array $accept,
        public readonly ?string $source,
        public readonly ?string $jev = null,
    ) {}

    public static function empty(): self
    {
        return new self([], null);
    }

    /** Find the config beside the query, then in the working directory */
    public static function discover(?string $explicit, string $queryPath): self
    {
        if ($explicit !== null) {
            if (! is_file($explicit)) {
                throw JevLintException::of(JevLintException::CONFIG, Text::of('config.not_found', ['path' => $explicit]));
            }

            return self::load($explicit);
        }

        $cwd = getcwd();

        foreach ([dirname($queryPath).'/'.self::FILE, ($cwd === false ? '.' : $cwd).'/'.self::FILE] as $candidate) {
            if (is_file($candidate)) {
                return self::load($candidate);
            }
        }

        return self::empty();
    }

    public static function load(string $path): self
    {
        /** @var array<string, mixed> $data */
        $data = Json::readFile($path);

        // A misspelled `accept` leaves the whole block covering nothing, which
        // is the failure this file exists to make visible.
        $unknown = array_diff(array_keys($data), ['accept', 'jev']);

        if ($unknown !== []) {
            throw JevLintException::of(JevLintException::CONFIG, Text::of('config.unknown_setting', [
                'path' => $path,
                'names' => implode('", "', array_map(strval(...), $unknown)),
            ]));
        }

        $accept = $data['accept'] ?? [];

        if (! is_array($accept)) {
            throw JevLintException::of(JevLintException::CONFIG, Text::of('config.accept_not_a_list', ['path' => $path]));
        }

        $accepted = [];

        foreach ($accept as $i => $entry) {
            if (! is_array($entry)) {
                throw JevLintException::of(JevLintException::CONFIG, Text::of('config.entry_not_an_object', ['path' => $path, 'entry' => (string) $i]));
            }

            $check = $entry['check'] ?? null;
            $reason = $entry['reason'] ?? null;
            $question = $entry['question'] ?? null;

            if (! is_string($check) || $check === '') {
                throw JevLintException::of(JevLintException::CONFIG, Text::of('config.entry_names_no_check', ['path' => $path, 'entry' => (string) $i]));
            }

            // An acceptance is a judgement somebody made. Recording why is what
            // separates it from switching the check off.
            if (! is_string($reason) || trim($reason) === '') {
                throw JevLintException::of(JevLintException::CONFIG, Text::of('config.acceptance_needs_a_reason', ['path' => $path, 'check' => $check]));
            }

            $accepted[] = new Acceptance($check, is_string($question) ? $question : null, $reason);
        }

        return new self($accepted, $path, self::jev($data, $path));
    }

    /**
     * The Jev version this repository writes its queries for.
     *
     * A query file carries no record of the build it will be sent to, so the
     * version a run checks against comes from here
     *
     * @param array<string, mixed> $data
     */
    private static function jev(array $data, string $path): ?string
    {
        $jev = $data['jev'] ?? null;

        if ($jev === null) {
            return null;
        }

        if (! is_string($jev) || $jev === '') {
            throw JevLintException::of(JevLintException::CONFIG, Text::of('config.jev_not_a_version', ['path' => $path]));
        }

        return $jev;
    }

    public function reasonFor(string $check, string $target): ?string
    {
        foreach ($this->accept as $acceptance) {
            if ($acceptance->covers($check, $target)) {
                return $acceptance->reason;
            }
        }

        return null;
    }

    /**
     * Check ids named in the config that the catalogue does not hold.
     *
     * @param  list<string> $known
     * @return list<string>
     */
    public function unknown(array $known): array
    {
        $missing = [];

        foreach ($this->accept as $acceptance) {
            if (! in_array($acceptance->check, $known, true)) {
                $missing[] = $acceptance->check;
            }
        }

        return array_values(array_unique($missing));
    }
}
