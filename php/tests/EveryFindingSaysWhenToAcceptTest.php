<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use PHPUnit\Framework\TestCase;

/**
 * A model check is a judgement, and a reader who disagrees needs to know what
 * disagreeing looks like. A finding that describes only the defect offers two
 * options, obey or ignore, and no way to record a reason for the third
 */
final class EveryFindingSaysWhenToAcceptTest extends TestCase
{
    public function test_every_model_check_names_the_case_where_the_finding_is_one_to_accept(): void
    {
        $silent = [];

        foreach (Catalogue::load()->written() as $check) {
            if (! $check->isModel()) {
                continue;
            }

            $said = $check->hint.' '.$check->advice;

            if (preg_match('/\bAccept it where\b|\bworth accepting\b|\bis the case to accept\b/i', $said) !== 1) {
                $silent[] = $check->id;
            }
        }

        self::assertSame([], $silent, sprintf(
            "These checks describe the defect and never say when the finding is one to live with:\n  %s",
            implode("\n  ", $silent),
        ));
    }
}
