<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Console\Args;
use Phox\JevLint\Console\Flags;
use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Report\Finding;
use Phox\JevLint\Report\Patch;
use Phox\JevLint\Report\Report;
use Phox\JevLint\Report\Severity;
use PHPUnit\Framework\TestCase;

/** The refusals that stop a run from looking like one that happened */
final class GuardsTest extends TestCase
{
    /**
     * @param list<string> $argv
     */
    private function guard(array $argv, string $command = 'check'): void
    {
        Flags::guard($command, Args::parse($argv));
    }

    public function test_an_option_written_with_one_dash_is_refused(): void
    {
        // It parsed as a positional, so the unknown-option guard never saw it and
        // the run went on to make the calls `--static-only` would have skipped.
        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('An option takes two dashes: write `-static-only` as `--static-only`.');

        $this->guard(['check', 'q.json', '-static-only']);
    }

    public function test_a_second_query_file_is_refused(): void
    {
        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('`jevlint check` takes one argument, so it has nothing to do with b.json.');

        $this->guard(['check', 'a.json', 'b.json']);
    }

    public function test_a_count_is_validated_even_where_this_run_would_not_read_it(): void
    {
        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('--repeats=abc is not a number.');

        $this->guard(['check', 'q.json', '--repeats=abc']);
    }

    public function test_a_flag_that_needs_a_call_is_refused_with_static_only(): void
    {
        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('--static-only makes no calls, so --all has nothing to do.');

        $this->guard(['check', 'q.json', '--static-only', '--all']);
    }

    public function test_a_value_option_written_bare_is_refused(): void
    {
        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('--jev takes a value.');

        $this->guard(['check', 'q.json', '--jev']);
    }

    public function test_a_query_that_is_a_json_list_is_refused(): void
    {
        $path = (string) tempnam(sys_get_temp_dir(), 'jevlint-query-');
        file_put_contents($path, '[]');

        try {
            $this->expectException(JevLintException::class);
            $this->expectExceptionMessage('holds a JSON list');

            Query::fromFile($path);
        } finally {
            @unlink($path);
        }
    }

    public function test_a_state_of_the_wrong_type_is_refused(): void
    {
        $this->expectException(JevLintException::class);
        $this->expectExceptionMessage('"state" holds a number');

        Query::fromArray(['state' => 42, 'questions' => []], 'q.json');
    }

    public function test_a_patch_says_when_an_earlier_one_removes_the_node_it_writes(): void
    {
        $report = new Report('q.json', '1');
        $report->add($this->finding('a/removes', '/questions/one', new Patch('remove', '/questions/one')));
        $report->add($this->finding('b/removes-too', '/questions/one', new Patch('remove', '/questions/one')));
        $report->add($this->finding('c/adds-inside', '/questions/one', new Patch(
            'add',
            '/questions/one/criteria',
            ['other' => 'Anything else'],
        )));
        $report->add($this->finding('d/elsewhere', '/questions/two', new Patch('add', '/questions/two/criteria', [])));

        $rows = [];

        foreach ($report->toArray()['findings'] as $row) {
            $rows[$row['check']] = $row['patch']['covered_by'] ?? null;
        }

        self::assertSame([
            'a/removes' => null,
            'b/removes-too' => 'a/removes',
            'c/adds-inside' => 'a/removes',
            'd/elsewhere' => null,
        ], $rows);
    }

    private function finding(string $check, string $path, Patch $patch): Finding
    {
        return new Finding(
            checkId: $check,
            title: 'A title',
            severity: Severity::Error,
            target: 'one',
            message: 'A message',
            mode: 'static',
            path: $path,
            patch: $patch,
        );
    }
}
