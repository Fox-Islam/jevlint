import { createHash } from 'node:crypto';
import { existsSync, readFileSync, statSync } from 'node:fs';
import type { Config } from '../config/config.js';
import { JevLintError } from '../exceptions/jevLintError.js';
import { Text } from '../i18n/text.js';
import { isRule } from '../lint/rules.js';
import { PRIMITIVES } from '../query/reviewedQuestion.js';
import { Json } from '../support/json.js';
import { from } from '../support/paths.js';
import { encodeLikePhp } from '../support/phpJson.js';
import { Check, VERSION, compareVersions } from './check.js';

/**
 * The check catalogue, read from `checks/catalogue.json`.
 *
 * The file sits at the root of the repository instead of inside this package,
 * so an implementation in another language reads the same one. Nothing in it is
 * JavaScript-specific: a static check names a rule the implementation owns, and
 * a model check is a Jev question, which is data in any language
 */
export class Catalogue {
    /** What `--jev` is given when nobody pins a version */
    static readonly LATEST = 'latest';

    /** The Jev build the carried checks are the rules for, as the report names it */
    public readonly model: string;

    private constructor(
        public readonly version: string,
        public readonly jev: string,
        /** the Jev versions the file covers, oldest first */
        public readonly versions: string[],
        public readonly fingerprint: string,
        public readonly asked: string,
        /** the checks carried for `jev` */
        private readonly checks: Check[],
        /** every check in the file, whatever version it is for */
        private readonly writtenChecks: Check[],
    ) {
        this.model = `jev-${jev}`;
    }

