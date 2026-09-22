<?php

declare(strict_types=1);

namespace Phox\JevLint\Format;

use Phox\JevLint\I18n\Text;
use Phox\JevLint\Lint\ModelLinter;
use Phox\JevLint\Report\Finding;
use Phox\JevLint\Report\Patch;
use Phox\JevLint\Report\Report;
use Phox\JevLint\Report\Severity;
use Phox\JevLint\Support\Json;

/** The report as a terminal reads it: grouped by what the finding is about */
final class TextFormatter
{
    use Colour;

    private const WIDTH = 96;

    private const LABEL = 11;

    public function __construct(
        private readonly bool $colour = true,
        private readonly bool $brief = false,
        private readonly bool $showAccepted = false,
        private readonly bool $showCleared = false,
    ) {}

    public function format(Report $report, ?Severity $floor = null): string
    {
        $findings = $report->findings($floor);
        $lines = [$this->dim(Text::of('report.header', [
            'source' => $report->source,
            'version' => $report->catalogueVersion,
            'fingerprint' => $report->fingerprint,
            'model' => $report->model,
            'pinned' => $report->askedThrough === null ? 'no' : 'yes',
            'through' => $report->askedThrough ?? '',
        ]))];

        if ($this->hasProbabilities($findings)) {
            $lines[] = $this->dim(Text::of('report.probability_note'));
        }

        $lines[] = '';

        if ($findings === []) {
            $hidden = count($report->findings());

            $lines[] = match (true) {
                // A run that evaluated nothing has nothing to report in a sense
                // no reader means by it.
                $report->askedCount() === 0 => $this->paint(Text::of('report.nothing_ran'), '31'),
                $hidden > 0 => $this->paint(Text::of('report.all_hidden', ['count' => $hidden]), '33'),
                // "Nothing to report" beside an exit of 3 reads as a pass.
                $report->unstable() !== [] => $this->paint(Text::of('report.only_undecided'), '33'),
                default => $this->paint(Text::of('report.nothing_to_report'), '32'),
            };
            $lines[] = '';
        }

        foreach ($this->groupByTarget($findings) as $target => $group) {
            // A question id of "0" is an int by the time it is an array key.
            $lines[] = $this->paint((string) $target, '1');

            foreach ($group as $i => $finding) {
                if ($i > 0 && ! $this->brief) {
                    $lines[] = '';
                }

                $lines = array_merge($lines, $this->brief
                    ? $this->briefly($finding)
                    : $this->fully($finding, $report));
            }

            $lines[] = '';
        }

        $cleared = $report->cleared();

        // Without `--all` the report still carries the readings that landed near
        // their trigger, because they are the ones worth a second look and they
        // cost nothing more to print.
        if (! $this->showCleared) {
            $cleared = array_values(array_filter(
                $cleared,
                // A caveat on a cleared reading says what that reading cannot
                // tell you, so it is kept however far from the trigger it landed.
                static fn (Finding $f): bool => $f->advice !== ''
                    || ($f->probability !== null
                        && $f->trigger !== null
                        && abs($f->probability - $f->trigger) <= ModelLinter::WORTH_SEEING),
            ));
        }

        if ($cleared !== []) {
            $lines[] = $this->paint(
                $this->showCleared ? Text::of('report.cleared_all') : Text::of('report.cleared_near'),
                '1',
            );

            foreach ($cleared as $finding) {
                $lines[] = $this->dim(sprintf(
                    '  %-34s %-24s %s%s',
                    $finding->checkId,
                    // A per-field check reports every field against the same target,
                    // so without the path these rows are indistinguishable.
                    $this->shorten($this->where($finding), 30),
                    Text::of('report.against_trigger', [
                        'probability' => $finding->probability ?? 0.0,
                        'trigger' => $finding->trigger ?? 0.0,
                    ]),
                    match (true) {
                        // A reading over the trigger in a list of things that
                        // cleared needs the reason beside it, or it reads as a
                        // defect that got away.
                        $finding->clearedBecause !== '' => ' - '.$finding->clearedBecause,
                        $finding->nearTrigger => Text::of('report.close_to_the_line'),
                        default => '',
                    },
                ));

                // The reading cleared and the caveat says that proves nothing.
                // Printing the number without it is the misreading it warns of.
                if ($finding->advice !== '') {
                    $lines = array_merge($lines, $this->wrap('  '.Text::of('label.caveat'), $finding->advice, '33'));
                }
            }

            $lines[] = '';
        }

        $unstable = $report->unstable();

        if ($unstable !== []) {
            $lines[] = $this->paint(Text::of('report.undecided_heading', ['count' => count($unstable)]), '33');

            foreach ($unstable as $finding) {
                $lines[] = $this->dim('  '.Text::of('report.undecided_row', [
                    'check' => $finding->checkId,
                    'target' => $finding->target,
                    'readings' => $finding->readings === []
                        ? Text::of('report.against_trigger', ['probability' => $finding->probability ?? 0.0, 'trigger' => $finding->trigger ?? 0.0])
                        : implode(', ', array_map(static fn (float $p): string => Text::of('report.probability', ['probability' => $p]), $finding->readings))
                            .Text::of('report.against_trigger_tail', ['trigger' => $finding->trigger ?? 0.0]),
                ]));

                // What the check was looking for, and what to do if it is right.
                // The uncertainty is about whether, not about what to do, and
                // printing the id alone made the deepest finding in some runs the
                // least useful line in the report.
                $lines = array_merge($lines, $this->wrap('', $finding->message));

                if ($finding->suggest !== '') {
                    $lines = array_merge($lines, $this->wrap(Text::of('label.if_it_is'), $finding->suggest));
                }
            }

            $lines[] = '';
        }

        $accepted = $report->accepted();

        if ($accepted !== []) {
            $lines[] = $this->dim(Text::of('report.accepted_heading', [
                'count' => count($accepted),
                'source' => $report->acceptedFrom(),
                'listed' => $this->showAccepted ? 'yes' : 'no',
            ]));

            if ($this->showAccepted) {
                foreach ($accepted as $finding) {
                    $lines[] = $this->dim('  '.Text::of('report.check_on_target', ['check' => $finding->checkId, 'target' => $finding->target]));
                    $lines = array_merge($lines, $this->wrap('', $finding->accepted ?? ''));
                }
            }

            $lines[] = '';
        }

        $unreachable = $report->unreachableNotes();

        if ($unreachable !== []) {
            $lines[] = $this->paint(Text::of('report.calls_lost', ['count' => count($unreachable)]), '31');
            $lines[] = '';
        }

        foreach ($report->notes() as $note) {
            $lines[] = $this->paint($note->isUnreachable() ? Text::of('label.failed') : Text::of('label.note'), '33').' '.$note->message;
        }

        if ($report->notes() !== []) {
            $lines[] = '';
        }

        if ($this->patched !== []) {
            $means = [
                Patch::LOSSLESS => Text::of('patch.lossless'),
                Patch::LOSSY => Text::of('patch.lossy'),
                Patch::DESTRUCTIVE => Text::of('patch.destructive'),
            ];

            $lines[] = $this->dim(Text::of('patch.legend', ['kinds' => implode('; ', array_map(
                static fn (string $k): string => $k.', '.$means[$k],
                array_keys(array_intersect_key($means, $this->patched)),
            ))]));
            $lines[] = '';
        }

        $lines[] = $this->summary($report);

        return implode(PHP_EOL, $lines).PHP_EOL;
    }

