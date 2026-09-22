import { Catalogue } from '../catalogue/catalogue.js';
import type { Check } from '../catalogue/check.js';
import { Config } from '../config/config.js';
import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';
import { Query } from '../query/query.js';
import { Report } from '../report/report.js';
import type { Client } from '../typesafe/client.js';
import { ClientFactory } from './clientFactory.js';
import { ModelLinter } from './modelLinter.js';
import { StaticLinter } from './staticLinter.js';

interface Settings {
    catalogue: Catalogue;
    /** built when the run reaches a check that needs it, so a run of only rules needs no key */
    client: (() => Client) | null;
    config: Config;
    /** check ids this run includes, or all of them when empty */
    only: string[];
    checkState: boolean;
    repeats: number;
    reportCleared: boolean;
    maxStateChars: number;
    askedThrough: string | null;
}

/**
 * One run of the linter, from a query to a report.
 *
 * The two linters are separately usable, and this puts them in the order a run
 * needs, stamps the report with the catalogue that produced it, validates the
 * narrowing against the catalogue, and records what the run left out. The
 * console commands go through here, so a caller in JavaScript gets the report
 * the CLI prints
 */
export class Linter {
    private constructor(private readonly settings: Settings) {}

    /**
     * A linter that asks its model checks through `client`.
     *
     * Any client will do, including one given a fake transport, which is how the
     * tests here run the model path without calling anything
     */
    static make(client: Client, catalogue?: Catalogue, config?: Config): Linter {
        return new Linter({
            catalogue: catalogue ?? Catalogue.load(),
            client: () => client,
            config: config ?? Config.empty(),
            only: [],
            checkState: true,
            repeats: 1,
            reportCleared: false,
            maxStateChars: 20000,
            askedThrough: null,
        });
    }

    /**
     * A linter that reads a key from the environment, or a `.env` in the working
     * directory, and builds its own client
     */
    static fromEnvironment(options: {
        model?: string | null;
        openRouter?: boolean;
        timeout?: number | null;
        catalogue?: Catalogue;
        config?: Config;
    } = {}): Linter {
        const model = options.model ?? null;

        return new Linter({
            catalogue: options.catalogue ?? Catalogue.load(),
            client: () => ClientFactory.make(model, options.openRouter ?? false, options.timeout ?? null, true),
            config: options.config ?? Config.empty(),
            only: [],
            checkState: true,
            repeats: 1,
            reportCleared: false,
            maxStateChars: 20000,
            askedThrough: model,
        });
    }

    /** A linter that runs the rules and makes no calls, so it needs no key */
    static rulesOnly(catalogue?: Catalogue, config?: Config): Linter {
        return new Linter({
            catalogue: catalogue ?? Catalogue.load(),
            client: null,
            config: config ?? Config.empty(),
            only: [],
            checkState: true,
            repeats: 1,
            reportCleared: false,
            maxStateChars: 20000,
            askedThrough: null,
        });
    }

    private with(changed: Partial<Settings>): Linter {
        return new Linter({ ...this.settings, ...changed });
    }

    /**
     * The rules for one Jev version.
     *
     * A query is sent to one build, and a build has the defects it has. Without
     * this the run uses the newest version the catalogue covers
     */
    forJev(version: string): Linter {
        return this.with({ catalogue: this.settings.catalogue.forJev(version) });
    }

    /** The acceptances a report reads to set findings aside */
    accepting(config: Config): Linter {
        return this.with({ config });
    }

    /**
     * Narrow the run to these checks.
     *
     * An id the catalogue does not hold is an error instead of a narrowing that
     * silently runs nothing
     */
    only(checkIds: string[]): Linter {
        const ids = this.settings.catalogue.written().map((check) => check.id);
        const unknown = checkIds.filter((id) => !ids.includes(id));

        if (unknown.length > 0) {
            throw new JevLintError(Text.of('catalogue.no_such_check', { ids: unknown.join(', ') }));
        }

        const withheld = checkIds.filter((id) => this.settings.catalogue.find(id) === null);

        if (withheld.length > 0) {
            throw new JevLintError(Text.of('narrow.withheld_for_version', {
                ids: withheld.join(', '),
                count: withheld.length,
                jev: this.settings.catalogue.jev,
            }));
        }

        return this.with({ only: checkIds });
    }

    /** Leave out the checks that read the query's state */
    withoutState(): Linter {
        return this.with({ checkState: false });
    }

    /** Ask each model check this many times, so the report has the spread */
    repeats(repeats: number): Linter {
        return this.with({ repeats });
    }

    /**
     * Carry every model check that ran and cleared, not only the readings near a
     * trigger. Without this a check that cleared and a check that never applied
     * are indistinguishable
     */
    reportingCleared(): Linter {
        return this.with({ reportCleared: true });
    }

