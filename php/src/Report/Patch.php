<?php

declare(strict_types=1);

namespace Phox\JevLint\Report;

/**
 * A change to the query file that a program can apply without reading it.
 *
 * Only a defect that is purely a shape gets one: turning a Choice's criteria
 * from a list into a map is a data transform, while rewriting a question is a
 * judgement about a subject the linter has not seen
 */
final class Patch
{
    /** Nothing the author wrote is lost, so a loop can apply it unattended */
    public const LOSSLESS = 'lossless';

    /** It keeps the content and drops something around it, so read it first */
    public const LOSSY = 'lossy';

    /** It takes something out of the query, so a person decides */
    public const DESTRUCTIVE = 'destructive';

    /**
     * @param 'replace'|'add'|'remove'                     $op
     * @param self::LOSSLESS|self::LOSSY|self::DESTRUCTIVE  $safety a `remove` is always destructive
     */
    public readonly string $safety;

    public function __construct(
        public readonly string $op,
        public readonly string $path,
        public readonly mixed $value = null,
        string $safety = self::LOSSLESS,
    ) {
        // Taking a node out is destructive whatever the caller passed, so the
        // classification a fixer gates on cannot be wrong by omission.
        $this->safety = $op === 'remove' ? self::DESTRUCTIVE : $safety;
    }

    /**
     * @return array{op: string, path: string, safety: string, value?: mixed}
     */
    public function toArray(): array
    {
        // What kind of change this is, as a field. `suggest_kind: "patch"` only
        // restates that a patch exists, so a loop applying patches unattended had
        // no way to tell a key rename from deleting somebody's question.
        $row = ['op' => $this->op, 'path' => $this->path, 'safety' => $this->safety];

        return $this->op === 'remove' ? $row : $row + ['value' => $this->value];
    }

    /**
     * Nodes a query always writes as an object, whatever their keys look like.
     *
     * @var list<string>
     */
    private const OBJECTS = ['questions', 'criteria', 'state'];

    /**
     * Apply this to a decoded query, so a caller can act on it and re-check.
     *
     * @param  array<string, mixed> $query
     * @return array<string, mixed>
     */
    public function applyTo(array $query): array
    {
        $parts = array_map(
            static fn (string $p): string => str_replace(['~1', '~0'], ['/', '~'], $p),
            array_slice(explode('/', $this->path), 1),
        );

        $applied = $this->at($query, $parts, true);

        return is_array($applied) ? $applied : $query;
    }

    /**
     * The node with this patch applied at `$parts`.
     *
     * A map whose remaining keys run 0, 1, 2 is a PHP list, and `json_encode`
     * writes it as a JSON array. `questions` and `criteria` are objects keyed by
     * names the caller chose, so removing from one has to keep it an object;
     * `stdClass` is what carries that through the encoder.
     *
     * @param  list<string> $parts
     * @param  bool         $isObject whether this node is an object by contract
     */
    private function at(mixed $node, array $parts, bool $isObject): mixed
    {
        $map = $node instanceof \stdClass ? (array) $node : $node;

        if (! is_array($map)) {
            return $this->op === 'remove' ? $node : $node;
        }

        // `{"0": ..., "1": ...}` decodes to a PHP list, so the value cannot say
        // whether it was an object. These three are objects in every query, and
        // that is what decides it.
        $wasObject = $isObject || $node instanceof \stdClass || ! array_is_list($map);
        $part = $parts[0];

        if (count($parts) === 1) {
            if ($this->op === 'remove') {
                unset($map[$part]);
            } else {
                $map[$part] = $this->value;
            }

            return $this->shape($map, $wasObject);
        }

        if (! isset($map[$part]) || ! (is_array($map[$part]) || $map[$part] instanceof \stdClass)) {
            // Creating the path is right for `add`, which is putting something
            // where nothing is. For `remove` there is nothing to delete from.
            if ($this->op === 'remove') {
                return $node;
            }

            $map[$part] = [];
        }

        $map[$part] = $this->at(
            $map[$part],
            array_slice($parts, 1),
            in_array($part, self::OBJECTS, true),
        );

        return $this->shape($map, $wasObject);
    }

    /**
     * @param array<array-key, mixed> $map
     */
    private function shape(array $map, bool $wasObject): mixed
    {
        return $wasObject && array_is_list($map) ? (object) $map : $map;
    }
}
