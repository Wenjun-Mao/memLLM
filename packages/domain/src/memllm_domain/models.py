from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ChatMessage(DomainModel):
    role: Literal['system', 'user', 'assistant']
    content: str


class MemoryBlockSeed(DomainModel):
    label: str
    value: str
    description: str | None = None
    limit: int | None = None
    read_only: bool | None = None


class ProviderConfig(DomainModel):
    kind: Literal['custom_simple_http', 'ollama_chat']
    endpoint: str | None = None
    base_url: str | None = None
    model: str | None = None
    transport: Literal['get', 'post'] = 'get'
    timeout_seconds: float = 45.0
    headers: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class MemorySettings(DomainModel):
    archival_memory_search_limit: int = 5
    snapshot_archival_memory_limit: int = 10
    conversation_history_window: int = 6
    initial_user_memory: str = 'No user-specific memory has been captured yet.'


class CharacterManifest(DomainModel):
    character_id: str
    display_name: str
    description: str
    system_instructions: str
    reply_provider: ProviderConfig
    memory: MemorySettings = Field(default_factory=MemorySettings)
    shared_memory_blocks: list[MemoryBlockSeed] = Field(default_factory=list)
    archival_memory_seed: list[str] = Field(default_factory=list)

    def seed_shared_memory_blocks(self) -> list[MemoryBlockSeed]:
        return list(self.shared_memory_blocks)


class CharacterRecord(CharacterManifest):
    manifest_path: str
    manifest_checksum: str
    shared_block_ids: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SessionRecord(DomainModel):
    user_id: str
    character_id: str
    agent_id: str
    provider_override: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SessionSummary(DomainModel):
    user_id: str
    character_id: str
    character_display_name: str
    agent_id: str
    created_at: datetime
    updated_at: datetime


class TraceEvent(DomainModel):
    kind: str
    title: str
    description: str
    paper_mapping: str | None = None
    request: dict[str, Any] | list[Any] | str | None = None
    response: dict[str, Any] | list[Any] | str | None = None


class ProviderCallDebug(DomainModel):
    provider_kind: str
    method: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] | list[Any] | str | None = None
    response: dict[str, Any] | list[Any] | str | None = None


class MemoryBlock(DomainModel):
    label: str
    value: str
    block_id: str | None = None
    scope: Literal['shared', 'user'] = 'user'
    description: str | None = None
    limit: int | None = None
    read_only: bool | None = None


class ArchivalMemoryItem(DomainModel):
    text: str
    memory_id: str | None = None
    score: float | None = None


class WorkingContextDebug(DomainModel):
    shared_memory_blocks: list[MemoryBlock] = Field(default_factory=list)
    user_memory_blocks: list[MemoryBlock] = Field(default_factory=list)


class PromptPipelineDebug(DomainModel):
    system_instructions: str
    working_context: WorkingContextDebug
    conversation_window: list[ChatMessage] = Field(default_factory=list)
    retrieved_archival_memory: list[ArchivalMemoryItem] = Field(default_factory=list)
    final_provider_payload: dict[str, Any] | list[Any] | str | None = None


class MemoryWriteOperation(DomainModel):
    kind: Literal['memory_block_update', 'archival_memory_insert']
    target: str
    value: str
    memory_id: str | None = None


class MemoryWritebackDebug(DomainModel):
    extractor_kind: str
    extractor_request: dict[str, Any] | list[Any] | str | None = None
    extractor_response: dict[str, Any] | list[Any] | str | None = None
    write_operations: list[MemoryWriteOperation] = Field(default_factory=list)


class MemoryExtractionResult(DomainModel):
    delta: MemoryDelta
    request_payload: dict[str, Any] | list[Any] | str | None = None
    response_payload: dict[str, Any] | list[Any] | str | None = None


class ChatDebugTrace(DomainModel):
    final_provider_call: ProviderCallDebug | None = None
    prompt_pipeline: PromptPipelineDebug | None = None
    trace_events: list[TraceEvent] = Field(default_factory=list)
    memory_writeback: MemoryWritebackDebug | None = None


class ChatTurn(DomainModel):
    user_id: str
    character_id: str
    agent_id: str
    user_message: str
    assistant_message: str
    created_at: datetime = Field(default_factory=utc_now)


class MemoryContext(DomainModel):
    memory_blocks: list[MemoryBlock] = Field(default_factory=list)
    archival_memory: list[ArchivalMemoryItem] = Field(default_factory=list)

    def block_value(self, label: str) -> str | None:
        for block in self.memory_blocks:
            if block.label == label:
                return block.value
        return None


class MemorySnapshot(MemoryContext):
    user_id: str
    character_id: str
    agent_id: str | None = None


class ReplyRequest(DomainModel):
    character: CharacterRecord
    user_id: str
    messages: list[ChatMessage]
    memory_context: MemoryContext


class ProviderResponse(DomainModel):
    provider_kind: str
    content: str
    raw_payload: dict[str, Any] | list[Any] | str | None = None
    request_debug: ProviderCallDebug | None = None


class MemoryDelta(DomainModel):
    user_memory_block_value: str | None = None
    archival_memory_entries: list[str] = Field(default_factory=list)


class ChatRequest(DomainModel):
    user_id: str
    character_id: str
    message: str


class ChatResponse(DomainModel):
    user_id: str
    character_id: str
    agent_id: str
    reply: str
    provider_kind: str
    debug: ChatDebugTrace | None = None


class SeedReportItem(DomainModel):
    character_id: str
    display_name: str
    created: bool
    shared_block_ids: dict[str, str]


class SeedReport(DomainModel):
    seeded: list[SeedReportItem] = Field(default_factory=list)