    /** Where a state stops being state and starts being a document */
    maxStateChars(chars: number): Linter {
        return this.with({ maxStateChars: chars });
    }

    /** Record in the report which build the run asked for */
    askedThrough(model: string | null): Linter {
        return this.with({ askedThrough: model });
    }

    catalogue(): Catalogue {
        return this.settings.catalogue;
    }

    async checkFile(path: string): Promise<Report> {
        return this.check(Query.fromFile(path));
    }

    /**
     * Run the catalogue over a query.
     *
     * `whole` is the query before any narrowing, where the caller narrowed it
     * with `Query.only()`. The checks that judge a state field against the whole
     * query cannot answer from part of it, so they are left out and said to be
     * left out
     */
    async check(query: Query, whole: Query | null = null): Promise<Report> {
        const { catalogue, config, client } = this.settings;
        const unknown = config.unknown(catalogue.written().map((check) => check.id));

        // A config naming a check that is not in the catalogue is accepting
        // nothing, which is worse than accepting the wrong thing.
        if (unknown.length > 0) {
            throw JevLintError.of(JevLintError.CONFIG, Text.of('config.accepts_unknown_check', {
                source: config.source ?? Config.FILE,
                ids: unknown.join(', '),
            }));
        }

        const left = whole === null ? 0 : whole.questions.length - query.questions.length;

        const report = new Report({
            source: query.source,
            catalogueVersion: catalogue.version,
            model: catalogue.model,
            fingerprint: catalogue.fingerprint,
            questionPrint: catalogue.asked,
            askedThrough: this.settings.askedThrough,
        });

        report.orderBy(query.questions.map((question) => question.id));
        report.acceptFrom(config);
        this.noteVersion(whole ?? query, report);

        new StaticLinter(catalogue, this.settings.maxStateChars, this.settings.only).run(query, report);

        this.noteWhatWasLeftOut(report, left);

        if (client !== null && this.asksJev()) {
            await new ModelLinter(
                catalogue,
                client(),
                this.settings.checkState,
                this.settings.repeats,
                this.settings.only,
                this.settings.reportCleared,
                left > 0,
            ).run(query, report);
        }

        return report;
    }

    /** Whether anything in this run needs a call at all */
    private asksJev(): boolean {
        return this.modelChecks().length > 0;
    }

    private modelChecks(): Check[] {
        return this.settings.catalogue.all().filter(
            (check) => check.isModel()
                && (this.settings.only.length === 0 || this.settings.only.includes(check.id)),
        );
    }

    /**
     * A query file may pin the build it will be sent to. Where that is a Jev
     * version and the run resolved another one, the findings are the rules for a
     * build this query never reaches
     */
    private noteVersion(query: Query, report: Report): void {
        const named = query.model === null ? null : /^jev-(\d+(?:\.\d+)*)$/.exec(query.model);

        if (named === null || named[1] === this.settings.catalogue.jev) {
            return;
        }

        // `--jev` only takes a version the catalogue covers, and a build id
        // carrying a patch number - `jev-1.13.0` is what the API answers for
        // `jev-latest` - is not one, so telling every reader to pass it sent
        // half of them to a flag that refuses the value they would pass.
        const covered = this.settings.catalogue.versions.includes(named[1] ?? '');

        const about = {
            source: query.source,
            model: query.model ?? '',
            jev: this.settings.catalogue.jev,
            named: named[1] ?? '',
        };

        report.note(covered
            ? Text.of('note.version_covered', about)
            : Text.of('note.version_not_covered', about));
    }

    /**
     * Say what this run left out. A narrowed run that matched nothing, or a run
     * with the model half switched off, produces the same empty report as a
     * query with nothing wrong with it
     */
    private noteWhatWasLeftOut(report: Report, questionsLeftOut: number): void {
        const { catalogue, client, only, checkState } = this.settings;

        if (questionsLeftOut > 0) {
            report.skipped(Text.of('skipped.questions_left_out', { count: questionsLeftOut }));
        }

        if (client === null) {
            const model = this.modelChecks();

            if (model.length > 0) {
                report.skipped(Text.of('skipped.jev_not_asked', { count: model.length }), model.length);
            }
        } else if (!checkState) {
            const stateScoped = catalogue.all().filter(
                (check) => check.isModel() && ['state', 'state-field', 'state-once'].includes(check.scope),
            );

            report.skipped(Text.of('skipped.state_not_checked', { count: stateScoped.length }), stateScoped.length);
        }

        if (only.length > 0) {
            report.skipped(Text.of('skipped.narrowed_to', {
                count: only.length,
                total: catalogue.all().length,
            }), catalogue.all().length - only.length);
        }

        if (catalogue.withheld() > 0) {
            report.skipped(Text.of('skipped.written_for_another_version', {
                jev: catalogue.jev,
                count: catalogue.withheld(),
            }), catalogue.withheld());
        }
    }
}
