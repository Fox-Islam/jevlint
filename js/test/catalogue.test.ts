import { strict as assert } from 'node:assert';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, it } from 'node:test';
import { Catalogue } from '../src/catalogue/catalogue.js';
import { compareVersions } from '../src/catalogue/check.js';
import { JevLintError } from '../src/exceptions/jevLintError.js';
import { Json } from '../src/support/json.js';
import { stringify } from '../src/support/ordered.js';

const catalogue = Catalogue.load();

/** The same file with one thing wrong with it, written somewhere temporary */
function damaged(change: (data: Record<string, unknown>) => void): string {
    const data = Json.readFile(Catalogue.locate('catalogue.json'));
    change(data);
    const path = join(mkdtempSync(join(tmpdir(), 'jevlint-')), 'catalogue.json');
    writeFileSync(path, stringify(data, 4));

    return path;
}

function checks(data: Record<string, unknown>): Record<string, unknown>[] {
    return data['checks'] as Record<string, unknown>[];
}

describe('the catalogue', () => {
    it('loads the shipped file', () => {
        assert.ok(catalogue.all().length > 0);
        assert.equal(catalogue.fingerprint.length, 12);
        assert.equal(catalogue.asked.length, 12);
        assert.equal(catalogue.model, `jev-${catalogue.jev}`);
    });

    it('orders Jev versions by number and not by text', () => {
        assert.equal(compareVersions('1.9', '1.13') < 0, true);
        assert.equal(compareVersions('1.13', '1.13'), 0);
        assert.equal(compareVersions('2', '1.99') > 0, true);
    });

    it('refuses a version it holds no rules for', () => {
        assert.throws(() => catalogue.forJev('9.9'), (error: JevLintError) => error.kind === 'usage');
        assert.throws(() => catalogue.forJev('latest-ish'), (error: JevLintError) => error.kind === 'usage');
        assert.equal(catalogue.forJev('latest').jev, catalogue.jev);
    });
});

/**
 * Each of these loaded without complaint at some point and produced a report
 * that read like a clean one
 */
describe('a catalogue with something wrong with it', () => {
    const refuses = (name: string, change: (data: Record<string, unknown>) => void): void => {
        it(name, () => {
            assert.throws(
                () => Catalogue.load(damaged(change)),
                (error: JevLintError) => error.kind === 'catalogue' || error.kind === 'not-found',
                name,
            );
        });
    };

    refuses('two checks under one id', (data) => {
        const first = checks(data)[0] as Record<string, unknown>;
        checks(data).push({ ...first });
    });

    refuses('a static check naming a rule no code raises', (data) => {
        const found = checks(data).find((check) => check['mode'] === 'static');
        if (found) found['rule'] = 'nothing.raisesThis';
    });

    refuses('two static checks naming one rule', (data) => {
        const statics = checks(data).filter((check) => check['mode'] === 'static');
        if (statics[1] && statics[0]) statics[1]['rule'] = statics[0]['rule'];
    });

    refuses('a model check carrying no question', (data) => {
        const found = checks(data).find((check) => check['mode'] === 'model');
        if (found) {
            delete found['question'];
            delete found['questions'];
        }
    });

    refuses('a model check with no trigger', (data) => {
        const found = checks(data).find((check) => check['mode'] === 'model');
        if (found) delete found['trigger'];
    });

    refuses('a trigger that would fire on everything', (data) => {
        const found = checks(data).find((check) => check['mode'] === 'model');
        if (found) found['trigger'] = 0.05;
    });

    refuses('a severity the report does not know', (data) => {
        const first = checks(data)[0];
        if (first) first['severity'] = 'critical';
    });

    refuses('a scope nothing asks', (data) => {
        const first = checks(data)[0];
        if (first) first['scope'] = 'somewhere';
    });

    refuses('a primitive Jev does not answer', (data) => {
        const first = checks(data)[0];
        if (first) first['applies_to'] = ['rating'];
    });

    refuses('a `reads` that addresses no part of a query', (data) => {
        const first = checks(data)[0];
        if (first) first['reads'] = 'somewhere';
    });

    refuses('a `supersedes` naming nothing', (data) => {
        const first = checks(data)[0];
        if (first) first['supersedes'] = ['nope/nope'];
    });

    refuses('a version span that covers nothing', (data) => {
        const first = checks(data)[0];
        if (first) {
            first['since'] = '2.0';
            first['until'] = '1.0';
        }
    });

    refuses('a check written for no version the file covers', (data) => {
        const first = checks(data)[0];
        if (first) first['since'] = '99.0';
    });

    refuses('a file naming no Jev version', (data) => {
        delete data['jev'];
    });

    refuses('a file with no checks', (data) => {
        data['checks'] = [];
    });

    refuses('a check that is not an object', (data) => {
        checks(data).push(null as unknown as Record<string, unknown>);
    });

    refuses('a suppression nothing tests', (data) => {
        const found = checks(data).find((check) => check['mode'] === 'model');
        if (found) found['suppress'] = [{ answer: 'noul', when: 'the_moon_is_full' }];
    });

    refuses('two model checks whose ids collapse onto one answer key', (data) => {
        const models = checks(data).filter((check) => check['mode'] === 'model');
        const first = models[0];
        const second = models[1];

        if (first && second) {
            first['id'] = 'a/b-c';
            second['id'] = 'a-b/c';
        }
    });
});

/**
 * The corpus keeps its readings against the `asked` digest and treats them as
 * still good while it does not move. A reworded message must not move it, and a
 * changed question must
 */
describe('the digest over what the checks ask', () => {
    it('does not move when a message is reworded', () => {
        const path = damaged((data) => {
            const found = checks(data).find((check) => check['mode'] === 'model');
            if (found) found['message'] = 'Something else entirely.';
        });

        assert.equal(Catalogue.load(path).asked, catalogue.asked);
        assert.notEqual(Catalogue.load(path).fingerprint, catalogue.fingerprint);
    });

    it('moves when a check asks something else', () => {
        const path = damaged((data) => {
            const found = checks(data).find((check) => check['mode'] === 'model');
            const question = found?.['question'] as Record<string, unknown> | undefined;
            if (question) question['instructions'] = 'Something else entirely?';
        });

        assert.notEqual(Catalogue.load(path).asked, catalogue.asked);
    });

    it('moves when a trigger moves', () => {
        const path = damaged((data) => {
            const found = checks(data).find((check) => check['mode'] === 'model');
            if (found) found['trigger'] = 0.55;
        });

        assert.notEqual(Catalogue.load(path).asked, catalogue.asked);
    });
});