    /**
     * The checks whose reasoning has already been printed in this run.
     *
     * One check firing on six state fields printed the same two lines of Why and
     * the same Docs link six times, which buries the six field names that are the
     * only part that differs.
     *
     * @var array<string, true>
     */
    private array $explained = [];

    /** @var array<string, true> */
    private array $patched = [];

    /**
     * The finding as somebody meeting the check for the first time reads it:
     * what is wrong, then what to write instead, then why it matters
     *
     * @return list<string>
     */
    private function fully(Finding $finding, Report $report): array
    {
        $repeat = isset($this->explained[$finding->checkId]);
        $this->explained[$finding->checkId] = true;

        $lines = [sprintf('  %s  %s', $this->severityLabel($finding->severity), $this->paint($finding->title, '1'))];
        $lines[] = '           '.$this->dim($finding->checkId);
        $lines = array_merge($lines, $this->wrap('', $finding->message));
        $lines = array_merge($lines, $this->wrap(
            $finding->measure === 'weight' ? Text::of('label.weight') : Text::of('label.likelihood'),
            $this->likelihood($finding),
        ));

        $supersededBy = $report->supersededBy($finding);

        if ($supersededBy !== null) {
            $lines = array_merge($lines, $this->wrap(
                Text::of('label.moot_if'),
                Text::of('report.moot_if', ['check' => $supersededBy]),
            ));
        }

        $supersedes = $report->superseding($finding);

        if ($supersedes !== []) {
            $lines = array_merge($lines, $this->wrap(
                Text::of('label.also_drops'),
                Text::of('report.also_drops', ['checks' => implode(', ', $supersedes)]),
            ));
        }

        if ($finding->evidence !== null) {
            // A static rule quotes what it read, which for a thirty-option Choice
            // is every label. The JSON carries it whole.
            $lines = array_merge($lines, $this->wrap(Text::of('label.found'), $this->shorten($finding->evidence, 220)));
        }

        if ($finding->readings !== []) {
            $places = $finding->nearTrigger || $finding->unstable ? 3 : 2;
            $lines = array_merge($lines, $this->wrap(Text::of('label.readings'), Text::of('report.readings', [
                'of' => $finding->readingsOf ?? Text::of('readings.repeats_word'),
                'readings' => implode(', ', array_map(
                    static fn (float $p): string => number_format($p, $places),
                    $finding->readings,
                )),
                'spread' => number_format(max($finding->readings) - min($finding->readings), $places),
            ])));
        }

        // Both, always. A patch says what to do to the file; the suggestion says
        // what to do about the query. On a `remove` patch the suggestion is the
        // only one of the two that tells you how to keep the answer you wanted.
        if ($finding->suggest !== '') {
            $lines = array_merge($lines, $this->wrap(Text::of('label.suggested'), $finding->suggest, '32'));
        }

        // What the self-test measured about this suggestion, where it is weak. A
        // reader deciding whether to act on advice is owed how far it got on the
        // check's own example.
        if ($finding->advice !== '' && ! $repeat) {
            $lines = array_merge($lines, $this->wrap(Text::of('label.advice'), $finding->advice, '33'));
        }

        if ($finding->patch !== null) {
            $this->patched[$finding->patch->safety] = true;
            $covered = $report->patchCoveredBy($finding);

            $lines = array_merge($lines, $this->wrap(
                Text::of('label.patch'),
                ($finding->patch->op === 'remove'
                    ? Text::of('report.patch', [
                        'safety' => $finding->patch->safety,
                        'op' => $finding->patch->op,
                        'path' => $finding->patch->path,
                    ])
                    : Text::of('report.patch_with_value', [
                        'safety' => $finding->patch->safety,
                        'op' => $finding->patch->op,
                        'path' => $finding->patch->path,
                        // The whole value goes out in the JSON, where a program
                        // reads it. Printing a rewritten thirty-option Choice to
                        // a terminal buries the finding it belongs to.
                        'value' => $this->shorten(Json::inline($finding->patch->value), 160),
                    ]))
                    .($covered === null ? '' : Text::of('report.patch_covered_by', ['check' => $covered])),
                '32',
            ));
        }

        if ($finding->hint !== '' && ! $repeat) {
            $lines = array_merge($lines, $this->wrap(Text::of('label.why'), $finding->hint));
        }

        if ($finding->docs !== null) {
            if (! $repeat) {
                $lines[] = $this->dim(sprintf('           %-'.self::LABEL.'s %s', Text::of('label.docs'), $finding->docs));
            }
        }

        return $lines;
    }

