<?php

declare(strict_types=1);

namespace Phox\JevLint\SelfTest;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Catalogue\Check;
use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Lint\ModelLinter;
use Phox\JevLint\Query\ReviewedQuestion;
use Phox\JevLint\Support\Json;
use Phox\TypeSafe\Client;
use Phox\TypeSafe\Exceptions\TypeSafeException;

/**
 * Does each model check separate a clean question from a broken one?
 *
 * Every check ships one example it should fire on and one it should not. This
 * asks both and reports the span between them. A check whose span is small is
 * not measuring what its title claims, whatever it reports about your query
 */
final class SelfTest
{
    /** Below this, a check is not telling clean and broken apart */
    public const FLAT = 0.15;

    /** Below this, it separates them, but not by much */
    public const WEAK = 0.30;

    public function __construct(
        private readonly Catalogue $catalogue,
        private readonly Client $client,
    ) {}

    /**
     * @param  list<string>    $only
     * @return list<CheckScore>
     */
    public function run(array $only = []): array
    {
        $path = Catalogue::locate('fixtures.json');
        /** @var array{fixtures?: list<array<string, mixed>>} $data */
        $data = Json::readFile($path);
        $results = [];

        foreach ($data['fixtures'] ?? [] as $fixture) {
            $id = is_string($fixture['check'] ?? null) ? $fixture['check'] : '';
            $check = $this->catalogue->find($id);

            // A fixture naming a check that is not there is a typo in a file
            // nobody reads twice, and skipping it quietly took a check's second
            // domain out of the run while the summary still said it separated.
            // The same typo on the command line is refused loudly.
            if (! $check instanceof Check && $this->catalogue->findWritten($id) === null) {
                throw JevLintException::of(JevLintException::CATALOGUE, Text::of('self_test.fixture_unknown_check', ['path' => $path, 'id' => $id]));
            }

            if (! $check instanceof Check || ($only !== [] && ! in_array($id, $only, true))) {
                continue;
            }

            $results[] = $this->score($check, $fixture);
        }

        return $results;
    }

    /**
     * @param array<string, mixed> $fixture
     */
    private function score(Check $check, array $fixture): CheckScore
    {
        $clean = $this->probability($check, $fixture['clean'] ?? null);
        $broken = $this->probability($check, $fixture['broken'] ?? null);
        $offersFixed = isset($fixture['fixed']);
        $fixed = $offersFixed ? $this->probability($check, $fixture['fixed']) : null;

        return new CheckScore(
            $check,
            $clean,
            $broken,
            $fixed,
            is_string($fixture['domain'] ?? null) ? $fixture['domain'] : '',
            $offersFixed,
        );
    }

    /** The probability this check puts on its own defect being present */
    private function probability(Check $check, mixed $example): ?float
    {
        if (! is_array($example)) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('self_test.fixture_missing_example', ['id' => $check->id]));
        }

        $field = is_string($example['field'] ?? null) ? $example['field'] : '';
        $linter = new ModelLinter($this->catalogue, $this->client);
        $request = $this->client->systemOne()->state($this->state($check, $example));
        $keys = [];

        $pair = is_array($example['pair'] ?? null) ? array_values($example['pair']) : null;

        foreach ($check->wordings as $index => $wording) {
            $keys[$index] = $check->answerKey().'__w'.$index;
            $question = $linter->build($wording, $field);

            if ($pair !== null && count($pair) === 2) {
                $question->instructions(str_replace(
                    '{pair}',
                    sprintf('"%s" and "%s"', (string) $pair[0], (string) $pair[1]),
                    $wording->instructions(),
                ));
            }

            $request->ask($keys[$index], $question);
        }

        try {
            $response = $request->send();
        } catch (TypeSafeException) {
            return null;
        }

        if ($check->compare === 'type') {
            $declared = is_string($example['type'] ?? null) ? $example['type'] : '';

            return 1.0 - ($response->choice($keys[0])->probabilityOf($declared) ?? 0.0);
        }

        // The wordings mean the same thing, so the check's answer is their mean
        $probabilities = array_map(
            static fn (string $key): float => $response->noul($key)->noul(),
            $keys,
        );

        return array_sum($probabilities) / count($probabilities);
    }

    /**
     * @param  array<string, mixed> $example
     * @return array<string, mixed>
     */
    private function state(Check $check, array $example): array
    {
        if ($check->scope === 'question') {
            return ReviewedQuestion::fromArray('fixture', $example)->asState();
        }

        // A query-scope check reads two questions, so its fixture holds the pair.
        if ($check->scope === 'query') {
            return ['questions' => $example['pair'] ?? []];
        }

        // The same shape a run shows a state-scoped check. A fixture writes its
        // question as text where it carries no criteria, and as an object where
        // it does, so the two cannot drift apart.
        $question = $example['question'] ?? '';

        return [
            'question' => is_array($question) ? $question : ['instructions' => $question],
            'state' => $example['state'] ?? null,
        ];
    }
}
