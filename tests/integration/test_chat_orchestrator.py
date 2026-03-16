from __future__ import annotations

from pathlib import Path

from memllm_api.services import ChatOrchestrator
from memllm_api.settings import ApiSettings
from memllm_api.store import InMemoryMetadataStore
from memllm_domain import (
    CharacterRecord,
    ChatRequest,
    MemoryBlockSeed,
    ProviderCallDebug,
    ProviderConfig,
)
from memllm_letta_integration import InMemoryLettaGateway
from memllm_memory_pipeline import MemoryExtractorRegistry
from memllm_reply_providers import ReplyProviderRegistry


class FakeReplyProvider:
    kind = 'ollama_chat'

    def generate(self, config: ProviderConfig, request):  # type: ignore[override]
        del config
        from memllm_domain import ProviderResponse

        message = request.messages[-1].content
        return ProviderResponse(
            provider_kind=self.kind,
            content=f'echo::{message}',
            request_debug=ProviderCallDebug(
                provider_kind=self.kind,
                method='POST',
                url='http://ollama:11434/api/generate',
                payload={'message': message},
                response={'response': f'echo::{message}'},
            ),
        )


class CapturingReplyProvider:
    kind = 'ollama_chat'

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
        description='test',
        system_instructions='test instructions',
        reply_provider=ProviderConfig(
            kind='ollama_chat', base_url='http://localhost:11434', model='qwen3.5:9b'
        ),
        shared_memory_blocks=[
            MemoryBlockSeed(label='style', value='calm and direct')
        ],
        archival_memory_seed=['seed fact'],
        manifest_path=f'{character_id}.yaml',
        manifest_checksum='abc',
        shared_block_ids={'style': f'{character_id}-style'},
    )


def test_sessions_are_isolated_per_user_character_pair() -> None:
    settings = ApiSettings(
        manifest_dir=Path('characters/manifests'),
        database_backend='memory',
        letta_mode='memory',
        memory_extractor_kind='heuristic',
    )
    store = InMemoryMetadataStore()
    for character_id in ('alpha', 'beta'):
        store.upsert_character(_make_character(character_id))

    orchestrator = ChatOrchestrator(
        settings=settings,
        store=store,
        letta_gateway=InMemoryLettaGateway(),
        reply_providers=ReplyProviderRegistry([FakeReplyProvider()]),
        memory_extractors=MemoryExtractorRegistry(),
    )

    response_a, pending_a = orchestrator.prepare_chat(
        ChatRequest(user_id='u1', character_id='alpha', message='hello')
    )
    response_b, pending_b = orchestrator.prepare_chat(
        ChatRequest(user_id='u1', character_id='beta', message='hello')
    )
    response_c, pending_c = orchestrator.prepare_chat(
        ChatRequest(user_id='u2', character_id='alpha', message='hello')
    )

    assert response_a.agent_id != response_b.agent_id
    assert response_a.agent_id != response_c.agent_id

    orchestrator.persist_turn(pending_a)
    orchestrator.persist_turn(pending_b)
    orchestrator.persist_turn(pending_c)

    snapshot_a = orchestrator.get_memory_snapshot(user_id='u1', character_id='alpha')
    snapshot_b = orchestrator.get_memory_snapshot(user_id='u1', character_id='beta')
    snapshot_c = orchestrator.get_memory_snapshot(user_id='u2', character_id='alpha')

    assert snapshot_a.agent_id != snapshot_b.agent_id
    assert snapshot_a.agent_id != snapshot_c.agent_id
    assert any(
        'Recent topic: hello' in block['value']
        for block in [item.model_dump(mode='json') for item in snapshot_a.memory_blocks]
        if block['label'] == 'human'
    )


def test_localhost_ollama_base_url_is_overridden_by_runtime_setting() -> None:
    settings = ApiSettings(
        manifest_dir=Path('characters/manifests'),
        database_backend='memory',
        letta_mode='memory',
        memory_extractor_kind='heuristic',
        reply_provider_ollama_base_url='http://ollama:11434',
    )
    store = InMemoryMetadataStore()
    store.upsert_character(_make_character('alpha'))
    provider = CapturingReplyProvider()

    orchestrator = ChatOrchestrator(
        settings=settings,
        store=store,
        letta_gateway=InMemoryLettaGateway(),
        reply_providers=ReplyProviderRegistry([provider]),
        memory_extractors=MemoryExtractorRegistry(),
    )

    orchestrator.prepare_chat(ChatRequest(user_id='u1', character_id='alpha', message='hello'))

    assert provider.last_config is not None
    assert provider.last_config.base_url == 'http://ollama:11434'


def test_prepare_chat_returns_structured_debug_trace_and_inline_writeback() -> None:
    settings = ApiSettings(
        manifest_dir=Path('characters/manifests'),
        database_backend='memory',
        letta_mode='memory',
        memory_extractor_kind='heuristic',
    )
    store = InMemoryMetadataStore()
    store.upsert_character(_make_character('alpha'))
    orchestrator = ChatOrchestrator(
        settings=settings,
        store=store,
        letta_gateway=InMemoryLettaGateway(),
        reply_providers=ReplyProviderRegistry([FakeReplyProvider()]),
        memory_extractors=MemoryExtractorRegistry(),
    )

    response, pending = orchestrator.prepare_chat(
        ChatRequest(user_id='u1', character_id='alpha', message='hello trace')
    )

    assert response.debug is not None
    assert response.debug.final_provider_call is not None
    assert response.debug.final_provider_call.url == 'http://ollama:11434/api/generate'
    assert response.debug.prompt_pipeline is not None
    assert any(event.kind == 'session_resolution' for event in response.debug.trace_events)
    assert any(event.kind == 'archival_memory_search' for event in response.debug.trace_events)

    persisted = orchestrator.persist_turn(pending, capture_debug=True)
    assert persisted is not None
    assert persisted.memory_writeback.extractor_kind == 'heuristic'
    assert any(event.kind == 'memory_extractor_call' for event in persisted.trace_events)
    assert any(event.kind == 'memory_block_update' for event in persisted.trace_events)
    assert any(event.kind == 'archival_memory_insert' for event in persisted.trace_events)

    sessions = orchestrator.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].character_display_name == 'Alpha'

    deleted = orchestrator.delete_session(user_id='u1', character_id='alpha')
    assert deleted is not None
    assert deleted.agent_id == response.agent_id
    assert orchestrator.list_sessions() == []

    snapshot = orchestrator.get_memory_snapshot(user_id='u1', character_id='alpha')
    assert snapshot.agent_id is None