    /**
     * @return list<string>
     */
    private function briefly(Finding $finding): array
    {
        $head = sprintf('  %s  %s', $this->severityLabel($finding->severity), $this->paint($finding->checkId, '36'));

        if ($finding->probability !== null) {
            $head .= $this->dim(sprintf('  %.2f', $finding->probability));
        }

        $lines = [$head, '    '.$finding->message];

        if ($finding->suggest !== '') {
            $lines[] = '    '.$this->paint('→ ', '32').$finding->suggest;
        }

        return $lines;
    }

    /**
     * How strongly the check read the defect, and the bar it had to clear.
     *
     * Its own field, beside what was found and what to do, because it is one of
     * the things a reader weighs and not a footnote on the check's name.
     */
    private function likelihood(Finding $finding): string
    {
        if ($finding->probability === null) {
            return Text::of('likelihood.certain');
        }

        // One check asks which primitive fits instead of whether a defect is
        // present, so its number is a weight and the bands do not apply to it.
        if ($finding->measure === 'weight') {
            return Text::of('likelihood.weight', [
                'weight' => number_format($finding->probability, 2),
                'trigger' => number_format($finding->trigger ?? 0.0, 2),
            ]);
        }

        $near = $finding->nearTrigger
            ? Text::of('likelihood.near_trigger', ['near' => ModelLinter::NEAR])
            : '';

        $straddled = $finding->unstable
            ? Text::of('likelihood.straddled')
            : '';

        // Two places rounded 0.704 and its 0.70 trigger to the same number, so a
        // finding said its readings disagreed and printed numbers that did not.
        $places = $finding->nearTrigger || $finding->unstable ? 3 : 2;

        return Text::of('likelihood.probability', [
            'probability' => number_format($finding->probability, $places),
            'band' => $this->band($finding->probability),
            'trigger' => number_format($finding->trigger ?? 0.0, $places),
            'near' => $near,
            'straddled' => $straddled,
        ]);
    }

