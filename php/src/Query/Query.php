<?php

declare(strict_types=1);

namespace Phox\JevLint\Query;

use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Support\Json;

/**
 * A Jev query as it would be sent: one state and the questions asked about it.
 *
 * The file format is the request body, so what you already send is what you
 * check. A `model` key is read if present and otherwise ignored
 */
final class Query
{
    /**
     * @param array<string, mixed>|list<mixed>|string|null $state
     * @param list<ReviewedQuestion>                       $questions
     * @param array<array-key, mixed>                      $raw the request as it was written
     */
    private function __construct(
        public readonly string|array|null $state,
        public readonly array $questions,
        public readonly ?string $model,
        public readonly string $source,
        public readonly array $raw = [],
    ) {}

    /**
     * The same query against state from somewhere else, for `probe --state`.
     *
     * @param array<array-key, mixed> $state
     */
    public function withState(array $state): self
    {
        return new self($state, $this->questions, $this->model, $this->source, ['state' => $state] + $this->raw);
    }

    public static function fromFile(string $path): self
    {
        return self::fromJson(Json::contents($path), $path);
    }

    /**
     * A query from the request body as it was written.
     *
     * `criteria` written as a JSON object and as a JSON array are different
     * requests, and `json_decode` to an associative array loses which one it
     * was, so a caller holding the body keeps more than one that has decoded it
     */
    public static function fromJson(string $json, string $source = 'query'): self
    {
        $shape = Json::shapeOf($json);

        // `[]` decodes to a PHP array like an object does, so a JSON list reached
        // the checks and came back as `query/no-questions` instead of a shape error.
        if (is_array($shape)) {
            throw JevLintException::of(JevLintException::QUERY, Text::of('query.is_a_list', ['source' => $source]));
        }

        return self::fromArray(Json::decode($json, $source), $source, $shape);
    }

    /**
     * Which questions wrote their `criteria` as a JSON object.
     *
     * @return array<string, bool>
     */
    private static function criteriaShapes(mixed $shape): array
    {
        $shapes = [];
        $questions = is_object($shape) ? ($shape->questions ?? null) : null;

        if (! is_object($questions)) {
            return $shapes;
        }

        foreach (get_object_vars($questions) as $id => $question) {
            if (is_object($question) && property_exists($question, 'criteria')) {
                $shapes[(string) $id] = is_object($question->criteria);
            }
        }

        return $shapes;
    }

    /**
     * @param array<array-key, mixed> $data
     */
    public static function fromArray(array $data, string $source = 'query', mixed $shape = null): self
    {
        $shapes = self::criteriaShapes($shape);

        $questions = $data['questions'] ?? null;

        // Whether this was written as an object has to come from the JSON, for the
        // same reason `criteria` does: `{"0": {...}, "1": {...}}` decodes to a PHP
        // list, and rejecting it refused ids the API accepts.
        $wasObject = is_object($shape) && isset($shape->questions) ? is_object($shape->questions) : null;

        if ($questions !== null && (! is_array($questions) || ($wasObject === false && $questions !== []))) {
            throw JevLintException::of(JevLintException::QUERY, Text::of('query.questions_is_a_list', ['source' => $source]));
        }

        $reviewed = [];

        foreach ($questions ?? [] as $id => $question) {
            if (! is_array($question)) {
                throw JevLintException::of(JevLintException::QUERY, Text::of('query.question_not_an_object', ['source' => $source, 'id' => (string) $id]));
            }

            $reviewed[] = ReviewedQuestion::fromArray((string) $id, $question, $shapes[(string) $id] ?? null);
        }

        $state = $data['state'] ?? null;

        // A number or a boolean here is a request the API rejects. Coercing it to
        // null reported the query as carrying no state, which is a different
        // defect and one the caller can exit 0 on.
        if ($state !== null && ! is_string($state) && ! is_array($state)) {
            throw JevLintException::of(JevLintException::QUERY, Text::of('query.state_wrong_type', [
                'source' => $source,
                'holds' => match (gettype($state)) {
                    'integer', 'double' => Text::of('query.state_a_number'),
                    'boolean' => Text::of('query.state_a_boolean'),
                    default => 'a '.gettype($state),
                },
            ]));
        }

        $model = $data['model'] ?? null;

        return new self(
            raw: $data,
            state: $state,
            questions: $reviewed,
            model: is_string($model) ? $model : null,
            source: $source,
        );
    }

