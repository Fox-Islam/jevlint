<?php

declare(strict_types=1);

namespace Phox\JevLint\Catalogue;

use Phox\JevLint\Config\Config;
use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Lint\StaticLinter;
use Phox\JevLint\Query\ReviewedQuestion;
use Phox\JevLint\Support\Json;

/**
 * The check catalogue, read from `checks/catalogue.json`.
 *
 * The file sits at the root of the repository instead of inside this package,
 * so an implementation in another language reads the same one. Nothing in it is
 * PHP-specific: a static check names a rule the implementation owns, and a
 * model check is a Jev question, which is data in any language
 */
final class Catalogue
{
    /** What `--jev` is given when nobody pins a version */
    public const LATEST = 'latest';

    /** The Jev build the carried checks are the rules for, as the report names it */
    public readonly string $model;

    /**
     * @param list<string> $versions the Jev versions the file covers, oldest first
     * @param list<Check>  $checks   the checks carried for $jev
     * @param list<Check>  $written  every check in the file, whatever version it is for
     */
    private function __construct(
        public readonly string $version,
        public readonly string $jev,
        public readonly array $versions,
        public readonly string $fingerprint,
        public readonly string $asked,
        private readonly array $checks,
        private readonly array $written,
    ) {
        $this->model = 'jev-'.$jev;
    }

    public static function load(?string $path = null): self
    {
        $path ??= self::locate('catalogue.json');

        /** @var array<string, mixed> $data */
        $data = Json::readFile($path);

        if (! isset($data['checks']) || ! is_array($data['checks']) || $data['checks'] === []) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.no_checks', ['path' => $path]));
        }

