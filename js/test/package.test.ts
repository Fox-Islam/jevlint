import { strict as assert } from 'node:assert';
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it } from 'node:test';
import { Application } from '../src/console/application.js';
import { root } from './helpers/root.js';
import { sources } from './helpers/sources.js';

const manifest = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')) as Record<string, unknown>;

/**
 * `jevlint --version` printed 0.1.0 from a tag that said 1.0.0, because nothing
 * read both. A report carries this number, so a run checked by one build and
 * reported as another is the thing it makes untraceable
 */
describe('the version the tool prints', () => {
    it('is the version the package publishes', () => {
        assert.equal(Application.VERSION, manifest['version']);
    });

    it('is not behind the newest release tag', () => {
        if (!existsSync(join(root, '.git'))) {
            // A published tarball has no tags to read. Nothing to compare.
            return;
        }

        let tags: string[];

        try {
            tags = execFileSync('git', ['-C', root, 'tag', '--sort=-v:refname'], { encoding: 'utf8' })
                .split('\n')
                .filter((tag) => /^v?\d+\.\d+\.\d+$/.test(tag));
        } catch {
            return;
        }

        if (tags.length === 0) {
            return;
        }

        const newest = (tags[0] ?? '').replace(/^v/, '');
        const order = (version: string): number[] => version.split('.').map(Number);
        const [a, b] = [order(Application.VERSION), order(newest)];

        // Ahead is fine: the constant is bumped, then the tag is cut. Behind
        // means a release went out printing an older number than it is.
        const behind = a.some((part, i) => part !== (b[i] ?? 0) && part < (b[i] ?? 0)
            && a.slice(0, i).every((earlier, j) => earlier === (b[j] ?? 0)));

        assert.equal(behind, false, `jevlint --version prints ${Application.VERSION}, behind the tag ${tags[0] ?? ''}.`);
    });
});

/**
 * A package that installs what it does not name works on the machine it was
 * built on and fails on the next one
 */
describe('what the package depends on', () => {
    it('names the SDK and nothing else', () => {
        assert.deepEqual(Object.keys(manifest['dependencies'] ?? {}), ['@typesafe-ai/sdk']);
    });

    it('imports nothing it does not name', () => {
        const declared = new Set(Object.keys(manifest['dependencies'] ?? {}));
        const undeclared = new Set<string>();

        for (const { contents } of sources()) {
            for (const match of contents.matchAll(/from '([^'.][^']*)'/g)) {
                const specifier = match[1] ?? '';

                if (specifier.startsWith('node:')) {
                    continue;
                }

                const name = specifier.startsWith('@')
                    ? specifier.split('/').slice(0, 2).join('/')
                    : specifier.split('/')[0] ?? '';

                if (!declared.has(name)) {
                    undeclared.add(name);
                }
            }
        }

        assert.deepEqual([...undeclared], []);
    });

    it('ships the catalogue, which is not JavaScript and is read by every implementation', () => {
        const files = (manifest['files'] ?? []) as string[];

        assert.ok(files.includes('checks'), 'A published package with no catalogue checks nothing.');
        assert.ok(files.includes('spec'));
        assert.ok(files.some((path) => path.startsWith('js/dist')));
    });

    it('points its bin at a file the build produces', () => {
        const bin = (manifest['bin'] ?? {}) as Record<string, string>;

        assert.deepEqual(Object.keys(bin), ['jevlint']);
        assert.ok(existsSync(join(root, bin['jevlint'] ?? '')), 'Run the build before the tests.');
    });

    /**
     * Node reads its own `--env-file` wherever it appears on the command line
     * and exits before this runs, so the shebang ends its option scanning
     */
    it('keeps Node out of the option list', () => {
        const bin = readFileSync(join(root, 'js/bin/jevlint.ts'), 'utf8');

        assert.ok(bin.startsWith('#!/usr/bin/env -S node --\n'));
    });
});
