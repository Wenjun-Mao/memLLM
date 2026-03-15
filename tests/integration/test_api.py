from __future__ import annotations

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
