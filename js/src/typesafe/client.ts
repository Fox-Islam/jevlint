import { TypeSafeClient, TypeSafeError, type EntryType, type Fetch, type Questions } from '@typesafe-ai/sdk';
import { ordered, stringify } from '../support/ordered.js';
import { SystemOneResponse } from './answers.js';
import type { Content, Question } from './questions.js';

/** Where System One calls are sent */
export type Provider = 'typesafe' | 'openrouter';

export interface ClientOptions {
    apiKey?: string | undefined;
    baseUrl?: string | undefined;
    defaultModel?: string | undefined;
    /** Seconds per attempt, as the command line writes one */
    timeout?: number | undefined;
    provider?: Provider | undefined;
    /** Swap the transport, for a test that calls nothing */
    fetch?: Fetch | undefined;
}

/** The path each provider answers System One on */
const PATHS: Record<Provider, string> = {
    typesafe: '/v1/systemone',
    openrouter: '/api/alpha/decisions',
};

const BASE_URLS: Record<Provider, string> = {
    typesafe: 'https://api.typesafe.ai',
    openrouter: 'https://openrouter.ai',
};

/** Marks a request whose body this rebuilt, so the transport can find it again */
const BODY_HEADER = 'x-jevlint-body';

/**
 * The SDK client, with what jevlint needs from it that it does not do.
 *
 * Jev is reachable directly from TypeSafe and through OpenRouter's decisions
 * endpoint. The bodies are the same on both and the SDK knows one path, so the
 * provider is a base URL and a path rewrite in the transport.
 *
 * The request body is rewritten there too. A Choice keyed `{"30": ..., "7":
 * ...}` is written by `JSON.stringify` the other way round, because a
 * JavaScript object lists a key that looks like an array index first and in
 * ascending order. Option order changes answers, so the body that goes out is
 * this package's own rendering of the request it built
 */
export class Client {
    private readonly sdk: TypeSafeClient;

    /** Bodies this rebuilt, by the id the request carries */
    private readonly bodies = new Map<string, string>();

    private sent = 0;

    constructor(private readonly options: ClientOptions = {}) {
        const provider = options.provider ?? 'typesafe';
        const path = PATHS[provider];
        const transport = options.fetch ?? ((input: string, init?: RequestInit) => fetch(input, init));

        this.sdk = new TypeSafeClient({
            ...(options.apiKey === undefined ? {} : { apiKey: options.apiKey }),
            ...(options.defaultModel === undefined ? {} : { defaultModel: options.defaultModel }),
            baseURL: options.baseUrl ?? env('TYPESAFE_BASE_URL') ?? BASE_URLS[provider],
            ...(options.timeout === undefined ? {} : { timeout: Math.round(options.timeout * 1000) }),
            fetch: (input, init) => {
                const headers = new Headers(init?.headers);
                const id = headers.get(BODY_HEADER);
                const body = id === null ? null : this.bodies.get(id) ?? null;

                if (id !== null) {
                    headers.delete(BODY_HEADER);
                }

                return transport(
                    provider === 'typesafe' ? input : input.replace(PATHS.typesafe, path),
                    { ...init, headers, ...(body === null ? {} : { body }) },
                );
            },
        });
    }

    static make(options: ClientOptions = {}): Client {
        return new Client(options);
    }

    /** Answer named questions about text or structured state */
    systemOne(): SystemOne {
        return new SystemOne(this);
    }

    getProvider(): Provider {
        return this.options.provider ?? 'typesafe';
    }

    getBaseUrl(): string {
        return this.sdk.baseURL;
    }

    getDefaultModel(): string {
        return this.sdk.defaultModel;
    }

    /**
     * Send one call, with the body written in the order the request was built.
     *
     * @internal Reached through {@link SystemOne}.
     */
    async send(request: Record<string, unknown>): Promise<SystemOneResponse> {
        const id = String(++this.sent);
        this.bodies.set(id, stringify(request));

        try {
            // The request was built from a file, so its state is whatever
            // JSON holds; the SDK types it as its own JSON value.
            const result = await this.sdk.systemOne(
                request as unknown as { state: EntryType; questions: Questions },
                { headers: { [BODY_HEADER]: id } },
            );

            return SystemOneResponse.fromObject(result as unknown as Record<string, unknown>);
        } finally {
            this.bodies.delete(id);
        }
    }
}

/**
 * Builds and sends a System One call: some state, and the questions to answer
 * about it
 */
export class SystemOne {
    private stateValue: Content = null;

    private readonly asked = new Map<string, Question>();

    private modelValue: string | null = null;

    constructor(private readonly client: Client) {}

    /** What the questions are about: text, or a JSON-ready value */
    state(state: Content): this {
        this.stateValue = state;

        return this;
    }

    /** Ask one question, keyed by the name its answer will come back under */
    ask(name: string, question: Question): this {
        this.asked.set(name, question);

        return this;
    }

    /** Override the model for this call only */
    model(model: string): this {
        this.modelValue = model;

        return this;
    }

    /** The request body as it will be sent, with the model resolved */
    toObject(): Record<string, unknown> {
        this.validate();

        return {
            state: this.stateValue,
            model: this.modelValue ?? this.client.getDefaultModel(),
            questions: ordered([...this.asked].map(([name, question]) => [name, question.toJSON()])),
        };
    }

    async send(): Promise<SystemOneResponse> {
        return this.client.send(this.toObject());
    }

    private validate(): void {
        if (this.asked.size === 0) {
            throw new TypeSafeError('At least one question is required.');
        }

        for (const [name, question] of this.asked) {
            question.validate(name);
        }
    }
}

function env(name: string): string | null {
    const value = process.env[name];

    if (typeof value !== 'string') {
        return null;
    }

    return value.trim() === '' ? null : value.trim();
}
