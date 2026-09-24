<?php

declare(strict_types=1);

namespace Phox\JevLint\Probe;

use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Probe\Variants\CriteriaStripped;
use Phox\JevLint\Probe\Variants\KeysHidden;
use Phox\JevLint\Probe\Variants\LevelsReversed;
use Phox\JevLint\Probe\Variants\NoulAsChoice;
use Phox\JevLint\Probe\Variants\OptionsReversed;
use Phox\JevLint\Probe\Variants\Reworded;
use Phox\JevLint\Probe\Variants\Unchanged;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Note;
use Phox\JevLint\Support\Cause;
use Phox\JevLint\Query\ReviewedQuestion;
use Phox\TypeSafe\Client;
use Phox\TypeSafe\Exceptions\TypeSafeException;
use Phox\TypeSafe\Responses\ChoiceAnswer;
use Phox\TypeSafe\Responses\SystemOneResponse;

/**
 * Runs the query, then runs rewrites of it that mean the same thing, and
 * reports how far each one moved the answer.
 *
 * The linter reports that a question is vague. This reports that your question,
 * against your state, answers 0.72 one way round and 0.31 the other.
 *
 * Movement is measured against the spread of the unchanged query repeated, so a
 * variant that moves less than the model's own jitter is reported as moving
 * nothing
 */
final class Probe
{
    /**
     * The floor used when a run is too short to measure its own spread.
     *
     * TypeSafe's consistency cookbook publishes 0.0102 as the mean per-question
     * probability deviation over 15 repeats per condition, which is the nearest
     * published figure; where this one came from is not recorded here
     */
    public const PUBLISHED_NOISE = 0.0085;

    private int $calls = 0;

    private int $tokens = 0;

    /** @var list<Note> */
    private array $notes = [];

    /** Calls that failed or came back without answering */
    private int $unreachable = 0;

    public function __construct(private readonly Client $client) {}

    /**
     * @param  list<Variant>              $extra
     * @return array<string, QuestionProbe>
     */
    public function run(Query $query, int $repeats = 5, array $extra = []): array
    {
        if (! $query->hasState()) {
            throw new JevLintException(Text::of('probe.needs_state'));
        }

        $probes = [];
        $unsendable = [];

        foreach ($query->questions as $question) {
            if ($question->isKnownType()) {
                $probes[$question->id] = new QuestionProbe($question);

                continue;
            }

            $unsendable[] = $question->id;
        }

        if ($probes === []) {
            throw new JevLintException(Text::of('probe.nothing_sendable'));
        }

        // A question of a type this cannot send is left out of every reading, so
        // a report that does not name it says nothing moved on a question it
        // never asked. `check` reports the same query as an error.
        if ($unsendable !== []) {
            $this->notes[] = new Note(Text::of('probe.unsendable_questions', [
                'ids' => implode(', ', $unsendable),
                'count' => count($unsendable),
            ]), 'skipped');
        }

        $baseline = $this->baseline($query, $probes, $repeats);

        foreach ([...self::variants(), ...$extra] as $variant) {
            $this->variant($query, $probes, $variant, $baseline);
        }

        return $probes;
    }

    /**
     * @return list<Variant>
     */
    public static function variants(): array
    {
        return [
            new CriteriaStripped(),
            new NoulAsChoice(),
            new OptionsReversed(),
            new KeysHidden(),
            new LevelsReversed(),
        ];
    }

    /**
     * @param  array<array-key, mixed> $rewordings variant name to a map of
     *                                             question id to its rewording
     * @return list<Variant>
     */
    public static function rewordings(array $rewordings): array
    {
        $variants = [];

        // The built-ins and the baseline. Two rows under one name share a legend
        // line, and the footer's note about which rewrites are expected to move
        // would speak about the wrong one.
        $taken = ['unchanged'];

        foreach (self::variants() as $builtIn) {
            $taken[] = $builtIn->name();
        }

        foreach ($rewordings as $name => $instructions) {
            if (in_array((string) $name, $taken, true)) {
                throw JevLintException::of(JevLintException::USAGE, Text::of('probe.variant_name_taken', [
                'name' => (string) $name,
                'taken' => implode(', ', $taken),
            ]));
            }

            // A file written as {"question_id": "text"} names no variant, and the
            // one input written by hand is the one that has to fail loudly.
            if (! is_array($instructions) || $instructions === []) {
                throw JevLintException::of(JevLintException::USAGE, Text::of('probe.variant_not_a_map', ['name' => (string) $name]));
            }

            $strings = [];

            foreach ($instructions as $id => $text) {
                if (! is_string($text)) {
                    throw JevLintException::of(JevLintException::USAGE, Text::of('probe.variant_not_text', [
                    'name' => (string) $name,
                    'id' => (string) $id,
                    'type' => gettype($text),
                ]));
                }

                $strings[(string) $id] = $text;
            }

            $variants[] = new Reworded((string) $name, $strings);
        }

        return $variants;
    }

