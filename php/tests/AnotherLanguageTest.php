<?php

declare(strict_types=1);

namespace Phox\JevLint\Tests;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\I18n\CheckText;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Lint\Linter;
use Phox\JevLint\Query\Query;
use PHPUnit\Framework\TestCase;

/**
 * Jev answers in whatever language the query is written in, so a query in
 * French is a query this has to check. The messages are one half of that; the
 * word lists a check matches against are the other, and only the second can
 * turn a clean query into a finding
 */
final class AnotherLanguageTest extends TestCase
{
    private string $dir = '';

    protected function setUp(): void
    {
        $this->dir = sys_get_temp_dir().'/jevlint-lang-'.bin2hex(random_bytes(4));
        mkdir($this->dir);
        file_put_contents($this->dir.'/fr.php', <<<'PHP'
            <?php

            return [
                'file.unreadable' => 'Impossible de lire {path}.',
                'words.fallback_labels' => ['autre', 'autres', 'aucun'],
            ];
            PHP);
        mkdir($this->dir.'/checks');
        mkdir($this->dir.'/checks/lang');
        copy(Catalogue::locate('catalogue.json'), $this->dir.'/checks/catalogue.json');
        copy(Catalogue::locate('fixtures.json'), $this->dir.'/checks/fixtures.json');
        file_put_contents($this->dir.'/checks/lang/fr.json', json_encode([
            'choice/no-fallback' => [
                'title' => 'Le Choice n\'a pas d\'option de repli',
                'question' => ['instructions' => 'traduit'],
            ],
        ]));
        putenv('JEVLINT_LANG_DIR='.$this->dir);
        Text::reset();
        CheckText::reset();
    }

    protected function tearDown(): void
    {
        foreach (['/checks/lang', '/checks', ''] as $under) {
            array_map(unlink(...), array_filter(glob($this->dir.$under.'/*') ?: [], is_file(...)));
            rmdir($this->dir.$under);
        }
        putenv('JEVLINT_LANG_DIR');
        putenv('JEVLINT_CHECKS_DIR');
        Text::reset();
        CheckText::reset();
    }

    public function test_a_message_the_locale_has_is_answered_in_it(): void
    {
        Text::use('fr');

        self::assertSame('Impossible de lire q.json.', Text::of('file.unreadable', ['path' => 'q.json']));
    }

    /** A part-finished translation prints English, never a key */
    public function test_a_message_the_locale_leaves_out_falls_back_to_english(): void
    {
        Text::use('fr');

        self::assertSame('Nothing to report.', Text::of('report.nothing_to_report'));
    }

    public function test_a_region_falls_back_to_its_language(): void
    {
        Text::use('fr_CA');

        self::assertSame('Impossible de lire q.json.', Text::of('file.unreadable', ['path' => 'q.json']));
    }

    /**
     * The check reads option labels, and `autre` is a catch-all to every French
     * reader and to nothing in an English list
     */
    public function test_a_catch_all_in_the_locale_clears_the_check_that_looks_for_one(): void
    {
        Text::use('en');
        self::assertSame(['choice/no-fallback'], $this->fallbackFindings());

        Text::use('fr');
        self::assertSame([], $this->fallbackFindings());
    }

    /** An English label in a query written in French is still a catch-all */
    public function test_the_english_list_is_read_beside_the_locale_one(): void
    {
        Text::use('fr');

        self::assertSame([], $this->fallbackFindings('other'));
    }

    public function test_a_check_says_its_piece_in_the_locale(): void
    {
        Text::use('fr');
        putenv('JEVLINT_CHECKS_DIR='.$this->dir.'/checks');
        CheckText::reset();

        $check = Catalogue::load($this->dir.'/checks/catalogue.json')->find('choice/no-fallback');

        self::assertNotNull($check);
        self::assertSame("Le Choice n'a pas d'option de repli", $check->title);
    }

    /**
     * The question a check puts to Jev is what the check measures, and every
     * figure in docs/evidence.md was taken with the wording in the
     * catalogue. A translation cannot reach it
     */
    public function test_a_translation_cannot_change_what_a_check_asks_jev(): void
    {
        Text::use('fr');
        putenv('JEVLINT_CHECKS_DIR='.$this->dir.'/checks');
        CheckText::reset();

        $check = Catalogue::load($this->dir.'/checks/catalogue.json')->find('choice/no-fallback');

        self::assertNotNull($check);
        self::assertNotContains('question', array_keys(CheckText::for('choice/no-fallback')));
    }

    /**
     * @return list<string>
     */
    private function fallbackFindings(string $catchAll = 'autre'): array
    {
        $report = Linter::rulesOnly()->only(['choice/no-fallback'])->check(Query::fromArray([
            'state' => ['demande' => "J'ai été facturé deux fois."],
            'questions' => [
                'service' => [
                    'type' => 'choice',
                    'instructions' => 'Quel service doit traiter cette demande ?',
                    'criteria' => [
                        'facturation' => 'Les factures',
                        'expedition' => 'La livraison',
                        $catchAll => 'Le reste',
                    ],
                ],
            ],
        ]));

        return array_map(static fn ($finding): string => $finding->checkId, $report->findings());
    }
}
