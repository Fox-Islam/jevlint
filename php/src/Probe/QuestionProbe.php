<?php

declare(strict_types=1);

namespace Phox\JevLint\Probe;

use Phox\JevLint\Query\ReviewedQuestion;

/** Every reading taken of one question, and what they add up to */
final class QuestionProbe
{
    /** @var list<float> */
    public array $repeats = [];

    /** @var list<Reading> */
    public array $readings = [];

    /** Movement smaller than this could not cross a threshold anybody sets */
    public const NEGLIGIBLE = 0.05;

    /** The label a Choice's probability belongs to, where the question is one */
    public ?string $reading = null;

    public function __construct(public readonly ReviewedQuestion $question) {}

    /**
     * Whether a rewrite moved the answer.
     *
     * The rule lives here so the table and the JSON cannot disagree about it:
     * movement counts when it clears both three times the repeat spread and a
     * size any threshold would notice
     */
    public function moved(Reading $reading): bool
    {
        $delta = $this->delta($reading);

        return $delta !== null && abs($delta) > 3 * $this->floor() && abs($delta) >= self::NEGLIGIBLE;
    }

    public function baseline(): ?float
    {
        if ($this->repeats === []) {
            return null;
        }

        return array_sum($this->repeats) / count($this->repeats);
    }

    /**
     * The spread of the unchanged query across its repeats.
     *
     * These repeats are sent back to back. Requests spread out over time vary
     * more than clustered ones, and nothing here sends them that way, so this is
     * a floor
     */
    public function noise(): ?float
    {
        $count = count($this->repeats);

        if ($count < 2) {
            return null;
        }

        $mean = array_sum($this->repeats) / $count;
        $sum = 0.0;

        foreach ($this->repeats as $value) {
            $sum += ($value - $mean) ** 2;
        }

        return sqrt($sum / ($count - 1));
    }

    /** The noise floor to compare against: the measured one, or the published one */
    public function floor(): float
    {
        return max($this->noise() ?? 0.0, Probe::PUBLISHED_NOISE);
    }

    public function delta(Reading $reading): ?float
    {
        $baseline = $this->baseline();

        if ($baseline === null || $reading->value === null) {
            return null;
        }

        return $reading->value - $baseline;
    }

    /** How far a variant moved the answer, in multiples of the noise floor */
    public function ratio(Reading $reading): ?float
    {
        $delta = $this->delta($reading);

        return $delta === null ? null : abs($delta) / $this->floor();
    }
}