    /**
     * Send the query unchanged, several times. The mean is what everything is
     * compared with; the spread is what counts as movement
     *
     * @param  array<string, QuestionProbe>            $probes
     * @return array<string, array{winner?: string, levels?: int}>
     */
    private function baseline(Query $query, array $probes, int $repeats): array
    {
        $unchanged = new Unchanged();
        $meta = [];

        foreach ($probes as $id => $probe) {
            $meta[$id] = ['levels' => is_array($probe->question->criteria) ? count($probe->question->criteria) : 2];
        }

        for ($run = 0; $run < max(1, $repeats); $run++) {
            $response = $this->send($query, array_map(static fn (QuestionProbe $p): ReviewedQuestion => $p->question, $probes));

            if (! $response instanceof SystemOneResponse) {
                continue;
            }

            foreach ($probes as $id => $probe) {
                if ($run === 0 && $response->has($id)) {
                    $answer = $response->answer($id);

                    if ($answer instanceof ChoiceAnswer) {
                        $meta[$id]['winner'] = $answer->choice();
                        $probe->reading = Text::of('probe.reading_choice', ['label' => $answer->choice()]);
                    }

                    if ($probe->question->type === 'score') {
                        $probe->reading = Text::of('probe.reading_score', ['levels' => $meta[$id]['levels'] ?? 2]);
                    }

                    if ($probe->question->type === 'noul') {
                        $probe->reading = Text::of('probe.reading_yes');
                    }
                }

                $value = $unchanged->read($response, $probe->question, $meta[$id]);

                if ($value !== null) {
                    $probe->repeats[] = $value;
                }
            }
        }

        return $meta;
    }

    /**
     * @param array<string, QuestionProbe>                   $probes
     * @param array<string, array{winner?: string, levels?: int}> $meta
     */
    private function variant(Query $query, array $probes, Variant $variant, array $meta): void
    {
        $questions = [];

        foreach ($probes as $id => $probe) {
            if ($variant->applies($probe->question)) {
                $questions[$id] = $variant->apply($probe->question);
            }
        }

        if ($questions === []) {
            return;
        }

        $response = $this->send($query, $questions);

        foreach ($questions as $id => $question) {
            $probes[$id]->readings[] = new Reading(
                variant: $variant->name(),
                describe: $variant->describe(),
                value: $response instanceof SystemOneResponse ? $variant->read($response, $question, $meta[$id] ?? []) : null,
                error: $response instanceof SystemOneResponse ? null : Text::of('probe.call_failed'),
            );
        }
    }

    /**
     * @param array<string, ReviewedQuestion> $questions
     */
    private function send(Query $query, array $questions): ?SystemOneResponse
    {
        $request = $this->client->systemOne()->state($query->state);

        foreach ($questions as $id => $question) {
            $request->ask($id, QuestionBuilder::build($question));
        }

        try {
            $response = $request->send();
        } catch (TypeSafeException $exception) {
            $this->notes[] = new Note($exception->getMessage(), 'unreachable', null, null, Cause::of($exception));
            $this->unreachable++;

            return null;
        }

        $missing = array_values(array_filter(
            array_keys($questions),
            static fn (int|string $id): bool => ! $response->has((string) $id),
        ));

        if ($missing !== []) {
            $this->notes[] = new Note(Text::of('probe.partial_answer', [
                'answered' => count($questions) - count($missing),
                'asked' => count($questions),
                'missing' => (string) $missing[0],
            ]), 'unreachable', (string) $missing[0], null, Cause::ANSWER);
            $this->unreachable++;
        }

        $this->calls++;
        $this->tokens += $response->usage()->totalTokens() ?? 0;

        return $response;
    }

    public function calls(): int
    {
        return $this->calls;
    }

    public function unreachable(): int
    {
        return $this->unreachable;
    }

    /** Whether every call this probe made came back with what it asked for */
    public function isComplete(): bool
    {
        return $this->unreachable === 0;
    }

    public function tokens(): int
    {
        return $this->tokens;
    }

    /**
     * @return list<Note>
     */
    public function notes(): array
    {
        return $this->notes;
    }
}
