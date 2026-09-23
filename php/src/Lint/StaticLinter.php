<?php

declare(strict_types=1);

namespace Phox\JevLint\Lint;

use Phox\JevLint\Catalogue\Catalogue;
use Phox\JevLint\Catalogue\Check;
use Phox\JevLint\Exceptions\JevLintException;
use Phox\JevLint\I18n\Text;
use Phox\JevLint\Query\Query;
use Phox\JevLint\Query\ReviewedQuestion;
use Phox\JevLint\Report\Finding;
use Phox\JevLint\Report\Patch;
use Phox\JevLint\Support\Json;
use Phox\JevLint\Report\Report;
use Phox\JevLint\Report\Severity;

/**
 * The rules that need no call: shapes the API rejects, and defects visible in
 * the structure instead of in the wording.
 *
 * These run first and always. A query that fails one of them either cannot be
 * sent or is broken in a way no amount of rephrasing fixes, and finding
 * that out should not cost a round trip
 */
final class StaticLinter
{
    /**
     * Every rule this file can raise.
     *
     * A catalogue naming a rule that is not here claims a condition nobody
     * tests: the check loads, lists, documents itself and never fires. The
     * opposite case throws where the rule is raised
     *
     * @var list<string>
     */
    public const RULES = [
        'choice.criteriaShape',
        'choice.descriptionNotText',
        'choice.indexLikeOptions',
        'choice.noCriteria',
        'choice.noFallback',
        'choice.tooFewOptions',
        'choice.tooManyOptions',
        'choice.undescribedOptions',
        'noul.criteriaShape',
        'noul.noCriteria',
        'query.duplicateInstructions',
        'query.floatingModel',
        'query.noQuestions',
        'query.unknownKey',
        'question.criteriaNotAStructure',
        'question.instructionIsId',
        'question.instructionsEmpty',
        'question.noInstructions',
        'question.typeNotLowercase',
        'question.unknownType',
        'score.criteriaShape',
        'score.levelsNotText',
        'score.noCriteria',
        'score.numericLevels',
        'score.tooFewLevels',
        'score.tooManyLevels',
        'state.missing',
        'state.oversized',
    ];

    /** What the API takes, as `Too many choices. Must have at most 255 choices.` on a 400 */
    private const MOST_OPTIONS = 255;

    /** The largest number a JavaScript object treats as an array index */
    private const LARGEST_INDEX = 4294967294;

    /**
     * @param list<string> $only check ids to run, or all of them when empty
     */
    public function __construct(
        private readonly Catalogue $catalogue,
        private readonly int $maxStateChars = 20000,
        private readonly array $only = [],
    ) {}

    public function run(Query $query, Report $report): void
    {
        $report->asked($this->applicable($query));
        $this->queryRules($query, $report);

        foreach ($query->questions as $question) {
            $this->questionRules($question, $report);
        }
    }

    /**
     * How many static checks have anything to look at in this query.
     *
     * A question-scoped rule needs a question of a type it covers; a
     * query-scoped one always has the query
     */
    private function applicable(Query $query): int
    {
        $types = array_values(array_unique(array_map(
            static fn (ReviewedQuestion $q): string => $q->type,
            $query->questions,
        )));
        $applicable = 0;

        foreach ($this->catalogue->static() as $check) {
            if ($this->only !== [] && ! in_array($check->id, $this->only, true)) {
                continue;
            }

            if ($check->scope === 'query' || array_filter($types, $check->covers(...)) !== []) {
                $applicable++;
            }
        }

        return $applicable;
    }

