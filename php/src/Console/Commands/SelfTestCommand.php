<?php

declare(strict_types=1);

namespace Phox\JevLint\Console\Commands;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Catalogue\Check;
use Phox\JevLint\Config\Config;
use Phox\JevLint\Console\Args;
use Phox\JevLint\Console\Output;
use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\Format\SelfTestFormatter;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Lint\ClientFactory;
use Phox\JevLint\SelfTest\CheckScore;
use Phox\JevLint\SelfTest\SelfTest;
use Phox\JevLint\Support\Json;

/** `jevlint self-test` - does each check separate its own two examples? */
final class SelfTestCommand
{
    public function run(Args $args, Output $output): int
    {
        $config = Config::discover($args->value('config'), '.');
        $catalogue = Catalogue::forRun($args->value('jev'), $config);
        $only = array_values(array_filter(array_map(trim(...), explode(',', $args->value('check', '') ?? ''))));

        if ($args->has('check') && $only === []) {
            throw JevLintException::of(JevLintException::USAGE,
                Text::of('narrow.no_check_named'));
        }

        // A check id the catalogue does not hold is a typo or a rename. Scoring
        // nothing and exiting 0 leaves a pinned CI job green for ever.
        $ids = array_map(static fn (Check $c): string => $c->id, $catalogue->written());
        $unknown = array_diff($only, $ids);

        if ($unknown !== []) {
            throw new JevLintException(Text::of('catalogue.no_such_check', ['ids' => implode(', ', $unknown)]));
        }

        $withheld = array_values(array_filter($only, static fn (string $id): bool => $catalogue->find($id) === null));

        if ($withheld !== []) {
            throw new JevLintException(Text::of('self_test.withheld_for_version', [
                'ids' => implode(', ', $withheld),
                'count' => count($withheld),
                'jev' => $catalogue->jev,
            ]));
        }

        $static = array_values(array_filter(
            $only,
            static fn (string $id): bool => ($catalogue->find($id)?->isStatic()) === true,
        ));

        if ($static !== []) {
            throw new JevLintException(Text::of('self_test.static_has_nothing_to_score', [
                'ids' => implode(', ', $static),
                'count' => count($static),
            ]));
        }

        $scores = (new SelfTest($catalogue, ClientFactory::make(
            model: $args->value('model'),
            openRouter: $args->flag('openrouter'),
        )))->run($only);

        if ($args->value('format') === 'json') {
            $output->line(Json::encode(array_map(static fn (CheckScore $s): array => $s->toArray(), $scores)));
        } else {
            $output->write((new SelfTestFormatter($output->colour()))->format($scores));
        }

        // A model check with no fixture is scored by nothing and would leave
        // the run reporting `0 of 0 checks separate their own examples`, which a
        // pinned CI job reads as a pass for ever.
        $scored = array_map(static fn (CheckScore $s): string => $s->check->id, $scores);
        $unscored = array_values(array_filter(
            $catalogue->all(),
            static fn (Check $c): bool => $c->isModel()
                && ($only === [] || in_array($c->id, $only, true))
                && ! in_array($c->id, $scored, true),
        ));

        if ($unscored !== []) {
            $output->error(Text::of('self_test.no_examples', [
                'ids' => implode(', ', array_map(static fn (Check $c): string => $c->id, $unscored)),
                'count' => count($unscored),
                'file' => basename(Catalogue::locate('fixtures.json')),
            ]));

            return 1;
        }

        // A check that could not be asked has not failed its examples; the run
        // did not happen. Exit 1 is for a catalogue that is wrong, exit 2 for a
        // run that could not tell.
        foreach ($scores as $score) {
            if ($score->errored()) {
                return 2;
            }
        }

        foreach ($scores as $score) {
            if (! $score->passed()) {
                return 1;
            }
        }

        return 0;
    }
}
