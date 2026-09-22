import { entriesOf, ordered } from '../support/ordered.js';

/**
 * A change to the query file that a program can apply without reading it.
 *
 * Only a defect that is purely a shape gets one: turning a Choice's criteria
 * from a list into a map is a data transform, while rewriting a question is a
 * judgement about a subject the linter has not seen
 */
export class Patch {
    /** Nothing the author wrote is lost, so a loop can apply it unattended */
    static readonly LOSSLESS = 'lossless';

    /** It keeps the content and drops something around it, so read it first */
    static readonly LOSSY = 'lossy';

    /** It takes something out of the query, so a person decides */
    static readonly DESTRUCTIVE = 'destructive';

    public readonly safety: string;

    constructor(
        public readonly op: 'replace' | 'add' | 'remove',
        public readonly path: string,
        public readonly value: unknown = null,
        safety: string = Patch.LOSSLESS,
    ) {
        // Taking a node out is destructive whatever the caller passed, so the
        // classification a fixer gates on cannot be wrong by omission.
        this.safety = op === 'remove' ? Patch.DESTRUCTIVE : safety;
    }

    toObject(): Record<string, unknown> {
        // What kind of change this is, as a field. `suggest_kind: "patch"` only
        // restates that a patch exists, so a loop applying patches unattended had
        // no way to tell a key rename from deleting somebody's question.
        const row: Record<string, unknown> = { op: this.op, path: this.path, safety: this.safety };

        return this.op === 'remove' ? row : { ...row, value: this.value };
    }

    /**
     * Apply this to a decoded query, so a caller can act on it and re-check.
     *
     * Objects stay objects: `questions` and `criteria` are keyed by names the
     * caller chose, and a decoder that turns counting keys into a list would
     * write them back as a JSON array the API rejects
     */
    applyTo(query: Record<string, unknown>): Record<string, unknown> {
        const parts = this.path.split('/').slice(1).map((part) => part.replace(/~1/g, '/').replace(/~0/g, '~'));
        const applied = this.at(query, parts);

        return typeof applied === 'object' && applied !== null && !Array.isArray(applied)
            ? applied as Record<string, unknown>
            : query;
    }

    private at(node: unknown, parts: string[]): unknown {
        if (typeof node !== 'object' || node === null) {
            return node;
        }

        const part = parts[0] ?? '';

        if (Array.isArray(node)) {
            const copy = [...node];
            const index = Number(part);

            if (!Number.isInteger(index) || index < 0 || index >= copy.length) {
                return node;
            }

            if (parts.length === 1) {
                if (this.op === 'remove') {
                    copy.splice(index, 1);
                } else {
                    copy[index] = this.value;
                }

                return copy;
            }

            copy[index] = this.at(copy[index], parts.slice(1));

            return copy;
        }

        const map = ordered(entriesOf(node));

        if (parts.length === 1) {
            if (this.op === 'remove') {
                delete map[part];
            } else {
                map[part] = this.value;
            }

            return map;
        }

        const child = map[part];

        if (typeof child !== 'object' || child === null) {
            // Creating the path is right for `add`, which is putting something
            // where nothing is. For `remove` there is nothing to delete from.
            if (this.op === 'remove') {
                return node;
            }

            map[part] = {};
        }

        map[part] = this.at(map[part], parts.slice(1));

        return map;
    }
}