    private function queryRules(Query $query, Report $report): void
    {
        if ($query->questions === []) {
            $this->raise('query.noQuestions', 'query', $report);

            return;
        }

        $seen = [];

        foreach ($query->questions as $question) {
            $text = trim($question->instructionsText());

            if ($text === '') {
                continue;
            }

            if (isset($seen[$text])) {
                $this->raise(
                    'query.duplicateInstructions',
                    $question->id,
                    $report,
                    Text::of('evidence.identical_to', ['other' => $seen[$text]]),
                );

                continue;
            }

            $seen[$text] = $question->id;
        }

        // A request naming no build at all makes no claim about one, and the
        // report names the build it ran against. An alias claims a build and
        // resolves to a different one the day a newer lands.
        if (is_string($query->model) && preg_match('/^jev-\d+(?:\.\d+)*$/', $query->model) !== 1) {
            $this->raise(
                'query.floatingModel',
                'query',
                $report,
                Text::of('evidence.found_quoted', ['what' => $query->model]),
            );
        }

        $extra = array_values(array_diff(array_keys($query->raw), ['state', 'questions', 'model']));

        if ($extra !== []) {
            // The keys as pointers, not only inside the sentence. An error whose
            // fix is "delete this key" gave a fixer nothing but prose to parse.
            $this->raise(
                'query.unknownKey',
                'query',
                $report,
                Text::of('evidence.found', ['what' => implode(', ', array_map(static fn (string $k): string => '`'.$k.'`', $extra))]),
                count($extra) === 1 ? new Patch('remove', '/'.Check::escape($extra[0])) : null,
                array_map(static fn (string $k): string => '/'.Check::escape($k), $extra),
            );
        }

        if (! $query->hasState()) {
            $this->raise('state.missing', 'query', $report);

            return;
        }

        $size = $query->stateSize();

        if ($size > $this->maxStateChars) {
            $this->raise(
                'state.oversized',
                'state',
                $report,
                Text::of('evidence.state_size', [
            'size' => $size,
            'threshold' => $this->maxStateChars,
        ]),
            );
        }
    }

    private function questionRules(ReviewedQuestion $question, Report $report): void
    {
        if (! $question->isKnownType()) {
            $this->raise('question.unknownType', $question->id, $report, Text::of('evidence.found_quoted', ['what' => $question->type]));

            return;
        }

        $declared = $question->raw['type'] ?? null;

        if (is_string($declared) && $declared !== strtolower($declared)) {
            // The whole fix is one call to strtolower, so it is a patch and not
            // advice, and it addresses `type` and not the question around it.
            $this->raise(
                'question.typeNotLowercase',
                $question->id,
                $report,
                Text::of('evidence.found_quoted', ['what' => $declared]),
                new Patch(
                    'replace',
                    '/questions/'.Check::escape($question->id).'/type',
                    strtolower($declared),
                    Patch::LOSSLESS,
                ),
            );
        }

        // `criteria` present but neither a list nor a map: a comma-separated string
        // reads as options to a person and is one value to the API.
        if (array_key_exists('criteria', $question->raw) && ! is_array($question->raw['criteria'])) {
            $this->raise(
                'question.criteriaNotAStructure',
                $question->id,
                $report,
                Text::of('evidence.found', ['what' => Json::inline($question->raw['criteria'])]),
            );
        }

        // `trim()` knows five ASCII characters. A non-breaking space, a zero-width
        // space or an ideographic space is an instruction carrying no words, and
        // the model answers a blank question instead of yours.
        if (preg_replace('/[\s\p{Z}\p{C}]+/u', '', $question->instructionsText()) === '') {
            $this->raise('question.noInstructions', $question->id, $report);
        } elseif (is_array($question->instructions) && trim($this->words($question->instructions)) === '') {
            $this->raise('question.instructionsEmpty', $question->id, $report);
        } elseif ($this->instructionIsId($question)) {
            $this->raise(
                'question.instructionIsId',
                $question->id,
                $report,
                Text::of('evidence.instructions', ['text' => $question->instructionsText()]),
            );
        }

        match ($question->type) {
            'noul' => $this->noulRules($question, $report),
            'choice' => $this->choiceRules($question, $report),
            'score' => $this->scoreRules($question, $report),
            default => null,
        };
    }

    /**
     * Every string anywhere inside a structured instruction
     *
     * @param array<array-key, mixed> $node
     */
    private function words(array $node): string
    {
        $text = '';

        foreach ($node as $value) {
            $text .= is_array($value) ? $this->words($value) : (is_string($value) ? $value : '');
        }

        return $text;
    }

