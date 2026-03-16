from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from loguru import logger
from memllm_domain import (
    CharacterNotFoundError,
    CharacterRecord,
    ChatDebugTrace,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatTurn,
    MemoryBlock,
    MemoryContext,
    MemoryDelta,
    MemorySnapshot,
    MemoryWritebackDebug,
    PromptPipelineDebug,
    ProviderConfig,
    ReplyRequest,
    SeedReport,
    SeedReportItem,
    SessionRecord,
    SessionSummary,
    TraceEvent,
    WorkingContextDebug,
)
from memllm_letta_integration import LettaEmbeddingConfig, LettaGateway, LettaLLMConfig
from memllm_memory_pipeline import MemoryExtractorRegistry
from memllm_reply_providers import ReplyProviderRegistry

from memllm_api.manifests import CharacterManifestLoader
from memllm_api.settings import ApiSettings
from memllm_api.store import MetadataStore

TRACE_EVENT_SPECS = {
    'session_resolution': {
        'title': 'Session Resolution',
        'description': 'Create or reuse the Letta agent for this exact user and character pair.',
        'paper_mapping': 'Agent lifecycle before working context is assembled.',
    },
    'memory_blocks_read': {
        'title': 'Memory Blocks Read',
        'description': 'Read the current Letta memory blocks that make up the working context.',
        'paper_mapping': 'Working Context.',
    },
    'archival_memory_search': {
        'title': 'Archival Memory Search',
        'description': 'Retrieve the archival memory items Letta returns for this turn.',
        'paper_mapping': 'Archival Memory.',
    },
    'conversation_window_load': {
        'title': 'Conversation Window Load',
        'description': (
            'Load the recent conversation window that will be included in the '
            'final call.'
        ),
        'paper_mapping': 'FIFO Queue analogue.',
    },
    'final_prompt_assembly': {
        'title': 'Final Prompt Assembly',
        'description': (
            'Assemble system instructions, working context, conversation window, '
            'and retrieved archival memory for the final provider call.'
        ),
        'paper_mapping': 'System Instructions + Working Context + FIFO-style conversation window.',
    },
    'final_provider_call': {
        'title': 'Final Provider Call',
        'description': 'Send the final user-facing request to DouBao or local Ollama.',
        'paper_mapping': 'Final reply generation step in this app-specific pipeline.',
    },
    'memory_extractor_call': {
        'title': 'Local Memory Extractor',
        'description': 'Run the local post-turn memory extractor that prepares Letta writebacks.',
        'paper_mapping': 'App-managed memory processing after the final reply.',
    },
    'memory_block_update': {
        'title': 'Memory Block Update',
        'description': 'Update the pair-specific Letta user memory block.',
        'paper_mapping': 'Working Context update.',
    },
    'archival_memory_insert': {
        'title': 'Archival Memory Insert',
        'description': 'Insert durable snippets into Letta archival memory.',
        'paper_mapping': 'Archival Memory write.',
    },
}


@dataclass
class PendingMemoryWrite:
    character: CharacterRecord
    session: SessionRecord
    memory_context: MemoryContext
    user_message: str
    assistant_message: str


@dataclass
class PersistedTurnDebug:
    memory_writeback: MemoryWritebackDebug
    trace_events: list[TraceEvent]


class CharacterSeeder:
    def __init__(
        self,
        *,
        loader: CharacterManifestLoader,
        store: MetadataStore,
        letta_gateway: LettaGateway,
    ) -> None:
        self._loader = loader
        self._store = store
        self._letta_gateway = letta_gateway

    def seed_all(self) -> SeedReport:
        items: list[SeedReportItem] = []
        for record in self._loader.load_all():
            existing = self._store.get_character(record.character_id)
            shared_block_ids = self._letta_gateway.upsert_shared_memory_blocks(
                blocks=record.seed_shared_memory_blocks(),
                existing_block_ids=existing.shared_block_ids if existing else None,
            )
            upserted, created = self._store.upsert_character(
                record.model_copy(update={'shared_block_ids': shared_block_ids})
            )
            items.append(
                SeedReportItem(
                    character_id=upserted.character_id,
                    display_name=upserted.display_name,
                    created=created,
                    shared_block_ids=upserted.shared_block_ids,
                )
            )
            logger.info('Seeded character {}', upserted.character_id)
        return SeedReport(seeded=items)


