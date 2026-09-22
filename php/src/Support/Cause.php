<?php

declare(strict_types=1);

namespace Phox\JevLint\Support;

use Phox\TypeSafe\Exceptions\ApiException;
use Phox\TypeSafe\Exceptions\AuthenticationException;
use Phox\TypeSafe\Exceptions\BadRequestException;
use Phox\TypeSafe\Exceptions\ConnectionException;
use Phox\TypeSafe\Exceptions\InternalServerException;
use Phox\TypeSafe\Exceptions\PermissionDeniedException;
use Phox\TypeSafe\Exceptions\RateLimitException;
use Phox\TypeSafe\Exceptions\TimeoutException;
use Phox\TypeSafe\Exceptions\TypeSafeException;
use Phox\TypeSafe\Exceptions\UnprocessableEntityException;

/**
 * Why a call did not come back, as a word.
 *
 * A caller deciding whether to retry has to tell a wrong key from a dropped
 * connection, and the message is English written for a person
 */
final class Cause
{
    /** Nothing failed; the answer that came back was unusable */
    public const ANSWER = 'answer';

    /**
     * Whether a second call would fail the same way.
     *
     * A wrong key or a denied account answers every call identically, so a run
     * that keeps going spends the rest of its calls learning what the first one
     * already said.
     */
    public static function isSettled(TypeSafeException $exception): bool
    {
        return $exception instanceof AuthenticationException
            || $exception instanceof PermissionDeniedException;
    }

    public static function of(TypeSafeException $exception): string
    {
        return match (true) {
            $exception instanceof AuthenticationException => 'auth',
            $exception instanceof PermissionDeniedException => 'permission',
            $exception instanceof RateLimitException => 'rate-limit',
            $exception instanceof TimeoutException => 'timeout',
            $exception instanceof ConnectionException => 'connection',
            $exception instanceof BadRequestException,
            $exception instanceof UnprocessableEntityException => 'request',
            $exception instanceof InternalServerException => 'server',
            $exception instanceof ApiException => 'api',
            default => 'api',
        };
    }
}