    private function noulRules(ReviewedQuestion $question, Report $report): void
    {
        if (! $question->hasCriteria()) {
            $this->raise('noul.noCriteria', $question->id, $report);

            return;
        }

        $criteria = $question->criteria ?? [];
        $keys = array_map(strtolower(...), array_map(strval(...), array_keys($criteria)));

        if ($question->criteriaIsList() || array_diff($keys, ['true', 'false']) !== []) {
            $renamed = null;

            // Two keys that differ only in case - `yes` beside `YES` - collapse
            // onto one renamed key, and the second description overwrites the
            // first. Nothing may be lost under a lossless patch, so where the
            // keys collide the advice stands without one.
            if (! $question->criteriaIsList()
                && array_diff($keys, ['yes', 'no']) === []
                && count(array_unique($keys)) === count($keys)) {
                $renamed = [];

                foreach ($criteria as $key => $value) {
                    $renamed[strtolower((string) $key) === 'yes' ? 'true' : 'false'] = $value;
                }
            }

            $this->raise(
                'noul.criteriaShape',
                $question->id,
                $report,
                Text::of('evidence.keys', ['keys' => $keys === [] ? Text::of('evidence.none') : implode(', ', $keys)]),
                $renamed === null ? null : new Patch('replace', '/questions/'.Check::escape($question->id).'/criteria', $renamed, Patch::LOSSLESS),
            );
        }
    }

    private function choiceRules(ReviewedQuestion $question, Report $report): void
    {
        $criteria = $question->criteria;

        // `criteria` absent altogether, as opposed to the wrong shape, left every
        // Choice rule unreached and the query reported clean.
        if ($criteria === null) {
            if (! array_key_exists('criteria', $question->raw)) {
                $this->raise('choice.noCriteria', $question->id, $report);
            }

            return;
        }

        if ($question->criteriaIsList()) {
            $labels = array_values(array_filter($criteria, 'is_string'));

            // Only where every entry is a label this can keep, and every label is
            // distinct. An entry that is a number or a nested object has no label
            // to carry over, and two entries spelled the same collapse onto one
            // key, so either way a patch here removes an option the caller wrote.
            $whole = count($labels) === count($criteria)
                && count(array_unique($labels)) === count($labels);

            // Numeric-looking labels make `array_fill_keys` a PHP list, which
            // encodes as a JSON array - the very shape this check exists to
            // refuse, so the patch would not clear its own finding.
            $keyed = array_reduce(
                $labels,
                static fn (bool $all, string $l): bool => $all && $l !== '' && (string) (int) $l !== $l,
                true,
            );

            $this->raise(
                'choice.criteriaShape',
                $question->id,
                $report,
                null,
                $whole && $keyed && count($labels) >= 2
                    ? new Patch('replace', '/questions/'.Check::escape($question->id).'/criteria', (object) array_fill_keys($labels, ''), Patch::LOSSY)
                    : null,
            );

            return;
        }

        $labels = array_map(strval(...), array_keys($criteria));

        if (count($labels) < 2) {
            $this->raise('choice.tooFewOptions', $question->id, $report, Text::of('evidence.option_count', ['count' => count($labels)]));
        }

        if (count($labels) > self::MOST_OPTIONS) {
            $this->raise('choice.tooManyOptions', $question->id, $report, Text::of('evidence.option_count', ['count' => count($labels)]));
        }

        $lowered = array_map(mb_strtolower(...), $labels);

        $notText = array_values(array_filter(
            $criteria,
            static fn (mixed $value): bool => $value !== null && ! is_string($value),
        ));

        if ($notText !== []) {
            $this->raise(
                'choice.descriptionNotText',
                $question->id,
                $report,
                Text::of('evidence.found', ['what' => Json::inline($notText[0])]),
            );

            return;
        }

        $described = array_filter($criteria, static fn (mixed $value): bool => $value !== null && $value !== '' && $value !== []);

        // One definition of a catch-all, on the question that owns it, so the
        // rule cannot offer to add a second one beside a catch-all it failed to
        // recognise by name.
        if (! $question->hasFallbackOption()) {
            $this->raise(
                'choice.noFallback',
                $question->id,
                $report,
                Text::of('evidence.options', ['options' => implode(', ', $labels)]),
                // Adding a fallback to options that carry no descriptions leaves
                // the criteria in a shape the next check rejects, so no patch
                $described === [] ? null : new Patch('add', '/questions/'.Check::escape($question->id).'/criteria', $criteria + ['other' => Text::of('patch.fallback_option')], Patch::LOSSY),
            );
        }

        if ($described === []) {
            $this->raise('choice.undescribedOptions', $question->id, $report);
        }

        $sent = self::asJavaScriptSends($labels);

        if ($sent !== $labels) {
            $this->raise('choice.indexLikeOptions', $question->id, $report, Text::of('evidence.reordered_options', [
                'written' => implode(', ', $labels),
                'sent' => implode(', ', $sent),
            ]));
        }
    }

