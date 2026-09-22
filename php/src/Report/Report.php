<?php

declare(strict_types=1);

namespace Phox\JevLint\Report;

use Phox\JevLint\Config\Config;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Support\Cause;

/** What one run of the linter found, and what it cost */
final class Report
{
    /** @var list<Finding> */
    private array $findings = [];

    /** @var list<Note> */
    private array $notes = [];

    private ?Config $config = null;

    /** @var array<string, int> */
    private array $order = [];

    private int $calls = 0;

    private int $callsWithoutUsage = 0;

    /** @var array<string, true> */
    private array $answeredBy = [];

    /** Checks this run put to a query or to the model */
    private int $asked = 0;

    /** @var array<string, array<string, true>> */
    private array $expected = [];

    /** @var array<string, array<string, true>> */
    private array $reached = [];

    private int $tokens = 0;

    public function __construct(
        public readonly string $source,
        public readonly string $catalogueVersion,
        public readonly string $model = 'jev-1.13',
        public readonly string $fingerprint = '',
        /** A fingerprint over what the checks ask, which a reworded message does not move */
        public readonly string $questionPrint = '',
        /** The build `--model` pinned, where one was pinned */
        public readonly ?string $askedThrough = null,
    ) {}

    public function acceptFrom(Config $config): void
    {
        $this->config = $config;
    }

    /** The file the acceptances were read from, where there was one */
    public function acceptedFrom(): string
    {
        return $this->configSource() ?? Config::FILE;
    }

    /** The config this run read, or null where it found none */
    public function configSource(): ?string
    {
        return $this->config instanceof Config ? $this->config->source : null;
    }

    public function add(Finding $finding): void
    {
        $reason = $this->config?->reasonFor($finding->checkId, $finding->target);

        $this->findings[] = $reason === null ? $finding : $finding->acceptedBecause($reason);
    }

    /**
     * The order the query wrote its questions in, so the report reads down the
     * file instead of down the alphabet
     *
     * @param list<string> $targets
     */
    public function orderBy(array $targets): void
    {
        $this->order = array_flip($targets);
    }

    private function order(string $target): int
    {
        return $this->order[$target] ?? PHP_INT_MAX;
    }

    /** Record that this many checks were evaluated, so a run that asked nothing can say so */
    public function asked(int $checks): void
    {
        $this->asked += $checks;
    }

    public function askedCount(): int
    {
        return $this->asked;
    }

    public function note(string $note, ?int $findings = null): void
    {
        $this->notes[] = new Note($note, 'note', null, null, null, $findings);
    }

    /**
     * A call that could not be made, so the checks it carried never ran.
     *
     * Recorded apart from an ordinary note because the run is now incomplete,
     * and a caller gating on the exit code has to be able to tell.
     */
    public function unreachable(string $target, string $message, ?string $cause = null): void
    {
        $this->notes[] = new Note(
            Text::of('report.unreachable', ['target' => $target, 'detail' => $message]),
            'unreachable',
            $target,
            null,
            $cause ?? Cause::ANSWER,
        );
    }

    /**
     * A check this run put into a call, and the question or state it was asked
     * about. Paired with `reached`, this is what `reconcile()` compares
     */
    public function expecting(string $checkId, string $target): void
    {
        $this->expected[$target][$checkId] = true;
    }

    /** A check that got as far as a verdict, whether or not it fired */
    public function reached(string $checkId, string $target): void
    {
        $this->reached[$target][$checkId] = true;
    }

    /**
     * Every check that went into a call has to come back as a finding, as a
     * cleared reading, or as a loss somebody can see.
     *
     * A check that produces nothing on some path and is never mentioned leaves a
     * report that reads as clean and complete. Reconciling what was asked
     * against what came back catches that wherever it happens, instead of each
     * path having to notice for itself.
     */
    public function reconcile(): void
    {
        foreach ($this->expected as $target => $checks) {
            // A target that already carries a loss has said so; adding a second
            // note per check would inflate the count without adding a fact.
            foreach ($this->unreachableNotes() as $note) {
                if ($note->target === $target) {
                    continue 2;
                }
            }

            $missing = array_keys(array_diff_key($checks, $this->reached[$target] ?? []));

            if ($missing === []) {
                continue;
            }

            sort($missing);

            $this->unreachable($target, Text::of('report.no_verdict', [
                'first' => $missing[0],
                'more' => count($missing) - 1,
            ]));
        }
    }

    /**
     * Checks this run did not carry: a flag narrowed it, or the
     * query is a shape a check cannot run on. Not a failure, but not coverage
     * either, and a report that cannot say so reads like a full clean pass.
     */
    public function skipped(string $message, ?int $checks = null): void
    {
        $this->notes[] = new Note($message, 'skipped', null, $checks);
    }

    /** @return list<Note> */
    public function skippedNotes(): array
    {
        return array_values(array_filter($this->notes, static fn (Note $n): bool => $n->isSkip()));
    }

