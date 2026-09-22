<?php

declare(strict_types=1);

namespace Phox\JevLint\Format;

use Phox\JevLint\I18n\Text;
use Phox\JevLint\Probe\Probe;
use Phox\JevLint\Report\Note;
use Phox\JevLint\Probe\QuestionProbe;
use Phox\JevLint\Probe\Reading;

/** The probe's readings as a table per question */
final class ProbeFormatter
{
    use Colour;

    public function __construct(private readonly bool $colour = true) {}

    /**
     * @param array<string, QuestionProbe> $probes
     * @param list<Note>                   $notes
     */
    public function format(array $probes, string $source, int $repeats, int $calls, int $tokens, array $notes = []): string
    {
        $lines = [
            $this->dim(Text::of('probe.header', [
                'source' => $source,
                'repeats' => $repeats,
                'calls' => $calls,
                'tokens' => number_format($tokens),
            ])),
            '',
        ];

        $moved = 0;

        foreach ($probes as $id => $probe) {
            $lines = array_merge($lines, $this->question($id, $probe));
            $lines[] = '';

            if ($this->movedQuestions($probe) > 0) {
                $moved++;
            }
        }

        $lines = array_merge($lines, $this->legend($probes));

        foreach ($notes as $note) {
            $lines[] = $this->paint($note->isUnreachable() ? Text::of('label.failed') : Text::of('label.note'), '33').' '.$note->message;
        }

        // Name the rewrites that moved. Reassuring the reader about
        // `criteria-stripped` whenever it merely ran pointed them away from
        // whichever variant was the reason the run failed.
        $movers = $this->moversIn($probes);

        $lines[] = Text::of('probe.summary', ['moved' => $moved, 'questions' => count($probes)])
            .($movers === [] ? '' : Text::of('probe.movers', [
                'count' => count($movers),
                'names' => implode(', ', array_map(static fn (string $v): string => '`'.$v.'`', $movers)),
            ]))
            .(in_array('criteria-stripped', $movers, true) ? Text::of('probe.criteria_stripped_moved') : '');
        $lines[] = $this->dim(Text::of('probe.starred_legend', [
            'negligible' => QuestionProbe::NEGLIGIBLE,
            'floor' => Probe::PUBLISHED_NOISE,
        ]));

        return implode(PHP_EOL, $lines).PHP_EOL;
    }

    /**
     * What each rewrite did to the query, named once at the end
     *
     * @param  array<string, QuestionProbe> $probes
     * @return list<string>
     */
    private function legend(array $probes): array
    {
        // The key is the variant name, which is an identifier the JSON carries
        // and `--variants` matches on, so it is not translated.
        $seen = ['unchanged' => Text::of('probe.unchanged_describe')];

        foreach ($probes as $probe) {
            foreach ($probe->readings as $reading) {
                $seen[$reading->variant] = $reading->describe;
            }
        }

        $lines = [$this->dim(Text::of('probe.legend_heading'))];

        foreach ($seen as $name => $describe) {
            $lines[] = $this->dim(sprintf('  %-20s %s', $name, $describe));
        }

        return [...$lines, ''];
    }

    /**
     * @return list<string>
     */
    private function question(string $id, QuestionProbe $probe): array
    {
        $baseline = $probe->baseline();
        $lines = [$this->paint($id, '1').$this->dim(sprintf(
            '  %s%s',
            $probe->question->type,
            $probe->reading === null ? '' : ', '.$probe->reading,
        ))];

        if ($baseline === null) {
            $lines[] = '  '.$this->paint(Text::of('probe.no_reading'), '31');

            return $lines;
        }

        $noise = $probe->noise();
        $lines[] = sprintf(
            '    %s %s %s',
            str_pad('unchanged', 20),
            $this->value($baseline),
            $this->dim($noise === null ? '' : Text::of('probe.noise', [
                'noise' => $noise,
                'below' => $noise < Probe::PUBLISHED_NOISE ? 'yes' : 'no',
            ])),
        );

        foreach ($probe->readings as $reading) {
            $lines[] = $this->reading($probe, $reading);
        }

        return $lines;
    }

    private function reading(QuestionProbe $probe, Reading $reading): string
    {
        if ($reading->value === null) {
            return sprintf('  %s %s', str_pad($reading->variant, 20), $this->paint($reading->error ?? Text::of('probe.no_reading'), '31'));
        }

        $delta = $probe->delta($reading) ?? 0.0;
        $ratio = $probe->ratio($reading) ?? 0.0;
        $moved = $probe->moved($reading);

        $line = sprintf(
            '  %s %s %s  %s',
            $moved ? $this->paint('*', '33') : ' ',
            str_pad($reading->variant, 20),
            $this->value($reading->value),
            sprintf('%+.3f', $delta),
        );

        $tail = Text::of('probe.noise_ratio', ['ratio' => $ratio]);

        return $line.'  '.($moved ? $this->paint($tail.', moved', '33') : $this->dim($tail));
    }

    /**
     * Every variant name that moved an answer, across all the questions.
     *
     * @param  array<string, QuestionProbe> $probes
     * @return list<string>
     */
    private function moversIn(array $probes): array
    {
        $movers = [];

        foreach ($probes as $probe) {
            foreach ($probe->readings as $reading) {
                if ($probe->moved($reading)) {
                    $movers[$reading->variant] = true;
                }
            }
        }

        return array_keys($movers);
    }

    private function movedQuestions(QuestionProbe $probe): int
    {
        return count(array_filter($probe->readings, $probe->moved(...)));
    }

    private function value(float $value): string
    {
        return sprintf('%.3f', $value);
    }

}
