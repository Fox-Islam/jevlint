import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

/**
 * The directory this module was loaded from.
 *
 * The package ships compiled, so a path written from the source tree addresses
 * nothing once it is installed. Every lookup starts here instead
 */
export function here(url: string): string {
    return dirname(fileURLToPath(url));
}

export function from(url: string, ...parts: string[]): string {
    return resolve(here(url), ...parts);
}