    /** @return list<Note> */
    public function unreachableNotes(): array
    {
        return array_values(array_filter(
            $this->notes,
            static fn (Note $n): bool => $n->isUnreachable(),
        ));
    }

    /** Whether every check that was meant to run got an answer */
    public function isComplete(): bool
    {
        return $this->unreachableNotes() === [];
    }

    /** The build the answers say they came from, whatever was asked for */
    public function answeredBy(string $model): void
    {
        $this->answeredBy[$model] = true;
    }

    /**
     * The builds that answered, as the API named them.
     *
     * `--model` and `--openrouter` say what was asked for. This says what
     * replied, which is what makes two reports comparable or not.
     *
     * @return list<string>
     */
    public function answeringModels(): array
    {
        $models = array_keys($this->answeredBy);
        sort($models);

        return $models;
    }

    /**
     * A call that left the machine.
     *
     * `$tokens` is null where the answer carried no usage, which is not a call
     * that cost nothing; counting it as zero prints the two the same way
     */
    public function recordCall(?int $tokens): void
    {
        $this->calls++;

        if ($tokens === null) {
            $this->callsWithoutUsage++;

            return;
        }

        $this->tokens += $tokens;
    }

    /** Calls whose answer carried no token count */
    public function callsWithoutUsage(): int
    {
        return $this->callsWithoutUsage;
    }

    /**
     * @return list<Finding>
     */
    public function findings(?Severity $floor = null): array
    {
        $fired = array_values(array_filter(
            $this->findings,
            static fn (Finding $f): bool => $f->fired && $f->accepted === null,
        ));

        $findings = $floor === null
            ? $fired
            : array_values(array_filter($fired, static fn (Finding $f): bool => $f->severity->atLeast($floor)));

        usort($findings, function (Finding $a, Finding $b): int {
            $rank = fn (Finding $f): int => $this->supersededBy($f) === null ? 0 : 1;

            return [$this->order($a->target), $rank($a), $b->severity->weight(), $a->checkId]
                <=> [$this->order($b->target), $rank($b), $a->severity->weight(), $b->checkId];
        });

        return $findings;
    }

    /**
     * The finding that makes this one moot, where one does.
     *
     * Changing a question's type discards the advice about the type it had
     * be, so an agent applying findings in order would otherwise write criteria
     * it immediately throws away
     */
    public function supersededBy(Finding $finding): ?string
    {
        foreach ($this->findings as $other) {
            // Only something the reader was told to do. A check that ran
            // and cleared, or one already accepted, is nothing to act on, so it
            // cannot make another finding moot - and naming it points the reader
            // at a line that is not in the report.
            if (! $other->fired || $other->accepted !== null) {
                continue;
            }

            if ($other->target !== $finding->target || ! in_array($finding->checkId, $other->supersedes, true)) {
                continue;
            }

            // No severity test. The catalogue declares these edges because acting
            // on one finding makes the other moot, which is a fact about the two
            // changes and not about how much either costs: retyping a question
            // discards the advice about the type it had, though the retype is
            // advice and the advice may be an error. A superseded finding is
            // still reported and still counted, so marking it hides nothing.
            return $other->checkId;
        }

        return null;
    }

    /**
     * The findings this one makes moot, of those reported
     *
     * @return list<string>
     */
    public function superseding(Finding $finding): array
    {
        $found = [];

        foreach ($this->findings as $other) {
            if ($other->target === $finding->target
                && in_array($other->checkId, $finding->supersedes, true)
                && $finding->severity->atLeast($other->severity)) {
                $found[] = $other->checkId;
            }
        }

        return $found;
    }

    /**
     * Checks that ran and cleared, when the caller asked to see them
     *
     * @return list<Finding>
     */
    public function cleared(): array
    {
        return array_values(array_filter($this->findings, static fn (Finding $f): bool => ! $f->fired));
    }

    /** @return list<Note> */
    public function notes(): array
    {
        return $this->notes;
    }

    public function calls(): int
    {
        return $this->calls;
    }

    public function tokens(): int
    {
        return $this->tokens;
    }

    public function count(Severity $severity): int
    {
        return count(array_filter(
            $this->findings,
            static fn (Finding $f): bool => $f->fired && $f->accepted === null && $f->severity === $severity,
        ));
    }

    /**
     * Checks whose readings straddled their trigger and did not fire.
     *
     * One whose mean clears the trigger is reported as the finding it is, with
     * the disagreement noted on it. Listing it here as well would count it twice
     * and leave a reader unable to tell which of the two the tool meant.
     *
     * @return list<Finding>
     */
    public function unstable(): array
    {
        return array_values(array_filter(
            $this->findings,
            static fn (Finding $f): bool => $f->unstable && ! $f->fired && $f->accepted === null,
        ));
    }

