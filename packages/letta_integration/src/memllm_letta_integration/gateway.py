from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import count
from typing import Protocol

from memllm_domain import (
    ArchivalMemoryItem,
    LettaGatewayError,
    MemoryBlock,
    MemoryBlockSeed,
    MemoryContext,
    MemoryDelta,
    MemorySnapshot,
    MemoryWriteOperation,
)


class LettaGateway(Protocol):
    def upsert_shared_memory_blocks(
        self,
        *,
        blocks: list[MemoryBlockSeed],
        existing_block_ids: dict[str, str] | None = None,
    ) -> dict[str, str]: ...

    def create_session_agent(
        self,
        *,
        agent_name: str,
        shared_block_ids: list[str],
        model: str,
        embedding: str,
        llm_config: LettaLLMConfig | None = None,
        embedding_config: LettaEmbeddingConfig | None = None,
        initial_user_memory: str,
    ) -> str: ...

    def get_memory_context(self, *, agent_id: str, query: str, top_k: int) -> MemoryContext: ...

    def get_memory_snapshot(
        self,
        *,
        user_id: str,
        character_id: str,
        agent_id: str | None,
        shared_memory_blocks: list[MemoryBlockSeed] | None = None,
        archival_memory_limit: int = 10,
    ) -> MemorySnapshot: ...

    def apply_memory_delta(
        self,
        *,
        agent_id: str,
        delta: MemoryDelta,
    ) -> list[MemoryWriteOperation]: ...

    def delete_session_agent(self, *, agent_id: str) -> None: ...


def _iter_page_items(page: object) -> Iterable[object]:
    if page is None:
        return []
    if isinstance(page, list):
        return page
    if hasattr(page, 'data'):
        return page.data
    return page


@dataclass(frozen=True)
class LettaLLMConfig:
    model: str
    endpoint: str
    context_window: int
    max_tokens: int
    endpoint_type: str = 'openai'


@dataclass(frozen=True)
class LettaEmbeddingConfig:
    model: str
    endpoint: str
    embedding_dim: int
    endpoint_type: str = 'openai'
    batch_size: int = 32
    chunk_size: int = 300


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
        if block.scope != 'shared':
            decorated.append(block)
            continue
        seed = metadata.get(block.label)
        if seed is None:
            decorated.append(block)
            continue
        decorated.append(
            block.model_copy(
                update={
                    'description': seed.description,
                    'limit': seed.limit,
                    'read_only': seed.read_only,
                }
            )
        )
    return decorated


