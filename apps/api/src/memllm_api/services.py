from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from memllm_domain import (
    CharacterNotFoundError,
    CharacterRecord,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatTurn,
    MemoryContext,
    MemorySnapshot,
    ReplyRequest,
    SeedReport,
    SeedReportItem,
    SessionRecord,
)
from memllm_letta_integration import LettaGateway
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
                record.model_copy(update={"shared_block_ids": shared_block_ids})
            )
            items.append(
                SeedReportItem(
                    character_id=upserted.character_id,
                    display_name=upserted.display_name,
                    created=created,
                    shared_block_ids=upserted.shared_block_ids,
                )
            )
            logger.info("Seeded character {}", upserted.character_id)
        return SeedReport(seeded=items)


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
            raise CharacterNotFoundError(f"Unknown character: {request.character_id}")

        session = self._get_or_create_session(request.user_id, character)
        memory_context = self._letta_gateway.get_memory_context(
            agent_id=session.agent_id,
            query=request.message,
            top_k=character.memory.archival_search_limit,
        )
        messages = self._build_message_history(request=request, character=character)
        provider_response = self._reply_providers.generate(
            config=character.reply_provider,
            request=ReplyRequest(
                character=character,
                user_id=request.user_id,
                messages=messages,
                memory_context=memory_context,
            ),
        )

        response = ChatResponse(
            user_id=request.user_id,
            character_id=request.character_id,
            agent_id=session.agent_id,
            reply=provider_response.content,
            provider_kind=provider_response.provider_kind,
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
            "Persisted turn for user={} character={}",
            pending.session.user_id,
            pending.session.character_id,
        )

    def get_memory_snapshot(self, user_id: str, character_id: str) -> MemorySnapshot:
        character = self._store.get_character(character_id)
        if not character:
            raise CharacterNotFoundError(f"Unknown character: {character_id}")
        session = self._store.get_session(user_id=user_id, character_id=character_id)
        return self._letta_gateway.get_memory_snapshot(
            user_id=user_id,
            character_id=character_id,
            agent_id=session.agent_id if session else None,
            shared_blocks=character.seed_blocks(),
            passage_limit=character.memory.snapshot_passage_limit,
        )

    def _get_or_create_session(self, user_id: str, character: CharacterRecord) -> SessionRecord:
        session = self._store.get_session(user_id=user_id, character_id=character.character_id)
        if session:
            return session

        agent_id = self._letta_gateway.create_session_agent(
            agent_name=f"{character.character_id}:{user_id}",
            shared_block_ids=list(character.shared_block_ids.values()),
            model=self._settings.letta_model,
            embedding=self._settings.letta_embedding,
            initial_human_block=character.memory.initial_human_block,
        )
        return self._store.upsert_session(
            SessionRecord(
                user_id=user_id,
                character_id=character.character_id,
                agent_id=agent_id,
            )
        )

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
            messages.append(ChatMessage(role="user", content=turn.user_message))
            messages.append(ChatMessage(role="assistant", content=turn.assistant_message))
        messages.append(ChatMessage(role="user", content=request.message))
        return messages
