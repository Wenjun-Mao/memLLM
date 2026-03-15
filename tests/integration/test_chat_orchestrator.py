from __future__ import annotations

from pathlib import Path

from memllm_api.services import ChatOrchestrator
from memllm_api.settings import ApiSettings
from memllm_api.store import InMemoryMetadataStore
from memllm_domain import CharacterRecord, ChatRequest, ProviderConfig
from memllm_letta_integration import InMemoryLettaGateway
from memllm_memory_pipeline import MemoryExtractorRegistry
from memllm_reply_providers import ReplyProviderRegistry


class FakeReplyProvider:
    kind = "ollama_chat"

    def generate(self, config: ProviderConfig, request):  # type: ignore[override]
        del config
        message = request.messages[-1].content
        from memllm_domain import ProviderResponse

        return ProviderResponse(provider_kind=self.kind, content=f"echo::{message}")


def _make_character(character_id: str) -> CharacterRecord:
    return CharacterRecord(
        character_id=character_id,
        display_name=character_id.title(),
        description="test",
        persona="test persona",
        reply_provider=ProviderConfig(
            kind="ollama_chat", base_url="http://localhost:11434", model="qwen3.5:9b"
        ),
        manifest_path=f"{character_id}.yaml",
        manifest_checksum="abc",
        shared_block_ids={"persona": f"{character_id}-persona"},
    )


def test_sessions_are_isolated_per_user_character_pair() -> None:
    settings = ApiSettings(
        manifest_dir=Path("characters/manifests"),
        database_backend="memory",
        letta_mode="memory",
        memory_extractor_kind="heuristic",
    )
    store = InMemoryMetadataStore()
    for character_id in ("alpha", "beta"):
        store.upsert_character(_make_character(character_id))

    orchestrator = ChatOrchestrator(
        settings=settings,
        store=store,
        letta_gateway=InMemoryLettaGateway(),
        reply_providers=ReplyProviderRegistry([FakeReplyProvider()]),
        memory_extractors=MemoryExtractorRegistry(),
    )

    response_a, pending_a = orchestrator.prepare_chat(
        ChatRequest(user_id="u1", character_id="alpha", message="hello")
    )
    response_b, pending_b = orchestrator.prepare_chat(
        ChatRequest(user_id="u1", character_id="beta", message="hello")
    )
    response_c, pending_c = orchestrator.prepare_chat(
        ChatRequest(user_id="u2", character_id="alpha", message="hello")
    )

    assert response_a.agent_id != response_b.agent_id
    assert response_a.agent_id != response_c.agent_id

    orchestrator.persist_turn(pending_a)
    orchestrator.persist_turn(pending_b)
    orchestrator.persist_turn(pending_c)

    snapshot_a = orchestrator.get_memory_snapshot(user_id="u1", character_id="alpha")
    snapshot_b = orchestrator.get_memory_snapshot(user_id="u1", character_id="beta")
    snapshot_c = orchestrator.get_memory_snapshot(user_id="u2", character_id="alpha")

    assert snapshot_a.agent_id != snapshot_b.agent_id
    assert snapshot_a.agent_id != snapshot_c.agent_id
    assert any(
        "Recent topic: hello" in block.value
        for block in snapshot_a.blocks
        if block.label == "human"
    )
