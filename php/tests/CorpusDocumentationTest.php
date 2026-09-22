<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use PHPUnit\Framework\TestCase;

/**
 * The corpus scripts are what produced the tables in docs/evidence.md, and a script
 * with no command written down is a figure nobody can produce again
 */
final class CorpusDocumentationTest extends TestCase
{
    private const CORPUS = __DIR__.'/../../corpus';

    /**
     * Naming a script in the table of what each one is does not say how to run
     * it. Only the fenced blocks carry a command, so only those count.
     */
    public function test_every_corpus_script_has_a_command_somebody_can_run(): void
    {
        $readme = (string) file_get_contents(self::CORPUS.'/README.md');

        preg_match_all('/```sh\n(.*?)```/s', $readme, $blocks);
        $commands = implode("\n", $blocks[1]);

        $missing = [];

        foreach (glob(self::CORPUS.'/*.py') ?: [] as $script) {
            if (! str_contains($commands, 'corpus/'.basename($script))) {
                $missing[] = basename($script);
            }
        }

        self::assertSame([], $missing, sprintf(
            'corpus/README.md has no command for %s.',
            implode(', ', $missing),
        ));
    }

    /**
     * What a harvest costs is what a reader decides on before paying for one,
     * and nothing else ties the figure in the prose to the run behind it
     */
    public function test_the_harvest_cost_the_readme_quotes_is_what_the_last_harvest_paid(): void
    {
        $scores = json_decode((string) file_get_contents(self::CORPUS.'/scores.json'), true);

        self::assertIsArray($scores);
        self::assertArrayHasKey('calls', $scores, 'corpus/scores.json records no call count for this to pin.');

        $readme = (string) file_get_contents(self::CORPUS.'/README.md');

        self::assertMatchesRegularExpression(
            '/\b'.preg_quote((string) $scores['calls'], '/').' calls\b/',
            $readme,
            sprintf('corpus/scores.json was harvested over %s calls. corpus/README.md quotes a different number.', (string) $scores['calls']),
        );
    }
}
