import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** The repository root, from wherever the compiled tests are run */
export const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..');
