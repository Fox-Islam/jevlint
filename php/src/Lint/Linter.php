<?php

declare(strict_types=1);

namespace Phox\JevLint\Lint;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Catalogue\Check;
use Phox\JevLint\Config\Config;
use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Report;
use Phox\TypeSafe\Client;

use function is_callable;

/**
 * One run of the linter, from a query to a report.
 *
 * The two linters are separately usable, and this puts them in the order a run
 * needs, stamps the report with the catalogue that produced it, validates the
 * narrowing against the catalogue, and records what the run left out. The
 * console commands go through here, so a caller in PHP gets the report the CLI
 * prints
 */
final class Linter
{
    /**
     * @param (callable(): Client)|null $client built when the run reaches a check
     *                                          that needs it, so a run of
     *                                          only rules needs no key
     * @param list<string>              $only   check ids this run includes, or all
     *                                          of them when empty
     */
    private function __construct(
        private readonly Catalogue $catalogue,
        private readonly mixed $client,
        private readonly Config $config,
        private readonly array $only = [],
        private readonly bool $checkState = true,
        private readonly int $repeats = 1,
        private readonly bool $reportCleared = false,
        private readonly int $maxStateChars = 20000,
        private readonly ?string $askedThrough = null,
    ) {}

    /**
     * A linter that asks its model checks through `$client`.
     *
     * Any SDK client will do, including the SDK's fake, which is how the tests
     * here run the model path without calling anything
     */
    public static function make(Client $client, ?Catalogue $catalogue = null, ?Config $config = null): self
    {
        return new self($catalogue ?? Catalogue::load(), static fn (): Client => $client, $config ?? Config::empty());
    }

    /**
     * A linter that reads a key from the environment, or a `.env` in the working
     * directory, and builds its own client
     */
    public static function fromEnvironment(?string $model = null, bool $openRouter = false, ?float $timeout = null, ?Catalogue $catalogue = null, ?Config $config = null): self
    {
        return (new self(
            $catalogue ?? Catalogue::load(),
            static fn (): Client => ClientFactory::make($model, $openRouter, $timeout, true),
            $config ?? Config::empty(),
        ))->askedThrough($model);
    }

    /** A linter that runs the rules and makes no calls, so it needs no key */
    public static function rulesOnly(?Catalogue $catalogue = null, ?Config $config = null): self
    {
        return new self($catalogue ?? Catalogue::load(), null, $config ?? Config::empty());
    }

    /** @param array{catalogue?: Catalogue, client?: (callable(): Client)|null, config?: Config, only?: list<string>, checkState?: bool, repeats?: int, reportCleared?: bool, maxStateChars?: int, askedThrough?: ?string} $changed */
    private function with(array $changed): self
    {
        return new self(
            $changed['catalogue'] ?? $this->catalogue,
            array_key_exists('client', $changed) ? $changed['client'] : $this->client,
            $changed['config'] ?? $this->config,
            $changed['only'] ?? $this->only,
            $changed['checkState'] ?? $this->checkState,
            $changed['repeats'] ?? $this->repeats,
            $changed['reportCleared'] ?? $this->reportCleared,
            $changed['maxStateChars'] ?? $this->maxStateChars,
            array_key_exists('askedThrough', $changed) ? $changed['askedThrough'] : $this->askedThrough,
        );
    }

    /**
     * The rules for one Jev version.
     *
     * A query is sent to one build, and a build has the defects it has. Without
     * this the run uses the newest version the catalogue covers
     */
    public function forJev(string $version): self
    {
        return $this->with(['catalogue' => $this->catalogue->forJev($version)]);
    }

    /** The acceptances a report reads to set findings aside */
    public function accepting(Config $config): self
    {
        return $this->with(['config' => $config]);
    }

    /**
     * Narrow the run to these checks.
     *
     * An id the catalogue does not hold is an error instead of a narrowing that
     * silently runs nothing.
     *
     * @param list<string> $checkIds
     */
    public function only(array $checkIds): self
    {
        $ids = array_map(static fn (Check $c): string => $c->id, $this->catalogue->written());
        $unknown = array_diff($checkIds, $ids);

        if ($unknown !== []) {
            throw new JevLintException(Text::of('catalogue.no_such_check', ['ids' => implode(', ', $unknown)]));
        }

        $withheld = array_values(array_filter(
            $checkIds,
            fn (string $id): bool => $this->catalogue->find($id) === null,
        ));

        if ($withheld !== []) {
            throw new JevLintException(Text::of('narrow.withheld_for_version', [
                'ids' => implode(', ', $withheld),
                'count' => count($withheld),
                'jev' => $this->catalogue->jev,
            ]));
        }

        return $this->with(['only' => $checkIds]);
    }

    /** Leave out the checks that read the query's state */
    public function withoutState(): self
    {
        return $this->with(['checkState' => false]);
    }

    /** Ask each model check this many times, so the report has the spread */
    public function repeats(int $repeats): self
    {
        return $this->with(['repeats' => $repeats]);
    }

    /**
     * Carry every model check that ran and cleared, not only the readings near a
     * trigger. Without this a check that cleared and a check that never applied
     * are indistinguishable
     */
    public function reportingCleared(): self
    {
        return $this->with(['reportCleared' => true]);
    }

