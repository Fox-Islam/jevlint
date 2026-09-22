<?php

declare(strict_types=1);

namespace Phox\JevLint\Console\Commands;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Catalogue\Check;
use Phox\JevLint\Catalogue\Wording;
use Phox\JevLint\Config\Config;
use Phox\JevLint\Console\Args;
use Phox\JevLint\Console\Output;
use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Support\Json;

/** `jevlint checks` - what the catalogue holds */
final class ChecksCommand
{
    /**
     * @return array<string, mixed>
     */
    private function describe(Check $check): array
    {
        return array_filter([
            'id' => $check->id,
            'title' => $check->title,
            'mode' => $check->mode,
            'scope' => $check->scope,
            'applies_to' => $check->appliesTo,
            'severity' => $check->severity,
            // Which builds the check is a rule for, where it is not all of them
            'since' => $check->since,
            'until' => $check->until,
            'reads' => $check->reads,
            'action' => $check->action,
            'message' => $check->message,
            'hint' => $check->hint,
            'suggest' => $check->suggest,
            'docs' => $check->docs,
            'removes' => $check->removes,
            // What a static check tests, and which findings it puts out of date.
            // A consumer that reads `superseded_by` in a report had nowhere to
            // look the relationship up.
            'rule' => $check->rule,
            'supersedes' => $check->supersedes === [] ? null : $check->supersedes,
            // A model check is a judgement against a threshold, and a caller that
            // cannot see the threshold cannot say what it gated on.
            'trigger' => $check->isModel() ? $check->trigger : null,
            'questions' => $check->isModel() ? array_map(
                static fn (Wording $w): array => array_filter([
                    'type' => $w->type,
                    // Keep the placeholder: the catalogue's own text is what a
                    // reader is being shown, and blanking it prints a hole.
                    'instructions' => $w->instructions('{field}'),
                    'criteria' => $w->criteria,
                ], static fn (mixed $v): bool => $v !== null),
                $check->wordings,
            ) : null,
        ], static fn (mixed $v): bool => $v !== null && $v !== '');
    }

    public function run(Args $args, Output $output): int
    {
        $config = Config::discover($args->value('config'), '.');
        $catalogue = Catalogue::forRun($args->value('jev'), $config);
        $wanted = $args->argument(1);

        // The README says a check id is how you look one up. Printing all of
        // them instead answers a question nobody asked.
        if ($wanted !== null) {
            $check = $catalogue->find($wanted);

            if (! $check instanceof Check) {
                throw JevLintException::of(JevLintException::USAGE, $catalogue->findWritten($wanted) instanceof Check
                    ? Text::of('catalogue.check_not_for_version', [
                'id' => $wanted,
                'jev' => $catalogue->jev,
                'versions' => implode(', ', $catalogue->versions),
            ])
                    : Text::of('catalogue.no_such_check', ['ids' => $wanted]));
            }

            if ($args->value('format') === 'json') {
                $output->line(Json::encode($this->describe($check)));

                return 0;
            }

            foreach ($this->describe($check) as $key => $value) {
                $output->line(sprintf('%-12s %s', $key, is_scalar($value) ? (string) $value : Json::inline($value)));
            }

            return 0;
        }

        if ($args->value('format') === 'json') {
            $output->line(Json::encode(array_map($this->describe(...), $catalogue->all())));

            return 0;
        }

        $output->line(Text::of('catalogue.header', [
            'version' => $catalogue->version,
            'model' => $catalogue->model,
            'withheld' => $catalogue->withheld(),
        ]));
        $output->line();

        foreach (['static', 'model'] as $mode) {
            $output->line(strtoupper($mode));

            foreach ($catalogue->all() as $check) {
                if ($check->mode !== $mode) {
                    continue;
                }

                $output->line(sprintf(
                    '  %-8s %-34s %-12s %s',
                    $check->severity,
                    $check->id,
                    implode(',', $check->appliesTo),
                    $check->title,
                ));
            }

            $output->line();
        }

        return 0;
    }
}
