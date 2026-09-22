<?php

declare(strict_types=1);

namespace Phox\JevLint\Report;

/**
 * Something about the run itself, as opposed to the query.
 *
 * `unreachable` is the one that matters: a call that could not be made means
 * those checks never ran, and a report that cannot say so reads exactly like a
 * report that ran them and found nothing.
 */
final class Note
{
    public function __construct(
        public readonly string $message,
        public readonly string $kind = 'note',
        public readonly ?string $target = null,
        public readonly ?int $checks = null,
        public readonly ?string $cause = null,
        public readonly ?int $findings = null,
    ) {}

    public function isUnreachable(): bool
    {
        return $this->kind === 'unreachable';
    }

    /** Checks this run did not carry, for a reason that is not a failure */
    public function isSkip(): bool
    {
        return $this->kind === 'skipped';
    }

    /**
     * @return array{kind: string, target: ?string, message: string, cause?: string, findings?: int, checks?: int}
     */
    public function toArray(): array
    {
        $row = ['kind' => $this->kind, 'target' => $this->target, 'message' => $this->message];

        // Why it failed, as a word. A caller deciding between stopping and
        // retrying had to read the English the person reads.
        if ($this->cause !== null) {
            $row += ['cause' => $this->cause];
        }

        // How many findings a floor leaves out, as a number. `checks` carries
        // the same for a narrowing. A caller reads neither out of the message.
        if ($this->findings !== null) {
            $row += ['findings' => $this->findings];
        }

        // The count as a number, not only inside the sentence. A caller working
        // out whether a run covered anything had to regex the English.
        return $this->checks === null ? $row : $row + ['checks' => $this->checks];
    }
}
