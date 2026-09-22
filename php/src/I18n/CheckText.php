<?php

declare(strict_types=1);

namespace Phox\JevLint\I18n;

use Phox\JevLint\Support\Json;

/**
 * What a check reports about your query, in the reader's language.
 *
 * These live beside the catalogue and not in `lang/`, because the catalogue is
 * not PHP: an implementation in another language reads the same file. A locale
 * with no file, or a check with no entry in it, is answered from the catalogue
 *
 * The question a model check puts to Jev is never read from here. Translating
 * it would change what the check measures, and every number in docs/evidence.md
 * was taken with the wording in the catalogue
 */
final class CheckText
{
    /** What a translation may replace. `question`, `trigger` and `docs` are not words about a query */
    public const FIELDS = ['title', 'message', 'hint', 'suggest'];

    /** @var array<string, array<string, array<string, string>>> by locale, then check id */
    private static array $loaded = [];

    /**
     * The fields a translation replaces for one check, in the order Text reads
     * its locales, so a region file wins over its language
     *
     * @return array<string, string>
     */
    public static function for(string $id): array
    {
        $found = [];

        foreach (self::locales() as $locale) {
            foreach (self::bundle($locale)[$id] ?? [] as $field => $text) {
                if (! isset($found[$field]) && in_array($field, self::FIELDS, true)) {
                    $found[$field] = $text;
                }
            }
        }

        return $found;
    }

    public static function reset(): void
    {
        self::$loaded = [];
    }

    /**
     * @return list<string>
     */
    private static function locales(): array
    {
        $locale = Text::locale();

        if ($locale === Text::FALLBACK) {
            return [];
        }

        return str_contains($locale, '_')
            ? [$locale, substr($locale, 0, (int) strpos($locale, '_'))]
            : [$locale];
    }

    /**
     * @return array<string, array<string, string>>
     */
    private static function bundle(string $locale): array
    {
        if (isset(self::$loaded[$locale])) {
            return self::$loaded[$locale];
        }

        $path = self::locate($locale);

        if ($path === null) {
            return self::$loaded[$locale] = [];
        }

        $bundle = [];

        foreach (Json::readFile($path) as $id => $fields) {
            if (is_string($id) && is_array($fields)) {
                $bundle[$id] = array_filter($fields, is_string(...));
            }
        }

        return self::$loaded[$locale] = $bundle;
    }

    private static function locate(string $locale): ?string
    {
        $fromEnv = getenv('JEVLINT_CHECKS_DIR');
        $candidates = [];

        if (is_string($fromEnv) && $fromEnv !== '') {
            $candidates[] = rtrim($fromEnv, '/').'/lang/'.$locale.'.json';
        }

        $candidates[] = __DIR__.'/../../../checks/lang/'.$locale.'.json';
        $candidates[] = __DIR__.'/../../checks/lang/'.$locale.'.json';

        foreach ($candidates as $candidate) {
            if (is_file($candidate)) {
                return $candidate;
            }
        }

        return null;
    }
}
