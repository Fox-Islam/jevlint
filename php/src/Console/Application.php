<?php

declare(strict_types=1);

namespace Phox\JevLint\Console;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Console\Commands\ChecksCommand;
use Phox\JevLint\Console\Commands\CheckCommand;
use Phox\JevLint\Console\Commands\ProbeCommand;
use Phox\JevLint\Console\Commands\SelfTestCommand;
use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Support\Env;
use Phox\JevLint\Support\Json;
use Phox\TypeSafe\Exceptions\TypeSafeException;

final class Application
{
    public const VERSION = '1.2.0';

    /**
     * @param list<string> $argv
     */
    public function run(array $argv): int
    {
        $args = Args::parse(array_slice($argv, 1));
        // Read without validating. `$args->flag()` throws on `--no-color=x`, and
        // one line above the try that threw before anything could report it.
        $output = Output::make($args->has('no-color'));

        $command = $args->argument(0) ?? 'help';

        try {
            $args->flag('no-color');

            // Before the first message. A usage error raised while reading the
            // options is the earliest thing this can print, and it is printed in
            // the reader's language like everything after it.
            if ($args->value('lang') !== null) {
                Text::use($args->value('lang'));
            } else {
                Text::fromEnvironment();
            }

            // Inside the try: a missing env file is a usage error and gets the
            // same reporting as any other, instead of an uncaught throw.
            if ($args->value('env-file') !== null) {
                Env::useFile($args->value('env-file'));
            }

            Flags::format($args);

            // `--version` is accepted everywhere and answers the same question
            // wherever it is written, so it is handled before the command runs.
            if ($args->has('version')) {
                Flags::guard('version', $args);

                return $this->version($output, $args->value('format') === 'json');
            }

            if (in_array($command, ['check', 'probe', 'self-test', 'checks'], true)) {
                if ($args->flag('help')) {
                    Flags::guard($command, $args);

                    return $this->help($output, $args->value('format') === 'json');
                }

                Flags::guard($command, $args);
            }

            return match ($command) {
                'check' => (new CheckCommand())->run($args, $output),
                'probe' => (new ProbeCommand())->run($args, $output),
                'self-test' => (new SelfTestCommand())->run($args, $output),
                'checks' => (new ChecksCommand())->run($args, $output),
                // An unknown option is an error on the four commands, so it is one
                // here too, instead of answering as though the flag were right.
                'help' => $this->helpCommand($args, $output),
                default => $this->unknown($command, $output),
            };
        } catch (JevLintException|TypeSafeException $exception) {
            if ($args->value('format') === 'json') {
                $output->line(Json::encodeSafely([
                    'error' => [
                        'kind' => $exception instanceof TypeSafeException ? 'api' : $exception->kind,
                        'message' => $exception->getMessage(),
                        'command' => $command,
                    ],
                ]));

                return 2;
            }

            $output->error($exception->getMessage());

            return 2;
        }
    }

    /**
     * `help` with an unknown option is the same mistake as any other command with
     * one, and answering it as though the flag were right hides the typo
     */
    private function helpCommand(Args $args, Output $output): int
    {
        Flags::guard('help', $args);

        return $this->help($output, $args->value('format') === 'json');
    }

    private function help(Output $output, bool $json = false): int
    {
        if ($json) {
            $output->line(Json::encodeSafely([
                'usage' => Text::of('help.usage'),
                'commands' => [
                    'check' => Text::of('help.command_check'),
                    'probe' => Text::of('help.command_probe'),
                    'self-test' => Text::of('help.command_self_test'),
                    'checks' => Text::of('help.command_checks'),
                ],
                'options' => Flags::documented(),
            ]));

            return 0;
        }

        $output->write(Text::of('help.page'));

        return 0;
    }

    private function version(Output $output, bool $json = false): int
    {
        $catalogue = Catalogue::load();

        if ($json) {
            $output->line(Json::encode([
                'jevlint' => self::VERSION,
                'catalogue' => [
                    'version' => $catalogue->version,
                    'fingerprint' => $catalogue->fingerprint,
                    'asked' => $catalogue->asked,
                    'model' => $catalogue->model,
                    'jev' => $catalogue->versions,
                ],
            ]));

            return 0;
        }

        $output->line(Text::of('version.line', [
            'jevlint' => self::VERSION,
            'version' => $catalogue->version,
            'fingerprint' => $catalogue->fingerprint,
            'model' => $catalogue->model,
        ]));
        $output->line(Text::of('version.covers', [
            'versions' => implode(', ', $catalogue->versions),
            'latest' => $catalogue->jev,
        ]));

        return 0;
    }

    private function unknown(string $command, Output $output): int
    {
        // Thrown, not printed, so it leaves through the same path as every other
        // usage error. Printing it here made it the one failure a caller reading
        // `--format=json` got as English on stderr and nothing on stdout.
        throw JevLintException::of(JevLintException::USAGE, Text::of('cli.no_such_command', ['command' => $command]));
    }
}