_AGENT_NAME_UNSAFE_RE = re.compile(r"[^\w\s\-']+", flags=re.UNICODE)


def build_agent_name(*, character_id: str, user_id: str) -> str:
    raw_name = f'{character_id}__{user_id}'
    sanitized = _AGENT_NAME_UNSAFE_RE.sub('_', raw_name)
    sanitized = re.sub(r'_+', '_', sanitized).strip(' _')
    return sanitized or 'memllm-agent'


def _event(kind: str, *, request: object = None, response: object = None) -> TraceEvent:
    spec = TRACE_EVENT_SPECS[kind]
    return TraceEvent(
        kind=kind,
        title=spec['title'],
        description=spec['description'],
        paper_mapping=spec['paper_mapping'],
        request=request,
        response=response,
    )


def _model_dump_list(items: list[object]) -> list[object]:
    result: list[object] = []
    for item in items:
        if hasattr(item, 'model_dump'):
            result.append(item.model_dump(mode='json'))
        else:
            result.append(item)
    return result


def _split_working_context(memory_context: MemoryContext) -> WorkingContextDebug:
    shared_memory_blocks: list[MemoryBlock] = []
    user_memory_blocks: list[MemoryBlock] = []
    for block in memory_context.memory_blocks:
        if block.scope == 'shared':
            shared_memory_blocks.append(block)
        else:
            user_memory_blocks.append(block)
    return WorkingContextDebug(
        shared_memory_blocks=shared_memory_blocks,
        user_memory_blocks=user_memory_blocks,
    )


