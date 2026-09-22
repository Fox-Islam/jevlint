import { JevLintError } from '../../exceptions/jevLintError.js';
import { ProbeFormatter } from '../../format/probeFormatter.js';
import { Text } from '../../i18n/text.js';
import { ClientFactory } from '../../lint/clientFactory.js';
import { Probe } from '../../probe/probe.js';
import { QuestionProbe } from '../../probe/questionProbe.js';
import { Query } from '../../query/query.js';
import type { Note } from '../../report/note.js';
import { Json } from '../../support/json.js';
import type { Args } from '../args.js';
import type { Output } from '../output.js';
import { ordered } from '../../support/ordered.js';

/** `jevlint probe <query.json>` - how far a rewrite moves the answer */
export class ProbeCommand {
    async run(args: Args, output: Output): Promise<number> {
        const path = args.argument(1);

        if (path === null) {
            throw new JevLintError(Text.of('probe.no_query_file'));
        }

        // The same load `check` does, so a file that is not a query is named as
        // one here too. Reading it straight into an object let a JSON list
        // through to be reported as a missing state, or as a missing key.
        let query = Query.fromFile(path);
        const statePath = args.value('state');

        if (statePath !== null) {
            query = query.withState(Json.readFile(statePath));
        }

        // Probing costs a call per variant per question, so narrowing to the one
        // question being iterated on is the difference between a run you make
        // once and a run you make while editing.
        const named = args.value('question');
        const wanted = named === null
            ? []
            : named.split(',').map((id) => id.trim()).filter((id) => id !== '');

        if (named !== null && wanted.length === 0) {
            throw JevLintError.of(JevLintError.USAGE, Text.of('narrow.no_question_named'));
        }

        const missing = wanted.filter((id) => !query.questions.some((question) => question.id === id));

        if (missing.length > 0) {
            throw JevLintError.of(JevLintError.USAGE, Text.of('query.no_such_question', { path, ids: missing.join(', ') }));
        }

        const whole = query;
        query = query.only(wanted);
        const repeats = args.int('repeats', 5);

        let extra: ReturnType<typeof Probe.rewordings> = [];
        const rewordings = args.value('variants');

        if (rewordings !== null) {
            extra = Probe.rewordings(Json.readFile(rewordings));

            // A rewording keyed by a question id that is not in the file applies
            // to nothing, and the run then reads as a query nothing moved.
            for (const variant of extra) {
                if (whole.questions.some((question) => variant.applies(question))) {
                    continue;
                }

                throw JevLintError.of(JevLintError.USAGE, Text.of('probe.variant_names_no_question', {
                    variant: variant.name(),
                    path,
                    ids: whole.questions.map((question) => question.id).join(', '),
                }));
            }
        }

        // The client is built after the variants are read, so a mistyped path is
        // reported as a mistyped path instead of as a missing key.
        const probe = new Probe(ClientFactory.make(args.value('model'), args.flag('openrouter')));

        const probes = await probe.run(query, repeats, extra);

        if (args.value('format') === 'json') {
            output.line(Json.encode(toObject(probes, path, repeats, probe, args.value('model'))));
        } else {
            output.write(new ProbeFormatter(output.colour()).format(
                probes,
                path,
                repeats,
                probe.calls(),
                probe.tokens(),
                probe.notes(),
            ));
        }

        // A probe that could not send is not a probe that found no movement, and
        // exit 1 is what `--strict` returns when it does find some.
        if (!probe.isComplete()) {
            return 2;
        }

        const moved = [...probes.values()].some(
            (question) => question.readings.some((reading) => question.moved(reading)),
        );

        return args.flag('strict') && moved ? 1 : 0;
    }
}

function toObject(
    probes: Map<string, QuestionProbe>,
    source: string,
    repeats: number,
    probe: Probe,
    askedThrough: string | null,
): Record<string, unknown> {
    const rows: [string, unknown][] = [];

    for (const [id, question] of probes) {
        rows.push([id, {
            type: question.question.type,
            reading: question.reading,
            moved: question.readings.filter((reading) => question.moved(reading)).length > 0,
            baseline: question.baseline(),
            repeats: question.repeats,
            noise: question.noise(),
            floor: question.floor(),
            readings: question.readings.map((reading) => ({
                variant: reading.variant,
                describes: reading.describe,
                value: reading.value,
                delta: question.delta(reading),
                noise_multiples: question.ratio(reading),
                moved: question.moved(reading),
                error: reading.error,
            })),
        }]);
    }

    const questions = ordered(rows);
    const moved = rows
        .filter(([, question]) => (question as { moved: boolean }).moved)
        .map(([id]) => id);

    return {
        source,
        asked_through: askedThrough,
        repeats,
        calls: probe.calls(),
        tokens: probe.tokens(),
        notes: probe.notes().map((note: Note) => note.toObject()),
        summary: {
            questions: rows.length,
            moved: moved.length,
            moved_questions: moved,
            unreachable: probe.unreachable(),
            complete: probe.isComplete(),
            rule: Text.of('probe.moved_definition', { floor: QuestionProbe.NEGLIGIBLE }),
            floor: Text.of('probe.floor_definition', { noise: Probe.PUBLISHED_NOISE }),
        },
        questions,
    };
}
