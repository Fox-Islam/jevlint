<?php

declare(strict_types=1);

namespace Phox\JevLint\Report;

/** One change a query needs, and the evidence for it */
final class Finding
{
    public function __construct(
        public readonly string $checkId,
        public readonly string $title,
        public readonly Severity $severity,
        public readonly string $target,
        public readonly string $message,
        public readonly string $hint = '',
        public readonly string $suggest = '',
        public readonly string $mode = 'static',
        public readonly string $action = 'rewrite',
        public readonly string $path = '',
        public readonly ?float $trigger = null,
        public readonly ?float $spread = null,
        public readonly bool $nearTrigger = false,
        /** @var list<string> */
        public readonly array $supersedes = [],
        public readonly ?string $docs = null,
        public readonly ?float $probability = null,
        public readonly ?string $evidence = null,
        /** @var list<float> */
        public readonly array $readings = [],
        public readonly ?string $readingsOf = null,
        public readonly ?string $suggestedType = null,
        /** @var list<string> */
        public readonly array $paths = [],
        public readonly ?Patch $patch = null,
        /** What the self-test measured about this check's own suggestion, where it is weak */
        public readonly string $advice = '',
        /**
         * Why a reading above the trigger is not a finding.
         *
         * A cleared entry carries a number and a trigger and nothing else, so a
         * reading the catalogue sets aside looks like a defect that got away
         */
        public readonly string $clearedBecause = '',
        /**
         * What the number on this finding is. Every check but one reports a
         * calibrated probability that the defect is present; `question/type-mismatch`
         * asks which primitive fits and reports the weight on the one it picked,
         * which is not a probability of anything being wrong
         */
        public readonly string $measure = 'probability',
        public readonly bool $fired = true,
        public readonly ?string $accepted = null,
        public readonly bool $unstable = false,
    ) {}

    /**
     * The same finding, marked as one somebody has decided to live with.
     *
     * Every property is listed because a readonly one cannot be reassigned on a
     * clone, so a property added and not listed here falls back to its default.
     * FindingCarriesEveryFieldTest fails when one is missed
     */
    public function acceptedBecause(string $reason): self
    {
        return new self(
            checkId: $this->checkId,
            title: $this->title,
            severity: $this->severity,
            target: $this->target,
            message: $this->message,
            hint: $this->hint,
            suggest: $this->suggest,
            mode: $this->mode,
            action: $this->action,
            path: $this->path,
            trigger: $this->trigger,
            spread: $this->spread,
            nearTrigger: $this->nearTrigger,
            supersedes: $this->supersedes,
            docs: $this->docs,
            probability: $this->probability,
            evidence: $this->evidence,
            readings: $this->readings,
            readingsOf: $this->readingsOf,
            suggestedType: $this->suggestedType,
            paths: $this->paths,
            patch: $this->patch,
            clearedBecause: $this->clearedBecause,
            measure: $this->measure,
            advice: $this->advice,
            fired: $this->fired,
            accepted: $reason,
            unstable: $this->unstable,
        );
    }

    /** Whether a model decided this, instead of a rule in code */
    public function fromModel(): bool
    {
        return $this->probability !== null;
    }

    /**
     * A probability as it is reported.
     *
     * A mean over three readings comes out of the float as 0.07500000000000001,
     * and a consumer comparing two reports is reading noise the model never put
     * there. Four places is finer than anything the readings carry
     */
    private static function reported(?float $value): ?float
    {
        return $value === null ? null : round($value, 4);
    }

    /**
     * @return array<string, mixed>
     */
    public function toArray(): array
    {
        // A check that cleared is a measurement, not advice. Giving it the shape
        // of a finding invites a reader to act on an argument against acting.
        if (! $this->fired) {
            return array_filter([
                'check' => $this->checkId,
                'path' => $this->path,
                'probability' => self::reported($this->probability),
                'trigger' => $this->trigger,
                'readings' => $this->readings === [] ? null : array_map(self::reported(...), $this->readings),
                'cleared_because' => $this->clearedBecause === '' ? null : $this->clearedBecause,
                // A cleared entry carries none of the fields that tell you to
                // act, but this one says what the reading cannot tell you, which
                // is exactly what a clear reading needs beside it.
                'advice_caveat' => $this->advice === '' ? null : $this->advice,
            ], static fn (mixed $value): bool => $value !== null && $value !== '')
                + [
                    'target' => $this->target,
                    'near_trigger' => $this->nearTrigger,
                    // Present on both shapes. An entry in `unstable` needs the
                    // key most, so it cannot be the one shape that omits it.
                    'unstable' => $this->unstable,
                    'fired' => false,
                ];
        }

        return array_filter([
            'check' => $this->checkId,
            'title' => $this->title,
            'severity' => $this->severity->value,
            'mode' => $this->mode,
            'action' => $this->action,
            'path' => $this->path,
            'message' => $this->message,
            'hint' => $this->hint,
            'suggest' => $this->suggest,
            'suggest_kind' => $this->suggest === '' ? null : ($this->patch === null ? 'guidance' : 'patch'),
            'advice_caveat' => $this->advice === '' ? null : $this->advice,
            'docs' => $this->docs,
            'probability' => $this->measure === 'probability' ? self::reported($this->probability) : null,
            'weight' => $this->measure === 'weight' ? self::reported($this->probability) : null,
            'trigger' => $this->trigger,
            'spread' => self::reported($this->spread),
            'supersedes' => $this->supersedes === [] ? null : $this->supersedes,
            'evidence' => $this->evidence,
            'readings' => $this->readings === [] ? null : array_map(self::reported(...), $this->readings),
            'readings_of' => $this->readingsOf,
            'suggested_type' => $this->suggestedType,
            'paths' => $this->paths === [] ? null : $this->paths,
            'patch' => $this->patch?->toArray(),
            'accepted' => $this->accepted,
        ], static fn (mixed $value): bool => $value !== null && $value !== '')
            + [
                // Always present, both of them. `near_trigger: false` says the
                // reading is clear of its trigger; an absent key says nothing,
                // and a caller has no way to tell which was meant.
                // A question id is a key somebody chose, and "" is a key. The
                // filter above drops an empty string, which would take the
                // required `target` out for the one query that has one.
                'target' => $this->target,
                'measure' => $this->measure,
                'near_trigger' => $this->nearTrigger,
                'unstable' => $this->unstable,
                'fired' => true,
            ];
    }
}
