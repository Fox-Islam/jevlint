<?php

declare(strict_types=1);

namespace Phox\JevLint\Catalogue;

use Phox\JevLint\I18n\CheckText;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Query\Query;

use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\Report\Severity;

/**
 * One entry from `checks/catalogue.json`.
 *
 * A static check names a rule implemented in code. A model check carries the
 * Jev question that decides it, and the probability above which that question's
 * answer becomes a finding
 */
final class Check
{
    /**
     * @param list<string>              $appliesTo
     * @param array<string, mixed>|null $question
     */
    private function __construct(
        public readonly string $id,
        public readonly string $title,
        public readonly string $mode,
        public readonly string $scope,
        public readonly array $appliesTo,
        public readonly string $severity,
        public readonly ?string $rule,
        public readonly ?string $message,
        public readonly ?array $question,
        /** @var list<Wording> */
        public readonly array $wordings,
        public readonly float $trigger,
        public readonly ?string $requires,
        public readonly ?string $compare,
        public readonly string $hint,
        public readonly string $suggest,
        public readonly string $reads,
        public readonly string $action,
        public readonly ?string $locate,
        public readonly ?string $removes,
        public readonly string $locateMode,
        /** @var list<string> */
        public readonly array $supersedes,
        /**
         * The documented failure modes this check is written against.
         *
         * @var list<string>
         */
        public readonly array $jaggedness,
        /**
         * Answers that do not count as a finding, each `{answer, when}`.
         *
         * @var list<array{answer: string, when: string}>
         */
        public readonly array $suppress,
        /**
         * Whether a reading under the trigger says nothing.
         *
         * A check whose clean and defective readings overlap is reported either
         * way, because silence from it would read as a clean bill of health
         */
        public readonly bool $inconclusive,
        public readonly ?string $docs,
        public readonly string $advice,
        public readonly ?string $since,
        public readonly ?string $until,
    ) {}

    /** A Jev version, as the catalogue and the command line write one */
    public const VERSION = '/^\\d+(\\.\\d+)*$/';

    /**
     * Conditions a `suppress` entry may name.
     *
     * @var list<string>
     */
    public const SUPPRESSIONS = ['question_has_fallback_option'];

    /** The parts of a query `path()` can address */
    public const READS = ['query', 'state', 'field', 'instructions', 'criteria', 'type', 'question'];