class RealLettaGateway:
    def __init__(self, *, base_url: str, api_key: str | None = None) -> None:
        from letta_client import Letta

        kwargs = {'base_url': base_url}
        if api_key:
            kwargs['api_key'] = api_key
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
                results[block.label] = getattr(updated, 'id', block_id)
            else:
                created = self._client.blocks.create(label=block.label, value=block.value)
                results[block.label] = created.id
        return results

    def create_session_agent(
        self,
        *,
        agent_name: str,
        shared_block_ids: list[str],
        model: str,
        embedding: str,
        llm_config: LettaLLMConfig | None = None,
        embedding_config: LettaEmbeddingConfig | None = None,
        initial_user_memory: str,
    ) -> str:
        create_kwargs: dict[str, object] = {
            'name': agent_name,
            'memory_blocks': [{'label': 'human', 'value': initial_user_memory}],
            'block_ids': shared_block_ids,
        }
        if llm_config and embedding_config:
            create_kwargs['llm_config'] = {
                'model': llm_config.model,
                'model_endpoint_type': llm_config.endpoint_type,
                'model_endpoint': llm_config.endpoint,
                'context_window': llm_config.context_window,
                'max_tokens': llm_config.max_tokens,
            }
            create_kwargs['embedding_config'] = {
                'embedding_model': embedding_config.model,
                'embedding_endpoint_type': embedding_config.endpoint_type,
                'embedding_endpoint': embedding_config.endpoint,
                'embedding_dim': embedding_config.embedding_dim,
                'batch_size': embedding_config.batch_size,
                'embedding_chunk_size': embedding_config.chunk_size,
            }
        else:
            create_kwargs['model'] = model
            create_kwargs['embedding'] = embedding
        agent = self._client.agents.create(**create_kwargs)
        return agent.id

    def get_memory_context(self, *, agent_id: str, query: str, top_k: int) -> MemoryContext:
        try:
            block_page = self._client.agents.blocks.list(agent_id=agent_id)
            memory_blocks = [
                MemoryBlock(
                    label=block.label,
                    value=block.value,
                    block_id=getattr(block, 'id', None),
                    scope='shared' if block.label != 'human' else 'user',
                )
                for block in _iter_page_items(block_page)
            ]
            if query:
                result = self._client.agents.passages.search(
                    agent_id=agent_id, query=query, top_k=top_k
                )
                archival_items = getattr(result, 'passages', [])
            else:
                archival_items = _iter_page_items(
                    self._client.agents.passages.list(agent_id=agent_id, limit=top_k)
                )
            archival_memory = [
                ArchivalMemoryItem(
                    text=getattr(item, 'text', ''),
                    memory_id=getattr(item, 'id', None),
                    score=getattr(item, 'score', None),
                )
                for item in archival_items
            ]
            return MemoryContext(memory_blocks=memory_blocks, archival_memory=archival_memory)
        except Exception as exc:  # noqa: BLE001
            raise LettaGatewayError('Failed to retrieve Letta memory context.') from exc

    def get_memory_snapshot(
        self,
        *,
        user_id: str,
        character_id: str,
        agent_id: str | None,
        shared_memory_blocks: list[MemoryBlockSeed] | None = None,
        archival_memory_limit: int = 10,
    ) -> MemorySnapshot:
        if not agent_id:
            return MemorySnapshot(
                user_id=user_id,
                character_id=character_id,
                agent_id=None,
                memory_blocks=[
                    MemoryBlock(
                        label=block.label,
                        value=block.value,
                        scope='shared',
                        description=block.description,
                        limit=block.limit,
                        read_only=block.read_only,
                    )
                    for block in shared_memory_blocks or []
                ],
                archival_memory=[],
            )

        context = self.get_memory_context(agent_id=agent_id, query='', top_k=archival_memory_limit)
        return MemorySnapshot(
            user_id=user_id,
            character_id=character_id,
            agent_id=agent_id,
            memory_blocks=_apply_block_seed_metadata(
                memory_blocks=context.memory_blocks,
                shared_memory_blocks=shared_memory_blocks,
            ),
            archival_memory=context.archival_memory,
        )

    def apply_memory_delta(
        self,
        *,
        agent_id: str,
        delta: MemoryDelta,
    ) -> list[MemoryWriteOperation]:
        operations: list[MemoryWriteOperation] = []
        try:
            if delta.user_memory_block_value:
                self._client.agents.blocks.update(
                    agent_id=agent_id,
                    block_label='human',
                    value=delta.user_memory_block_value,
                )
                operations.append(
                    MemoryWriteOperation(
                        kind='memory_block_update',
                        target='human',
                        value=delta.user_memory_block_value,
                    )
                )
            for entry in delta.archival_memory_entries:
                created = self._client.agents.passages.create(agent_id=agent_id, text=entry)
                operations.append(
                    MemoryWriteOperation(
                        kind='archival_memory_insert',
                        target='archival_memory',
                        value=entry,
                        memory_id=getattr(created, 'id', None),
                    )
                )
            return operations
        except Exception as exc:  # noqa: BLE001
            raise LettaGatewayError('Failed to apply memory delta to Letta.') from exc

    def delete_session_agent(self, *, agent_id: str) -> None:
        try:
            self._client.agents.delete(agent_id=agent_id)
        except Exception as exc:  # noqa: BLE001
            raise LettaGatewayError(f'Failed to delete Letta agent: {agent_id}.') from exc


