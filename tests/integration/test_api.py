from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from memllm_api.app import create_app
from memllm_api.settings import ApiSettings
from memllm_domain import ProviderCallDebug, ProviderConfig
from memllm_reply_providers import ReplyProviderRegistry


class FakeReplyProvider:
    kind = "ollama_chat"

    def generate(self, config: ProviderConfig, request):  # type: ignore[override]
        del config
        from memllm_domain import ProviderResponse

        return ProviderResponse(
            provider_kind=self.kind,
            content=f"stub::{request.messages[-1].content}",
            request_debug=ProviderCallDebug(
                provider_kind=self.kind,
                method='POST',
                url='http://ollama:11434/api/generate',
                payload={'model': 'fake', 'message': request.messages[-1].content},
                response={'response': f"stub::{request.messages[-1].content}"},
            ),
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
        chat_payload = chat_response.json()
        assert chat_payload["reply"] == "stub::remember tea"
        assert chat_payload["debug"]["final_request"]["url"] == 'http://ollama:11434/api/generate'
        assert any(
            step["label"] == 'letta_memory_context'
            for step in chat_payload["debug"]["steps"]
        )

        sessions_response = client.get('/sessions')
        assert sessions_response.status_code == 200
        sessions_payload = sessions_response.json()
        assert len(sessions_payload) == 1
        assert sessions_payload[0]["user_id"] == 'dev-user'
        assert sessions_payload[0]["character_id"] == first_character

        memory_response = client.get(f"/memory/dev-user/{first_character}")
        assert memory_response.status_code == 200
        snapshot = memory_response.json()
        assert snapshot["agent_id"] is not None
        assert any(block["label"] == "human" for block in snapshot["blocks"])

        delete_response = client.delete(f'/sessions/dev-user/{first_character}')
        assert delete_response.status_code == 200
        assert delete_response.json()["character_id"] == first_character

        sessions_after_delete = client.get('/sessions')
        assert sessions_after_delete.status_code == 200
        assert sessions_after_delete.json() == []

        memory_after_delete = client.get(f"/memory/dev-user/{first_character}")
        assert memory_after_delete.status_code == 200
        assert memory_after_delete.json()["agent_id"] is None


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
