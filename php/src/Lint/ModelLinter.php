<?php

declare(strict_types=1);

namespace Phox\JevLint\Lint;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Catalogue\Check;
use Phox\JevLint\Catalogue\Wording;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Query\ReviewedQuestion;
use Phox\JevLint\Report\Finding;
use Phox\JevLint\Report\Patch;
use Phox\JevLint\Report\Report;
use Phox\JevLint\Report\Severity;
use Phox\JevLint\Support\Cause;
use Phox\JevLint\Support\Json;
use Phox\TypeSafe\Client;
use Phox\TypeSafe\Exceptions\TypeSafeException;
use Phox\TypeSafe\Questions\Choice;
use Phox\TypeSafe\Questions\Noul;
use Phox\TypeSafe\Requests\SystemOne;
use Phox\TypeSafe\Responses\SystemOneResponse;

/**
 * The half that asks Jev about the query.
 *
 * Every check for one reviewed question goes in a single call, because a call
 * costs its round trip and not its question count. The question under review is
 * the state; the checks are the questions. State-scoped checks need the real
 * state in front of them, so they are a second call.
 *
 * A check may be asked several ways at once. The wordings are meant to mean the
 * same thing, so their mean is the answer and their spread is the error bar.
 *
 * Jev's answers about prompts are not calibrated against human judgement, so
 * every model finding carries the probability that produced it, and
 * `jevlint self-test` measures whether each check separates a clean question
 * from a broken one
 */
final class ModelLinter
{
    /** Beyond this many questions the pairs outgrow one call */
    public const MOST_QUESTIONS = 12;

    /** How close to its trigger a probability has to be before the finding is a coin flip */
    public const NEAR = 0.05;

    /**
     * How close to its trigger a cleared reading has to be to be worth printing
     * without `--all`.
     *
     * `--all` costs nothing extra in calls but a whole second run to ask for,
     * and a check sitting just under its trigger is the reading a reader is most
     * likely to want. This is the band the corpus tables count as shaky
     */
    public const WORTH_SEEING = 0.1;

    /**
     * @param list<string> $only check ids to run, or all of them when empty
     */
    public function __construct(
        private readonly Catalogue $catalogue,
        private readonly Client $client,
        private readonly bool $checkState = true,
        private readonly int $repeats = 1,
        private readonly array $only = [],
        private readonly bool $reportAll = false,
        private readonly bool $narrowed = false,
    ) {}

    private function wanted(Check $check): bool
    {
        return $this->only === [] || in_array($check->id, $this->only, true);
    }

    /** @var array<string, array<string, float>> field to question id to probability */
    private array $fields = [];

    /** How many questions the query under review holds */
    private int $questionCount = 0;

    /** Set when a call failed in a way every later call would repeat */
    private bool $stopped = false;

    public function run(Query $query, Report $report): void
    {
        $this->fields = [];
        $this->stopped = false;
        $this->questionCount = count($query->questions);
        $asked = [];
        $unreadable = [];

        foreach ($query->questions as $question) {
            // Nothing here can read a question whose type is not one Jev answers
            // or whose instruction is blank. Skipping it in silence left a report
            // that could not be told from one where every check ran.
            if (! $question->isKnownType() || trim($question->instructionsText()) === '') {
                $unreadable[] = $question->id;

                continue;
            }

            $asked[] = $question->id;
            $this->askAboutQuestion($question, $report);

            if ($this->checkState && $query->hasState()) {
                $this->askAboutState($query, $question, $report);
            }
        }

        if ($unreadable !== []) {
            $report->skipped(Text::of('skipped.unreadable_questions', [
                'ids' => implode(', ', $unreadable),
                'count' => count($unreadable),
            ]), count($this->catalogue->modelChecks('question')) * count($unreadable));
        }

        // A check that asks whether a field serves the query cannot answer it
        // from some of the questions. Narrowed, it reads a field the hidden
        // questions use as one nothing reads, which is a wrong answer rather
        // than a partial one, so it is not asked.
        if ($this->narrowed && $this->fields !== []) {
            $fieldChecks = count($this->catalogue->modelChecks('state-field'));

            $report->skipped(Text::of('skipped.state_field_needs_whole_query', ['count' => $fieldChecks]), $fieldChecks);

            $this->fields = [];
        }

        $this->reportFields($asked, $report);

        if ($this->checkState && $query->hasState()) {
            $this->askAboutStateAlone($query, $report);
        } elseif ($this->checkState) {
            // A query with no state leaves every state-scoped check out. The only
            // other sign is a `state/missing` finding, which `--min=warning`
            // filters away.
            $stateScoped = array_values(array_filter(
                $this->catalogue->modelChecks('state'),
                $this->wanted(...),
            ));

            foreach (['state-field', 'state-once'] as $scope) {
                $stateScoped = [...$stateScoped, ...array_filter($this->catalogue->modelChecks($scope), $this->wanted(...))];
            }

            if ($stateScoped !== []) {
                $report->skipped(Text::of('skipped.no_state', ['count' => count($stateScoped)]), count($stateScoped));
            }
        }

        $this->askAboutQuery($query, $report);

        // Last, once every call has been made: anything that went into a call and
        // never came back with a verdict is a loss, whichever path lost it.
        $report->reconcile();
    }

