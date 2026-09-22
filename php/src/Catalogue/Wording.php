<?php

declare(strict_types=1);

namespace Phox\JevLint\Catalogue;

/**
 * One way of asking a check.
 *
 * A check may carry several. They are meant to mean the same thing, so the
 * spread between their answers is reported with the finding as its error bar
 */
final class Wording
{
    /**
     * @param array<string, mixed>|list<mixed>|null $criteria
     */
    public function __construct(
        public readonly string $type,
        public readonly string $instructions,
        public readonly ?array $criteria,
    ) {}

    /**
     * @param array<string, mixed> $data
     */
    public static function fromArray(array $data): self
    {
        $type = $data['type'] ?? 'noul';
        $instructions = $data['instructions'] ?? '';
        $criteria = $data['criteria'] ?? null;

        return new self(
            type: is_string($type) ? $type : 'noul',
            instructions: is_string($instructions) ? $instructions : '',
            criteria: is_array($criteria) ? $criteria : null,
        );
    }

    /** The instructions with `{field}` filled in, where the check is asked per state field */
    public function instructions(string $field = ''): string
    {
        return str_replace('{field}', $field, $this->instructions);
    }
}
