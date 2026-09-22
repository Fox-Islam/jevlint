<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Console\Application;
use PHPUnit\Framework\TestCase;

/**
 * `jevlint --version` printed 0.1.0 from a tag that said 1.0.0, because nothing
 * read both. A report carries this number, so a run checked by one build and
 * reported as another is the thing it makes untraceable
 */
final class VersionMatchesTheTagTest extends TestCase
{
    public function test_the_version_the_tool_prints_is_not_behind_the_newest_tag(): void
    {
        $root = dirname(__DIR__, 2);

        if (! is_dir($root.'/.git')) {
            // A dist archive has no tags to read. Nothing to compare, and
            // nothing wrong.
            self::markTestSkipped('Not a git checkout.');
        }

        exec(sprintf('git -C %s tag --sort=-v:refname 2>/dev/null', escapeshellarg($root)), $tags);
        $tags = array_values(array_filter($tags, static fn (string $t): bool => preg_match('/^v?\d+\.\d+\.\d+$/', $t) === 1));

        if ($tags === []) {
            self::markTestSkipped('No release tag yet.');
        }

        $newest = ltrim($tags[0], 'v');

        // Ahead is fine: the constant is bumped, then the tag is cut. Behind
        // means a release went out printing an older number than it is.
        self::assertTrue(
            version_compare(Application::VERSION, $newest, '>='),
            sprintf('jevlint --version prints %s, behind the tag %s.', Application::VERSION, $tags[0]),
        );
    }
}
