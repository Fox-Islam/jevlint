import { Catalogue } from '../catalogue/catalogue.js';
import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';
import { Env } from '../support/env.js';
import { Json } from '../support/json.js';
import { TypeSafeError } from '../typesafe/errors.js';
import { Args } from './args.js';
import { CheckCommand } from './commands/checkCommand.js';
import { ChecksCommand } from './commands/checksCommand.js';
import { ProbeCommand } from './commands/probeCommand.js';
import { SelfTestCommand } from './commands/selfTestCommand.js';
import { Flags } from './flags.js';
import { Output } from './output.js';

export class Application {
    static readonly VERSION = '1.2.0';

    async run(argv: string[]): Promise<number> {
        const args = Args.parse(argv.slice(1));
        // Read without validating. `args.flag()` throws on `--no-color=x`, and
        // one line above the try that threw before anything could report it.
        const output = Output.make(args.has('no-color'));

        const command = args.argument(0) ?? 'help';

        try {
            args.flag('no-color');

            // Before the first message. A usage error raised while reading the
            // options is the earliest thing this can print, and it is printed in
            // the reader's language like everything after it.
            if (args.value('lang') !== null) {
                Text.use(args.value('lang'));
            } else {
                Text.fromEnvironment();
            }

            // Inside the try: a missing env file is a usage error and gets the
            // same reporting as any other, instead of an uncaught throw.
            if (args.value('env-file') !== null) {
                Env.useFile(args.value('env-file'));
            }

            Flags.format(args);

            // `--version` is accepted everywhere and answers the same question
            // wherever it is written, so it is handled before the command runs.
            if (args.has('version')) {
                Flags.guard('version', args);

                return this.version(output, args.value('format') === 'json');
            }

            if (['check', 'probe', 'self-test', 'checks'].includes(command)) {
                if (args.flag('help')) {
                    Flags.guard(command, args);

                    return this.help(output, args.value('format') === 'json');
                }

                Flags.guard(command, args);
            }

            switch (command) {
                case 'check':
                    return await new CheckCommand().run(args, output);
                case 'probe':
                    return await new ProbeCommand().run(args, output);
                case 'self-test':
                    return await new SelfTestCommand().run(args, output);
                case 'checks':
                    return new ChecksCommand().run(args, output);
                // An unknown option is an error on the four commands, so it is
                // one here too, instead of answering as though the flag were
                // right.
                case 'help':
                    Flags.guard('help', args);

                    return this.help(output, args.value('format') === 'json');
                default:
                    return this.unknown(command);
            }
        } catch (error) {
            if (!(error instanceof JevLintError) && !(error instanceof TypeSafeError)) {
                throw error;
            }

            if (args.value('format') === 'json') {
                output.line(Json.encodeSafely({
                    error: {
                        kind: error instanceof TypeSafeError ? 'api' : error.kind,
                        message: error.message,
                        command,
                    },
                }));

                return 2;
            }

            output.error(error.message);

            return 2;
        }
    }

    private help(output: Output, json = false): number {
        if (json) {
            output.line(Json.encodeSafely({
                usage: Text.of('help.usage'),
                commands: {
                    check: Text.of('help.command_check'),
                    probe: Text.of('help.command_probe'),
                    'self-test': Text.of('help.command_self_test'),
                    checks: Text.of('help.command_checks'),
                },
                options: Flags.documented(),
            }));

            return 0;
        }

        output.write(Text.of('help.page'));

        return 0;
    }

    private version(output: Output, json = false): number {
        const catalogue = Catalogue.load();

        if (json) {
            output.line(Json.encode({
                jevlint: Application.VERSION,
                catalogue: {
                    version: catalogue.version,
                    fingerprint: catalogue.fingerprint,
                    asked: catalogue.asked,
                    model: catalogue.model,
                    jev: catalogue.versions,
                },
            }));

            return 0;
        }

        output.line(Text.of('version.line', {
            jevlint: Application.VERSION,
            version: catalogue.version,
            fingerprint: catalogue.fingerprint,
            model: catalogue.model,
        }));
        output.line(Text.of('version.covers', {
            versions: catalogue.versions.join(', '),
            latest: catalogue.jev,
        }));

        return 0;
    }

    /**
     * Thrown, not printed, so it leaves through the same path as every other
     * usage error. Printing it here made it the one failure a caller reading
     * `--format=json` got as English on stderr and nothing on stdout
     */
    private unknown(command: string): never {
        throw JevLintError.of(JevLintError.USAGE, Text.of('cli.no_such_command', { command }));
    }
}
