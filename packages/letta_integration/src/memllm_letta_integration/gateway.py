from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import count
from time import sleep, time
from typing import Any, Protocol

from memllm_domain import (
    ArchivalMemoryItem,
    CharacterRecord,
    LettaGatewayError,
    LettaMessageDebug,
    LettaSession,
    LettaStepDebug,
    MemoryBlock,
    MemoryBlockSeed,
    MemoryContext,
    MemorySnapshot,
)


@dataclass(frozen=True)
class LettaLLMConfig:
    model_route: str
    context_window: int
    max_tokens: int
    endpoint: str | None = None
    endpoint_type: str = "openai"
    native_provider: bool = False


@dataclass(frozen=True)
class LettaEmbeddingConfig:
    model_route: str
    embedding_dim: int
    endpoint: str | None = None
    endpoint_type: str = "openai"
    batch_size: int = 32
    chunk_size: int = 300
    native_provider: bool = False


@dataclass(frozen=True)
class SessionCreateConfig:
    user_id: str
    character: CharacterRecord
    primary_llm: LettaLLMConfig
    sleep_time_llm: LettaLLMConfig | None
    embedding: LettaEmbeddingConfig
    default_user_memory: str


@dataclass(frozen=True)
class LettaTurnResult:
    reply: str
    response_messages: list[dict[str, Any]]
    raw_response: dict[str, Any]


