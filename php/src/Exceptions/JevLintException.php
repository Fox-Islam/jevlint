<?php

declare(strict_types=1);

namespace Phox\JevLint\Exceptions;

use RuntimeException;

/**
 * Everything this package throws.
 *
 * The kind is for a caller deciding what to do next. A missing file and a
 * mistyped flag are both the caller's fault and neither is worth retrying; an
 * `api` failure might be. Collapsing them all into one label leaves a program
 * matching on English.
 */
class JevLintException extends RuntimeException
{
    public const USAGE = 'usage';

    public const NOT_FOUND = 'not-found';

    public const INVALID_JSON = 'invalid-json';

    public const QUERY = 'query';

    public const CONFIG = 'config';

    public const AUTH = 'auth';

    public const CATALOGUE = 'catalogue';

    public string $kind = self::USAGE;

    public static function of(string $kind, string $message): self
    {
        $exception = new self($message);
        $exception->kind = $kind;

        return $exception;
    }
}
