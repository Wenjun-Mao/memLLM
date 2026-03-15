from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatMessage(DomainModel):
    role: Literal["system", "user", "assistant"]
    content: str


class SharedBlockSeed(DomainModel):
    label: str
    value: str


class ProviderConfig(DomainModel):
    kind: Literal["custom_simple_http", "ollama_chat"]
    endpoint: str | None = None
    base_url: str | None = None
    model: str | None = None
    transport: Literal["get", "post"] = "get"
    timeout_seconds: float = 45.0
    headers: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class MemorySettings(DomainModel):
    archival_search_limit: int = 5
    snapshot_passage_limit: int = 10
    recent_message_window: int = 6
    initial_human_block: str = "No user-specific memory has been captured yet."


class CharacterManifest(DomainModel):
    character_id: str
    display_name: str
    description: str
    persona: str
    system_prompt: str | None = None
    reply_provider: ProviderConfig
    memory: MemorySettings = Field(default_factory=MemorySettings)
    shared_blocks: list[SharedBlockSeed] = Field(default_factory=list)
    shared_passages: list[str] = Field(default_factory=list)

    def seed_blocks(self) -> list[SharedBlockSeed]:
        blocks = [SharedBlockSeed(label="persona", value=self.persona)]
        blocks.extend(self.shared_blocks)
        if self.shared_passages:
            lore_text = "\n".join(f"- {passage}" for passage in self.shared_passages)
            blocks.append(SharedBlockSeed(label="lore", value=lore_text))
        return blocks


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


class ChatTurn(DomainModel):
    user_id: str
    character_id: str
    agent_id: str
    user_message: str
    assistant_message: str
    created_at: datetime = Field(default_factory=utc_now)


class MemoryBlock(DomainModel):
    label: str
    value: str
    block_id: str | None = None
    scope: Literal["shared", "user"] = "user"


class MemoryPassage(DomainModel):
    text: str
    memory_id: str | None = None
    score: float | None = None


class MemoryContext(DomainModel):
    blocks: list[MemoryBlock] = Field(default_factory=list)
    passages: list[MemoryPassage] = Field(default_factory=list)

    def block_value(self, label: str) -> str | None:
        for block in self.blocks:
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


class MemoryDelta(DomainModel):
    human_block_value: str | None = None
    passages: list[str] = Field(default_factory=list)


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


class SeedReportItem(DomainModel):
    character_id: str
    display_name: str
    created: bool
    shared_block_ids: dict[str, str]


class SeedReport(DomainModel):
    seeded: list[SeedReportItem] = Field(default_factory=list)