    /**
     * One call for the checks that read the question set.
     *
     * Every check but these sees one question at a time, so two questions that
     * ask the same thing in different words are invisible to all of them. The
     * pairs go in a single call, which is why this is affordable at all.
     */
    private function askAboutQuery(Query $query, Report $report): void
    {
        $checks = array_filter($this->catalogue->modelChecks('query'), $this->wanted(...));
        $questions = array_values(array_filter(
            $query->questions,
            static fn (ReviewedQuestion $q): bool => $q->isKnownType() && trim($q->instructionsText()) !== '',
        ));

        if ($checks === []) {
            return;
        }

        // Not `unreachable`: nothing failed, and this check was never going to run
        // on a query this size. It is a note because the alternative is a report
        // that silently omits a check the caller may have asked for by name.
        if (count($questions) > self::MOST_QUESTIONS) {
            $report->skipped(Text::of('skipped.too_many_questions', [
                'questions' => count($questions),
                'most' => self::MOST_QUESTIONS,
            ]), count($checks));

            return;
        }

        // One question makes no pairs. Returning bare left these checks out of a
        // report that then read as a full run.
        if (count($questions) < 2) {
            $report->skipped(Text::of('skipped.too_few_questions', ['questions' => count($questions)]), count($checks));

            return;
        }

        $report->asked(count($checks));
        $request = $this->client->systemOne()->state([
            'questions' => array_map(static fn (ReviewedQuestion $q): string => $q->instructionsText(), $questions),
        ]);
        $pairs = [];

        foreach ($checks as $check) {
            foreach ($questions as $i => $first) {
                foreach (array_slice($questions, $i + 1) as $second) {
                    $key = sprintf('%s__%s__%s', $check->answerKey(), $this->slug($first->id), $this->slug($second->id));

                    $pairs[$key] = [$check, $first, $second];
                    $request->ask($key, $this->build(
                        $check->wordings[0],
                    )->instructions(str_replace(
                        '{pair}',
                        sprintf('"%s" and "%s"', $first->instructionsText(), $second->instructionsText()),
                        $check->instructions(),
                    )));
                }
            }
        }

        if ($pairs === []) {
            return;
        }

        foreach ($pairs as [$check, , $second]) {
            $report->expecting($check->id, $second->id);
        }

        $response = $this->send($request, 'query', $report);

        if (! $response instanceof SystemOneResponse
            || ! $this->answered(array_keys($pairs), $response, 'query', $report)) {
            return;
        }

        foreach ($pairs as $key => [$check, $first, $second]) {
            if (! $response->has($key)) {
                continue;
            }

            $report->reached($check->id, $second->id);
            $probability = $this->reading($response, $key);

            if ($probability === null) {
                $report->unreachable($second->id, Text::of('report.no_usable_reading', ['key' => $key]));

                continue;
            }

            $fired = $probability > $check->trigger;

            if (! $fired && ! $this->reportAll) {
                continue;
            }

            $report->add(new Finding(
                checkId: $check->id,
                title: Text::of('finding.pair_title', ['title' => $check->title, 'first' => $first->id, 'second' => $second->id]),
                severity: Severity::fromName($check->severity),
                target: $second->id,
                message: $check->message ?? $check->title,
                hint: $check->hint,
                suggest: $check->suggest,
                advice: $check->advice,
                mode: $check->mode,
                action: $check->action,
                path: '/questions/'.Check::escape($second->id),
                trigger: $check->trigger,
                nearTrigger: abs($probability - $check->trigger) <= self::NEAR,
                docs: $check->docs,
                probability: $probability,
                fired: $fired,
                evidence: Text::of('evidence.both_ask', [
                    'first' => $this->shorten($first->instructionsText(), 70),
                    'second' => $this->shorten($second->instructionsText(), 70),
                ]),
                paths: ['/questions/'.Check::escape($first->id), '/questions/'.Check::escape($second->id)],
            ));
        }
    }

    /**
     * An id as an answer key, without losing which id it was.
     *
     * Collapsing every run of punctuation to `_` made `a.b`, `a-b` and `a_b` the
     * same key, so one of them silently replaced the others on the request and
     * the reading that came back was reported against whichever name was asked
     * last. Each byte that cannot appear in a key becomes its own escape, so two
     * different ids cannot produce one key.
     */
    private function slug(string $id): string
    {
        return (string) preg_replace_callback(
            '/[^a-zA-Z0-9]/',
            static fn (array $match): string => '_'.bin2hex($match[0]),
            $id,
        );
    }

