from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from memllm_api.app import create_app
from memllm_api.settings import ApiSettings
from memllm_domain import ProviderConfig
from memllm_reply_providers import ReplyProviderRegistry


class FakeReplyProvider:
    kind = "ollama_chat"

    def generate(self, config: ProviderConfig, request):  # type: ignore[override]
        del config
        from memllm_domain import ProviderResponse

        return ProviderResponse(
            provider_kind=self.kind, content=f"stub::{request.messages[-1].content}"
        )


def test_seed_chat_and_memory_flow() -> None:
    settings = ApiSettings(
        manifest_dir=Path("characters/manifests"),
        database_backend="memory",
        letta_mode="memory",
        memory_extractor_kind="heuristic",
    )
    app = create_app(settings)
    app.state.container.orchestrator._reply_providers = ReplyProviderRegistry([FakeReplyProvider()])  # noqa: SLF001

    with TestClient(app) as client:
        seed_response = client.post("/seed/characters")
        assert seed_response.status_code == 200
        assert len(seed_response.json()["seeded"]) >= 2

        characters_response = client.get("/characters")
        assert characters_response.status_code == 200
        first_character = characters_response.json()[0]["character_id"]

        chat_response = client.post(
            "/chat",
            json={
                "user_id": "dev-user",
                "character_id": first_character,
                "message": "remember tea",
            },
        )
        assert chat_response.status_code == 200
        assert chat_response.json()["reply"] == "stub::remember tea"

        memory_response = client.get(f"/memory/dev-user/{first_character}")
        assert memory_response.status_code == 200
        snapshot = memory_response.json()
        assert snapshot["agent_id"] is not None
        assert any(block["label"] == "human" for block in snapshot["blocks"])


class _FakeJsonResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.headers = {'content-type': 'application/json'}

    def json(self) -> object:
        return self._payload


def test_parse_simple_payload_extracts_nested_data_content() -> None:
    from memllm_reply_providers.providers import _parse_simple_payload

    payload = {
        'status': 1001,
        'info': 'success!',
        'data': [
            {
                'content': 'Greetings. The air carries a faint frost.',
                'role': 'assistant',
            }
        ],
    }

    content, raw_payload = _parse_simple_payload(_FakeJsonResponse(payload))

    assert content == 'Greetings. The air carries a faint frost.'
    assert raw_payload == payload


class _FakeTextResponse:
    def __init__(self, text: str, content_type: str = 'text/plain') -> None:
        self.text = text
        self.headers = {'content-type': content_type}

    def json(self) -> object:
        raise AssertionError('json() should not be used for text/plain response in this test')


def test_parse_simple_payload_extracts_nested_content_from_json_text() -> None:
    from memllm_reply_providers.providers import _parse_simple_payload

    payload = {
        'status': 1001,
        'info': 'success!',
        'data': {
            'content': 'The snow has settled since we last spoke.',
            'role': 'assistant',
        },
    }

    content, raw_payload = _parse_simple_payload(
        _FakeTextResponse(json.dumps(payload, ensure_ascii=False))
    )

    assert content == 'The snow has settled since we last spoke.'
    assert raw_payload == payload


def test_parse_simple_payload_extracts_nested_content_from_double_encoded_json_text() -> None:
    from memllm_reply_providers.providers import _parse_simple_payload

    payload = {
        'status': 1001,
        'info': 'success!',
        'data': {
            'content': 'Again, the snowfall pauses.',
            'role': 'assistant',
        },
    }

    content, raw_payload = _parse_simple_payload(
        _FakeTextResponse(json.dumps(json.dumps(payload, ensure_ascii=False), ensure_ascii=False))
    )

    assert content == 'Again, the snowfall pauses.'
    assert raw_payload == json.dumps(payload, ensure_ascii=False)
