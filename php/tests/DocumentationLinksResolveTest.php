<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use PHPUnit\Framework\TestCase;

/**
 * A relative link is written against the page it sits in, so moving prose from
 * the README into docs/ breaks every link it carries. Nothing else notices:
 * the page still renders and the link still looks like a link
 */
final class DocumentationLinksResolveTest extends TestCase
{
    public function test_every_link_between_pages_resolves(): void
    {
        $root = __DIR__.'/../..';
        $broken = [];

        foreach ($this->pages($root) as $page) {
            $from = dirname($page);
            preg_match_all('/\]\(([^)#][^)]*?)(?:#[^)]*)?\)/', (string) file_get_contents($page), $links);

            foreach ($links[1] as $target) {
                if (str_starts_with($target, 'http')) {
                    continue;
                }

                if (! file_exists($from.'/'.$target)) {
                    $broken[] = sprintf('%s links to %s', substr($page, strlen($root) + 1), $target);
                }
            }
        }

        self::assertSame([], $broken, implode("\n", $broken));
    }

    /**
     * @return list<string>
     */
    private function pages(string $root): array
    {
        $pages = array_merge(
            [$root.'/README.md'],
            glob($root.'/docs/*.md') ?: [],
            glob($root.'/corpus/*.md') ?: [],
        );

        self::assertNotSame([], $pages, 'No pages found, so this test pins nothing.');

        return $pages;
    }
}
