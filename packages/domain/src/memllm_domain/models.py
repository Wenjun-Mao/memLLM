from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


def is_native_provider_handle(route: str) -> bool:
    """Treat provider/model strings as native Letta provider handles.

    Slashless names such as `doubao_primary` are reserved for model_gateway routes.
    Slash-containing strings such as `ollama/memllm-qwen3.5-9b-q4km:latest` are
    treated as native Letta provider handles.
    """

    return "/" in route and "://" not in route


class DomainModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ChatMessage(DomainModel):
    role: Literal['system', 'user', 'assistant', 'tool']
    content: str
    name: str | None = None
    tool_call_id: str | None = None


class MemoryBlockSeed(DomainModel):
    label: str
    value: str
    description: str | None = None
    limit: int | None = None
    read_only: bool | None = None


class PrimaryAgentRuntimeConfig(DomainModel):
    model_route: str


class SleepTimeAgentRuntimeConfig(DomainModel):
    enabled: bool = True
    model_route: str
    frequency: int = 1


class LettaRuntimeConfig(DomainModel):
    primary_agent: PrimaryAgentRuntimeConfig
    sleep_time_agent: SleepTimeAgentRuntimeConfig


class CharacterManifest(DomainModel):
    character_id: str
    display_name: str
    description: str
    system_instructions: str
    shared_memory_blocks: list[MemoryBlockSeed] = Field(default_factory=list)
    archival_memory_seed: list[str] = Field(default_factory=list)
    letta_runtime: LettaRuntimeConfig

    def seed_shared_memory_blocks(self) -> list[MemoryBlockSeed]:
        return list(self.shared_memory_blocks)


class CharacterRecord(CharacterManifest):
    manifest_path: str
    manifest_checksum: str
    shared_block_ids: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class LettaSession(DomainModel):
    user_id: str
    character_id: str
    primary_agent_id: str
    sleep_time_agent_id: str | None = None
    managed_group_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SessionSummary(DomainModel):
    user_id: str
    character_id: str
    character_display_name: str
    primary_agent_id: str
    sleep_time_agent_id: str | None = None
    managed_group_id: str | None = None
    created_at: datetime
    updated_at: datetime


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
    primary_agent_id: str | None = None
    sleep_time_agent_id: str | None = None
    managed_group_id: str | None = None


class LettaMessageDebug(DomainModel):
    message_type: str | None = None
    role: str | None = None
    name: str | None = None
    content: str | None = None
    raw: dict[str, Any] | list[Any] | str | None = None


class LettaStepDebug(DomainModel):
    step_id: str
    agent_id: str | None = None
    model: str | None = None
    model_endpoint: str | None = None
    model_handle: str | None = None
    status: str | None = None
    stop_reason: str | None = None
    trace_id: str | None = None
    request_id: str | None = None
    total_tokens: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    messages: list[LettaMessageDebug] = Field(default_factory=list)


class GatewayTraceDebug(DomainModel):
    sequence: int | None = None
    created_at: datetime | None = None
    phase: str
    route_name: str
    method: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] | list[Any] | str | None = None
    response: dict[str, Any] | list[Any] | str | None = None
    status_code: int | None = None


class TraceEvent(DomainModel):
    kind: str
    title: str
    description: str
    paper_mapping: str | None = None
    request: dict[str, Any] | list[Any] | str | None = None
    response: dict[str, Any] | list[Any] | str | None = None


class ProviderCallDebug(DomainModel):
    provider_kind: str | None = None
    route_name: str | None = None
    phase: str | None = None
    method: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] | list[Any] | str | None = None
    response: dict[str, Any] | list[Any] | str | None = None


class WorkingContextDebug(DomainModel):
    shared_memory_blocks: list[MemoryBlock] = Field(default_factory=list)
    user_memory_blocks: list[MemoryBlock] = Field(default_factory=list)


class PromptPipelineDebug(DomainModel):
    system_instructions: str
    working_context: WorkingContextDebug
    conversation_window: list[ChatMessage] = Field(default_factory=list)
    retrieved_archival_memory: list[ArchivalMemoryItem] = Field(default_factory=list)
    final_provider_payload: dict[str, Any] | list[Any] | str | None = None


class MemoryWritebackDebug(DomainModel):
    status: Literal['completed', 'timed_out', 'skipped']
    sleep_time_agent_id: str | None = None
    letta_steps: list[LettaStepDebug] = Field(default_factory=list)
    gateway_traces: list[GatewayTraceDebug] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ChatDebugTrace(DomainModel):
    final_provider_call: ProviderCallDebug | None = None
    prompt_pipeline: PromptPipelineDebug | None = None
    trace_events: list[TraceEvent] = Field(default_factory=list)
    memory_writeback: MemoryWritebackDebug | None = None


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


# Kept so dormant phase-1 packages still import cleanly until they are removed from the workspace.
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


class MemoryWriteOperation(DomainModel):
    kind: Literal['memory_block_update', 'archival_memory_insert']
    target: str
    value: str
    memory_id: str | None = None


class MemoryDelta(DomainModel):
    user_memory_block_value: str | None = None
    archival_memory_entries: list[str] = Field(default_factory=list)


class MemoryExtractionResult(DomainModel):
    delta: MemoryDelta
    request_payload: dict[str, Any] | list[Any] | str | None = None
    response_payload: dict[str, Any] | list[Any] | str | None = None


class ChatTurn(DomainModel):
    user_id: str
    character_id: str
    agent_id: str
    user_message: str
    assistant_message: str
    created_at: datetime = Field(default_factory=utc_now)