    /**
     * One reading, or null if it is not a probability.
     *
     * A calibrated answer is between 0 and 1. A response carrying anything else
     * is not a reading this can compare against a trigger, and reporting it
     * verbatim produced findings at 1.50 on a query with nothing wrong with it.
     */
    private function reading(SystemOneResponse $response, string $key): ?float
    {
        if (! $response->has($key)) {
            return null;
        }

        $value = $response->noul($key)->noul();

        return $value >= 0.0 && $value <= 1.0 ? $value : null;
    }

    /**
     * Every question put on a call came back with an answer.
     *
     * A transport failure throws and is already handled. A 200 carrying none of
     * the keys that were asked for - an answer-key skew, a truncated payload, a
     * proxy answering on the endpoint's behalf - does not, and every check would
     * then be skipped one at a time by `has()` with nothing recorded. The run
     * would report a clean query it never looked at.
     *
     * @param list<string> $keys
     */
    private function answered(array $keys, SystemOneResponse $response, string $target, Report $report): bool
    {
        $missing = array_values(array_filter($keys, static fn (string $k): bool => ! $response->has($k)));

        if ($missing === []) {
            return true;
        }

        $report->unreachable($target, Text::of('report.partial_answer', [
                'answered' => count($keys) - count($missing),
                'asked' => count($keys),
                'missing' => count($missing) === 1 ? '`'.$missing[0].'`' : '`'.$missing[0].'` and '.(count($missing) - 1).' more',
            ]));

        // Some answers are still answers. Only a call that came back with none of
        // what it was asked has nothing to record.
        return count($missing) < count($keys);
    }

    /**
     * Send one call and record what it cost.
     *
     * A call that fails is a note on the report and a null here. One set of
     * checks that could not be asked is not a reason to abandon the rest.
     */
    private function send(SystemOne $request, string $target, Report $report): ?SystemOneResponse
    {
        if ($this->stopped) {
            return null;
        }

        try {
            $response = $request->send();
        } catch (TypeSafeException $exception) {
            // Counted: it left the machine and was paid for, and the SDK retries
            // twice before giving up, so one failed call is up to three requests.
            $report->recordCall(null);
            $report->unreachable($target, $exception->getMessage(), Cause::of($exception));

            // A wrong key answers every call the same way, so the rest of the run
            // is spent buying the same refusal again.
            if (Cause::isSettled($exception)) {
                $this->stopped = true;
            }

            return null;
        }

        $report->recordCall($response->usage()->totalTokens());
        $report->answeredBy($response->model());

        return $response;
    }

    /**
     * One call for the checks that read the material and nothing else.
     *
     * Asking them once per question asked the same question of the same state
     * as many times as the query had questions
     */
    private function askAboutStateAlone(Query $query, Report $report): void
    {
        $request = $this->client->systemOne()->state(['state' => $query->state]);
        $asked = [];
        $parts = $this->stateParts($query);

        foreach ($this->catalogue->modelChecks('state-once') as $check) {
            if ($this->wanted($check)) {
                $asked[] = $this->ask($request, $check, null, $parts);
            }
        }

        $report->asked(count($asked));

        if ($asked === []) {
            return;
        }

        $keys = self::answerKeys($asked);

        foreach ($asked as ['check' => $check]) {
            $report->expecting($check->id, 'state');
        }

        $response = $this->send($request, 'state', $report);

        if (! $response instanceof SystemOneResponse
            || ! $this->answered($keys, $response, 'state', $report)) {
            return;
        }

        foreach ($asked as ['check' => $check, 'keys' => $keys, 'locator' => $locator]) {
            $this->record($check, $keys, null, [$response], 'state', $report, null, $locator);
        }
    }

    /**
     * The state's own parts, as something to choose between
     *
     * @return array<string, string>
     */
    private function stateParts(Query $query): array
    {
        $parts = [];

        foreach ($query->stateLeaves() as $path) {
            $value = Json::inline($query->stateAt($path));
            $parts[$path] = $this->shorten($value === '' ? $path : $value, 120);
        }

        return $parts;
    }

