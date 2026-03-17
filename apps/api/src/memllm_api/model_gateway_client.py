from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx


class ModelGatewayDebugClient:
    def __init__(self, *, base_url: str, timeout_seconds: float = 15.0) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip('/'), timeout=timeout_seconds)

    def latest_sequence(self) -> int:
        response = self._client.get('/debug/sequence')
        response.raise_for_status()
        return int(response.json()['latest_sequence'])

    def list_traces(self, *, since_sequence: int, limit: int) -> list[dict[str, Any]]:
        response = self._client.get(
            '/debug/traces',
            params={'since_sequence': since_sequence, 'limit': limit},
        )
        response.raise_for_status()
        payload = response.json()
        return list(payload.get('traces', []))


class InMemoryModelGatewayDebugClient:
    def __init__(self) -> None:
        self._sequence = 0
        self._traces: list[dict[str, Any]] = []

    def latest_sequence(self) -> int:
        return self._sequence

    def list_traces(self, *, since_sequence: int, limit: int) -> list[dict[str, Any]]:
        return [item for item in self._traces if item['sequence'] > since_sequence][-limit:]

    def record(self, trace: dict[str, Any]) -> None:
        self._sequence += 1
        item = {'sequence': self._sequence, 'created_at': datetime.now(UTC).isoformat(), **trace}
        self._traces.append(item)
