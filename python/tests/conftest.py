"""Helpers the suite shares: a client that answers from a table instead of calling anything."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest

from jevlint.text import CheckText, Text
from jevlint.typesafe import Client

ROOT = Path(__file__).resolve().parents[2]


class FakeClient:
    """
    A client that answers from a table, so the model path runs in a test without a
    key and without a network.

    The SDK takes a transport, so the whole of it - retries, error mapping, the
    request body - runs exactly as it does against the API.
    """

    def __init__(
        self,
        answers: dict[str, Any] | None = None,
        fallback: float = 0.1,
        fail_with: dict[str, Any] | None = None,
    ) -> None:
        self.answers = answers or {}
        self.fallback = fallback
        self.fail_with = fail_with
        self.calls: list[dict[str, Any]] = []
        self.client = Client(
            api_key='fake-key',
            transport=httpx2.MockTransport(self._handle),
        )

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content or b'{}')
        self.calls.append(body)

        if self.fail_with is not None:
            return httpx2.Response(
                self.fail_with['status'],
                json=self.fail_with.get('body', {'error': 'no'}),
            )

        given: dict[str, Any] = {}

        for name, question in (body.get('questions') or {}).items():
            answer = self.answers.get(name)

            if isinstance(answer, dict):
                given[name] = answer

                continue

            value = self.fallback if answer is None else answer

            if question.get('type') == 'choice':
                labels = list(question.get('criteria') or {})
                pick = labels[0] if labels else ''
                given[name] = {
                    'type': 'choice',
                    'choice': pick,
                    'confidence': value,
                    'probabilities': {label: (value if label == pick else 0) for label in labels},
                }

                continue

            if question.get('type') == 'score':
                given[name] = {
                    'type': 'score',
                    'score': value,
                    'confidence': value,
                    'legend': {},
                    'probabilities': {},
                }

                continue

            given[name] = {'type': 'noul', 'noul': value}

        return httpx2.Response(200, json={
            'model': 'jev-1.13.0',
            'answers': given,
            'usage': {'input_tokens': 10, 'output_tokens': 2},
        })


@pytest.fixture(autouse=True)
def _english() -> Any:
    """Every test starts in English, whatever the one before it asked for."""
    Text.reset()
    CheckText.reset()

    yield

    Text.reset()
    CheckText.reset()