    /**
     * One finding per state field, however many questions were asked about it
     *
     * @param list<string> $asked
     */
    private function reportFields(array $asked, Report $report): void
    {
        $check = $this->catalogue->find('state/irrelevant-field');

        if (! $check instanceof Check) {
            return;
        }

        foreach ($this->fields as $field => $byQuestion) {
            if ($byQuestion === []) {
                continue;
            }

            $unused = array_filter($byQuestion, static fn (float $p): bool => $p > $check->trigger);

            $fired = count($unused) === count($asked) && $asked !== [];

            // The verdict is that *every* question ignored the field, so the
            // statistic behind it is the weakest reading, not the average of
            // them. Publishing the mean printed 0.86 beside a cleared verdict
            // against a 0.75 trigger, which is a number arguing with itself.
            $decided = min($byQuestion);

            if (! $fired && ! $this->reportAll) {
                continue;
            }

            $read = ['asked' => count($asked) === 1 ? $asked[0] : implode(', ', $asked), 'field' => $field];
            $evidence = $fired
                ? Text::of('evidence.field_unread', $read)
                : Text::of('evidence.field_read', $read);

            $report->add(new Finding(
                checkId: $check->id,
                title: str_replace('{field}', $field, $check->title),
                severity: Severity::fromName($check->severity),
                target: 'state',
                message: str_replace('{field}', $field, $check->message ?? $check->title),
                hint: $check->hint,
                suggest: str_replace('{field}', $field, $check->suggest),
                advice: $check->advice,
                mode: $check->mode,
                action: $check->action,
                path: $check->path('state', $field),
                trigger: $check->trigger,
                nearTrigger: abs($decided - $check->trigger) <= self::NEAR,
                supersedes: $check->supersedes,
                docs: $check->docs,
                probability: $decided,
                readings: count($byQuestion) > 1 ? array_values($byQuestion) : [],
                readingsOf: count($byQuestion) > 1 ? Text::of('evidence.question_count', ['count' => count($byQuestion)]) : null,
                spread: count($byQuestion) > 1 ? max($byQuestion) - min($byQuestion) : null,
                fired: $fired,
                patch: $this->removal($check, 'state', $field),
                evidence: $evidence,
            ));
        }
    }

    /** One call: every question-scoped check, with the question as the state */
    private function askAboutQuestion(ReviewedQuestion $question, Report $report): void
    {
        $request = $this->client->systemOne()->state($question->asState());
        $asked = [];
        $elements = $this->elements($question);

        foreach ($this->catalogue->modelChecks('question', $question->type) as $check) {
            if (! $this->wanted($check)) {
                continue;
            }

            if ($check->requires === 'criteria' && ! $question->hasCriteria()) {
                continue;
            }

            $asked[] = $this->ask($request, $check, null, $elements);
        }

        $report->asked(count($asked));
        $this->collect($asked, $request, $question, $question->id, $report, $question->asState());
    }

    /** One call: the state-scoped checks, with the real state in front of them */
    private function askAboutState(Query $query, ReviewedQuestion $question, Report $report): void
    {
        $request = $this->client->systemOne()->state($query->stateWith($question));
        $asked = [];

        foreach ($this->catalogue->modelChecks('state', $question->type) as $check) {
            if ($this->wanted($check)) {
                $asked[] = $this->ask($request, $check);
            }
        }

        foreach ($this->catalogue->modelChecks('state-field', $question->type) as $check) {
            if (! $this->wanted($check)) {
                continue;
            }

            $leaves = $query->stateLeaves();

            // A state that is a string or a list has no named fields, so a check
            // asked once per field is asked zero times. Saying nothing left that
            // looking like a state whose every field was needed.
            if ($leaves === []) {
                $report->skipped(Text::of('skipped.no_fields_to_name', ['id' => $check->id]), 1);

                continue;
            }

            foreach ($leaves as $field) {
                $asked[] = $this->ask($request, $check, (string) $field);
            }
        }

        $report->asked(count($asked));
        $this->collect($asked, $request, $question, $question->id, $report, $query->stateWith($question));
    }

    /**
     * Put every wording of one check on the request
     *
     * @param  array<string, string>                                                              $options what the check's locator chooses between
     * @return array{check: Check, field: ?string, keys: list<string>, locator: array<string, string>}
     */
    private function ask(SystemOne $request, Check $check, ?string $field = null, array $options = []): array
    {
        $keys = [];
        $suffix = $field === null ? '' : '__'.$this->slug($field);

        foreach ($check->wordings as $index => $wording) {
            $key = $check->answerKey().$suffix.($check->isComposite() ? '__w'.$index : '');
            $keys[] = $key;
            $request->ask($key, $this->build($wording, $field ?? ''));
        }

        $locator = [];

        if ($check->locate !== null && count($options) > 1) {
            if ($check->locateMode === 'each') {
                foreach ($options as $label => $text) {
                    $key = $check->answerKey().'__where__'.$this->slug((string) $label);
                    $locator[$key] = (string) $label;
                    $request->ask($key, Noul::ask(str_replace('{element}', '"'.$text.'"', $check->locate)));
                }
            } else {
                $key = $check->answerKey().'__where';
                $locator[$key] = '';
                $request->ask($key, Choice::ask($check->locate)->options($options));
            }
        }

        return ['check' => $check, 'field' => $field, 'keys' => $keys, 'locator' => $locator];
    }

    /**
     * The reviewed question's own levels or options, as something to choose from
     *
     * @return array<string, string>
     */
    private function elements(ReviewedQuestion $question): array
    {
        $criteria = $question->criteria;

        if ($criteria === null || $criteria === []) {
            return [];
        }

        $options = [];

        foreach ($criteria as $key => $value) {
            $label = $question->criteriaIsList() ? 'level_'.$key : (string) $key;
            $text = is_string($value) ? $value : Json::inline($value);
            $options[$label] = $text === '' ? $label : $text;
        }

        return $options;
    }

