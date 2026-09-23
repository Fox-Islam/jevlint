"""
The SDK client, with what jevlint needs from it that it does not do.

Jev is reachable directly from TypeSafe and through OpenRouter's decisions
endpoint. The bodies are the same on both and the SDK knows one path, so the
provider is a base URL and a path rewrite in the transport.

The answers come back as the payload the API sent and not as the SDK's typed
models, because jevlint reads three fields and reports the rest of a malformed
answer as a check with no reading. A response the SDK would refuse whole is one
this can still take the readings out of.
"""
from __future__ import annotations

import os
from typing import Any

import httpx2
from pydantic import BaseModel, ConfigDict, Field
from typesafe_sdk import TypeSafeClient
from typesafe_sdk.constants import DEFAULT_BASE_URL, DEFAULT_MODEL

from .answers import SystemOneResponse
from .errors import TypeSafeError
from .questions import Question

# The path each provider answers System One on
PATHS = {'typesafe': '/v1/systemone', 'openrouter': '/api/alpha/decisions'}

BASE_URLS = {'typesafe': DEFAULT_BASE_URL, 'openrouter': 'https://openrouter.ai'}


class _Payload(BaseModel):
    """The response body as the API wrote it, before jevlint reads anything out of it."""

    model_config = ConfigDict(extra='allow', protected_namespaces=())

    model: str = ''

    answers: dict[str, Any] = Field(default_factory=dict)

    usage: dict[str, Any] = Field(default_factory=dict)


class _Rewriting(httpx2.BaseTransport):
    """Sends System One to the path the provider answers it on."""

    def __init__(self, inner: httpx2.BaseTransport, path: str) -> None:
        self._inner = inner
        self._path = path

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.path == PATHS['typesafe'] and self._path != PATHS['typesafe']:
            request.url = request.url.copy_with(path=self._path)

        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


class Client:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
        provider: str = 'typesafe',
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        """`transport` swaps the transport, for a test that calls nothing."""
        self._provider = provider
        self._base_url = base_url or _env('TYPESAFE_BASE_URL') or BASE_URLS[provider]
        self._default_model = default_model or _env('TYPESAFE_DEFAULT_MODEL') or DEFAULT_MODEL
        self._sdk = TypeSafeClient(
            api_key=api_key,
            model=self._default_model,
            base_url=self._base_url,
            timeout=timeout,
            transport=_Rewriting(transport or httpx2.HTTPTransport(), PATHS[provider]),
        )

    @staticmethod
    def make(**options: Any) -> Client:
        return Client(**options)

    def system_one(self) -> SystemOne:
        """Answer named questions about text or structured state."""
        return SystemOne(self)

    def get_provider(self) -> str:
        return self._provider

    def get_base_url(self) -> str:
        return self._base_url

    def get_default_model(self) -> str:
        return self._default_model

    def send(self, request: dict[str, Any]) -> SystemOneResponse:
        """Send one call. Reached through SystemOne."""
        payload = self._sdk.system_one(
            request['state'],
            request['questions'],
            model=request['model'],
            response_model=_Payload,
        )

        return SystemOneResponse.from_dict(payload.model_dump())

    def close(self) -> None:
        self._sdk.close()


class SystemOne:
    """Builds and sends a System One call: some state, and the questions to answer about it."""

    def __init__(self, client: Client) -> None:
        self._client = client
        self._state: Any = None
        self._asked: dict[str, Question] = {}
        self._model: str | None = None

    def state(self, state: Any) -> SystemOne:
        """What the questions are about: text, or a JSON-ready value."""
        self._state = state

        return self

    def ask(self, name: str, question: Question) -> SystemOne:
        """Ask one question, keyed by the name its answer will come back under."""
        self._asked[name] = question

        return self

    def model(self, model: str) -> SystemOne:
        """Override the model for this call only."""
        self._model = model

        return self

    def to_dict(self) -> dict[str, Any]:
        """The request body as it will be sent, with the model resolved."""
        self._validate()

        return {
            'state': self._state,
            'model': self._model or self._client.get_default_model(),
            'questions': {name: question.to_json() for name, question in self._asked.items()},
        }

    def send(self) -> SystemOneResponse:
        return self._client.send(self.to_dict())

    def _validate(self) -> None:
        if len(self._asked) == 0:
            raise TypeSafeError('At least one question is required.')

        for name, question in self._asked.items():
            question.validate(name)


def _env(name: str) -> str | None:
    value = os.environ.get(name, '').strip()

    return value or None
