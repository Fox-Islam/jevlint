<?php

declare(strict_types=1);

namespace Phox\JevLint\I18n;

use MessageFormatter;

/**
 * Every message the tool prints, in the reader's language.
 *
 * Patterns are ICU MessageFormat, so a plural is chosen by the locale's CLDR
 * rules instead of by a `=== 1` written here. English takes two forms and
 * Polish four. A locale file needs only the keys it translates, and the rest
 * are read from English, so a part-finished translation prints English
 */
final class Text
{
    public const FALLBACK = 'en';

    private static string $locale = self::FALLBACK;

    /** @var array<string, array<string, mixed>> loaded bundles, by locale */
    private static array $bundles = [];

    /**
     * The locale to answer in.
     *
     * A tag no file has falls back a step at a time, `fr_CA` to `fr` to
     * English, so a missing `fr_CA` reaches French before it reaches English
     */
    public static function use(?string $locale): void
    {
        self::$locale = self::normalise($locale) ?? self::FALLBACK;
    }

    public static function locale(): string
    {
        return self::$locale;
    }

    /**
     * Read the locale from the environment, for a run nobody told.
     *
     * `LC_ALL` outranks `LC_MESSAGES`, which outranks `LANG`, which is the order
     * POSIX gives them
     */
    public static function fromEnvironment(): void
    {
        foreach (['JEVLINT_LANG', 'LC_ALL', 'LC_MESSAGES', 'LANG'] as $name) {
            $value = getenv($name);

            if (is_string($value) && $value !== '' && self::normalise($value) !== null) {
                self::use($value);

                return;
            }
        }

        self::use(null);
    }

    /**
     * One message, formatted.
     *
     * @param array<string, mixed> $values named arguments the pattern reads
     */
    public static function of(string $key, array $values = []): string
    {
        $pattern = self::lookup($key);

        if (! is_string($pattern)) {
            // A key no locale has prints as itself, which is findable by
            // eye. An empty string is not.
            return $key;
        }

        // Every pattern goes through ICU, including one with no arguments. A
        // pattern that skipped it would print its literal braces unquoted, and
        // adding an argument to it later would change how the rest of it reads.
        $formatted = MessageFormatter::formatMessage(self::$locale, $pattern, $values);

        // A pattern ICU cannot parse comes back as false, and casting that to a
        // string puts a blank line where an error belongs.
        return is_string($formatted) ? $formatted : $pattern;
    }

    /**
     * A list of words or phrases a check matches against.
     *
     * The locale's list and English are both returned. A query written in
     * French can still name its options in English, and a check given only the
     * French list would stop finding them
     *
     * @return list<string>
     */
    public static function list(string $key): array
    {
        $mine = self::lookup($key);
        $english = self::$locale === self::FALLBACK ? [] : self::bundle(self::FALLBACK)[$key] ?? [];

        $merged = array_merge(
            is_array($mine) ? $mine : [],
            is_array($english) ? $english : [],
        );

        /** @var list<string> $strings */
        $strings = array_values(array_unique(array_filter($merged, is_string(...))));

        return $strings;
    }

    /** Forget what is loaded, so a test can change locale inside one process */
    public static function reset(): void
    {
        self::$bundles = [];
        self::$locale = self::FALLBACK;
    }

    private static function lookup(string $key): mixed
    {
        foreach (self::candidates(self::$locale) as $locale) {
            $bundle = self::bundle($locale);

            if (array_key_exists($key, $bundle)) {
                return $bundle[$key];
            }
        }

        return null;
    }

    /**
     * The locale, then what it falls back to, then English
     *
     * @return list<string>
     */
    private static function candidates(string $locale): array
    {
        $candidates = [$locale];

        if (str_contains($locale, '_')) {
            $candidates[] = substr($locale, 0, (int) strpos($locale, '_'));
        }

        $candidates[] = self::FALLBACK;

        return array_values(array_unique($candidates));
    }

    /**
     * @return array<string, mixed>
     */
    private static function bundle(string $locale): array
    {
        if (isset(self::$bundles[$locale])) {
            return self::$bundles[$locale];
        }

        $path = self::locate($locale);

        if ($path === null) {
            return self::$bundles[$locale] = [];
        }

        /** @var mixed $loaded */
        $loaded = require $path;

        /** @var array<string, mixed> $bundle */
        $bundle = is_array($loaded) ? $loaded : [];

        return self::$bundles[$locale] = $bundle;
    }

    /**
     * The file holding a locale, from `JEVLINT_LANG_DIR` before the shipped
     * one, so a language nobody has contributed can be added without forking.
     *
     * Unlike `JEVLINT_CHECKS_DIR` this falls through to the shipped directory:
     * a directory holding only `fr.php` is a translation and not a rule set,
     * and English still has to be found behind it
     */
    private static function locate(string $locale): ?string
    {
        $fromEnv = getenv('JEVLINT_LANG_DIR');
        $candidates = [];

        if (is_string($fromEnv) && $fromEnv !== '') {
            $candidates[] = rtrim($fromEnv, '/').'/'.$locale.'.php';
        }

        $candidates[] = __DIR__.'/../../lang/'.$locale.'.php';

        foreach ($candidates as $candidate) {
            if (is_file($candidate)) {
                return $candidate;
            }
        }

        return null;
    }

    /**
     * A language tag as the files are named: `fr_CA` from `fr_CA.UTF-8`,
     * `fr-ca` or `fr_ca`. `C` and `POSIX` name no language and are read as none
     */
    private static function normalise(?string $locale): ?string
    {
        if ($locale === null) {
            return null;
        }

        $tag = preg_replace('/[.@].*$/', '', trim($locale)) ?? '';
        $tag = str_replace('-', '_', $tag);

        if (preg_match('/^([a-zA-Z]{2,3})(?:_([a-zA-Z0-9]{2,4}))?$/', $tag, $named) !== 1) {
            return null;
        }

        $language = strtolower($named[1]);

        if (in_array($language, ['c', 'posix'], true)) {
            return null;
        }

        return isset($named[2]) ? $language.'_'.strtoupper($named[2]) : $language;
    }
}
