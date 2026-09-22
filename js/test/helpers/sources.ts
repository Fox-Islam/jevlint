import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { root } from './root.js';

/** Every shipped source file, for the sweeps that read the source itself */
export function sources(): { path: string; contents: string }[] {
    const found: { path: string; contents: string }[] = [];

    const walk = (dir: string): void => {
        for (const entry of readdirSync(dir)) {
            const path = join(dir, entry);

            if (statSync(path).isDirectory()) {
                walk(path);

                continue;
            }

            if (path.endsWith('.ts') && !path.endsWith('.d.ts')) {
                found.push({ path, contents: readFileSync(path, 'utf8') });
            }
        }
    };

    walk(join(root, 'js/src'));

    if (found.length === 0) {
        throw new Error('No source files found, so this sweep pins nothing.');
    }

    return found;
}