    /** Turn one wording into the SDK question that asks it */
    public function build(Wording $wording, string $field = ''): Noul|Choice
    {
        $criteria = $wording->criteria ?? [];

        if ($wording->type === 'choice') {
            $options = [];

            foreach ($criteria as $label => $description) {
                $options[(string) $label] = is_string($description) ? $description : null;
            }

            return Choice::ask($wording->instructions($field))->options($options);
        }

        $noul = Noul::ask($wording->instructions($field));

        if (isset($criteria['true']) && is_string($criteria['true'])) {
            $noul->yes($criteria['true']);
        }

        if (isset($criteria['false']) && is_string($criteria['false'])) {
            $noul->no($criteria['false']);
        }

        return $noul;
    }

    /**
     * @param list<array{check: Check, field: ?string, keys: list<string>, locator: array<string, string>}> $asked
     * @param array<string, mixed>                                                                          $state the state the first call used
     */
    private function collect(array $asked, SystemOne $request, ReviewedQuestion $question, string $target, Report $report, array $state): void
    {
        if ($asked === []) {
            return;
        }

        foreach ($asked as ['check' => $check]) {
            $report->expecting($check->id, $target);
        }

        $responses = [];

        for ($run = 0; $run < max(1, $this->repeats); $run++) {
            $response = $this->send($request, $target, $report);

            if ($response instanceof SystemOneResponse) {
                $responses[] = $response;
            }
        }

        if ($responses === []) {
            return;
        }

        $keys = self::answerKeys($asked);

        // Every response, not the first: a repeat can answer 200 with the answer
        // keys missing, and a verdict resting on the calls that did answer is
        // not the verdict the caller asked for.
        foreach ($responses as $response) {
            if (! $this->answered($keys, $response, $target, $report)) {
                return;
            }
        }

        $extra = $this->settle($asked, $responses, $question, $report, $state);

        // The re-ask is a call like any other: if it answers nothing, the
        // borderline verdict it was asked to settle is still unsettled.
        foreach ($extra as $checkId => $settled) {
            foreach ($settled as $response) {
                $this->answered($this->keysFor($asked, $checkId), $response, $target, $report);
            }
        }

        foreach ($asked as ['check' => $check, 'field' => $field, 'keys' => $keys, 'locator' => $locator]) {
            if ($check->compare === 'type') {
                $this->recordTypeComparison($check, $keys[0], $responses[0], $question, $target, $report);

                continue;
            }

            $this->record($check, $keys, $field, [...$responses, ...($extra[$check->id] ?? [])], $target, $report, $question, $locator);
        }
    }

    /**
     * Every answer key a call carries, the locators among them.
     *
     * @param  list<array{check: Check, field: ?string, keys: list<string>, locator: array<string, string>}> $asked
     * @return list<string>
     */
    private static function answerKeys(array $asked): array
    {
        $keys = [];

        foreach ($asked as ['keys' => $theseKeys, 'locator' => $locator]) {
            $keys = [...$keys, ...$theseKeys, ...array_keys($locator)];
        }

        return $keys;
    }

    /**
     * The answer keys one check was asked under.
     *
     * @param  list<array{check: Check, field: ?string, keys: list<string>, locator: array<string, string>}> $asked
     * @return list<string>
     */
    private function keysFor(array $asked, string $checkId): array
    {
        foreach ($asked as ['check' => $check, 'keys' => $keys]) {
            if ($check->id === $checkId) {
                return $keys;
            }
        }

        return [];
    }

    /**
     * Ask again, once, about every check whose first answer sat on its trigger.
     *
     * The repeats ride in a single call and only for the checks that need them,
     * so settling a borderline verdict costs one round trip however many are
     * borderline.
     *
     * @param  list<array{check: Check, field: ?string, keys: list<string>, locator: array<string, string>}> $asked
     * @param  list<SystemOneResponse>                                                                       $responses
     * @param  array<string, mixed>                                                                          $state
     * @return array<string, list<SystemOneResponse>>
     */
    private function settle(array $asked, array $responses, ReviewedQuestion $question, Report $report, array $state): array
    {
        if ($responses === [] || $this->repeats > 1) {
            return [];
        }

        $borderline = [];

        foreach ($asked as ['check' => $check, 'keys' => $keys]) {
            if ($check->compare === 'type' || $check->scope === 'state-field') {
                continue;
            }

            $values = [];

            foreach ($responses as $response) {
                foreach ($keys as $key) {
                    $value = $this->reading($response, $key);

                    if ($value !== null) {
                        $values[] = $value;
                    }
                }
            }

            if ($values !== [] && abs((array_sum($values) / count($values)) - $check->trigger) <= self::NEAR) {
                $borderline[] = ['check' => $check, 'keys' => $keys];
            }
        }

        if ($borderline === []) {
            return [];
        }

        // The same state the first call used. Rebuilding it from the question
        // alone showed a state-scoped check `{instructions, criteria}` when its
        // wording asks about `question` and `state`, so the re-ask answered a
        // question that was not on the page and was averaged in regardless.
        $request = $this->client->systemOne()->state($state);

        foreach ($borderline as ['check' => $check, 'keys' => $keys]) {
            foreach ($check->wordings as $index => $wording) {
                $request->ask($keys[$index] ?? $check->answerKey().'__w'.$index, $this->build($wording));
            }
        }

        try {
            $again = $request->send();
        } catch (TypeSafeException $exception) {
            // The first readings still stand, but the borderline ones were not
            // settled, and a run that swallows that reads like one that settled them.
            $report->unreachable(
                $question->id,
                Text::of('report.resettle_failed', ['detail' => $exception->getMessage()]),
                Cause::of($exception),
            );

            return [];
        }

        $report->recordCall($again->usage()->totalTokens());

        $out = [];

        foreach ($borderline as ['check' => $check]) {
            $out[$check->id] = [$again];
        }

        return $out;
    }