    /**
     * Findings somebody has read and decided to live with.
     *
     * They are reported and they count for nothing. A tool that deletes them
     * from its own output teaches you to distrust the output.
     *
     * @return list<Finding>
     */
    public function accepted(): array
    {
        return array_values(array_filter(
            $this->findings,
            static fn (Finding $f): bool => $f->fired && $f->accepted !== null,
        ));
    }

    /**
     * The finding whose patch already settles the node this one's patch writes.
     *
     * Two checks can want the same question gone, and a third can want a key
     * added inside it. Applied in order the second delete fails and the add puts
     * the deleted question back as a stub the API rejects, so each patch is
     * right and the set is not. Replacing a node settles it the same way: what
     * the replacement holds is what is there, whatever a patch inside it wanted
     */
    public function patchCoveredBy(Finding $finding): ?string
    {
        if (! $finding->patch instanceof Patch) {
            return null;
        }

        $seenSelf = false;

        foreach ($this->findings() as $other) {
            if ($other === $finding) {
                $seenSelf = true;

                continue;
            }

            $patch = $other->patch;

            if (! $patch instanceof Patch) {
                continue;
            }

            // A patch writing inside a node another finding removes or replaces
            // is void wherever the two sort, because a caller may apply either
            // first and the node it wrote into is then gone or overwritten.
            if (str_starts_with($finding->patch->path, $patch->path.'/')) {
                return $other->checkId;
            }

            // Two patches on the same node make each other moot, so only the
            // later one is marked; marking both would name a cycle.
            if ($patch->path === $finding->patch->path && ! $seenSelf) {
                return $other->checkId;
            }
        }

        return null;
    }

    public function hasErrors(): bool
    {
        return $this->count(Severity::Error) > 0;
    }

    public function isEmpty(?Severity $floor = null): bool
    {
        return $this->findings($floor) === [];
    }

    /**
     * @return array<string, mixed>
     */
    public function toArray(?Severity $floor = null): array
    {
        return [
            'source' => $this->source,
            'catalogue' => [
                'version' => $this->catalogueVersion,
                'fingerprint' => $this->fingerprint,
                'asked' => $this->questionPrint,
                'model' => $this->model,
            ],
            // Which build answered, against the build the checks are written for.
            // Without it, two runs through different models are one document.
            'asked_through' => $this->askedThrough,
            // What answered, not what was asked for: two providers serving the
            // same build, or one serving a different one, are only visible here.
            'answered_by' => $this->answeringModels(),
            'summary' => [
                'error' => $this->count(Severity::Error),
                'warning' => $this->count(Severity::Warning),
                'advice' => $this->count(Severity::Advice),
                'calls' => $this->calls,
                'tokens' => $this->tokens,
                // Calls the answer carried no usage for. Without it a run whose
                // provider reported no usage prints the same figure as a run
                // that cost nothing.
                'tokens_unreported_for' => $this->callsWithoutUsage,
                'accepted' => count($this->accepted()),
                'unstable' => count($this->unstable()),
                'unreachable' => count($this->unreachableNotes()),
                // Checks evaluated. A narrowed run that left nothing to do
                // produced the same empty report as a query with nothing wrong.
                'asked' => $this->asked,
                'complete' => $this->isComplete(),
                // Not a total: two reasons can leave out the same check, so the
                // count that means anything is the one on each note.
                'narrowed' => $this->skippedNotes() !== [],
            ],
            // Which config was read. A query copied to another directory loses its
            // acceptances, and this is what says so instead of the findings
            // reappearing with no reason given.
            'accepted_from' => $this->configSource(),
            'notes' => array_map(static fn (Note $n): array => $n->toArray(), $this->notes),
            'cleared' => array_map(static fn (Finding $f): array => $f->toArray(), $this->cleared()),
            // Accepted findings go through the same resolution. Left raw, their
            // `supersedes` is the catalogue's whole list and not the checks
            // this report holds, and one field means two things in one document.
            'accepted' => array_map($this->resolved(...), $this->accepted()),
            'unstable' => array_map($this->resolved(...), $this->unstable()),
            'findings' => array_map($this->resolved(...), $this->findings($floor)),
        ];
    }

    /**
     * A finding with its relationships answered against this report, instead of
     * against the catalogue the check was written in.
     *
     * @return array<string, mixed>
     */
    private function resolved(Finding $finding): array
    {
        $row = $finding->toArray();
        $superseded = $this->supersededBy($finding);
        $supersedes = $this->superseding($finding);

        if ($superseded !== null) {
            $row['superseded_by'] = $superseded;
        }

        $row['supersedes'] = $supersedes === [] ? null : $supersedes;
        $covered = $this->patchCoveredBy($finding);

        if ($covered !== null && is_array($row['patch'] ?? null)) {
            $row['patch']['covered_by'] = $covered;
        }

        return array_filter($row, static fn (mixed $v): bool => $v !== null);
    }
}