    /** Where a state stops being state and starts being a document */
    public function maxStateChars(int $chars): self
    {
        return $this->with(['maxStateChars' => $chars]);
    }

    /** Record in the report which build the run asked for */
    public function askedThrough(?string $model): self
    {
        return $this->with(['askedThrough' => $model]);
    }

    public function catalogue(): Catalogue
    {
        return $this->catalogue;
    }

    public function checkFile(string $path): Report
    {
        return $this->check(Query::fromFile($path));
    }

    /**
     * Run the catalogue over a query.
     *
     * `$whole` is the query before any narrowing, where the caller narrowed it
     * with `Query::only()`. The checks that judge a state field against the
     * whole query cannot answer from part of it, so they are left out and said
     * to be left out
     */
    public function check(Query $query, ?Query $whole = null): Report
    {
        $unknown = $this->config->unknown(array_map(static fn (Check $c): string => $c->id, $this->catalogue->written()));

        // A config naming a check that is not in the catalogue is accepting
        // nothing, which is worse than accepting the wrong thing.
        if ($unknown !== []) {
            throw JevLintException::of(JevLintException::CONFIG, Text::of('config.accepts_unknown_check', [
                'source' => $this->config->source ?? Config::FILE,
                'ids' => implode(', ', $unknown),
            ]));
        }

        $left = $whole instanceof Query ? count($whole->questions) - count($query->questions) : 0;

        $report = new Report(
            $query->source,
            $this->catalogue->version,
            $this->catalogue->model,
            $this->catalogue->fingerprint,
            $this->catalogue->asked,
            $this->askedThrough,
        );
        $report->orderBy(array_map(static fn ($q): string => $q->id, $query->questions));
        $report->acceptFrom($this->config);
        $this->noteVersion($whole ?? $query, $report);

        (new StaticLinter($this->catalogue, $this->maxStateChars, $this->only))->run($query, $report);

        $this->noteWhatWasLeftOut($report, $left);

        if (is_callable($this->client) && $this->asksJev()) {
            (new ModelLinter(
                $this->catalogue,
                ($this->client)(),
                $this->checkState,
                $this->repeats,
                $this->only,
                $this->reportCleared,
                $left > 0,
            ))->run($query, $report);
        }

        return $report;
    }

    /** Whether anything in this run needs a call at all */
    private function asksJev(): bool
    {
        return array_filter(
            $this->catalogue->all(),
            fn (Check $c): bool => $c->isModel() && ($this->only === [] || in_array($c->id, $this->only, true)),
        ) !== [];
    }

    /**
     * A query file may pin the build it will be sent to. Where that is a Jev
     * version and the run resolved another one, the findings are the rules for a
     * build this query never reaches
     */
    private function noteVersion(Query $query, Report $report): void
    {
        if (! is_string($query->model)
            || preg_match('/^jev-(\d+(?:\.\d+)*)$/', $query->model, $named) !== 1
            || $named[1] === $this->catalogue->jev) {
            return;
        }

        // `--jev` only takes a version the catalogue covers, and a build id
        // carrying a patch number - `jev-1.13.0` is what the API answers for
        // `jev-latest` - is not one, so telling every reader to pass it sent
        // half of them to a flag that refuses the value they would pass.
        $covered = in_array($named[1], $this->catalogue->versions, true);

        $about = [
            'source' => $query->source,
            'model' => $query->model,
            'jev' => $this->catalogue->jev,
            'named' => $named[1],
        ];

        $report->note($covered
            ? Text::of('note.version_covered', $about)
            : Text::of('note.version_not_covered', $about));
    }

    /**
     * Say what this run left out. A narrowed run that matched nothing, or a run
     * with the model half switched off, produces the same empty report as a
     * query with nothing wrong with it
     */
    private function noteWhatWasLeftOut(Report $report, int $questionsLeftOut): void
    {
        if ($questionsLeftOut > 0) {
            $report->skipped(Text::of('skipped.questions_left_out', ['count' => $questionsLeftOut]));
        }

        if (! is_callable($this->client)) {
            $model = array_values(array_filter(
                $this->catalogue->all(),
                fn (Check $c): bool => $c->isModel() && ($this->only === [] || in_array($c->id, $this->only, true)),
            ));

            if ($model !== []) {
                $report->skipped(Text::of('skipped.jev_not_asked', ['count' => count($model)]), count($model));
            }
        } elseif (! $this->checkState) {
            $stateScoped = array_values(array_filter(
                $this->catalogue->all(),
                static fn (Check $c): bool => $c->isModel()
                    && in_array($c->scope, ['state', 'state-field', 'state-once'], true),
            ));

            $report->skipped(Text::of('skipped.state_not_checked', ['count' => count($stateScoped)]), count($stateScoped));
        }

        if ($this->only !== []) {
            $report->skipped(Text::of('skipped.narrowed_to', [
                'count' => count($this->only),
                'total' => count($this->catalogue->all()),
            ]), count($this->catalogue->all()) - count($this->only));
        }

        if ($this->catalogue->withheld() > 0) {
            $report->skipped(Text::of('skipped.written_for_another_version', [
                'jev' => $this->catalogue->jev,
                'count' => $this->catalogue->withheld(),
            ]), $this->catalogue->withheld());
        }
    }
}