    /**
     * @param array<string, mixed> $data
     */
    public static function fromArray(array $data): self
    {
        $trigger = $data['trigger'] ?? null;

        if ($trigger !== null && (! is_numeric($trigger) || $trigger < 0.3 || $trigger > 0.95)) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('check.trigger_out_of_range', [
                'id' => is_string($data['id'] ?? null) ? $data['id'] : '?',
                'trigger' => is_scalar($trigger) ? (string) $trigger : gettype($trigger),
            ]));
        }

        foreach (['id', 'title', 'mode', 'scope', 'severity'] as $required) {
            if (! isset($data[$required]) || ! is_string($data[$required])) {
                throw JevLintException::of(JevLintException::CATALOGUE, Text::of('check.missing_field', ['field' => $required]));
            }
        }

        // A severity nobody recognises cannot fall back to `warning`: one typo in
        // the catalogue would demote an error and a failing run would pass.
        $severities = array_map(static fn (Severity $s): string => $s->value, Severity::cases());

        if (! in_array($data['severity'], $severities, true)) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('check.bad_severity', [
                'id' => $data['id'],
                'given' => $data['severity'],
                'allowed' => implode(', ', $severities),
            ]));
        }

        $modes = ['static', 'model'];

        if (! in_array($data['mode'], $modes, true)) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('check.bad_mode', [
                'id' => $data['id'],
                'given' => $data['mode'],
                'allowed' => implode(', ', $modes),
            ]));
        }

        if ($data['mode'] === 'model' && ! isset($data['trigger'])) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('check.model_without_trigger', ['id' => $data['id']]));
        }

        // Every one of these is asked by name in the model linter. A check under
        // a scope it does not ask never runs.
        $scopes = ['question', 'state', 'state-field', 'state-once', 'query'];

        if (! in_array($data['scope'], $scopes, true)) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('check.bad_scope', [
                'id' => $data['id'],
                'given' => $data['scope'],
                'allowed' => implode(', ', $scopes),
            ]));
        }

        $appliesTo = $data['applies_to'] ?? ['*'];

        if (! is_array($appliesTo) || array_values(array_filter($appliesTo, 'is_string')) === []) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('check.applies_to_nothing', ['id' => $data['id']]));
        }

        $since = self::bound($data, 'since');
        $until = self::bound($data, 'until');

        if ($since !== null && $until !== null && version_compare($since, $until, '>')) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('check.empty_version_span', ['id' => $data['id'], 'since' => $since, 'until' => $until]));
        }

        $translated = CheckText::for($data['id']);

        return new self(
            id: $data['id'],
            title: $translated['title'] ?? $data['title'],
            mode: $data['mode'],
            scope: $data['scope'],
            appliesTo: array_values(array_filter($appliesTo, 'is_string')),
            severity: $data['severity'],
            rule: is_string($data['rule'] ?? null) ? $data['rule'] : null,
            message: $translated['message'] ?? (is_string($data['message'] ?? null) ? $data['message'] : null),
            question: is_array($data['question'] ?? null) ? $data['question'] : null,
            wordings: self::readWordings($data),
            trigger: is_numeric($data['trigger'] ?? null) ? (float) $data['trigger'] : 0.7,
            requires: is_string($data['requires'] ?? null) ? $data['requires'] : null,
            compare: is_string($data['compare'] ?? null) ? $data['compare'] : null,
            hint: $translated['hint'] ?? (is_string($data['hint'] ?? null) ? $data['hint'] : ''),
            suggest: $translated['suggest'] ?? (is_string($data['suggest'] ?? null) ? $data['suggest'] : ''),
            reads: self::reads($data),
            action: is_string($data['action'] ?? null) ? $data['action'] : 'rewrite',
            locate: is_string($data['locate'] ?? null) ? $data['locate'] : null,
            removes: is_string($data['removes'] ?? null) ? $data['removes'] : null,
            locateMode: is_string($data['locate_mode'] ?? null) ? $data['locate_mode'] : 'pick',
            supersedes: is_array($data['supersedes'] ?? null)
                ? array_values(array_filter($data['supersedes'], 'is_string'))
                : [],
            jaggedness: is_array($data['jaggedness'] ?? null)
                ? array_values(array_filter($data['jaggedness'], 'is_string'))
                : [],
            suppress: self::suppressions($data),
            inconclusive: ($data['inconclusive'] ?? false) === true,
            docs: is_string($data['docs'] ?? null) ? $data['docs'] : null,
            advice: is_string($data['advice'] ?? null) ? $data['advice'] : '',
            since: $since,
            until: $until,
        );
    }

    /**
     * One end of the range of Jev versions a check is written for.
     *
     * @param array<string, mixed> $data
     */
    private static function bound(array $data, string $key): ?string
    {
        $value = $data[$key] ?? null;

        if ($value === null) {
            return null;
        }

        if (! is_string($value) || preg_match(self::VERSION, $value) !== 1) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('check.bad_version', [
                'id' => is_string($data['id'] ?? null) ? $data['id'] : '?',
                'field' => $key,
                'given' => is_scalar($value) ? '"'.$value.'"' : gettype($value),
            ]));
        }

        return $value;
    }

    /**
     * Whether this check is one of the rules for this Jev version.
     *
     * A defect one build reads past is a defect the next one may not have, so a
     * check retired by `until` keeps working for the versions it was written for
     */
    public function coversJev(string $version): bool
    {
        if ($this->since !== null && version_compare($version, $this->since, '<')) {
            return false;
        }

        return $this->until === null || version_compare($version, $this->until, '<=');
    }

    /**
     * Every way this check can be asked.
     *
     * `question` holds one wording, `questions` holds several. Several go in the
     * same call, so they cost the questions but not a round trip, and their
     * answers are combined
     *
     * @param  array<string, mixed> $data
     * @return list<Wording>
     */
    private static function readWordings(array $data): array
    {
        $questions = $data['questions'] ?? null;

        if (is_array($questions) && $questions !== []) {
            return array_values(array_map(
                static fn (mixed $q): Wording => Wording::fromArray(is_array($q) ? $q : []),
                $questions,
            ));
        }

        $question = $data['question'] ?? null;

        return is_array($question) ? [Wording::fromArray($question)] : [];
    }

    /** Whether this check is asked more than one way */
    public function isComposite(): bool
    {
        return count($this->wordings) > 1;
    }

    /**
     * @param  array<string, mixed> $data
     * @return list<array{answer: string, when: string}>
     */
    private static function suppressions(array $data): array
    {
        $rules = [];

        foreach (is_array($data['suppress'] ?? null) ? $data['suppress'] : [] as $rule) {
            if (! is_array($rule) || ! is_string($rule['answer'] ?? null) || ! is_string($rule['when'] ?? null)) {
                throw JevLintException::of(JevLintException::CATALOGUE, Text::of('check.bad_suppress_entry', [
                'id' => is_string($data['id'] ?? null) ? $data['id'] : '?',
            ]));
            }

            if (! in_array($rule['when'], self::SUPPRESSIONS, true)) {
                throw JevLintException::of(JevLintException::CATALOGUE, Text::of('check.unknown_suppression', [
                'id' => is_string($data['id'] ?? null) ? $data['id'] : '?',
                'given' => $rule['when'],
                'allowed' => implode(', ', self::SUPPRESSIONS),
            ]));
            }

            $rules[] = ['answer' => $rule['answer'], 'when' => $rule['when']];
        }

        return $rules;
    }

    /**
     * Which part of the query a check looks at, checked against what `path()`
     * knows how to address. A typo would fall through to the default arm and
     * report a pointer to the question instead of the node, which reads as a
     * real value
     *
     * @param array<string, mixed> $data
     */
    private static function reads(array $data): string
    {
        $reads = $data['reads'] ?? 'question';

        if (! is_string($reads) || ! in_array($reads, self::READS, true)) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('check.unknown_reads', [
                'id' => is_string($data['id'] ?? null) ? $data['id'] : '?',
                'given' => is_scalar($reads) ? (string) $reads : get_debug_type($reads),
                'allowed' => implode(', ', self::READS),
            ]));
        }

        return $reads;
    }

    /**
     * Where in the query file the finding points, as a JSON pointer.
     *
     * An agent patching a query needs the node, not the question id
     */
    public function path(string $target, ?string $field = null): string
    {
        return match ($this->reads) {
            'query' => '',
            'state' => '/state',
            'field' => '/state'.self::pointer($field ?? ''),
            'instructions' => '/questions/'.self::escape($target).'/instructions',
            'criteria' => '/questions/'.self::escape($target).'/criteria',
            'type' => '/questions/'.self::escape($target).'/type',
            // `reads` is checked against READS at load, so this is `question`
            // and not a typo that fell through.
            default => '/questions/'.self::escape($target),
        };
    }

    /**
     * A dotted field path as an RFC 6901 pointer.
     *
     * `application.role` addresses `/application/role`, and a `/` or `~` inside
     * a key is escaped so a key containing one still resolves.
     */
    private static function pointer(string $dotted): string
    {
        if ($dotted === '') {
            return '';
        }

        return '/'.implode('/', array_map(self::escape(...), Query::segments($dotted)));
    }

    /**
     * One segment of an RFC 6901 pointer.
     *
     * A question id is a key somebody chose, so it can hold a `/` or a `~`, and
     * an unescaped one addresses a different node or none at all.
     */
    public static function escape(string $segment): string
    {
        return str_replace(['~', '/'], ['~0', '~1'], $segment);
    }

    public function isStatic(): bool
    {
        return $this->mode === 'static';
    }

    public function isModel(): bool
    {
        return $this->mode === 'model';
    }

    /** Whether this check has anything to say about a question of this type */
    public function covers(string $type): bool
    {
        return in_array('*', $this->appliesTo, true) || in_array($type, $this->appliesTo, true);
    }

    /** The key this check's answer comes back under, with `/` and `-` mapped to `_` */
    public function answerKey(): string
    {
        return str_replace(['/', '-'], '_', $this->id);
    }

    /** The question type this check asks, for a model check */
    public function questionType(): string
    {
        return $this->wordings[0]->type ?? 'noul';
    }

    /**
     * The check's own instructions, with `{field}` replaced where the check is
     * asked once per state field
     */
    public function instructions(string $field = ''): string
    {
        return isset($this->wordings[0]) ? $this->wordings[0]->instructions($field) : '';
    }

    /**
     * @return array<string, mixed>|list<mixed>|null
     */
    public function criteria(): ?array
    {
        return $this->wordings[0]->criteria ?? null;
    }
}