    /**
     * The options in the order a JavaScript object would list them.
     *
     * A key holding the plain decimal form of a number up to 2^32 - 2 is an
     * array index, and an object lists every one of those first, in ascending
     * order, before the keys it was written with.
     *
     * @param  list<string>  $labels
     * @return list<string>
     */
    private static function asJavaScriptSends(array $labels): array
    {
        $isIndex = static fn (string $label): bool => preg_match('/^(0|[1-9][0-9]*)$/', $label) === 1
            && (float) $label <= self::LARGEST_INDEX;

        $indexes = array_values(array_filter($labels, $isIndex));
        $rest = array_values(array_filter($labels, static fn (string $label): bool => ! $isIndex($label)));

        usort($indexes, static fn (string $a, string $b): int => (float) $a <=> (float) $b);

        return array_merge($indexes, $rest);
    }

    private function scoreRules(ReviewedQuestion $question, Report $report): void
    {
        $criteria = $question->criteria;

        if ($criteria === null) {
            if (! array_key_exists('criteria', $question->raw)) {
                $this->raise('score.noCriteria', $question->id, $report);
            }

            return;
        }

        $structured = array_values(array_filter($criteria, is_array(...)));

        if ($structured !== []) {
            $this->raise(
                'score.levelsNotText',
                $question->id,
                $report,
                Text::of('evidence.found', ['what' => Json::inline($structured[0])]),
            );

            return;
        }

        if (! $question->criteriaIsList()) {
            $ordered = $criteria;

            // A Score is an ordered rubric, so the order of the list this becomes is
            // the meaning. Keys that are all numbers say what the order is, and taking
            // them in the order they happened to be written ships a reversed scale
            // that clears this check and is wrong.
            $keys = array_keys($ordered);
            $numeric = $keys !== [] && count(array_filter(
                $keys,
                static fn (int|string $k): bool => is_int($k) || preg_match('/^-?\d+$/', $k) === 1,
            )) === count($keys);

            if ($numeric) {
                uksort($ordered, static fn (int|string $a, int|string $b): int => (int) $a <=> (int) $b);
            }

            $levels = array_map(
                static fn (mixed $v, int|string $k): mixed => is_string($v) && $v !== '' ? $v : $k,
                $ordered,
                array_keys($ordered),
            );

            // Every level has to survive as the text somebody wrote. Where a
            // value is empty or is not text, the line above puts the key in its
            // place, and a rubric level replaced by its own index is content
            // lost under a patch that says nothing is.
            $describes = array_reduce(
                $ordered,
                static fn (bool $all, mixed $v): bool => $all && is_string($v) && $v !== '',
                true,
            );

            // A map of one is not a rubric, and a map of more than ten is past
            // what a Score takes, so reshaping either produces a file that fails
            // the query schema.
            $sized = count($ordered) >= 2 && count($ordered) <= 10;

            $this->raise(
                'score.criteriaShape',
                $question->id,
                $report,
                $numeric
                    ? Text::of('evidence.keys_are_numbers')
                    : Text::of('evidence.keys_are_names'),
                // Only where the keys say what the order is. With names, the order
                // of a map is the order it happened to be written in, and a patch
                // built from that ships a scrambled rubric that clears this check.
                // A caller applying patches unattended cannot read the line above.
                $numeric && $describes && $sized
                    ? new Patch('replace', '/questions/'.Check::escape($question->id).'/criteria', $levels, Patch::LOSSLESS)
                    : null,
            );

            return;
        }

        $levels = $criteria;

        if (count($levels) < 2) {
            $this->raise('score.tooFewLevels', $question->id, $report, Text::of('evidence.level_count', ['count' => count($levels)]));

            return;
        }

        if (count($levels) > 10) {
            $this->raise('score.tooManyLevels', $question->id, $report, Text::of('evidence.level_count', ['count' => count($levels)]));
        }

        $wordless = array_filter(
            $levels,
            static fn (mixed $level): bool => is_scalar($level) && preg_match('/\p{L}/u', (string) $level) !== 1,
        );

        if (count($wordless) === count($levels)) {
            $this->raise('score.numericLevels', $question->id, $report, Text::of('evidence.levels', ['levels' => implode(', ', array_map(strval(...), $levels))]));
        }
    }