    public function hasState(): bool
    {
        return $this->state !== null && $this->state !== '' && $this->state !== [];
    }

    /**
     * State as a JSON object, or null when it is a bare string
     *
     * @return array<array-key, mixed>|null
     */
    public function stateFields(): ?array
    {
        return is_array($this->state) && ! array_is_list($this->state) ? $this->state : null;
    }

    /**
     * The removable parts of the state, by dotted path.
     *
     * A state is commonly one object holding everything, so stopping at the top
     * level would ask whether that object is needed and never get a useful
     * answer. Nesting is followed to `$depth` levels, however wide each one is:
     * a width limit would blind this on exactly the states it exists for
     *
     * @return list<string>
     */
    public function stateLeaves(int $depth = 2): array
    {
        $fields = $this->stateFields();

        return $fields === null ? [] : $this->walk($fields, '', $depth);
    }

    /**
     * @param  array<array-key, mixed> $node
     * @return list<string>
     */
    private function walk(array $node, string $prefix, int $depth): array
    {
        $paths = [];

        foreach ($node as $key => $value) {
            $path = $prefix === '' ? self::quote((string) $key) : $prefix.'.'.self::quote((string) $key);

            // Descend on size, not in spite of it. A width limit blinds the field
            // checks on exactly the states they exist for: the bigger the object,
            // the fewer fields they see, and a fifteen-field object reads as one
            // field nobody reads.
            $nest = $depth > 1 && is_array($value) && ! array_is_list($value);

            if ($nest) {
                /** @var array<array-key, mixed> $value */
                $paths = [...$paths, ...$this->walk($value, $path, $depth - 1)];

                continue;
            }

            $paths[] = $path;
        }

        return $paths;
    }

    /**
     * A key with the separator in it, made safe to join with.
     *
     * A state key can hold a `.`, so joining it into a dotted path unescaped is
     * indistinguishable from nesting: the field `a.b` reads as `a` containing
     * `b`, and addresses a node that is not there.
     */
    public static function quote(string $segment): string
    {
        return str_replace(['\\', '.'], ['\\\\', '\\.'], $segment);
    }

    /**
     * A dotted path back into the keys it was built from.
     *
     * @return list<string>
     */
    public static function segments(string $path): array
    {
        $parts = [];
        $current = '';
        $escaped = false;

        foreach (str_split($path) as $char) {
            if ($escaped) {
                $current .= $char;
                $escaped = false;

                continue;
            }

            if ($char === '\\') {
                $escaped = true;
            } elseif ($char === '.') {
                $parts[] = $current;
                $current = '';
            } else {
                $current .= $char;
            }
        }

        $parts[] = $current;

        return $parts;
    }

    public function stateAt(string $path): mixed
    {
        $node = $this->stateFields();

        foreach (self::segments($path) as $part) {
            if (! is_array($node) || ! array_key_exists($part, $node)) {
                return null;
            }

            $node = $node[$part];
        }

        return $node;
    }

    public function stateSize(): int
    {
        // The threshold is described in characters, and `strlen` counts bytes, so
        // an accented state hit the limit at about half the stated budget.
        return mb_strlen(Json::inline($this->state ?? ''));
    }

    /**
     * The state a state-scoped check is shown: the question it is about, and
     * the material itself, each under a name the check can point at
     *
     * @return array<string, mixed>
     */
    public function stateWith(ReviewedQuestion $question): array
    {
        return [
            'question' => $question->instructionsText(),
            'state' => $this->state,
        ];
    }

    /**
     * The same query narrowed to some of its questions, for a cheap re-check
     *
     * @param list<string> $ids
     */
    public function only(array $ids): self
    {
        if ($ids === []) {
            return $this;
        }

        return new self(
            $this->state,
            array_values(array_filter($this->questions, static fn (ReviewedQuestion $q): bool => in_array($q->id, $ids, true))),
            $this->model,
            $this->source,
            $this->raw,
        );
    }

    public function question(string $id): ?ReviewedQuestion
    {
        foreach ($this->questions as $question) {
            if ($question->id === $id) {
                return $question;
            }
        }

        return null;
    }
}