class LettaGateway(Protocol):
    def upsert_shared_memory_blocks(
        self,
        *,
        blocks: list[MemoryBlockSeed],
        existing_block_ids: dict[str, str] | None = None,
    ) -> dict[str, str]: ...

    def resolve_session(self, *, create: SessionCreateConfig) -> tuple[LettaSession, bool]: ...

    def list_sessions(self) -> list[LettaSession]: ...

    def send_user_message(
        self,
        *,
        primary_agent_id: str,
        message: str,
        max_steps: int,
    ) -> LettaTurnResult: ...

    def wait_for_sleep_time(
        self,
        *,
        session: LettaSession,
        baseline_completion: datetime | None,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> bool: ...

    def get_agent_last_completion(self, *, agent_id: str) -> datetime | None: ...

    def list_recent_steps(self, *, agent_id: str, limit: int) -> list[LettaStepDebug]: ...

    def get_memory_context(self, *, agent_id: str, query: str, top_k: int) -> MemoryContext: ...

    def get_memory_snapshot(
        self,
        *,
        user_id: str,
        character_id: str,
        session: LettaSession | None,
        shared_memory_blocks: list[MemoryBlockSeed] | None = None,
        archival_memory_limit: int = 10,
    ) -> MemorySnapshot: ...

    def delete_session(self, *, session: LettaSession) -> None: ...


def _iter_page_items(page: object) -> Iterable[object]:
    if page is None:
        return []
    if isinstance(page, list):
        return page
    if hasattr(page, "data"):
        return page.data
    return page


def _shared_block_metadata(
    shared_memory_blocks: list[MemoryBlockSeed] | None,
) -> dict[str, MemoryBlockSeed]:
    return {block.label: block for block in shared_memory_blocks or []}


def _apply_block_seed_metadata(
    *,
    memory_blocks: list[MemoryBlock],
    shared_memory_blocks: list[MemoryBlockSeed] | None,
) -> list[MemoryBlock]:
    metadata = _shared_block_metadata(shared_memory_blocks)
    decorated: list[MemoryBlock] = []
    for block in memory_blocks:
        if block.scope != "shared":
            decorated.append(block)
            continue
        seed = metadata.get(block.label)
        if seed is None:
            decorated.append(block)
            continue
        decorated.append(
            block.model_copy(
                update={
                    "description": seed.description,
                    "limit": seed.limit,
                    "read_only": seed.read_only,
                }
            )
        )
    return decorated


def _stringify_message_content(content: object) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        joined = "\n".join(part for part in text_parts if part)
        return joined or None
    if content is None:
        return None
    return str(content)


def _message_to_debug(message: object) -> LettaMessageDebug:
    payload = message.model_dump(mode="json") if hasattr(message, "model_dump") else dict(message)
    return LettaMessageDebug(
        message_type=payload.get("message_type"),
        role=payload.get("role"),
        name=payload.get("name"),
        content=_stringify_message_content(payload.get("content")),
        raw=payload,
    )


def _response_to_payload(response: object) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return response
    raise TypeError(f"Unsupported Letta response payload type: {type(response)!r}")


def _llm_create_kwargs(config: LettaLLMConfig) -> dict[str, Any]:
    if config.native_provider:
        return {
            "model": config.model_route,
            "context_window_limit": config.context_window,
            "max_tokens": config.max_tokens,
        }
    if not config.endpoint:
        raise ValueError("Gateway-backed LettaLLMConfig requires an endpoint.")
    return {
        "llm_config": {
            "model": config.model_route,
            "model_endpoint_type": config.endpoint_type,
            "model_endpoint": config.endpoint,
            "context_window": config.context_window,
            "max_tokens": config.max_tokens,
        }
    }


def _embedding_create_kwargs(config: LettaEmbeddingConfig) -> dict[str, Any]:
    if config.native_provider:
        return {
            "embedding": config.model_route,
            "embedding_chunk_size": config.chunk_size,
        }
    if not config.endpoint:
        raise ValueError("Gateway-backed LettaEmbeddingConfig requires an endpoint.")
    return {
        "embedding_config": {
            "embedding_model": config.model_route,
            "embedding_endpoint_type": config.endpoint_type,
            "embedding_endpoint": config.endpoint,
            "embedding_dim": config.embedding_dim,
            "batch_size": config.batch_size,
            "embedding_chunk_size": config.chunk_size,
        }
    }


def _llm_update_kwargs(config: LettaLLMConfig) -> dict[str, Any]:
    if config.native_provider:
        return {
            "model": config.model_route,
            "context_window_limit": config.context_window,
            "max_tokens": config.max_tokens,
        }
    if not config.endpoint:
        raise ValueError("Gateway-backed LettaLLMConfig requires an endpoint.")
    return {
        "llm_config": {
            "model": config.model_route,
            "model_endpoint_type": config.endpoint_type,
            "model_endpoint": config.endpoint,
            "context_window": config.context_window,
            "max_tokens": config.max_tokens,
        }
    }


def _extract_reply_from_messages(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("message_type") != "assistant_message":
            continue
        content = _stringify_message_content(message.get("content"))
        if content:
            return content
    for message in reversed(messages):
        content = _stringify_message_content(message.get("content"))
        if content:
            return content
    return ""


def build_primary_agent_name(*, character_id: str, user_id: str) -> str:
    return f"{character_id}__{user_id}__primary"


def build_sleep_time_agent_name(*, character_id: str, user_id: str) -> str:
    return f"{character_id}__{user_id}__sleeptime"


def _primary_agent_tags(*, character_id: str) -> list[str]:
    return [
        "memllm",
        "memllm-runtime:v2",
        "memllm-role:primary",
        f"memllm-character:{character_id}",
    ]


def _sleep_time_agent_tags(*, character_id: str) -> list[str]:
    return [
        "memllm",
        "memllm-runtime:v2",
        "memllm-role:sleeptime",
        f"memllm-character:{character_id}",
    ]


class RealLettaGateway:
    def __init__(self, *, base_url: str, api_key: str | None = None) -> None:
        from letta_client import Letta

        kwargs = {"base_url": base_url}
        if api_key:
            kwargs["api_key"] = api_key
        self._client = Letta(**kwargs)

    def upsert_shared_memory_blocks(
        self,
        *,
        blocks: list[MemoryBlockSeed],
        existing_block_ids: dict[str, str] | None = None,
    ) -> dict[str, str]:
        existing_block_ids = existing_block_ids or {}
        results: dict[str, str] = {}
        for block in blocks:
            block_id = existing_block_ids.get(block.label)
            if block_id:
                updated = self._client.blocks.update(block_id=block_id, value=block.value)
                results[block.label] = getattr(updated, "id", block_id)
            else:
                created = self._client.blocks.create(label=block.label, value=block.value)
                results[block.label] = created.id
        return results

    def resolve_session(self, *, create: SessionCreateConfig) -> tuple[LettaSession, bool]:
        existing = self._find_primary_agent(
            user_id=create.user_id,
            character_id=create.character.character_id,
        )
        if existing is not None:
            return existing, False

        metadata = {
            "memllm_runtime": "v2",
            "role": "primary",
            "user_id": create.user_id,
            "character_id": create.character.character_id,
            "manifest_checksum": create.character.manifest_checksum,
        }
        extra_body: dict[str, Any] = {}
        if create.character.letta_runtime.sleep_time_agent.enabled:
            extra_body["sleeptime_agent_frequency"] = (
                create.character.letta_runtime.sleep_time_agent.frequency
            )
        agent_create_kwargs: dict[str, Any] = {
            "name": build_primary_agent_name(
                character_id=create.character.character_id,
                user_id=create.user_id,
            ),
            "description": create.character.description,
            "system": create.character.system_instructions,
            "memory_blocks": [{"label": "human", "value": create.default_user_memory}],
            "block_ids": list(create.character.shared_block_ids.values()),
            "enable_sleeptime": create.character.letta_runtime.sleep_time_agent.enabled,
            "tags": _primary_agent_tags(character_id=create.character.character_id),
            "metadata": metadata,
            "extra_body": extra_body or None,
        }
        agent_create_kwargs.update(_llm_create_kwargs(create.primary_llm))
        agent_create_kwargs.update(_embedding_create_kwargs(create.embedding))
        agent = self._client.agents.create(**agent_create_kwargs)
        primary = self._retrieve_primary_session(agent_id=agent.id)
        if primary is None:
            raise LettaGatewayError(
                "Created Letta agent but could not retrieve managed session state."
            )
        if create.character.archival_memory_seed:
            for item in create.character.archival_memory_seed:
                self._client.agents.passages.create(agent_id=primary.primary_agent_id, text=item)
        if (
            create.character.letta_runtime.sleep_time_agent.enabled
            and create.sleep_time_llm is not None
        ):
            self._configure_sleep_time_agent(session=primary, create=create)
            primary = self._retrieve_primary_session(agent_id=primary.primary_agent_id) or primary
        return primary, True

    def list_sessions(self) -> list[LettaSession]:
        page = self._client.agents.list(
            tags=["memllm", "memllm-runtime:v2", "memllm-role:primary"],
            match_all_tags=True,
            include=["agent.managed_group"],
        )
        sessions: list[LettaSession] = []
        for agent in _iter_page_items(page):
            session = self._agent_to_session(agent)
            if session is not None:
                sessions.append(session)
        sessions.sort(key=lambda item: (item.updated_at, item.created_at), reverse=True)
        return sessions

    def send_user_message(
        self,
        *,
        primary_agent_id: str,
        message: str,
        max_steps: int,
    ) -> LettaTurnResult:
        try:
            response = self._client.agents.messages.create(
                primary_agent_id,
                input=message,
                max_steps=max_steps,
                use_assistant_message=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise LettaGatewayError("Failed to send a message to Letta.") from exc
        payload = _response_to_payload(response)
        messages = payload.get("messages") or []
        return LettaTurnResult(
            reply=_extract_reply_from_messages(messages),
            response_messages=messages,
            raw_response=payload,
        )

    def wait_for_sleep_time(
        self,
        *,
        session: LettaSession,
        baseline_completion: datetime | None,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> bool:
        if not session.sleep_time_agent_id:
            return True
        deadline = time() + timeout_seconds
        while time() < deadline:
            completion = self.get_agent_last_completion(agent_id=session.sleep_time_agent_id)
            if completion is not None and (
                baseline_completion is None or completion > baseline_completion
            ):
                return True
            sleep(poll_interval_seconds)
        return False

    def get_agent_last_completion(self, *, agent_id: str) -> datetime | None:
        agent = self._client.agents.retrieve(agent_id)
        return getattr(agent, "last_run_completion", None)

    def list_recent_steps(self, *, agent_id: str, limit: int) -> list[LettaStepDebug]:
        try:
            # Some Letta builds currently reject /v1/steps `order=` queries server-side even though
            # the primary chat turn succeeded. Keep this debug lookup best-effort and stick to the
            # server defaults so step tracing never turns into a user-facing 500.
            steps_page = self._client.steps.list(agent_id=agent_id, limit=limit)
        except Exception:
            return []

        steps: list[LettaStepDebug] = []
        for step in _iter_page_items(steps_page):
            try:
                step_messages = self._client.steps.messages.list(
                    step_id=step.id,
                    limit=50,
                )
            except Exception:
                step_messages = []
            messages = []
            for payload in _iter_page_items(step_messages):
                if isinstance(payload, list):
                    for nested in payload:
                        messages.append(_message_to_debug(nested))
                else:
                    messages.append(_message_to_debug(payload))
            steps.append(
                LettaStepDebug(
                    step_id=step.id,
                    agent_id=getattr(step, "agent_id", None),
                    model=getattr(step, "model", None),
                    model_endpoint=getattr(step, "api_model_endpoint", None),
                    model_handle=getattr(step, "api_model_handle", None),
                    status=getattr(step, "status", None),
                    stop_reason=getattr(step, "stop_reason", None),
                    trace_id=getattr(step, "trace_id", None),
                    request_id=getattr(step, "request_id", None),
                    total_tokens=getattr(step, "total_tokens", None),
                    prompt_tokens=getattr(step, "prompt_tokens", None),
                    completion_tokens=getattr(step, "completion_tokens", None),
                    messages=messages,
                )
            )
        return steps

    def get_memory_context(self, *, agent_id: str, query: str, top_k: int) -> MemoryContext:
        try:
            block_page = self._client.agents.blocks.list(agent_id=agent_id)
            memory_blocks = [
                MemoryBlock(
                    label=block.label,
                    value=block.value,
                    block_id=getattr(block, "id", None),
                    scope="shared" if block.label != "human" else "user",
                )
                for block in _iter_page_items(block_page)
            ]
            if query:
                result = self._client.agents.passages.search(
                    agent_id=agent_id, query=query, top_k=top_k
                )
                archival_items = getattr(result, "passages", [])
            else:
                archival_items = _iter_page_items(
                    self._client.agents.passages.list(agent_id=agent_id, limit=top_k)
                )
            archival_memory = [
                ArchivalMemoryItem(
                    text=getattr(item, "text", ""),
                    memory_id=getattr(item, "id", None),
                    score=getattr(item, "score", None),
                )
                for item in archival_items
            ]
            return MemoryContext(memory_blocks=memory_blocks, archival_memory=archival_memory)
        except Exception as exc:  # noqa: BLE001
            raise LettaGatewayError("Failed to retrieve Letta memory context.") from exc

    def get_memory_snapshot(
        self,
        *,
        user_id: str,
        character_id: str,
        session: LettaSession | None,
        shared_memory_blocks: list[MemoryBlockSeed] | None = None,
        archival_memory_limit: int = 10,
    ) -> MemorySnapshot:
        if session is None:
            return MemorySnapshot(
                user_id=user_id,
                character_id=character_id,
                primary_agent_id=None,
                sleep_time_agent_id=None,
                managed_group_id=None,
                memory_blocks=[
                    MemoryBlock(
                        label=block.label,
                        value=block.value,
                        scope="shared",
                        description=block.description,
                        limit=block.limit,
                        read_only=block.read_only,
                    )
                    for block in shared_memory_blocks or []
                ],
                archival_memory=[],
            )
        context = self.get_memory_context(
            agent_id=session.primary_agent_id,
            query="",
            top_k=archival_memory_limit,
        )
        return MemorySnapshot(
            user_id=user_id,
            character_id=character_id,
            primary_agent_id=session.primary_agent_id,
            sleep_time_agent_id=session.sleep_time_agent_id,
            managed_group_id=session.managed_group_id,
            memory_blocks=_apply_block_seed_metadata(
                memory_blocks=context.memory_blocks,
                shared_memory_blocks=shared_memory_blocks,
            ),
            archival_memory=context.archival_memory,
        )

    def delete_session(self, *, session: LettaSession) -> None:
        agent_ids = []
        primary = self._retrieve_primary_session(agent_id=session.primary_agent_id)
        if primary and primary.sleep_time_agent_id:
            agent_ids.append(primary.sleep_time_agent_id)
        agent_ids.append(session.primary_agent_id)
        for agent_id in agent_ids:
            try:
                self._client.agents.delete(agent_id=agent_id)
            except Exception:  # noqa: BLE001
                continue

    def _configure_sleep_time_agent(
        self,
        *,
        session: LettaSession,
        create: SessionCreateConfig,
    ) -> None:
        if not session.sleep_time_agent_id or create.sleep_time_llm is None:
            return
        update_kwargs: dict[str, Any] = {
            "name": build_sleep_time_agent_name(
                character_id=create.character.character_id,
                user_id=create.user_id,
            ),
            "tags": _sleep_time_agent_tags(character_id=create.character.character_id),
            "metadata": {
                "memllm_runtime": "v2",
                "role": "sleeptime",
                "user_id": create.user_id,
                "character_id": create.character.character_id,
                "manifest_checksum": create.character.manifest_checksum,
            },
        }
        update_kwargs.update(_llm_update_kwargs(create.sleep_time_llm))
        self._client.agents.update(session.sleep_time_agent_id, **update_kwargs)

    def _find_primary_agent(self, *, user_id: str, character_id: str) -> LettaSession | None:
        name = build_primary_agent_name(character_id=character_id, user_id=user_id)
        page = self._client.agents.list(name=name, include=["agent.managed_group"])
        for agent in _iter_page_items(page):
            session = self._agent_to_session(agent)
            if session is not None:
                return session
        return None

    def _retrieve_primary_session(self, *, agent_id: str) -> LettaSession | None:
        agent = self._client.agents.retrieve(agent_id, include=["agent.managed_group"])
        return self._agent_to_session(agent)

    def _agent_to_session(self, agent: object) -> LettaSession | None:
        payload = agent.model_dump(mode="json") if hasattr(agent, "model_dump") else dict(agent)
        metadata = payload.get("metadata") or {}
        if metadata.get("role") != "primary":
            return None
        managed_group = payload.get("managed_group") or {}
        agent_ids = list(managed_group.get("agent_ids") or [])
        sleep_time_agent_id = next(
            (candidate for candidate in agent_ids if candidate != payload.get("id")),
            None,
        )
        created_at = payload.get("created_at")
        updated_at = (
            payload.get("updated_at")
            or payload.get("last_run_completion")
            or payload.get("created_at")
        )
        return LettaSession(
            user_id=str(metadata.get("user_id", "")),
            character_id=str(metadata.get("character_id", "")),
            primary_agent_id=str(payload.get("id")),
            sleep_time_agent_id=sleep_time_agent_id,
            managed_group_id=managed_group.get("id"),
            created_at=self._parse_datetime(created_at),
            updated_at=self._parse_datetime(updated_at),
        )

    @staticmethod
    def _parse_datetime(value: str | datetime | None) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized)
        return datetime.now(UTC)


@dataclass
class _InMemoryAgent:
    agent_id: str
    name: str
    user_id: str
    character_id: str
    role: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_run_completion: datetime | None = None
    shared_block_ids: list[str] = field(default_factory=list)
    memory_blocks: dict[str, MemoryBlock] = field(default_factory=dict)
    archival_memory: list[ArchivalMemoryItem] = field(default_factory=list)
    steps: list[LettaStepDebug] = field(default_factory=list)
    managed_group_id: str | None = None
    participant_ids: list[str] = field(default_factory=list)


class InMemoryLettaGateway:
    def __init__(self) -> None:
        self._block_counter = count(1)
        self._agent_counter = count(1)
        self._step_counter = count(1)
        self.shared_memory_blocks: dict[str, MemoryBlock] = {}
        self.agents: dict[str, _InMemoryAgent] = {}

    def _next_block_id(self) -> str:
        return f"block-{next(self._block_counter)}"

    def _next_agent_id(self) -> str:
        return f"agent-{next(self._agent_counter)}"

    def _next_step_id(self) -> str:
        return f"step-{next(self._step_counter)}"

    def upsert_shared_memory_blocks(
        self,
        *,
        blocks: list[MemoryBlockSeed],
        existing_block_ids: dict[str, str] | None = None,
    ) -> dict[str, str]:
        existing_block_ids = existing_block_ids or {}
        result: dict[str, str] = {}
        for block in blocks:
            block_id = existing_block_ids.get(block.label, self._next_block_id())
            self.shared_memory_blocks[block_id] = MemoryBlock(
                label=block.label,
                value=block.value,
                block_id=block_id,
                scope="shared",
                description=block.description,
                limit=block.limit,
                read_only=block.read_only,
            )
            result[block.label] = block_id
        return result

    def resolve_session(self, *, create: SessionCreateConfig) -> tuple[LettaSession, bool]:
        existing = next(
            (
                self._session_from_primary(agent)
                for agent in self.agents.values()
                if agent.role == "primary"
                and agent.user_id == create.user_id
                and agent.character_id == create.character.character_id
            ),
            None,
        )
        if existing is not None:
            return existing, False

        primary_id = self._next_agent_id()
        primary = _InMemoryAgent(
            agent_id=primary_id,
            name=build_primary_agent_name(
                character_id=create.character.character_id,
                user_id=create.user_id,
            ),
            user_id=create.user_id,
            character_id=create.character.character_id,
            role="primary",
            shared_block_ids=list(create.character.shared_block_ids.values()),
            memory_blocks={
                "human": MemoryBlock(label="human", value=create.default_user_memory, scope="user")
            },
        )
        self.agents[primary_id] = primary
        sleep_time_agent_id: str | None = None
        if create.character.letta_runtime.sleep_time_agent.enabled:
            sleep_time_agent_id = self._next_agent_id()
            sleep_time_agent = _InMemoryAgent(
                agent_id=sleep_time_agent_id,
                name=build_sleep_time_agent_name(
                    character_id=create.character.character_id,
                    user_id=create.user_id,
                ),
                user_id=create.user_id,
                character_id=create.character.character_id,
                role="sleeptime",
                managed_group_id=f"group-{primary_id}",
            )
            sleep_time_agent.participant_ids = [primary_id, sleep_time_agent_id]
            self.agents[sleep_time_agent_id] = sleep_time_agent
            primary.managed_group_id = f"group-{primary_id}"
            primary.participant_ids = [primary_id, sleep_time_agent_id]
        for item in create.character.archival_memory_seed:
            primary.archival_memory.append(
                ArchivalMemoryItem(
                    text=item, memory_id=f"memory-{len(primary.archival_memory) + 1}"
                )
            )
        return self._session_from_primary(primary), True

    def list_sessions(self) -> list[LettaSession]:
        sessions = [
            self._session_from_primary(agent)
            for agent in self.agents.values()
            if agent.role == "primary"
        ]
        return sorted(sessions, key=lambda item: (item.updated_at, item.created_at), reverse=True)

    def send_user_message(
        self,
        *,
        primary_agent_id: str,
        message: str,
        max_steps: int,
    ) -> LettaTurnResult:
        del max_steps
        agent = self.agents[primary_agent_id]
        reply = f"letta::{message}"
        now = datetime.now(UTC)
        agent.updated_at = now
        agent.last_run_completion = now
        step = LettaStepDebug(
            step_id=self._next_step_id(),
            agent_id=agent.agent_id,
            model="memory-letta-primary",
            model_endpoint="memory://letta",
            model_handle="memory/primary",
            status="success",
            stop_reason="assistant_message",
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            messages=[
                LettaMessageDebug(
                    message_type="user_message",
                    role="user",
                    content=message,
                    raw={"role": "user", "content": message},
                ),
                LettaMessageDebug(
                    message_type="assistant_message",
                    role="assistant",
                    content=reply,
                    raw={"role": "assistant", "content": reply},
                ),
            ],
        )
        agent.steps.insert(0, step)
        current_human = agent.memory_blocks["human"].value
        if message not in current_human:
            agent.memory_blocks["human"] = MemoryBlock(
                label="human",
                value=f"{current_human}\n- Recent topic: {message}".strip(),
                scope="user",
            )
        agent.archival_memory.append(
            ArchivalMemoryItem(
                text=f"User: {message}\nAssistant: {reply}",
                memory_id=f"memory-{len(agent.archival_memory) + 1}",
            )
        )
        if participant_id := self._sleep_time_agent_id(agent):
            sleeper = self.agents[participant_id]
            sleeper.updated_at = now
            sleeper.last_run_completion = now
            sleeper.steps.insert(
                0,
                LettaStepDebug(
                    step_id=self._next_step_id(),
                    agent_id=sleeper.agent_id,
                    model="memory-letta-sleeptime",
                    model_endpoint="memory://letta",
                    model_handle="memory/sleeptime",
                    status="success",
                    stop_reason="done",
                    messages=[
                        LettaMessageDebug(
                            message_type="event_message",
                            role="assistant",
                            content="Updated human block and archival memory.",
                            raw={"event": "sleep_time_complete"},
                        )
                    ],
                ),
            )
        return LettaTurnResult(
            reply=reply,
            response_messages=[
                {"message_type": "user_message", "role": "user", "content": message},
                {"message_type": "assistant_message", "role": "assistant", "content": reply},
            ],
            raw_response={
                "messages": [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": reply},
                ]
            },
        )

    def wait_for_sleep_time(
        self,
        *,
        session: LettaSession,
        baseline_completion: datetime | None,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> bool:
        del timeout_seconds, poll_interval_seconds
        if not session.sleep_time_agent_id:
            return True
        completion = self.get_agent_last_completion(agent_id=session.sleep_time_agent_id)
        return completion is not None and (
            baseline_completion is None or completion > baseline_completion
        )

    def get_agent_last_completion(self, *, agent_id: str) -> datetime | None:
        return self.agents[agent_id].last_run_completion

    def list_recent_steps(self, *, agent_id: str, limit: int) -> list[LettaStepDebug]:
        return list(self.agents[agent_id].steps[:limit])

    def get_memory_context(self, *, agent_id: str, query: str, top_k: int) -> MemoryContext:
        del query
        agent = self.agents[agent_id]
        shared = [
            self.shared_memory_blocks[block_id]
            for block_id in agent.shared_block_ids
            if block_id in self.shared_memory_blocks
        ]
        archival_memory = agent.archival_memory[-top_k:] if top_k else []
        return MemoryContext(
            memory_blocks=[*shared, *agent.memory_blocks.values()], archival_memory=archival_memory
        )

    def get_memory_snapshot(
        self,
        *,
        user_id: str,
        character_id: str,
        session: LettaSession | None,
        shared_memory_blocks: list[MemoryBlockSeed] | None = None,
        archival_memory_limit: int = 10,
    ) -> MemorySnapshot:
        if session is None:
            return MemorySnapshot(
                user_id=user_id,
                character_id=character_id,
                primary_agent_id=None,
                sleep_time_agent_id=None,
                managed_group_id=None,
                memory_blocks=[
                    MemoryBlock(
                        label=block.label,
                        value=block.value,
                        scope="shared",
                        description=block.description,
                        limit=block.limit,
                        read_only=block.read_only,
                    )
                    for block in shared_memory_blocks or []
                ],
                archival_memory=[],
            )
        context = self.get_memory_context(
            agent_id=session.primary_agent_id,
            query="",
            top_k=archival_memory_limit,
        )
        return MemorySnapshot(
            user_id=user_id,
            character_id=character_id,
            primary_agent_id=session.primary_agent_id,
            sleep_time_agent_id=session.sleep_time_agent_id,
            managed_group_id=session.managed_group_id,
            memory_blocks=_apply_block_seed_metadata(
                memory_blocks=context.memory_blocks,
                shared_memory_blocks=shared_memory_blocks,
            ),
            archival_memory=context.archival_memory,
        )

    def delete_session(self, *, session: LettaSession) -> None:
        if session.sleep_time_agent_id:
            self.agents.pop(session.sleep_time_agent_id, None)
        self.agents.pop(session.primary_agent_id, None)

    def _session_from_primary(self, agent: _InMemoryAgent) -> LettaSession:
        return LettaSession(
            user_id=agent.user_id,
            character_id=agent.character_id,
            primary_agent_id=agent.agent_id,
            sleep_time_agent_id=self._sleep_time_agent_id(agent),
            managed_group_id=agent.managed_group_id,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )

    @staticmethod
    def _sleep_time_agent_id(agent: _InMemoryAgent) -> str | None:
        return next((item for item in agent.participant_ids if item != agent.agent_id), None)