    /**
     * An instruction that says no more than the id does. Ids are never sent, so
     * the model sees nothing
     */
    private function instructionIsId(ReviewedQuestion $question): bool
    {
        // Letters and digits in any script, so an accented word survives instead
        // of being cut into the pieces between its accents.
        $normalise = static fn (string $value): string => trim(preg_replace('/[^\p{L}\p{N} ]+/u', ' ', mb_strtolower($value)) ?? '');
        $id = $normalise(str_replace(['_', '-', '.'], ' ', $question->id));
        $instructions = $normalise($question->instructionsText());

        if ($id === '' || $instructions === '') {
            return false;
        }

        $instructionWords = preg_split('/\s+/', $instructions) ?: [];

        if (count($instructionWords) > 4) {
            return false;
        }

        $idWords = preg_split('/\s+/', $id) ?: [];

        // "Is the customer blocked?" is four words and contains the id, and it is
        // a whole question. What makes an instruction lean on its id is that it
        // adds nothing to it: "Refund requested?" beside `refund_requested` does,
        // and the grammar around it is not content.
        $content = array_values(array_diff($instructionWords, Text::list('words.grammar')));

        if (array_diff($content, $idWords) !== []) {
            return false;
        }

        return array_diff($idWords, $instructionWords) === [];
    }

    /**
     * @param list<string> $paths every node at fault, where a finding names more than one
     */
    private function raise(
        string $rule,
        string $target,
        Report $report,
        ?string $evidence = null,
        ?Patch $patch = null,
        array $paths = [],
    ): void {
        $check = $this->catalogue->rule($rule);

        // A rule the catalogue does not name is a typo, not a condition. Returning
        // quietly drops the finding, turns a failing run green, and leaves every
        // test passing, so it is raised as the programming error it is.
        if (! $check instanceof Check) {
            throw JevLintException::of(JevLintException::CATALOGUE, Text::of('catalogue.rule_unclaimed', ['rule' => $rule]));
        }

        if ($this->only !== [] && ! in_array($check->id, $this->only, true)) {
            return;
        }

        $report->add(new Finding(
            checkId: $check->id,
            title: $check->title,
            severity: Severity::fromName($check->severity),
            target: $target,
            message: $check->message ?? $check->title,
            hint: $check->hint,
            suggest: str_replace('{target}', $target, $check->suggest),
            advice: $check->advice,
            mode: $check->mode,
            action: $check->action,
            path: $paths === [] ? $check->path($target) : $paths[0],
            supersedes: $check->supersedes,
            docs: $check->docs,
            evidence: $evidence,
            patch: $patch,
            paths: $paths,
        ));
    }
}