class ChatOrchestrator:
    def __init__(
        self,
        *,
        settings: ApiSettings,
        store: MetadataStore,
        letta_gateway: LettaGateway,
        reply_providers: ReplyProviderRegistry,
        memory_extractors: MemoryExtractorRegistry,
    ) -> None:
        self._settings = settings
        self._store = store
        self._letta_gateway = letta_gateway
        self._reply_providers = reply_providers
        self._memory_extractors = memory_extractors

    def list_characters(self) -> list[CharacterRecord]:
        return self._store.list_characters()

    def prepare_chat(self, request: ChatRequest) -> tuple[ChatResponse, PendingMemoryWrite]:
        character = self._store.get_character(request.character_id)
        if not character:
            raise CharacterNotFoundError(f'Unknown character: {request.character_id}')

        trace_events: list[TraceEvent] = []
        session, created = self._get_or_create_session(request.user_id, character)
        trace_events.append(
            _event(
                'session_resolution',
                request={
                    'user_id': request.user_id,
                    'character_id': character.character_id,
                },
                response={
                    'agent_id': session.agent_id,
                    'created': created,
                    'agent_name': build_agent_name(
                        character_id=character.character_id,
                        user_id=request.user_id,
                    ),
                    'archival_memory_seed_count': (
                        len(character.archival_memory_seed) if created else 0
                    ),
                },
            )
        )

        memory_context = self._letta_gateway.get_memory_context(
            agent_id=session.agent_id,
            query=request.message,
            top_k=character.memory.archival_memory_search_limit,
        )
        trace_events.append(
            _event(
                'memory_blocks_read',
                request={'agent_id': session.agent_id},
                response={
                    'memory_blocks': _model_dump_list(memory_context.memory_blocks),
                },
            )
        )
        trace_events.append(
            _event(
                'archival_memory_search',
                request={
                    'agent_id': session.agent_id,
                    'query': request.message,
                    'top_k': character.memory.archival_memory_search_limit,
                },
                response={
                    'archival_memory': _model_dump_list(memory_context.archival_memory),
                },
            )
        )

        messages = self._build_conversation_window(request=request, character=character)
        trace_events.append(
            _event(
                'conversation_window_load',
                request={
                    'conversation_history_window': character.memory.conversation_history_window,
                },
                response={'conversation_window': _model_dump_list(messages)},
            )
        )

        provider_config = self._resolve_reply_provider_config(character.reply_provider)
        provider_request = ReplyRequest(
            character=character,
            user_id=request.user_id,
            messages=messages,
            memory_context=memory_context,
        )
        provider_response = self._reply_providers.generate(
            config=provider_config,
            request=provider_request,
        )
        prompt_pipeline = PromptPipelineDebug(
            system_instructions=character.system_instructions,
            working_context=_split_working_context(memory_context),
            conversation_window=messages,
            retrieved_archival_memory=memory_context.archival_memory,
            final_provider_payload=(
                provider_response.request_debug.payload
                if provider_response.request_debug is not None
                else None
            ),
        )
        trace_events.append(
            _event(
                'final_prompt_assembly',
                request={
                    'provider_kind': provider_config.kind,
                    'character_id': character.character_id,
                },
                response=prompt_pipeline.model_dump(mode='json'),
            )
        )
        if provider_response.request_debug is not None:
            trace_events.append(
                _event(
                    'final_provider_call',
                    request={
                        'method': provider_response.request_debug.method,
                        'url': provider_response.request_debug.url,
                        'headers': provider_response.request_debug.headers,
                        'payload': provider_response.request_debug.payload,
                    },
                    response=provider_response.request_debug.response,
                )
            )

        response = ChatResponse(
            user_id=request.user_id,
            character_id=request.character_id,
            agent_id=session.agent_id,
            reply=provider_response.content,
            provider_kind=provider_response.provider_kind,
            debug=ChatDebugTrace(
                final_provider_call=provider_response.request_debug,
                prompt_pipeline=prompt_pipeline,
                trace_events=trace_events,
                memory_writeback=None,
            ),
        )
        pending = PendingMemoryWrite(
            character=character,
            session=session,
            memory_context=memory_context,
            user_message=request.message,
            assistant_message=provider_response.content,
        )
        return response, pending

    def persist_turn(
        self,
        pending: PendingMemoryWrite,
        *,
        capture_debug: bool = False,
    ) -> PersistedTurnDebug | None:
        extraction = self._memory_extractors.extract(
            kind=self._settings.memory_extractor_kind,
            character=pending.character,
            memory_context=pending.memory_context,
            user_message=pending.user_message,
            assistant_message=pending.assistant_message,
        )
        operations = self._letta_gateway.apply_memory_delta(
            agent_id=pending.session.agent_id,
            delta=extraction.delta,
        )
        self._store.add_chat_turn(
            ChatTurn(
                user_id=pending.session.user_id,
                character_id=pending.session.character_id,
                agent_id=pending.session.agent_id,
                user_message=pending.user_message,
                assistant_message=pending.assistant_message,
            )
        )
        logger.debug(
            'Persisted turn for user={} character={}',
            pending.session.user_id,
            pending.session.character_id,
        )
        if not capture_debug:
            return None

        trace_events = [
            _event(
                'memory_extractor_call',
                request=extraction.request_payload,
                response=extraction.response_payload,
            )
        ]
        for operation in operations:
            trace_events.append(
                _event(
                    operation.kind,
                    request={
                        'target': operation.target,
                        'value': operation.value,
                    },
                    response=operation.model_dump(mode='json'),
                )
            )
        return PersistedTurnDebug(
            memory_writeback=MemoryWritebackDebug(
                extractor_kind=self._settings.memory_extractor_kind,
                extractor_request=extraction.request_payload,
                extractor_response=extraction.response_payload,
                write_operations=operations,
            ),
            trace_events=trace_events,
        )

    def get_memory_snapshot(self, user_id: str, character_id: str) -> MemorySnapshot:
        character = self._store.get_character(character_id)
        if not character:
            raise CharacterNotFoundError(f'Unknown character: {character_id}')
        session = self._store.get_session(user_id=user_id, character_id=character_id)
        return self._letta_gateway.get_memory_snapshot(
            user_id=user_id,
            character_id=character_id,
            agent_id=session.agent_id if session else None,
            shared_memory_blocks=character.seed_shared_memory_blocks(),
            archival_memory_limit=character.memory.snapshot_archival_memory_limit,
        )

    def list_sessions(self) -> list[SessionSummary]:
        characters = {
            character.character_id: character.display_name
            for character in self._store.list_characters()
        }
        return [
            SessionSummary(
                user_id=session.user_id,
                character_id=session.character_id,
                character_display_name=characters.get(session.character_id, session.character_id),
                agent_id=session.agent_id,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
            for session in self._store.list_sessions()
        ]

    def delete_session(self, *, user_id: str, character_id: str) -> SessionSummary | None:
        session = self._store.get_session(user_id=user_id, character_id=character_id)
        if session is None:
            return None
        character = self._store.get_character(character_id)
        self._letta_gateway.delete_session_agent(agent_id=session.agent_id)
        removed = self._store.delete_session(user_id=user_id, character_id=character_id)
        if removed is None:
            return None
        return SessionSummary(
            user_id=removed.user_id,
            character_id=removed.character_id,
            character_display_name=(
                character.display_name if character else removed.character_id
            ),
            agent_id=removed.agent_id,
            created_at=removed.created_at,
            updated_at=removed.updated_at,
        )

    def _get_or_create_session(
        self, user_id: str, character: CharacterRecord
    ) -> tuple[SessionRecord, bool]:
        session = self._store.get_session(user_id=user_id, character_id=character.character_id)
        if session:
            return session, False

        agent_id = self._letta_gateway.create_session_agent(
            agent_name=build_agent_name(character_id=character.character_id, user_id=user_id),
            shared_block_ids=list(character.shared_block_ids.values()),
            model=self._settings.letta_model,
            embedding=self._settings.letta_embedding,
            llm_config=self._build_letta_llm_config(),
            embedding_config=self._build_letta_embedding_config(),
            initial_user_memory=character.memory.initial_user_memory,
        )
        if character.archival_memory_seed:
            self._letta_gateway.apply_memory_delta(
                agent_id=agent_id,
                delta=MemoryDelta(archival_memory_entries=character.archival_memory_seed),
            )
        created = self._store.upsert_session(
            SessionRecord(
                user_id=user_id,
                character_id=character.character_id,
                agent_id=agent_id,
            )
        )
        return created, True

    def _build_letta_llm_config(self) -> LettaLLMConfig | None:
        if not self._settings.letta_use_direct_model_config:
            return None
        return LettaLLMConfig(
            model=self._settings.letta_model_name,
            endpoint=self._settings.letta_model_endpoint,
            context_window=self._settings.letta_model_context_window,
            max_tokens=self._settings.letta_model_max_tokens,
        )

    def _build_letta_embedding_config(self) -> LettaEmbeddingConfig | None:
        if not self._settings.letta_use_direct_model_config:
            return None
        return LettaEmbeddingConfig(
            model=self._settings.letta_embedding_name,
            endpoint=self._settings.letta_embedding_endpoint,
            embedding_dim=self._settings.letta_embedding_dim,
        )

    def _resolve_reply_provider_config(self, config: ProviderConfig) -> ProviderConfig:
        if config.kind != 'ollama_chat':
            return config

        resolved_base_url = self._resolve_ollama_base_url(config.base_url)
        if resolved_base_url == (config.base_url or '').rstrip('/'):
            return config
        return config.model_copy(update={'base_url': resolved_base_url})

    def _resolve_ollama_base_url(self, base_url: str | None) -> str:
        fallback = self._settings.reply_provider_ollama_base_url.rstrip('/')
        if not base_url:
            return fallback

        normalized = base_url.rstrip('/')
        hostname = urlsplit(normalized).hostname
        if hostname in {'localhost', '127.0.0.1', '::1'}:
            return fallback
        return normalized

    def _build_conversation_window(
        self, *, request: ChatRequest, character: CharacterRecord
    ) -> list[ChatMessage]:
        turns = self._store.list_recent_chat_turns(
            user_id=request.user_id,
            character_id=request.character_id,
            limit=character.memory.conversation_history_window,
        )
        messages: list[ChatMessage] = []
        for turn in turns:
            messages.append(ChatMessage(role='user', content=turn.user_message))
            messages.append(ChatMessage(role='assistant', content=turn.assistant_message))
        messages.append(ChatMessage(role='user', content=request.message))
        return messages
