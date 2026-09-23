<?php

declare(strict_types=1);

namespace Phox\JevLint\Console\Commands;

use Phox\JevLint\Console\Args;
use Phox\JevLint\Console\Output;
use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\Format\ProbeFormatter;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Lint\ClientFactory;
use Phox\JevLint\Probe\Probe;
use Phox\JevLint\Probe\QuestionProbe;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Note;
use Phox\JevLint\Support\Json;

/** `jevlint probe <query.json>` - how far a rewrite moves the answer */
final class ProbeCommand
{
    public function run(Args $args, Output $output): int
    {
        $path = $args->argument(1);

        if ($path === null) {
            throw new JevLintException(Text::of('probe.no_query_file'));
        }

        // The same load `check` does, so a file that is not a query is named as
        // one here too. Reading it straight into `fromArray` let a JSON list
        // through to be reported as a missing state, or as a missing key.
        $query = Query::fromFile($path);
        $statePath = $args->value('state');

        if ($statePath !== null) {
            $query = $query->withState(Json::readFile($statePath));
        }

        // Probing costs a call per variant per question, so narrowing to the one
        // question being iterated on is the difference between a run you make
        // once and a run you make while editing.
        $wanted = $args->value('question') === null
            ? []
            : array_values(array_filter(array_map(trim(...), explode(',', (string) $args->value('question')))));

        if ($args->value('question') !== null && $wanted === []) {
            throw JevLintException::of(JevLintException::USAGE,
                Text::of('narrow.no_question_named'));
        }
        $missing = array_diff($wanted, array_map(static fn ($q): string => $q->id, $query->questions));

        if ($missing !== []) {
            throw JevLintException::of(JevLintException::USAGE, Text::of('query.no_such_question', ['path' => $path, 'ids' => implode(', ', $missing)]));
        }

        $whole = $query;
        $query = $query->only($wanted);
        $repeats = $args->int('repeats', 5);

        $extra = [];
        $rewordings = $args->value('variants');

        if ($rewordings !== null) {
            $extra = Probe::rewordings(Json::readFile($rewordings));

            // A rewording keyed by a question id that is not in the file applies
            // to nothing, and the run then reads as a query nothing moved.
            foreach ($extra as $variant) {
                if (array_filter($whole->questions, $variant->applies(...)) !== []) {
                    continue;
                }

                throw JevLintException::of(JevLintException::USAGE, Text::of('probe.variant_names_no_question', [
                    'variant' => $variant->name(),
                    'path' => $path,
                    'ids' => implode(', ', array_map(static fn ($q): string => $q->id, $whole->questions)),
                ]));
            }
        }

        // The client is built after the variants are read, so a mistyped path is
        // reported as a mistyped path instead of as a missing key.
        $probe = new Probe(ClientFactory::make(
            model: $args->value('model'),
            openRouter: $args->flag('openrouter'),
        ));

        $probes = $probe->run($query, $repeats, $extra);

        if ($args->value('format') === 'json') {
            $output->line(Json::encode($this->toArray($probes, $path, $repeats, $probe, $args->value('model'))));
        } else {
            $output->write((new ProbeFormatter($output->colour()))->format(
                $probes,
                $path,
                $repeats,
                $probe->calls(),
                $probe->tokens(),
                $probe->notes(),
            ));
        }

        // A probe that could not send is not a probe that found no movement, and
        // exit 1 is what `--strict` returns when it does find some.
        if (! $probe->isComplete()) {
            return 2;
        }

        $moved = array_filter($probes, static fn (QuestionProbe $q): bool => array_filter($q->readings, $q->moved(...)) !== []);

        return $args->flag('strict') && $moved !== [] ? 1 : 0;
    }

    /**
     * @param  array<string, QuestionProbe> $probes
     * @return array<string, mixed>
     */
    private function toArray(array $probes, string $source, int $repeats, Probe $probe, ?string $askedThrough): array
    {
        $questions = [];

        foreach ($probes as $id => $question) {
            $readings = [];

            foreach ($question->readings as $reading) {
                $readings[] = [
                    'variant' => $reading->variant,
                    'describes' => $reading->describe,
                    'value' => $reading->value,
                    'delta' => $question->delta($reading),
                    'noise_multiples' => $question->ratio($reading),
                    'moved' => $question->moved($reading),
                    'error' => $reading->error,
                ];
            }

            $questions[$id] = [
                'type' => $question->question->type,
                'reading' => $question->reading,
                'moved' => count(array_filter($question->readings, $question->moved(...))) > 0,
                'undecided' => $question->undecided(),
                'flips' => $question->flips(),
                'baseline' => $question->baseline(),
                'repeats' => $question->repeats,
                'noise' => $question->noise(),
                'floor' => $question->floor(),
                'readings' => $readings,
            ];
        }

        $moved = array_keys(array_filter(
            $questions,
            static fn (array $q): bool => $q['moved'] === true,
        ));
        $undecided = array_keys(array_filter(
            $questions,
            static fn (array $q): bool => $q['undecided'] === true,
        ));

        return [
            'source' => $source,
            'asked_through' => $askedThrough,
            'repeats' => $repeats,
            'calls' => $probe->calls(),
            'tokens' => $probe->tokens(),
            'notes' => array_map(static fn (Note $n): array => $n->toArray(), $probe->notes()),
            'summary' => [
                'questions' => count($questions),
                'moved' => count($moved),
                'moved_questions' => $moved,
                'undecided' => count($undecided),
                'undecided_questions' => $undecided,
                'unreachable' => $probe->unreachable(),
                'complete' => $probe->isComplete(),
                'rule' => Text::of('probe.moved_definition', ['floor' => QuestionProbe::NEGLIGIBLE]),
                'undecided_rule' => Text::of('probe.undecided_definition', ['band' => QuestionProbe::UNDECIDED]),
                'floor' => Text::of('probe.floor_definition', ['noise' => Probe::PUBLISHED_NOISE]),
            ],
            'questions' => $questions,
        ];
    }
}