    /** Words for a probability, so the number is not read as a score out of one */
    private function band(float $probability): string
    {
        return match (true) {
            $probability >= 0.90 => Text::of('band.almost_certain'),
            $probability >= 0.75 => Text::of('band.very_likely'),
            $probability >= 0.50 => Text::of('band.likely'),
            $probability >= 0.25 => Text::of('band.unlikely'),
            default => Text::of('band.very_unlikely'),
        };
    }

    /**
     * @return list<string>
     */
    private function wrap(string $label, string $text, ?string $colour = null): array
    {
        $indent = str_repeat(' ', 11 + ($label === '' ? 0 : self::LABEL + 1));
        $words = preg_split('/\s+/', trim($text)) ?: [];
        $lines = [];
        $current = '';

        foreach ($words as $word) {
            if ($current !== '' && strlen($current) + strlen($word) + 1 > self::WIDTH - strlen($indent)) {
                $lines[] = $current;
                $current = $word;

                continue;
            }

            $current = $current === '' ? $word : $current.' '.$word;
        }

        if ($current !== '') {
            $lines[] = $current;
        }

        $out = [];

        foreach ($lines as $i => $line) {
            $body = $colour === null ? $line : $this->paint($line, $colour);
            $out[] = $i === 0 && $label !== ''
                ? sprintf('           %-'.self::LABEL.'s %s', $label, $body)
                : $indent.$body;
        }

        return $out;
    }

    private function summary(Report $report): string
    {
        $counts = Text::of('report.counts', [
            'errors' => $report->count(Severity::Error),
            'warnings' => $report->count(Severity::Warning),
            'advice' => $report->count(Severity::Advice),
        ]);

        if ($report->calls() === 0) {
            return $counts.$this->dim(Text::of('report.no_calls'));
        }

        // A call whose answer carried no usage is not a call that cost nothing,
        // so the token figure is marked a floor instead of printing a total
        // that is short by an unknown amount.
        return $counts.$this->dim(Text::of('report.cost', [
            'calls' => $report->calls(),
            'floor' => $report->callsWithoutUsage() > 0 ? 'yes' : 'no',
            'tokens' => number_format($report->tokens()),
        ]));
    }

    /**
     * @param list<Finding> $findings
     */
    private function hasProbabilities(array $findings): bool
    {
        foreach ($findings as $finding) {
            // A weight is not a probability, so a report carrying only weights
            // should not print the sentence explaining probabilities.
            if ($finding->probability !== null && $finding->measure === 'probability') {
                return true;
            }
        }

        return false;
    }

    /**
     * @param  list<Finding>                $findings
     * @return array<string, list<Finding>>
     */
    private function groupByTarget(array $findings): array
    {
        $grouped = [];

        foreach ($findings as $finding) {
            $grouped[$finding->target][] = $finding;
        }

        return $grouped;
    }

    /**
     * The severity, padded so the titles beside it line up.
     *
     * The width comes from the three translations and not from the seven
     * characters `warning` happens to take, because another language has its
     * own longest word
     */
    private function severityLabel(Severity $severity): string
    {
        $words = [
            Severity::Error->value => Text::of('severity.error'),
            Severity::Warning->value => Text::of('severity.warning'),
            Severity::Advice->value => Text::of('severity.advice'),
        ];
        $width = max(array_map(mb_strlen(...), $words));

        return $this->paint(mb_str_pad($words[$severity->value], $width), match ($severity) {
            Severity::Error => '31',
            Severity::Warning => '33',
            Severity::Advice => '34',
        });
    }

    /**
     * Which thing this reading was about.
     *
     * The target alone is right for a question check and useless for a per-field
     * one, where every row reads `state`. What the path adds beyond the target
     * is the field name, which is the only part that differs.
     */
    private function where(Finding $finding): string
    {
        $target = $finding->target;
        $prefix = '/'.($target === 'state' ? 'state' : 'questions/'.$target);

        if ($finding->path === '' || $finding->path === $prefix) {
            return $target;
        }

        $extra = str_starts_with($finding->path, $prefix.'/')
            ? substr($finding->path, strlen($prefix) + 1)
            : ltrim($finding->path, '/');

        return $target.' · '.str_replace('/', '.', $extra);
    }

    private function shorten(string $text, int $limit): string
    {
        return strlen($text) <= $limit ? $text : substr($text, 0, $limit - 1).'…';
    }

}
