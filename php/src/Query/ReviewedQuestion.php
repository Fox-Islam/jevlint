<?php

declare(strict_types=1);

namespace Phox\JevLint\Query;

use Phox\JevLint\I18n\Text;
use Phox\JevLint\Support\Json;

/** One question from the query under review */
final class ReviewedQuestion
{
    /**
     * @param string|array<array-key, mixed>|null $instructions
     * @param array<array-key, mixed>|null        $criteria
     * @param array<string, mixed>                $raw
     * @param bool|null                           $criteriaWasObject what the JSON said, where the JSON is known
     */
    public function __construct(
        public readonly string $id,
        public readonly string $type,
        public readonly string|array|null $instructions,
        public readonly array|null $criteria,
        public readonly array $raw,
        private readonly ?bool $criteriaWasObject = null,
    ) {}

    /**
     * The same question with other criteria, for a probe variant.
     *
     * @param array<array-key, mixed>|null $criteria
     */
    public function withCriteria(?array $criteria): self
    {
        return new self($this->id, $this->type, $this->instructions, $criteria, $this->raw, $this->criteriaWasObject);
    }

    /** The same question asked in other words */
    public function withInstructions(string $instructions): self
    {
        return new self($this->id, $this->type, $instructions, $this->criteria, $this->raw, $this->criteriaWasObject);
    }

    /**
     * @param array<string, mixed> $data
     */
    public static function fromArray(string $id, array $data, ?bool $criteriaWasObject = null): self
    {
        $type = $data['type'] ?? '';
        $instructions = $data['instructions'] ?? null;
        $criteria = $data['criteria'] ?? null;

        return new self(
            id: $id,
            type: is_string($type) ? strtolower($type) : '',
            instructions: is_string($instructions) || is_array($instructions) ? $instructions : null,
            criteria: is_array($criteria) ? $criteria : null,
            raw: $data,
            criteriaWasObject: $criteriaWasObject,
        );
    }

    /**
     * Whether `criteria` was written as a JSON array.
     *
     * `json_decode(..., true)` turns `{"0":"a","1":"b"}` into a PHP list, so
     * `array_is_list` cannot tell an object with counting keys from an array.
     * The API can, and rejects the wrong one, so the shape is taken from the
     * JSON itself wherever the JSON is what the query came from.
     */
    public function criteriaIsList(): bool
    {
        if ($this->criteriaWasObject !== null) {
            return ! $this->criteriaWasObject;
        }

        return is_array($this->criteria) && array_is_list($this->criteria);
    }

    /** The instructions as one string, whatever structure they were given in */
    public function instructionsText(): string
    {
        if ($this->instructions === null) {
            return '';
        }

        return is_string($this->instructions) ? $this->instructions : Json::inline($this->instructions);
    }

    public function hasCriteria(): bool
    {
        return $this->criteria !== null && $this->criteria !== [];
    }

    /**
     * Whether a Choice carries an option for what the others do not cover.
     *
     * A Score's levels are steps along one quality and cannot hold one, so this
     * is evidence the question is a Choice whatever else it looks like.
     */
    public function hasFallbackOption(): bool
    {
        if ($this->type !== 'choice' || ! is_array($this->criteria)) {
            return false;
        }

        $labels = array_map(
            static fn (int|string $k): string => mb_strtolower((string) $k),
            array_keys($this->criteria),
        );

        if (array_intersect($labels, Text::list('words.fallback_labels')) !== []) {
            return true;
        }

        // A catch-all can be called anything. Matching only a list of labels
        // missed one named `misc` and offered to add a second one beside it,
        // which splits the mass the catch-all exists to collect. What makes an
        // option a catch-all is what its description says it holds.
        foreach ($this->criteria as $description) {
            if (! is_string($description)) {
                continue;
            }

            $text = mb_strtolower($description);

            foreach (Text::list('words.catch_all_phrases') as $phrase) {
                if (str_contains($text, $phrase)) {
                    return true;
                }
            }
        }

        return false;
    }

    /**
     * The primitives Jev takes. The catalogue is checked against this list, so a
     * check narrowed to a primitive that does not exist is refused at load
     */
    public const PRIMITIVES = ['noul', 'choice', 'score'];

    public function isKnownType(): bool
    {
        return in_array($this->type, self::PRIMITIVES, true);
    }

    /**
     * What a question-scoped check is shown.
     *
     * The id is left out: Jev never sees it when the query runs, so the checker
     * should not see it either, or a well-named id papers over an instruction
     * that says nothing. The declared type is left out for a second reason -
     * `question/type-mismatch` works out which primitive fits the answer, and
     * naming the declared one in the state hands it what it is meant to decide.
     * Which checks apply to which type is settled in code before the call
     *
     * @return array<string, mixed>
     */
    public function asState(): array
    {
        $state = [
            'instructions' => $this->instructions ?? '',
        ];

        if ($this->hasCriteria()) {
            $state['criteria'] = $this->criteria;
        }

        return $state;
    }
}