@dataclass
class _InMemoryAgent:
    agent_id: str
    name: str
    shared_block_ids: list[str]
    memory_blocks: dict[str, MemoryBlock] = field(default_factory=dict)
    archival_memory: list[ArchivalMemoryItem] = field(default_factory=list)


class InMemoryLettaGateway:
    def __init__(self) -> None:
        self._block_counter = count(1)
        self._agent_counter = count(1)
        self.shared_memory_blocks: dict[str, MemoryBlock] = {}
        self.agents: dict[str, _InMemoryAgent] = {}

    def _next_block_id(self) -> str:
        return f'block-{next(self._block_counter)}'

    def _next_agent_id(self) -> str:
        return f'agent-{next(self._agent_counter)}'

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
                scope='shared',
                description=block.description,
                limit=block.limit,
                read_only=block.read_only,
            )
            result[block.label] = block_id
        return result

    def create_session_agent(
        self,
        *,
        agent_name: str,
        shared_block_ids: list[str],
        model: str,
        embedding: str,
        llm_config: LettaLLMConfig | None = None,
        embedding_config: LettaEmbeddingConfig | None = None,
        initial_user_memory: str,
    ) -> str:
        del model, embedding, llm_config, embedding_config
        agent_id = self._next_agent_id()
        self.agents[agent_id] = _InMemoryAgent(
            agent_id=agent_id,
            name=agent_name,
            shared_block_ids=shared_block_ids,
            memory_blocks={
                'human': MemoryBlock(label='human', value=initial_user_memory, scope='user')
            },
        )
        return agent_id

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
            memory_blocks=[*shared, *agent.memory_blocks.values()],
            archival_memory=archival_memory,
        )

    def get_memory_snapshot(
        self,
        *,
        user_id: str,
        character_id: str,
        agent_id: str | None,
        shared_memory_blocks: list[MemoryBlockSeed] | None = None,
        archival_memory_limit: int = 10,
    ) -> MemorySnapshot:
        del archival_memory_limit
        if not agent_id:
            return MemorySnapshot(
                user_id=user_id,
                character_id=character_id,
                agent_id=None,
                memory_blocks=[
                    MemoryBlock(
                        label=block.label,
                        value=block.value,
                        scope='shared',
                        description=block.description,
                        limit=block.limit,
                        read_only=block.read_only,
                    )
                    for block in shared_memory_blocks or []
                ],
                archival_memory=[],
            )

        context = self.get_memory_context(agent_id=agent_id, query='', top_k=0)
        return MemorySnapshot(
            user_id=user_id,
            character_id=character_id,
            agent_id=agent_id,
            memory_blocks=_apply_block_seed_metadata(
                memory_blocks=context.memory_blocks,
                shared_memory_blocks=shared_memory_blocks,
            ),
            archival_memory=self.agents[agent_id].archival_memory,
        )

    def apply_memory_delta(
        self,
        *,
        agent_id: str,
        delta: MemoryDelta,
    ) -> list[MemoryWriteOperation]:
        agent = self.agents[agent_id]
        operations: list[MemoryWriteOperation] = []
        if delta.user_memory_block_value:
            agent.memory_blocks['human'] = MemoryBlock(
                label='human', value=delta.user_memory_block_value, scope='user'
            )
            operations.append(
                MemoryWriteOperation(
                    kind='memory_block_update',
                    target='human',
                    value=delta.user_memory_block_value,
                )
            )
        for entry in delta.archival_memory_entries:
            if not any(existing.text == entry for existing in agent.archival_memory):
                memory_id = f'memory-{len(agent.archival_memory) + 1}'
                agent.archival_memory.append(
                    ArchivalMemoryItem(
                        text=entry,
                        memory_id=memory_id,
                    )
                )
                operations.append(
                    MemoryWriteOperation(
                        kind='archival_memory_insert',
                        target='archival_memory',
                        value=entry,
                        memory_id=memory_id,
                    )
                )
        return operations

    def delete_session_agent(self, *, agent_id: str) -> None:
        self.agents.pop(agent_id, None)
