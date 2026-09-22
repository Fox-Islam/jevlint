<?php

declare(strict_types=1);

namespace Phox\JevLint\Lint;

use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Support\Env;
use Phox\TypeSafe\Client;

/**
 * Builds the SDK client the checks are asked through.
 *
 * The SDK reads the environment itself; this adds a `.env` in the working
 * directory and turns a missing key into an error at startup instead of at the
 * first call, so a run either costs nothing or completes
 */
final class ClientFactory
{
    public static function make(?string $model = null, bool $openRouter = false, ?float $timeout = null, bool $rulesRunAlone = false): Client
    {
        Env::hydrate();

        $key = Env::get($openRouter ? 'OPENROUTER_API_KEY' : 'TYPESAFE_API_KEY');

        if ($key === null) {
            // Only `check` has a path that needs no key. Offering it to `probe`
            // sent a reader to a mode probe does not have.
            throw JevLintException::of(JevLintException::AUTH, Text::of('auth.no_key', [
                'name' => $openRouter ? 'OPENROUTER_API_KEY' : 'TYPESAFE_API_KEY',
                'where' => Env::file() ?? Text::of('auth.env_default'),
                'rules_alone' => $rulesRunAlone ? 'yes' : 'no',
            ]));
        }

        $client = Client::make($key);

        if ($openRouter) {
            $client = $client->openRouter();
        }

        if ($model !== null) {
            $client->defaultModel($model);
        }

        if ($timeout !== null) {
            $client->timeout($timeout);
        }

        return $client;
    }
}