    static load(path?: string): Catalogue {
        const file = path ?? Catalogue.locate('catalogue.json');
        const contents = readFileSync(file);
        const data = Json.decode(contents.toString('utf8'), file);

        if (!Array.isArray(data['checks']) || data['checks'].length === 0) {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.no_checks', { path: file }));
        }

        const declared = data['checks'] as unknown[];

        // The version is what two reports are compared on, so an invented one is
        // worse than none.
        if (data['version'] !== undefined && typeof data['version'] !== 'string' && typeof data['version'] !== 'number') {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.version_wrong_type', {
                path: file,
                type: typeName(data['version']),
            }));
        }

        // Two checks under one id behave as one or the other depending on which
        // lookup you go through: `--only` narrows to both, `find()` answers with
        // whichever comes first.
        const ids = new Set<string>();

        for (const check of declared) {
            const id = typeof check === 'object' && check !== null && typeof (check as Record<string, unknown>)['id'] === 'string'
                ? (check as Record<string, string>)['id']
                : null;

            if (id === undefined || id === null) {
                continue;
            }

            if (ids.has(id)) {
                throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.duplicate_id', { path: file, id }));
            }

            ids.add(id);
        }

        const versions = readVersions(data, file);

        for (const [position, check] of declared.entries()) {
            // A `null` or a number reaching Check.fromObject is a crash and a
            // stack trace, where a caller was promised a message.
            if (typeof check !== 'object' || check === null || Array.isArray(check)) {
                throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.check_not_an_object', {
                    path: file,
                    type: typeName(check),
                    position: `#${position + 1}`,
                }));
            }
        }

        const checks = declared.map((check) => Check.fromObject(check as Record<string, unknown>));

        // A static check naming a rule no code raises can never fire, and the
        // report that leaves it out reads exactly like a clean one. The opposite
        // case throws where the rule is raised.
        for (const check of checks) {
            if (check.isStatic() && (check.rule === null || !isRule(check.rule))) {
                throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.unknown_rule', {
                    id: check.id,
                    rule: check.rule === null ? Text.of('catalogue.rule_nothing') : `"${check.rule}"`,
                }));
            }
        }

        // Both of these are collisions only among the checks one version runs. A
        // rule whose severity changed between Jev versions is two checks naming
        // it, separated by `since` and `until`, and they never meet.
        for (const version of versions) {
            const rules = new Map<string, string>();
            const keys = new Map<string, string>();

            for (const check of checks) {
                if (!check.coversJev(version)) {
                    continue;
                }

                // Two checks naming one rule is worse than two sharing an id:
                // `rule()` answers with the first, and the finding is reported
                // under its id and its severity. A second check demoting the
                // first to advice takes a run that exited 1 down to 0, and the
                // report reads as a pass.
                if (check.isStatic() && check.rule !== null) {
                    const first = rules.get(check.rule);

                    if (first !== undefined) {
                        throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.rule_shadowed', {
                            first,
                            second: check.id,
                            rule: check.rule,
                            jev: version,
                        }));
                    }

                    rules.set(check.rule, check.id);
                }

                // Two ids differing only in `/` against `-` collide once
                // `answerKey()` has replaced both, so the second overwrites the
                // first in the request and is reported carrying its answer.
                if (check.isModel()) {
                    const key = check.answerKey();
                    const first = keys.get(key);

                    if (first !== undefined) {
                        throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.key_collision', {
                            first,
                            second: check.id,
                            key,
                            jev: version,
                        }));
                    }

                    keys.set(key, check.id);
                }
            }
        }

        // The model half of the rule guard above. A model check is its question,
        // so one carrying none is counted among the checks that ask, listed by
        // `checks`, and never asked.
        for (const check of checks) {
            if (check.isModel() && check.wordings.length === 0) {
                throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.model_without_question', { id: check.id }));
            }
        }

        // `applies_to` is matched against a question's type, so a primitive that
        // does not exist narrows the check to nothing.
        for (const check of checks) {
            const allowed: string[] = [...PRIMITIVES, '*'];
            const unknown = check.appliesTo.filter((primitive) => !allowed.includes(primitive));

            if (unknown.length > 0) {
                throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.unknown_primitive', {
                    id: check.id,
                    primitive: unknown[0] ?? '',
                    primitives: PRIMITIVES.join(', '),
                }));
            }
        }

        // A `supersedes` naming nothing drops the suppression it was written for,
        // and the finding it should have discarded is reported beside the one
        // that replaces it.
        const known = new Set(checks.map((check) => check.id));

        for (const check of checks) {
            for (const superseded of check.supersedes) {
                if (!known.has(superseded)) {
                    throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.supersedes_unknown', {
                        id: check.id,
                        other: superseded,
                    }));
                }
            }
        }

        // A check written for no version the file covers can never run: a `since`
        // a release ahead of the catalogue does that.
        for (const check of checks) {
            if (!versions.some((version) => check.coversJev(version))) {
                throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.covers_no_version', {
                    id: check.id,
                    versions: versions.join(', '),
                }));
            }
        }

        const latest = versions[versions.length - 1] ?? '';

        // A second fingerprint over what the checks ask, and nothing else. The
        // whole-file one moves when a message is reworded, which tells a corpus
        // its readings are stale when nothing it measured has changed.
        const asked: unknown[] = [];

        for (const raw of declared) {
            const check = raw as Record<string, unknown>;

            if (check['mode'] !== 'model') {
                continue;
            }

            // `scope` decides whether the state goes in front of the check and
            // `locate_mode` decides whether a locator is one Choice or one
            // question per level, so both change the calls without touching a
            // word of the question. `since` and `until` decide whether the check
            // is asked at all.
            asked.push({
                id: check['id'] ?? null,
                scope: check['scope'] ?? null,
                trigger: check['trigger'] ?? null,
                questions: check['questions'] ?? check['question'] ?? null,
                requires: check['requires'] ?? null,
                compare: check['compare'] ?? null,
                locate: check['locate'] ?? null,
                locate_mode: check['locate_mode'] ?? null,
                applies_to: check['applies_to'] ?? null,
                since: check['since'] ?? null,
                until: check['until'] ?? null,
            });
        }

        return new Catalogue(
            String(data['version'] ?? '0'),
            latest,
            versions,
            // The version moves when somebody remembers. This moves whenever the
            // file does, which is what decides whether two reports compare; the
            // `asked` digest beside it moves only when a call would change.
            digest(contents),
            digest(encodeLikePhp(asked)),
            checks.filter((check) => check.coversJev(latest)),
            checks,
        );
    }

    /**
     * The catalogue for the version this run resolves, which every command needs
     * before it does anything else.
     *
     * The command line pins the version, then the config, then the newest the
     * catalogue covers
     */
    static forRun(flag: string | null, config: Config): Catalogue {
        return Catalogue.load().forJev(
            flag ?? config.jev ?? Catalogue.LATEST,
            flag !== null || config.jev === null ? null : config.source,
        );
    }

    /**
     * The same catalogue narrowed to the rules for one Jev version.
     *
     * A query is sent to one build, and a build has the defects it has. Checking
     * it against a later build's rules reports a defect the run will not hit.
     * `source` is the file a version was pinned in, where one was, so a version
     * this catalogue cannot run names that file and not a flag nobody passed
     */
    forJev(requested: string, source: string | null = null): Catalogue {
        const version = this.resolve(requested, source);

        return new Catalogue(
            this.version,
            version,
            this.versions,
            this.fingerprint,
            this.asked,
            this.writtenChecks.filter((check) => check.coversJev(version)),
            this.writtenChecks,
        );
    }

    /** The version a request names, with `latest` resolved */
    resolve(requested: string, source: string | null = null): string {
        if (requested === Catalogue.LATEST) {
            return this.versions[this.versions.length - 1] ?? '';
        }

        const named = { from: source === null ? 'flag' : 'config', source: source ?? '', requested };
        const kind = source === null ? JevLintError.USAGE : JevLintError.CONFIG;

        if (!VERSION.test(requested)) {
            throw JevLintError.of(kind, Text.of('catalogue.not_a_version', named));
        }

        // Running 1.13's rules against a 1.9 query would report defects nobody
        // measured on 1.9 and miss the ones somebody did.
        if (!this.versions.includes(requested)) {
            throw JevLintError.of(kind, Text.of('catalogue.version_not_covered', {
                ...named,
                versions: this.versions.join(', '),
            }));
        }

        return requested;
    }

    /** How many of the file's checks this version does not carry */
    withheld(): number {
        return this.writtenChecks.length - this.checks.length;
    }

    /**
     * Find a file in `checks/`, whether this package is the repository or is
     * installed inside someone else's node_modules
     */
    static locate(file: string): string {
        const dir = process.env['JEVLINT_CHECKS_DIR'];

        // An override, not a preference. Falling through to the bundled copy ran
        // a CI job against a different check set than the one it had mounted.
        if (typeof dir === 'string' && dir !== '') {
            const named = `${dir.replace(/\/+$/, '')}/${file}`;

            if (!isFile(named)) {
                throw JevLintError.of(JevLintError.NOT_FOUND, Text.of('catalogue.checks_dir_missing_file', { dir, file }));
            }

            return named;
        }

        const candidates = [
            from(import.meta.url, '../../../../checks', file),
            from(import.meta.url, '../../../checks', file),
        ];

        const found = candidates.find(isFile);

        if (found === undefined) {
            throw JevLintError.of(JevLintError.NOT_FOUND, Text.of('catalogue.checks_not_found', { file }));
        }

        return found;
    }

    all(): Check[] {
        return this.checks;
    }

    /** Every check in the file, including the ones this version does not carry */
    written(): Check[] {
        return this.writtenChecks;
    }

    /** A check by id, wherever in the file it is */
    findWritten(id: string): Check | null {
        return this.writtenChecks.find((check) => check.id === id) ?? null;
    }

    static(): Check[] {
        return this.checks.filter((check) => check.isStatic());
    }

    /** Model checks in one scope, applicable to a question of this type */
    modelChecks(scope: string, type: string | null = null): Check[] {
        return this.checks.filter((check) => check.isModel()
            && check.scope === scope
            && (type === null || check.covers(type)));
    }

    find(id: string): Check | null {
        return this.checks.find((check) => check.id === id) ?? null;
    }

    rule(rule: string): Check | null {
        return this.checks.find((check) => check.rule === rule) ?? null;
    }
}

/** The Jev versions the file names, oldest first */
function readVersions(data: Record<string, unknown>, path: string): string[] {
    const declared = data['jev'];
    const versions = Array.isArray(declared)
        ? [...new Set(declared.filter((version): version is string => typeof version === 'string'))]
        : [];

    if (versions.length === 0) {
        throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.no_versions', { path }));
    }

    for (const version of versions) {
        if (!VERSION.test(version)) {
            throw JevLintError.of(JevLintError.CATALOGUE, Text.of('catalogue.version_malformed', { path, version }));
        }
    }

    return [...versions].sort(compareVersions);
}

function digest(contents: string | Buffer): string {
    return createHash('sha256').update(contents).digest('hex').slice(0, 12);
}

function isFile(path: string): boolean {
    return existsSync(path) && statSync(path).isFile();
}

function typeName(value: unknown): string {
    if (value === null) return 'null';
    if (Array.isArray(value)) return 'array';

    return typeof value;
}
