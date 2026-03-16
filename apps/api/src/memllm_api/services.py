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
    DebugStep,
    MemoryContext,
    MemorySnapshot,
    ProviderConfig,
    ReplyRequest,
    SeedReport,
    SeedReportItem,
    SessionRecord,
    SessionSummary,
)
from memllm_letta_integration import (
    LettaEmbeddingConfig,
    LettaGateway,
    LettaLLMConfig,
)
from memllm_memory_pipeline import MemoryExtractorRegistry
from memllm_reply_providers import ReplyProviderRegistry

from memllm_api.manifests import CharacterManifestLoader
from memllm_api.settings import ApiSettings
from memllm_api.store import MetadataStore


@dataclass
class PendingMemoryWrite:
    character: CharacterRecord
    session: SessionRecord
    memory_context: MemoryContext
    user_message: str
    assistant_message: str


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
            shared_block_ids = self._letta_gateway.upsert_shared_blocks(
                blocks=record.seed_blocks(),
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


def _messages_debug_payload(messages: list[ChatMessage]) -> list[dict[str, str]]:
    return [message.model_dump(mode='json') for message in messages]


def _memory_context_debug_payload(context: MemoryContext) -> dict[str, object]:
    return context.model_dump(mode='json')


_AGENT_NAME_UNSAFE_RE = re.compile(r"[^\w\s\-']+", flags=re.UNICODE)


def build_agent_name(*, character_id: str, user_id: str) -> str:
    raw_name = f'{character_id}__{user_id}'
    sanitized = _AGENT_NAME_UNSAFE_RE.sub('_', raw_name)
    sanitized = re.sub(r'_+', '_', sanitized).strip(' _')
    return sanitized or 'memllm-agent'


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

        debug_steps: list[DebugStep] = []
        session, created = self._get_or_create_session(request.user_id, character)
        debug_steps.append(
            DebugStep(
                label='session_resolution',
                input={
                    'user_id': request.user_id,
                    'character_id': character.character_id,
                },
                output={
                    'agent_id': session.agent_id,
                    'created': created,
                    'agent_name': build_agent_name(
                        character_id=character.character_id,
                        user_id=request.user_id,
                    ),
                },
            )
        )
        memory_context = self._letta_gateway.get_memory_context(
            agent_id=session.agent_id,
            query=request.message,
            top_k=character.memory.archival_search_limit,
        )
        debug_steps.append(
            DebugStep(
                label='letta_memory_context',
                input={
                    'agent_id': session.agent_id,
                    'query': request.message,
                    'top_k': character.memory.archival_search_limit,
                },
                output=_memory_context_debug_payload(memory_context),
            )
        )
        messages = self._build_message_history(request=request, character=character)
        debug_steps.append(
            DebugStep(
                label='message_history',
                input={
                    'recent_message_window': character.memory.recent_message_window,
                },
                output={'messages': _messages_debug_payload(messages)},
            )
        )
        provider_config = self._resolve_reply_provider_config(character.reply_provider)
        debug_steps.append(
            DebugStep(
                label='reply_provider_resolution',
                input=character.reply_provider.model_dump(mode='json'),
                output=provider_config.model_dump(mode='json'),
            )
        )
        provider_response = self._reply_providers.generate(
            config=provider_config,
            request=ReplyRequest(
                character=character,
                user_id=request.user_id,
                messages=messages,
                memory_context=memory_context,
            ),
        )
        debug_steps.append(
            DebugStep(
                label='memory_persistence_schedule',
                input={
                    'extractor_kind': self._settings.memory_extractor_kind,
                    'agent_id': session.agent_id,
                },
                output={
                    'scheduled': True,
                    'user_message': request.message,
                    'assistant_message': provider_response.content,
                },
            )
        )

        response = ChatResponse(
            user_id=request.user_id,
            character_id=request.character_id,
            agent_id=session.agent_id,
            reply=provider_response.content,
            provider_kind=provider_response.provider_kind,
            debug=ChatDebugTrace(
                final_request=provider_response.request_debug,
                steps=debug_steps,
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

    def persist_turn(self, pending: PendingMemoryWrite) -> None:
        delta = self._memory_extractors.extract(
            kind=self._settings.memory_extractor_kind,
            character=pending.character,
            memory_context=pending.memory_context,
            user_message=pending.user_message,
            assistant_message=pending.assistant_message,
        )
        self._letta_gateway.apply_memory_delta(agent_id=pending.session.agent_id, delta=delta)
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

    def get_memory_snapshot(self, user_id: str, character_id: str) -> MemorySnapshot:
        character = self._store.get_character(character_id)
        if not character:
            raise CharacterNotFoundError(f'Unknown character: {character_id}')
        session = self._store.get_session(user_id=user_id, character_id=character_id)
        return self._letta_gateway.get_memory_snapshot(
            user_id=user_id,
            character_id=character_id,
            agent_id=session.agent_id if session else None,
            shared_blocks=character.seed_blocks(),
            passage_limit=character.memory.snapshot_passage_limit,
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
            initial_human_block=character.memory.initial_human_block,
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

    def _build_message_history(
        self, *, request: ChatRequest, character: CharacterRecord
    ) -> list[ChatMessage]:
        turns = self._store.list_recent_chat_turns(
            user_id=request.user_id,
            character_id=request.character_id,
            limit=character.memory.recent_message_window,
        )
        messages: list[ChatMessage] = []
        for turn in turns:
            messages.append(ChatMessage(role='user', content=turn.user_message))
            messages.append(ChatMessage(role='assistant', content=turn.assistant_message))
        messages.append(ChatMessage(role='user', content=request.message))
        return messages
