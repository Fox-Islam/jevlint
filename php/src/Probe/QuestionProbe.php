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

    /**
     * How near the middle a yes/no answer sits before the threshold reading it
     * decides the outcome.
     *
     * A Noul answers with the probability of yes, and a caller turns that into
     * a decision at a threshold of their own. This band is a judgement and not
     * a measured figure: no corpus run sets it, and the probe reports what it
     * covers without gating on it
     */
    public const UNDECIDED = 0.15;

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

    /**
     * Whether the query as written failed to decide this question.
     *
     * Only a Noul has a middle. A Choice reports the winning label's own
     * probability and a Score a position on its scale, and neither is undecided
     * for sitting halfway
     */
    public function undecided(): bool
    {
        $baseline = $this->baseline();

        return $this->question->type === 'noul'
            && $baseline !== null
            && abs($baseline - 0.5) <= self::UNDECIDED;
    }

    /**
     * Whether the repeats of the unchanged query fell on both sides of the
     * middle, so the answer did not hold still from one send to the next
     */
    public function flips(): bool
    {
        if ($this->question->type !== 'noul' || count($this->repeats) < 2) {
            return false;
        }

        return min($this->repeats) <= 0.5 && max($this->repeats) > 0.5;
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
