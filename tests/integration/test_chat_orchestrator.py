from __future__ import annotations

from pathlib import Path

from memllm_api.services import ChatOrchestrator
from memllm_api.settings import ApiSettings
from memllm_api.store import InMemoryMetadataStore
from memllm_domain import CharacterRecord, ChatRequest, ProviderCallDebug, ProviderConfig
from memllm_letta_integration import InMemoryLettaGateway
from memllm_memory_pipeline import MemoryExtractorRegistry
from memllm_reply_providers import ReplyProviderRegistry


class FakeReplyProvider:
    kind = "ollama_chat"

    def generate(self, config: ProviderConfig, request):  # type: ignore[override]
        del config
        message = request.messages[-1].content
        from memllm_domain import ProviderResponse

        return ProviderResponse(
            provider_kind=self.kind,
            content=f"echo::{message}",
            request_debug=ProviderCallDebug(
                provider_kind=self.kind,
                method='POST',
                url='http://ollama:11434/api/generate',
                payload={'message': message},
                response={'response': f"echo::{message}"},
            ),
        )


class CapturingReplyProvider:
    kind = "ollama_chat"

    def __init__(self) -> None:
        self.last_config: ProviderConfig | None = None

    def generate(self, config: ProviderConfig, request):  # type: ignore[override]
        del request
        self.last_config = config
        from memllm_domain import ProviderResponse

        return ProviderResponse(
            provider_kind=self.kind,
            content='ok',
            request_debug=ProviderCallDebug(
                provider_kind=self.kind,
                method='POST',
                url='http://ollama:11434/api/generate',
                payload={'ok': True},
                response={'response': 'ok'},
            ),
        )


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


def test_localhost_ollama_base_url_is_overridden_by_runtime_setting() -> None:
    settings = ApiSettings(
        manifest_dir=Path("characters/manifests"),
        database_backend="memory",
        letta_mode="memory",
        memory_extractor_kind="heuristic",
        reply_provider_ollama_base_url="http://ollama:11434",
    )
    store = InMemoryMetadataStore()
    store.upsert_character(_make_character("alpha"))
    provider = CapturingReplyProvider()

    orchestrator = ChatOrchestrator(
        settings=settings,
        store=store,
        letta_gateway=InMemoryLettaGateway(),
        reply_providers=ReplyProviderRegistry([provider]),
        memory_extractors=MemoryExtractorRegistry(),
    )

    orchestrator.prepare_chat(
        ChatRequest(user_id="u1", character_id="alpha", message="hello")
    )

    assert provider.last_config is not None
    assert provider.last_config.base_url == "http://ollama:11434"


def test_prepare_chat_returns_debug_trace_and_session_management() -> None:
    settings = ApiSettings(
        manifest_dir=Path("characters/manifests"),
        database_backend="memory",
        letta_mode="memory",
        memory_extractor_kind="heuristic",
    )
    store = InMemoryMetadataStore()
    store.upsert_character(_make_character("alpha"))
    orchestrator = ChatOrchestrator(
        settings=settings,
        store=store,
        letta_gateway=InMemoryLettaGateway(),
        reply_providers=ReplyProviderRegistry([FakeReplyProvider()]),
        memory_extractors=MemoryExtractorRegistry(),
    )

    response, pending = orchestrator.prepare_chat(
        ChatRequest(user_id="u1", character_id="alpha", message="hello trace")
    )

    assert response.debug is not None
    assert response.debug.final_request is not None
    assert response.debug.final_request.url == 'http://ollama:11434/api/generate'
    assert any(step.label == 'session_resolution' for step in response.debug.steps)
    assert any(step.label == 'letta_memory_context' for step in response.debug.steps)

    orchestrator.persist_turn(pending)
    sessions = orchestrator.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].character_display_name == 'Alpha'

    deleted = orchestrator.delete_session(user_id='u1', character_id='alpha')
    assert deleted is not None
    assert deleted.agent_id == response.agent_id
    assert orchestrator.list_sessions() == []

    snapshot = orchestrator.get_memory_snapshot(user_id='u1', character_id='alpha')
    assert snapshot.agent_id is None