    /**
     * @param list<string>            $keys
     * @param list<SystemOneResponse> $responses
     * @param array<string, string>   $locator
     */
    private function record(Check $check, array $keys, ?string $field, array $responses, string $target, Report $report, ?ReviewedQuestion $question = null, array $locator = []): void
    {
        $probabilities = [];
        // Per call as well as pooled. Two wordings that disagree the same way
        // every run are an error bar on one verdict, not a verdict that moves.
        $perCall = [];

        foreach ($responses as $response) {
            $thisCall = [];

            foreach ($keys as $key) {
                $value = $this->reading($response, $key);

                if ($value !== null) {
                    $probabilities[] = $value;
                    $thisCall[] = $value;
                }
            }

            if ($thisCall !== []) {
                $perCall[] = array_sum($thisCall) / count($thisCall);
            }
        }

        // No reading survived: every one was missing or outside 0..1. The check
        // reached no verdict, so it is a loss and not a clear.
        if ($probabilities === []) {
            $report->unreachable($target, Text::of('report.no_reading_from', ['id' => $check->id, 'questions' => count($keys)]));

            return;
        }

        $mean = array_sum($probabilities) / count($probabilities);
        $report->reached($check->id, $target);

        if ($check->scope === 'state-field' && $field !== null) {
            $this->fields[$field][$target] = $mean;

            return;
        }

        $fired = $mean > $check->trigger;
        // Across calls, not across wordings: `undecided` says another run might
        // answer differently, so what has to straddle the trigger is what a run
        // produces, which is the mean of its wordings. The spread over the
        // wordings is reported either way.
        $unstable = count($perCall) > 1
            && min($perCall) <= $check->trigger
            && max($perCall) > $check->trigger;

        // A cleared check within touching distance of its trigger is kept even
        // without `--all`, because the reading is already paid for and it is the
        // one a reader would otherwise re-run the whole query to see.
        $worthSeeing = abs($mean - $check->trigger) <= self::WORTH_SEEING;

        // An `inconclusive` check is reported either way: dropping it when it
        // clears would say the defect is absent, which is the one thing its
        // reading cannot tell you.
        if (! $fired && ! $unstable && ! $worthSeeing && ! $check->inconclusive && ! $this->reportAll) {
            return;
        }

        $elements = $fired && $locator !== [] ? $this->locate($locator, $responses[0]) : [];
        $element = count($elements) === 1 ? $elements[0] : null;

        $report->add(new Finding(
            checkId: $check->id,
            title: match (true) {
                $element !== null => Text::of('finding.title_with_detail', ['title' => $check->title, 'detail' => $this->describe($element, $question)]),
                $elements !== [] => Text::of('finding.title_with_detail', ['title' => $check->title, 'detail' => implode(', ', array_map(
                fn (string $e): string => $this->describe($e, $question),
                $elements,
            ))]),
                $field !== null => Text::of('finding.title_with_field', ['title' => $check->title, 'field' => $field]),
                default => $check->title,
            },
            severity: Severity::fromName($check->severity),
            target: $target,
            message: str_replace('{field}', $field ?? '', $check->message ?? $check->title),
            hint: $check->hint,
            suggest: str_replace(['{target}', '{field}'], [$target, $field ?? ''], $check->suggest),
            advice: $check->advice,
            mode: $check->mode,
            action: $check->action,
            path: $check->path($target, $field).($element === null ? '' : '/'.$this->pointer($check, $element)),
            paths: array_map(
                fn (string $e): string => $check->path($target, $field).'/'.$this->pointer($check, $e),
                $elements,
            ),
            trigger: $check->trigger,
            spread: count($probabilities) > 1 ? max($probabilities) - min($probabilities) : null,
            nearTrigger: abs($mean - $check->trigger) <= self::NEAR,
            supersedes: $check->supersedes,
            docs: $check->docs,
            probability: $mean,
            fired: $fired,
            unstable: $unstable,
            patch: $this->removal($check, $target, $field),
            evidence: $this->evidence($probabilities, $field, $check, $question, $element),
            readings: count($probabilities) > 1 ? $probabilities : [],
            readingsOf: count($probabilities) > 1
                ? $this->readingsOf(count($keys), count($responses), $this->repeats)
                : null,
        ));
    }

