import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';
import { Env } from '../support/env.js';
import { Client } from '../typesafe/client.js';

/**
 * Builds the client the checks are asked through.
 *
 * The client reads the environment itself; this adds a `.env` in the working
 * directory and turns a missing key into an error at startup instead of at the
 * first call, so a run either costs nothing or completes
 */
export const ClientFactory = {
    make(
        model: string | null = null,
        openRouter = false,
        timeout: number | null = null,
        rulesRunAlone = false,
    ): Client {
        Env.hydrate();

        const name = openRouter ? 'OPENROUTER_API_KEY' : 'TYPESAFE_API_KEY';
        const key = Env.get(name);

        if (key === null) {
            // Only `check` has a path that needs no key. Offering it to `probe`
            // sent a reader to a mode probe does not have.
            throw JevLintError.of(JevLintError.AUTH, Text.of('auth.no_key', {
                name,
                where: Env.file() ?? Text.of('auth.env_default'),
                rules_alone: rulesRunAlone ? 'yes' : 'no',
            }));
        }

        return Client.make({
            apiKey: key,
            provider: openRouter ? 'openrouter' : 'typesafe',
            ...(model === null ? {} : { defaultModel: model }),
            ...(timeout === null ? {} : { timeout }),
        });
    },
};
