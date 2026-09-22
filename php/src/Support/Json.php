<?php

declare(strict_types=1);

namespace Phox\JevLint\Support;

use JsonException;
use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;

final class Json
{
    /**
     * The file's text, or an error naming why it could not be read.
     *
     * `file_get_contents` on a directory returns "" and a warning, not false, so
     * without the first guard a directory passed where a file goes is reported
     * as a syntax error in JSON nobody wrote
     */
    public static function contents(string $path): string
    {
        if (is_dir($path)) {
            throw JevLintException::of(JevLintException::NOT_FOUND, Text::of('file.is_a_directory', ['path' => $path]));
        }

        $contents = @file_get_contents($path);

        if ($contents === false) {
            throw JevLintException::of(JevLintException::NOT_FOUND, Text::of('file.unreadable', ['path' => $path]));
        }

        return $contents;
    }

    /**
     * @return array<array-key, mixed>
     */
    public static function readFile(string $path): array
    {
        return self::decode(self::contents($path), $path);
    }

    /**
     * @return array<array-key, mixed>
     */
    public static function decode(string $contents, string $what = 'input'): array
    {
        try {
            $decoded = json_decode($contents, true, 512, JSON_THROW_ON_ERROR);
        } catch (JsonException $exception) {
            throw JevLintException::of(JevLintException::INVALID_JSON, Text::of('json.invalid', ['what' => $what, 'detail' => $exception->getMessage()]));
        }

        if (! is_array($decoded)) {
            throw JevLintException::of(JevLintException::INVALID_JSON, Text::of('json.not_an_object', ['what' => $what]));
        }

        return $decoded;
    }

    /**
     * The same text decoded without turning objects into arrays.
     *
     * Only the shape is wanted: `{"0":"a"}` and `["a"]` are the same associative
     * array and different JSON, and the API treats them differently.
     */
    public static function shapeOf(string $contents): mixed
    {
        try {
            return json_decode($contents, false, 512, JSON_THROW_ON_ERROR);
        } catch (JsonException) {
            return null;
        }
    }

    public static function encode(mixed $value): string
    {
        try {
            return json_encode($value, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
        } catch (JsonException $exception) {
            // A path with a byte that is not UTF-8 reaches the report as its
            // `source`, and the throw landed outside every handler.
            throw JevLintException::of(JevLintException::INVALID_JSON, Text::of('json.report_unencodable', ['detail' => $exception->getMessage()]));
        }
    }

    /**
     * The same, for the error document.
     *
     * The handler cannot fail: a path holding a byte that is not UTF-8 reaches it
     * as the message, and a throw here leaves the run with no output at all. The
     * bad bytes come out as U+FFFD, which is visible in what the caller reads
     */
    public static function encodeSafely(mixed $value): string
    {
        return json_encode(
            $value,
            JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE,
            // `command` is required by spec/error.schema.json, so the one
            // document written without going through the encoder has to carry it
            // too, or the last thing a caller reads is the one thing it cannot
            // parse against the schema it was given.
        ) ?: '{"error":{"kind":"internal","message":"The error could not be written as JSON.","command":"check"}}';
    }

    /** A stable, readable rendering of a state or criteria value */
    public static function inline(mixed $value): string
    {
        if (is_string($value)) {
            return $value;
        }

        return json_encode($value, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) ?: '';
    }
}