    /**
     * @param list<float> $probabilities
     */
    private function evidence(array $probabilities, ?string $field, Check $check, ?ReviewedQuestion $question, ?string $element = null): ?string
    {
        $parts = [];

        if ($element !== null && $question instanceof ReviewedQuestion) {
            $criteria = $question->criteria ?? [];
            $key = str_starts_with($element, 'level_') ? (int) substr($element, 6) : $element;
            $text = $criteria[$key] ?? null;
            $parts[] = Text::of('evidence.read', ['what' => is_string($text) ? '"'.$this->shorten($text).'"' : $element]);
        } elseif ($field !== null) {
            $parts[] = Text::of('evidence.field', ['field' => $field]);
        } elseif ($question instanceof ReviewedQuestion) {
            $read = $this->quote($check, $question);

            if ($read !== null) {
                $parts[] = $read;
            }
        }

        return $parts === [] ? null : implode(' ', $parts);
    }

    /**
     * What the readings behind a probability are.
     *
     * `$calls` counts the answers; `$asked` is what the caller asked for. A
     * borderline check is re-asked without `--repeats`, so a run of one can end
     * with two answers, and calling those "2 repeats" names a flag nobody passed.
     */
    private function readingsOf(int $wordings, int $calls, int $asked): string
    {
        $settled = $asked < 2 && $calls > 1;

        return match (true) {
            $wordings > 1 && $settled => Text::of('readings.wordings_resettled', ['wordings' => $wordings]),
            $settled => Text::of('readings.one_and_a_resettle'),
            $wordings > 1 && $calls > 1 => Text::of('readings.wordings_over_repeats', ['wordings' => $wordings, 'repeats' => $calls]),
            $wordings > 1 => Text::of('readings.wordings', ['wordings' => $wordings]),
            default => Text::of('readings.repeats', ['repeats' => $calls]),
        };
    }

    /**
     * The node a finding says to delete, where deleting one node is the fix.
     *
     * Rewording a question that asks Jev for arithmetic leaves the arithmetic
     * with Jev. The fix is to take the question out and do the work in code.
     */
    private function removal(Check $check, string $target, ?string $field): ?Patch
    {
        return match ($check->removes) {
            // Taking the last question out leaves a query that asks nothing,
            // which this tool reports as an error of its own. The suggestion
            // still stands - the work belongs in code - but it is not a change
            // anything can apply on its own, so no patch is offered.
            'question' => $this->questionCount > 1
                ? new Patch('remove', '/questions/'.Check::escape($target), null, Patch::DESTRUCTIVE)
                : null,
            'field' => $field === null ? null : new Patch('remove', $check->path('state', $field), null, Patch::DESTRUCTIVE),
            default => null,
        };
    }

    /**
     * Every level or option the check fires on.
     *
     * Reporting one of three broken levels sends a literal reader round the
     * loop twice more, so each is asked about and all of them are named.
     *
     * @param  array<string, string> $locator answer key to the element it is about
     * @return list<string>
     */
    private function locate(array $locator, SystemOneResponse $response): array
    {
        $found = [];

        foreach ($locator as $key => $label) {
            if (! $response->has($key)) {
                continue;
            }

            // An empty label marks the Choice form, which names one element.
            if ($label === '') {
                $answer = $response->choice($key);

                if (($answer->probabilityOf($answer->choice()) ?? 0.0) >= 0.5) {
                    $found[] = $answer->choice();
                }

                continue;
            }

            if (($this->reading($response, $key) ?? 0.0) >= 0.6) {
                $found[] = $label;
            }
        }

        return $found;
    }

    /**
     * An element as a reader of their own query would name it.
     *
     * `level_2` is this class's own addressing, zero-based, and printing it at
     * somebody whose rubric starts at 1 names a different level from the one
     * that is wrong. A Choice option is already the label they wrote.
     */
    private function describe(string $element, ?ReviewedQuestion $question): string
    {
        if (! str_starts_with($element, 'level_')) {
            return '`'.$element.'`';
        }

        $index = (int) substr($element, 6);
        $levels = $question instanceof ReviewedQuestion ? count($question->criteria ?? []) : 0;
        $text = $question?->criteria[$index] ?? null;
        $quoted = is_string($text) && $text !== '' ? Text::of('evidence.level_quoted', ['text' => $this->shorten($text, 60)]) : '';

        return $levels > 0
            ? Text::of('evidence.level_of', ['index' => $index + 1, 'levels' => $levels, 'quoted' => $quoted])
            : Text::of('evidence.level', ['index' => $index + 1, 'quoted' => $quoted]);
    }

    /**
     * The pointer tail for one element a check located.
     *
     * `level_2` addresses index 2. A state field is a dotted path and splits into
     * segments, so `ticket.body` is `/ticket/body`. An option label is a key
     * somebody chose, so the `.` in `billing.invoices` belongs to the label, and
     * splitting it addresses a node that is not there or one that is the wrong
     * one.
     */
    private function pointer(Check $check, string $element): string
    {
        if (str_starts_with($element, 'level_')) {
            return substr($element, 6);
        }

        return $check->reads === 'field'
            ? implode('/', array_map(Check::escape(...), Query::segments($element)))
            : Check::escape($element);
    }