        // The version is what two reports are compared on, so an invented one is
        // worse than none. An array reached the cast and was recorded as the
        // string "Array", beside a PHP warning on stderr.
        if (isset($data['version']) && ! is_string($data['version']) && ! is_int($data['version'])) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.version_wrong_type', ['path' => $path, 'type' => get_debug_type($data['version'])]));
        }

        // Two checks under one id behave as one or the other depending on which
        // lookup you go through: `--only` narrows to both, `find()` answers with
        // whichever comes first.
        $ids = [];

        foreach ($data['checks'] as $check) {
            $id = is_array($check) && is_string($check['id'] ?? null) ? $check['id'] : null;

            if ($id === null) {
                continue;
            }

            if (isset($ids[$id])) {
                throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.duplicate_id', ['path' => $path, 'id' => $id]));
            }

            $ids[$id] = true;
        }

        $versions = self::versions($data, $path);

        foreach ($data['checks'] as $position => $check) {
            // A `null` or a number reaching Check::fromArray's typed parameter is
            // a TypeError, which is a stack trace and exit 255.
            if (! is_array($check)) {
                throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.check_not_an_object', [
                    'path' => $path,
                    'type' => get_debug_type($check),
                    'position' => is_int($position) ? '#'.($position + 1) : '"'.(string) $position.'"',
                ]));
            }
        }

        $checks = array_map(Check::fromArray(...), array_values($data['checks']));

        // A static check naming a rule no code raises can never fire, and the
        // report that leaves it out reads exactly like a clean one. The opposite
        // case throws where the rule is raised.
        foreach ($checks as $check) {
            if ($check->isStatic() && ! in_array($check->rule, StaticLinter::RULES, true)) {
                throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.unknown_rule', [
                    'id' => $check->id,
                    'rule' => $check->rule === null ? Text::of('catalogue.rule_nothing') : '"'.$check->rule.'"',
                ]));
            }
        }

        // Both of these are collisions only among the checks one version runs.
        // A rule whose severity changed between Jev versions is two checks
        // naming it, separated by `since` and `until`, and they never meet.
        foreach ($versions as $version) {
            $rules = [];
            $keys = [];

            foreach ($checks as $check) {
                if (! $check->coversJev($version)) {
                    continue;
                }

                // Two checks naming one rule is worse than two sharing an id:
                // `rule()` answers with the first, and the finding is reported
                // under its id and its severity. A second check demoting the
                // first to advice takes a run that exited 1 down to 0, and the
                // report reads as a pass.
                if ($check->isStatic() && $check->rule !== null) {
                    if (isset($rules[$check->rule])) {
                        throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.rule_shadowed', [
                        'first' => $rules[$check->rule],
                        'second' => $check->id,
                        'rule' => $check->rule,
                        'jev' => $version,
                    ]));
                    }

                    $rules[$check->rule] = $check->id;
                }

                // Two ids differing only in `/` against `-` collide once
                // `answerKey()` has replaced both, so the second overwrites the
                // first in the request and is reported carrying its answer.
                if ($check->isModel()) {
                    $key = $check->answerKey();

                    if (isset($keys[$key])) {
                        throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.key_collision', [
                        'first' => $keys[$key],
                        'second' => $check->id,
                        'key' => $key,
                        'jev' => $version,
                    ]));
                    }

                    $keys[$key] = $check->id;
                }
            }
        }

        // The model half of the rule guard above. A model check is its question,
        // so one carrying none is counted among the checks that ask, listed by
        // `checks`, and never asked.
        foreach ($checks as $check) {
            if ($check->isModel() && $check->wordings === []) {
                throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.model_without_question', ['id' => $check->id]));
            }
        }

        // `applies_to` is matched against a question's type, so a primitive that
        // does not exist narrows the check to nothing. The guard in Check rejects
        // an empty list with that reasoning and then accepts any string.
        foreach ($checks as $check) {
            $unknown = array_values(array_diff($check->appliesTo, [...ReviewedQuestion::PRIMITIVES, '*']));

            if ($unknown !== []) {
                throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.unknown_primitive', [
                        'id' => $check->id,
                        'primitive' => $unknown[0],
                        'primitives' => implode(', ', ReviewedQuestion::PRIMITIVES),
                    ]));
            }
        }

        // A `supersedes` naming nothing drops the suppression it was written for,
        // and the finding it should have discarded is reported beside the one
        // that replaces it.
        $known = [];

        foreach ($checks as $check) {
            $known[$check->id] = true;
        }

        foreach ($checks as $check) {
            foreach ($check->supersedes as $superseded) {
                if (! isset($known[$superseded])) {
                    throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.supersedes_unknown', ['id' => $check->id, 'other' => $superseded]));
                }
            }
        }

        // A check written for no version the file covers can never run: a `since`
        // a release ahead of the catalogue does that.
        foreach ($checks as $check) {
            $covered = array_filter($versions, $check->coversJev(...));

            if ($covered === []) {
                throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.covers_no_version', ['id' => $check->id, 'versions' => implode(', ', $versions)]));
            }
        }

        $latest = $versions[count($versions) - 1];

        // A second fingerprint over what the checks ask, and nothing else. The
        // whole-file one moves when a message is reworded, which tells a corpus
        // its readings are stale when nothing it measured has changed.
        $asked = [];

        foreach ($data['checks'] as $check) {
            if (($check['mode'] ?? null) !== 'model') {
                continue;
            }

            // `scope` decides whether the state goes in front of the check and
            // `locate_mode` decides whether a locator is one Choice or one
            // question per level, so both change the calls without touching a
            // word of the question. `since` and `until` decide whether the check
            // is asked at all.
            $asked[] = [
                'id' => $check['id'] ?? null,
                'scope' => $check['scope'] ?? null,
                'trigger' => $check['trigger'] ?? null,
                'questions' => $check['questions'] ?? $check['question'] ?? null,
                'requires' => $check['requires'] ?? null,
                'cleared_by' => $check['cleared_by'] ?? null,
                'fired_by' => $check['fired_by'] ?? null,
                'compare' => $check['compare'] ?? null,
                'locate' => $check['locate'] ?? null,
                'locate_mode' => $check['locate_mode'] ?? null,
                'applies_to' => $check['applies_to'] ?? null,
                'since' => $check['since'] ?? null,
                'until' => $check['until'] ?? null,
            ];
        }

        return new self(
            version: (string) ($data['version'] ?? '0'),
            jev: $latest,
            versions: $versions,
            // The version moves when somebody remembers. This moves whenever the
            // file does, which is what decides whether two reports compare; the
            // `asked` digest beside it moves only when a call would change.
            fingerprint: substr(hash('sha256', (string) file_get_contents($path)), 0, 12),
            asked: substr(hash('sha256', (string) json_encode($asked)), 0, 12),
            checks: array_values(array_filter($checks, static fn (Check $c): bool => $c->coversJev($latest))),
            written: $checks,
        );
    }

    /**
     * The Jev versions the file names, oldest first.
     *
     * @param  array<string, mixed> $data
     * @return list<string>
     */
    private static function versions(array $data, string $path): array
    {
        $declared = $data['jev'] ?? null;
        $versions = is_array($declared) ? array_values(array_unique(array_filter($declared, 'is_string'))) : [];

        if ($versions === []) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.no_versions', ['path' => $path]));
        }

        foreach ($versions as $version) {
            if (preg_match(Check::VERSION, $version) !== 1) {
                throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.version_malformed', ['path' => $path, 'version' => (string) $version]));
            }
        }

        usort($versions, static fn (string $a, string $b): int => version_compare($a, $b));

        return $versions;
    }

    /**
     * The catalogue for the version this run resolves, which every command needs
     * before it does anything else.
     *
     * The command line pins the version, then the config, then the newest the
     * catalogue covers
     */
    public static function forRun(?string $flag, Config $config): self
    {
        return self::load()->forJev(
            $flag ?? $config->jev ?? self::LATEST,
            $flag !== null || $config->jev === null ? null : $config->source,
        );
    }

    /**
     * The same catalogue narrowed to the rules for one Jev version.
     *
     * A query is sent to one build, and a build has the defects it has. Checking
     * it against a later build's rules reports a defect the run will not hit.
     * `$source` is the file a version was pinned in, where one was, so a version
     * this catalogue cannot run names that file and not a flag nobody passed
     */
    public function forJev(string $requested, ?string $source = null): self
    {
        $version = $this->resolve($requested, $source);

        return new self(
            version: $this->version,
            jev: $version,
            versions: $this->versions,
            fingerprint: $this->fingerprint,
            asked: $this->asked,
            checks: array_values(array_filter($this->written, static fn (Check $c): bool => $c->coversJev($version))),
            written: $this->written,
        );
    }

    /**
     * The version a request names, with `latest` resolved.
     *
     * `$source` names where the version was written, so a version this catalogue
     * cannot run names the config file that pinned it and not a flag the caller
     * never passed
     */
    public function resolve(string $requested, ?string $source = null): string
    {
        if ($requested === self::LATEST) {
            return $this->versions[count($this->versions) - 1];
        }

        $named = ['from' => $source === null ? 'flag' : 'config', 'source' => $source ?? '', 'requested' => $requested];
        $kind = $source === null ? JevLintException::USAGE : JevLintException::CONFIG;

        if (preg_match(Check::VERSION, $requested) !== 1) {
            throw JevLintException::of($kind, Text::of('catalogue.not_a_version', $named));
        }

        // Running 1.13's rules against a 1.9 query would report defects nobody
        // measured on 1.9 and miss the ones somebody did.
        if (! in_array($requested, $this->versions, true)) {
            throw JevLintException::of($kind, Text::of('catalogue.version_not_covered', $named + [
                'versions' => implode(', ', $this->versions),
            ]));
        }

        return $requested;
    }

    /** How many of the file's checks this version does not carry */
    public function withheld(): int
    {
        return count($this->written) - count($this->checks);
    }

    /**
     * Find a file in `checks/`, whether this package is the repository or is
     * installed inside someone else's vendor directory
     */
    public static function locate(string $file): string
    {
        $fromEnv = getenv('JEVLINT_CHECKS_DIR');
        $candidates = [];

        // An override, not a preference. Falling through to the bundled copy ran
        // a CI job against a different check set than the one it had mounted.
        if (is_string($fromEnv) && $fromEnv !== '') {
            $named = rtrim($fromEnv, '/').'/'.$file;

            if (! is_file($named)) {
                throw JevLintException::of(JevLintException::NOT_FOUND, Text::of('catalogue.checks_dir_missing_file', ['dir' => $fromEnv, 'file' => $file]));
            }

            return $named;
        }

        $candidates[] = __DIR__.'/../../../checks/'.$file;
        $candidates[] = __DIR__.'/../../checks/'.$file;

        foreach ($candidates as $candidate) {
            if (is_file($candidate)) {
                return $candidate;
            }
        }

        throw JevLintException::of(JevLintException::NOT_FOUND, Text::of('catalogue.checks_not_found', ['file' => $file]));
    }

    /**
     * @return list<Check>
     */
    public function all(): array
    {
        return $this->checks;
    }

    /**
     * Every check in the file, including the ones this version does not carry
     *
     * @return list<Check>
     */
    public function written(): array
    {
        return $this->written;
    }

    /** A check by id, wherever in the file it is */
    public function findWritten(string $id): ?Check
    {
        foreach ($this->written as $check) {
            if ($check->id === $id) {
                return $check;
            }
        }

        return null;
    }

    /**
     * @return list<Check>
     */
    public function static(): array
    {
        return array_values(array_filter($this->checks, static fn (Check $check): bool => $check->isStatic()));
    }

    /**
     * Model checks in one scope, applicable to a question of this type
     *
     * @return list<Check>
     */
    public function modelChecks(string $scope, ?string $type = null): array
    {
        return array_values(array_filter(
            $this->checks,
            static fn (Check $check): bool => $check->isModel()
                && $check->scope === $scope
                && ($type === null || $check->covers($type)),
        ));
    }

    public function find(string $id): ?Check
    {
        foreach ($this->checks as $check) {
            if ($check->id === $id) {
                return $check;
            }
        }

        return null;
    }

    public function rule(string $rule): ?Check
    {
        foreach ($this->checks as $check) {
            if ($check->rule === $rule) {
                return $check;
            }
        }

        return null;
    }
}
