<?php

declare(strict_types=1);

namespace Phox\JevLint\SelfTest;

use Phox\JevLint\Catalogue\Check;

/** What one check scored against its own clean and broken examples */
final class CheckScore
{
    public function __construct(
        public readonly Check $check,
        public readonly ?float $clean,
        public readonly ?float $broken,
        public readonly ?float $fixed = null,
        public readonly string $domain = '',
        /**
         * Whether the fixture shipped a `fixed` example at all.
         *
         * Without it, a `fixed` call that failed and a check that ships no
         * rewrite are both `null`, and only the second is a pass
         */
        public readonly bool $offersFixed = false,
    ) {}

    public function span(): ?float
    {
        if ($this->clean === null || $this->broken === null) {
            return null;
        }

        return $this->broken - $this->clean;
    }

    /**
     * `flat` and `inverted` mean the check is not measuring what it claims.
     * `fires-on-clean` and `misses-broken` mean it is, but the trigger is in
     * the wrong place
     */
    public function verdict(): string
    {
        $span = $this->span();

        // Before anything about the readings: a run that lost a call did not
        // measure this check, and reporting a catalogue as wrong on the strength
        // of a call that never came back sends the reader to the wrong file.
        if ($span === null || ($this->offersFixed && $this->fixed === null)) {
            return 'errored';
        }

        // A suggestion that leaves the check firing sends the reader in a circle
        if ($this->fixed !== null && $this->fixed > $this->check->trigger) {
            return 'suggestion-fails';
        }

        if ($span < 0) {
            return 'inverted';
        }

        if ($span < SelfTest::FLAT) {
            return 'flat';
        }

        if ($this->clean !== null && $this->clean > $this->check->trigger) {
            return 'fires-on-clean';
        }

        if ($this->broken !== null && $this->broken <= $this->check->trigger) {
            return 'misses-broken';
        }

        return $span < SelfTest::WEAK ? 'weak' : 'ok';
    }

    public function passed(): bool
    {
        return in_array($this->verdict(), ['ok', 'weak'], true);
    }

    /** The check was never scored, because the call carrying it did not come back */
    public function errored(): bool
    {
        return $this->verdict() === 'errored';
    }

    /**
     * @return array<string, mixed>
     */
    public function toArray(): array
    {
        return [
            'check' => $this->check->id,
            'domain' => $this->domain === '' ? null : $this->domain,
            'trigger' => $this->check->trigger,
            'clean' => $this->clean,
            'broken' => $this->broken,
            'fixed' => $this->fixed,
            'span' => $this->span(),
            'verdict' => $this->verdict(),
        ];
    }
}
