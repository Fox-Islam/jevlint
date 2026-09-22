<?php

declare(strict_types=1);

namespace Phox\JevLint\Support;

use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;

/**
 * Reads a key from the environment, falling back to a `.env` in the working
 * directory or the one `--env-file` names. The SDK reads the environment
 * itself; this exists so a `.env` in the directory you run from is enough
 */
final class Env
{
    /** @var array<string, string>|null */
    private static ?array $loaded = null;

    /** The file `--env-file` named, where one was named */
    private static ?string $file = null;

    public static function get(string $name): ?string
    {
        // A named file is where the key comes from, whether or not it holds one.
        // Falling back to the shell sent a run whose caller had pointed at one
        // account to whichever account the environment happened to carry.
        if (self::$file !== null) {
            return self::fromFile()[$name] ?? null;
        }

        $value = getenv($name);

        if (is_string($value) && $value !== '') {
            return $value;
        }

        return self::fromFile()[$name] ?? null;
    }

    /** The file `--env-file` named, for an error message that can say so */
    public static function file(): ?string
    {
        return self::$file;
    }

    /** Put what a `.env` holds into the environment, without overwriting it */
    public static function hydrate(): void
    {
        foreach (self::fromFile() as $name => $value) {
            // The SDK reads the environment, so a named file has to reach it
            // there or the call goes out with whatever the shell held.
            if (self::$file !== null || getenv($name) === false) {
                putenv($name.'='.$value);
            }
        }
    }

    public static function useFile(?string $path): void
    {
        self::$loaded = null;
        self::$file = null;

        if ($path === null) {
            return;
        }

        // Somebody who passed --env-file wants that file. Falling back to the
        // ambient environment sends them looking for a variable when what they
        // mistyped is a path.
        if (! is_file($path)) {
            throw JevLintException::of(JevLintException::NOT_FOUND, file_exists($path)
                ? Text::of('env.not_a_file', ['path' => $path])
                : Text::of('env.no_such_file', ['path' => $path]));
        }

        // `file()` on an unreadable path warns and returns false, which read as
        // an env file holding nothing and was reported as a missing key.
        if (! is_readable($path)) {
            throw JevLintException::of(JevLintException::NOT_FOUND, Text::of('env.unreadable', ['path' => $path]));
        }

        self::$file = $path;
        self::$loaded = self::parse($path);
    }

    /**
     * @return array<string, string>
     */
    private static function fromFile(): array
    {
        if (self::$loaded !== null) {
            return self::$loaded;
        }

        $cwd = getcwd();

        return self::$loaded = $cwd === false ? [] : self::parse($cwd.'/.env');
    }

    /**
     * @return array<string, string>
     */
    private static function parse(string $path): array
    {
        if (! is_file($path)) {
            return [];
        }

        $values = [];

        foreach (file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) ?: [] as $line) {
            $line = trim($line);

            if ($line === '' || str_starts_with($line, '#') || ! str_contains($line, '=')) {
                continue;
            }

            [$name, $value] = explode('=', $line, 2);
            $values[trim($name)] = trim(trim($value), "\"'");
        }

        return $values;
    }
}