    /** What the check was looking at, quoted back from the query */
    private function quote(Check $check, ReviewedQuestion $question): ?string
    {
        $criteria = $question->hasCriteria() ? Json::inline($question->criteria) : null;

        return match ($check->reads) {
            'instructions' => Text::of('evidence.read_quoted', ['what' => $this->shorten($question->instructionsText())]),
            'criteria' => $criteria === null ? null : Text::of('evidence.read', ['what' => $this->shorten($criteria)]),
            'question', 'type' => $criteria === null
                ? Text::of('evidence.read_quoted', ['what' => $this->shorten($question->instructionsText())])
                : Text::of('evidence.read_with', [
                    'instructions' => $this->shorten($question->instructionsText(), 80),
                    'criteria' => $this->shorten($criteria, 80),
                ]),
            default => null,
        };
    }

    /**
     * The text a check was shown, short enough to print.
     *
     * Cut from the middle, not the tail. A question that weighs several factors
     * or asks two things usually carries the second at the end, and a quote that
     * stops before it shows the reader everything except the reason.
     */
    private function shorten(string $text, int $limit = 150): string
    {
        if (mb_strlen($text) <= $limit) {
            return $text;
        }

        $head = (int) floor(($limit - 3) * 0.6);
        $tail = $limit - 3 - $head;

        return mb_substr($text, 0, $head).' … '.mb_substr($text, -$tail);
    }

    /**
     * Whether the catalogue says this answer does not count as a finding.
     *
     * The conditions live in `suppress` and not here, so an implementation
     * in another language reads the same rule out of the same file.
     */
    private function suppressed(Check $check, string $answer, ReviewedQuestion $question): bool
    {
        foreach ($check->suppress as $rule) {
            if ($rule['answer'] !== $answer) {
                continue;
            }

            if ($rule['when'] === 'question_has_fallback_option' && $question->hasFallbackOption()) {
                return true;
            }
        }

        return false;
    }

    /**
     * The type check asks how the options in `criteria` relate to each other,
     * and picks the primitive that fits. The finding is the disagreement with
     * what the query declared
     */
    private function recordTypeComparison(
        Check $check,
        string $key,
        SystemOneResponse $response,
        ReviewedQuestion $question,
        string $target,
        Report $report,
    ): void {
        $report->reached($check->id, $target);

        if (! $response->has($key)) {
            return;
        }

        $answer = $response->choice($key);
        $picked = $answer->choice();

        // How strongly the declared type is read as the wrong one. Defined the
        // same way whichever type the check picks, so a run that agrees with the
        // query still produces a reading, and `--all` can report it. Taking the
        // picked type's own probability instead left the check with no reading at
        // all wherever it agreed, and a firing rate whose denominator was the
        // questions it had already disagreed about.
        $probability = 1.0 - ($answer->probabilityOf($question->type) ?? 0.0);

        $setAside = $picked !== $question->type && $this->suppressed($check, $picked, $question);
        $agrees = $picked === $question->type || $setAside;

        $fired = ! $agrees && $probability > $check->trigger;

        if (! $fired && ! $this->reportAll) {
            return;
        }

        $message = $agrees
            ? Text::of('type.agrees', ['declared' => $question->type])
            : ($picked === 'other'
            ? Text::of('type.none_fits', ['declared' => $question->type])
            : Text::of('type.looks_like', ['picked' => $picked, 'declared' => $question->type]));

        $report->add(new Finding(
            checkId: $check->id,
            title: $check->title,
            severity: Severity::fromName($check->severity),
            target: $target,
            message: $message,
            hint: $check->hint,
            suggest: $check->suggest,
            advice: $check->advice,
            mode: $check->mode,
            action: $check->action,
            path: $check->path($target),
            clearedBecause: $setAside
                ? Text::of('type.suppressed_catch_all', ['picked' => $picked])
                : '',
            trigger: $check->trigger,
            nearTrigger: abs($probability - $check->trigger) <= self::NEAR,
            supersedes: $check->supersedes,
            suggestedType: $agrees || $picked === 'other' ? null : $picked,
            docs: $check->docs,
            // Not a probability that anything is wrong, and not the weight on the
            // primitive this picked either: one minus the weight on the primitive
            // the question declares, so it covers every other primitive at once.
            // `evidence` carries the picked one's own weight.
            measure: 'weight',
            probability: $probability,
            fired: $fired,
            evidence: Text::of('type.evidence', [
                'picked' => $picked,
                'picked_weight' => $answer->probabilityOf($picked) ?? 0.0,
                'declared' => $question->type,
                'declared_weight' => $answer->probabilityOf($question->type) ?? 0.0,
            ]),
        ));
    }
}
