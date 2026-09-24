<?php

declare(strict_types=1);

namespace Phox\JevLint\Format;

use Phox\JevLint\I18n\Text;
use Phox\JevLint\SelfTest\CheckScore;

/** What each check scored against its own clean and broken examples */
final class SelfTestFormatter
{
    use Colour;

    public function __construct(private readonly bool $colour = true) {}

    /**
     * @param list<CheckScore> $scores
     */
    public function format(array $scores): string
    {
        $name = static fn (CheckScore $score): string => $score->domain === '' ? $score->check->id : $score->check->id.' ('.$score->domain.')';
        // Wide enough for the longest id with its domain, so a long one does not push its row out of line.
        $width = max([44, ...array_map(static fn (CheckScore $score): int => strlen($name($score)), $scores)]);
        $row = '%-'.$width.'s %7s %7s %7s %7s  %s';
        $lines = [
            $this->dim(Text::of('self_test.heading')),
            '',
            $this->paint(sprintf(
                $row,
                Text::of('self_test.column_check'),
                Text::of('self_test.column_clean'),
                Text::of('self_test.column_broken'),
                Text::of('self_test.column_fixed'),
                Text::of('self_test.column_span'),
                Text::of('self_test.column_verdict'),
            ), '1'),
        ];

        foreach ($scores as $score) {
            $lines[] = sprintf(
                $row,
                $name($score),
                $this->number($score->clean),
                $this->number($score->broken),
                $this->number($score->fixed),
                $this->number($score->span()),
                $this->verdict($score),
            );
        }

        $failed = array_filter($scores, static fn (CheckScore $score): bool => ! $score->passed());
        $lines[] = '';
        // One row per example set, and every check ships two. Counting rows as
        // checks read as though `--check=one-id` had matched two ids.
        $checks = array_unique(array_map(static fn (CheckScore $s): string => $s->check->id, $scores));
        $lines[] = Text::of('self_test.summary', [
            'separated' => count($scores) - count($failed),
            'sets' => count($scores),
            'checks' => count($checks),
        ]);

        if ($failed !== []) {
            $lines[] = $this->dim(Text::of('self_test.footer'));
        }

        return implode(PHP_EOL, $lines).PHP_EOL;
    }

    private function verdict(CheckScore $score): string
    {
        return match ($verdict = $score->verdict()) {
            'ok' => $this->paint($verdict, '32'),
            'weak' => $this->paint($verdict, '33'),
            default => $this->paint($verdict, '31'),
        };
    }

    private function number(?float $value): string
    {
        return $value === null ? 'n/a' : sprintf('%.2f', $value);
    }

}
