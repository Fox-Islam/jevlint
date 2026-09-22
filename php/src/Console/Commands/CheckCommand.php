<?php

declare(strict_types=1);

namespace Phox\JevLint\Console\Commands;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Config\Config;
use Phox\JevLint\Console\Args;
use Phox\JevLint\Console\Output;
use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\Format\TextFormatter;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Lint\Linter;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Severity;
use Phox\JevLint\Support\Json;

/** `jevlint check <query.json>` - the linter */
final class CheckCommand
{
    /**
     * @return list<string>
     */
    private function list(?string $value, string $option = ''): array
    {
        if ($value === null) {
            return [];
        }

        $named = array_values(array_filter(array_map(trim(...), explode(',', $value))));

        // `--only=$CHECKS` with the variable unset read as no narrowing at all,
        // so a run meant to carry one check carried the catalogue and paid for it.
        if ($named === []) {
            throw JevLintException::of(JevLintException::USAGE, Text::of('narrow.nothing_named', ['option' => $option]));
        }

        return $named;
    }

    public function run(Args $args, Output $output): int
    {
        $path = $args->argument(1);

        if ($path === null) {
            throw new JevLintException(Text::of('check.no_query_file'));
        }

        $whole = Query::fromFile($path);
        $wanted = $this->list($args->value('question'), 'question');
        $missing = array_diff($wanted, array_map(static fn ($q): string => $q->id, $whole->questions));

        if ($missing !== []) {
            throw new JevLintException(Text::of('query.no_such_question', ['path' => $path, 'ids' => implode(', ', $missing)]));
        }

        $query = $whole->only($wanted);
        $config = Config::discover($args->value('config'), $path);
        $catalogue = Catalogue::forRun($args->value('jev'), $config);
        $only = $this->list($args->value('only'), 'only');

        $linter = $args->flag('static-only')
            ? Linter::rulesOnly($catalogue, $config)
            : Linter::fromEnvironment(
                model: $args->value('model'),
                openRouter: $args->flag('openrouter'),
                timeout: $args->has('timeout') ? $args->seconds('timeout', 10.0) : null,
                catalogue: $catalogue,
                config: $config,
            );

        $linter = $linter
            ->only($only)
            ->repeats($args->int('repeats', 1))
            ->maxStateChars($args->int('max-state', 20000, PHP_INT_MAX));

        if ($args->flag('no-state')) {
            $linter = $linter->withoutState();
        }

        if ($args->flag('all')) {
            $linter = $linter->reportingCleared();
        }

        $report = $linter->check($query, $whole);

        $floor = Severity::fromName($args->value('min', 'advice') ?? 'advice');

        // The counts stay whole while the list is filtered, so a reader who sees
        // `4 advice` and no advice rows is owed the reason.
        $hidden = count($report->findings()) - count($report->findings($floor));

        if ($hidden > 0) {
            $report->note(Text::of('note.below_the_floor', ['floor' => $floor->value, 'count' => $hidden]), $hidden);
        }

        if ($args->value('format') === 'json') {
            $output->line(Json::encode($report->toArray($floor)));
        } else {
            $output->write((new TextFormatter($output->colour(), $args->flag('brief'), $args->flag('show-accepted'), $args->flag('all')))->format($report, $floor));
        }

        // Checks that could not be asked did not pass. Reporting 0 here would
        // tell a caller gating on the exit code that a query nobody checked is fine.
        if (! $report->isComplete()) {
            return 2;
        }

        // A run can leave nothing to do - a narrowing that names a state check on
        // a query with no state - and every reason is recorded as a skipped note.
        // Reporting that as a pass is the same lie as reporting a failed call as one.
        if ($report->askedCount() === 0) {
            return 2;
        }

        if ($report->hasErrors()) {
            return 1;
        }

        if ($args->flag('strict') && ! $report->isEmpty($floor)) {
            return 1;
        }

        // A run that could not decide is not a run that passed.
        return $report->unstable() === [] ? 0 : 3;
    }
}
