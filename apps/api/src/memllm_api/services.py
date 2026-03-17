from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from memllm_domain import (
    CharacterNotFoundError,
    CharacterRecord,
    ChatDebugTrace,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    GatewayTraceDebug,
    LettaSession,
    LettaStepDebug,
    MemoryBlock,
    MemorySnapshot,
    MemoryWritebackDebug,
    PromptPipelineDebug,
    ProviderCallDebug,
    SeedReport,
    SeedReportItem,
    SessionSummary,
    TraceEvent,
    WorkingContextDebug,
    is_native_provider_handle,
)
from memllm_letta_integration import (
    LettaEmbeddingConfig,
    LettaGateway,
    LettaLLMConfig,
    SessionCreateConfig,
)

from memllm_api.manifests import CharacterManifestLoader
from memllm_api.model_gateway_client import (
    InMemoryModelGatewayDebugClient,
    ModelGatewayDebugClient,
)
from memllm_api.registry import CharacterBootstrapEntry, FileBootstrapRegistry
from memllm_api.settings import ApiSettings

TRACE_EVENT_SPECS = {
    "session_resolution": {
        "title": "Session Resolution",
        "description": "Create or reuse the Letta-managed primary agent and sleep-time partner.",
        "paper_mapping": "Agent lifecycle before the main conversational loop.",
    },
    "primary_agent_response": {
        "title": "Primary Agent Response",
        "description": (
            "The primary Letta agent handled the user message and produced the live reply."
        ),
        "paper_mapping": "Main MemGPT conversation loop.",
    },
    "letta_primary_step": {
        "title": "Letta Primary Step",
        "description": (
            "A Letta step from the primary agent, including tool use or final assistant output."
        ),
        "paper_mapping": "Working Context + FIFO queue execution.",
    },
    "gateway_route_call": {
        "title": "Gateway Route Call",
        "description": (
            "A model-gateway call triggered by Letta for policy, surface rendering, or embeddings."
        ),
        "paper_mapping": "Model endpoint invocation visible from the Letta-native runtime.",
    },
    "native_provider_call": {
        "title": "Native Provider Call",
        "description": (
            "A Letta-native provider/model handle was used directly, "
            "so the raw HTTP payload stays inside Letta."
        ),
        "paper_mapping": "Model endpoint invocation visible only through Letta-exposed state.",
    },
    "sleep_time_wait": {
        "title": "Sleep-Time Wait",
        "description": (
            "Wait for the Letta sleep-time/background agent so the "
            "full current-round trace is visible."
        ),
        "paper_mapping": "Background memory consolidation.",
    },
    "letta_sleep_time_step": {
        "title": "Sleep-Time Step",
        "description": (
            "A Letta sleep-time/background step that updated the primary agent memory surfaces."
        ),
        "paper_mapping": "Background memory consolidation.",
    },
}


@dataclass
class CharacterSeeder:
    loader: CharacterManifestLoader
    registry: FileBootstrapRegistry
    letta_gateway: LettaGateway

    def seed_all(self) -> SeedReport:
        items: list[SeedReportItem] = []
        valid_ids: set[str] = set()
        for record in self.loader.load_all():
            valid_ids.add(record.character_id)
            existing = self.registry.get(record.character_id)
            shared_block_ids = self.letta_gateway.upsert_shared_memory_blocks(
                blocks=record.seed_shared_memory_blocks(),
                existing_block_ids=existing.shared_block_ids if existing else None,
            )
            self.registry.upsert(
                CharacterBootstrapEntry(
                    character_id=record.character_id,
                    manifest_checksum=record.manifest_checksum,
                    shared_block_ids=shared_block_ids,
                )
            )
            items.append(
                SeedReportItem(
                    character_id=record.character_id,
                    display_name=record.display_name,
                    created=existing is None,
                    shared_block_ids=shared_block_ids,
                )
            )
        self.registry.prune(valid_ids)
        return SeedReport(seeded=items)


def _event(kind: str, *, request: object = None, response: object = None) -> TraceEvent:
    spec = TRACE_EVENT_SPECS[kind]
    return TraceEvent(
        kind=kind,
        title=spec["title"],
        description=spec["description"],
        paper_mapping=spec["paper_mapping"],
        request=request,
        response=response,
    )


def _split_working_context(memory_blocks: list[MemoryBlock]) -> WorkingContextDebug:
    shared_memory_blocks: list[MemoryBlock] = []
    user_memory_blocks: list[MemoryBlock] = []
    for block in memory_blocks:
        if block.scope == "shared":
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
        loader: CharacterManifestLoader,
        registry: FileBootstrapRegistry,
        letta_gateway: LettaGateway,
        model_gateway_debug: ModelGatewayDebugClient | InMemoryModelGatewayDebugClient,
    ) -> None:
        self._settings = settings
        self._loader = loader
        self._registry = registry
        self._letta_gateway = letta_gateway
        self._model_gateway_debug = model_gateway_debug

    def list_characters(self) -> list[CharacterRecord]:
        return self._loader.load_all()

    def chat(self, request: ChatRequest) -> ChatResponse:
        character = self._loader.load_character(request.character_id)
        if not character:
            raise CharacterNotFoundError(f"Unknown character: {request.character_id}")

        session, created = self._letta_gateway.resolve_session(
            create=SessionCreateConfig(
                user_id=request.user_id,
                character=character,
                primary_llm=self._build_primary_llm(character),
                sleep_time_llm=self._build_sleep_time_llm(character),
                embedding=self._build_embedding_config(),
                default_user_memory=self._settings.letta_default_user_memory_block,
            )
        )

        trace_events: list[TraceEvent] = [
            _event(
                "session_resolution",
                request={"user_id": request.user_id, "character_id": character.character_id},
                response={
                    "created": created,
                    "primary_agent_id": session.primary_agent_id,
                    "sleep_time_agent_id": session.sleep_time_agent_id,
                    "managed_group_id": session.managed_group_id,
                },
            )
        ]

        pre_memory_context = self._letta_gateway.get_memory_context(
            agent_id=session.primary_agent_id,
            query=request.message,
            top_k=6,
        )
        baseline_primary_ids = {
            step.step_id
            for step in self._letta_gateway.list_recent_steps(
                agent_id=session.primary_agent_id, limit=self._settings.debug_step_limit
            )
        }
        baseline_sleep_ids: set[str] = set()
        baseline_sleep_completion = None
        if session.sleep_time_agent_id:
            baseline_sleep_ids = {
                step.step_id
                for step in self._letta_gateway.list_recent_steps(
                    agent_id=session.sleep_time_agent_id,
                    limit=self._settings.debug_step_limit,
                )
            }
            baseline_sleep_completion = self._letta_gateway.get_agent_last_completion(
                agent_id=session.sleep_time_agent_id
            )
        baseline_gateway_sequence = self._model_gateway_debug.latest_sequence()

        turn = self._letta_gateway.send_user_message(
            primary_agent_id=session.primary_agent_id,
            message=request.message,
            max_steps=self._settings.letta_message_max_steps,
        )
        trace_events.append(
            _event(
                "primary_agent_response",
                request={"primary_agent_id": session.primary_agent_id, "message": request.message},
                response=turn.raw_response,
            )
        )

        sleep_time_completed = True
        if self._settings.debug_wait_for_sleep_time and session.sleep_time_agent_id:
            sleep_time_completed = self._letta_gateway.wait_for_sleep_time(
                session=session,
                baseline_completion=baseline_sleep_completion,
                timeout_seconds=self._settings.debug_sleep_time_timeout_seconds,
                poll_interval_seconds=self._settings.debug_sleep_time_poll_interval_seconds,
            )
            trace_events.append(
                _event(
                    "sleep_time_wait",
                    request={
                        "sleep_time_agent_id": session.sleep_time_agent_id,
                        "timeout_seconds": self._settings.debug_sleep_time_timeout_seconds,
                    },
                    response={"completed": sleep_time_completed},
                )
            )

        primary_route = character.letta_runtime.primary_agent.model_route
        primary_route_is_native = is_native_provider_handle(primary_route)
        gateway_traces = self._model_gateway_debug.list_traces(
            since_sequence=baseline_gateway_sequence,
            limit=self._settings.model_gateway_trace_limit,
        )
        if (
            not gateway_traces
            and not primary_route_is_native
            and isinstance(self._model_gateway_debug, InMemoryModelGatewayDebugClient)
        ):
            gateway_traces = self._synthesize_memory_traces(character=character, request=request)

        primary_steps = self._new_steps(
            agent_id=session.primary_agent_id,
            baseline_ids=baseline_primary_ids,
        )
        sleep_steps = []
        if session.sleep_time_agent_id:
            sleep_steps = self._new_steps(
                agent_id=session.sleep_time_agent_id,
                baseline_ids=baseline_sleep_ids,
            )

        for step in primary_steps:
            trace_events.append(
                _event(
                    "letta_primary_step",
                    response=step.model_dump(mode="json"),
                )
            )
        for trace in gateway_traces:
            trace_events.append(
                _event(
                    "gateway_route_call",
                    response=trace,
                )
            )
        native_provider_payload = None
        if primary_route_is_native:
            native_provider_payload = self._build_native_provider_payload(
                character=character,
                request=request,
            )
            trace_events.append(
                _event(
                    "native_provider_call",
                    request=native_provider_payload,
                    response={
                        "model": primary_route,
                        "reply": turn.reply,
                        "source": "derived_from_letta_native_provider",
                    },
                )
            )
        for step in sleep_steps:
            trace_events.append(
                _event(
                    "letta_sleep_time_step",
                    response=step.model_dump(mode="json"),
                )
            )

        prompt_trace = self._pick_prompt_trace(gateway_traces, primary_route)
        final_trace = self._pick_final_provider_trace(gateway_traces, primary_route)
        final_provider_call = self._build_final_provider_call(final_trace)
        prompt_pipeline = self._build_prompt_pipeline(
            character=character,
            memory_blocks=pre_memory_context.memory_blocks,
            archival_memory=pre_memory_context.archival_memory,
            prompt_trace=prompt_trace,
        )
        if primary_route_is_native and native_provider_payload is not None:
            final_provider_call = self._build_native_provider_call(
                route_name=primary_route,
                payload=native_provider_payload,
                reply=turn.reply,
            )
            prompt_pipeline = self._build_native_prompt_pipeline(
                character=character,
                memory_blocks=pre_memory_context.memory_blocks,
                archival_memory=pre_memory_context.archival_memory,
                payload=native_provider_payload,
            )
        response = ChatResponse(
            user_id=request.user_id,
            character_id=request.character_id,
            agent_id=session.primary_agent_id,
            reply=turn.reply,
            provider_kind=character.letta_runtime.primary_agent.model_route,
            debug=ChatDebugTrace(
                final_provider_call=final_provider_call,
                prompt_pipeline=prompt_pipeline,
                trace_events=trace_events,
                memory_writeback=MemoryWritebackDebug(
                    status="completed" if sleep_time_completed else "timed_out",
                    sleep_time_agent_id=session.sleep_time_agent_id,
                    letta_steps=sleep_steps,
                    gateway_traces=[
                        self._trace_to_debug(trace)
                        for trace in gateway_traces
                        if trace.get("route_name")
                        == character.letta_runtime.sleep_time_agent.model_route
                    ],
                    notes=(
                        ["Sleep-time agent is disabled for this character."]
                        if not session.sleep_time_agent_id
                        else []
                    ),
                ),
            ),
        )
        return response

    def get_memory_snapshot(self, user_id: str, character_id: str) -> MemorySnapshot:
        character = self._loader.load_character(character_id)
        if not character:
            raise CharacterNotFoundError(f"Unknown character: {character_id}")
        session = self._find_session(user_id=user_id, character_id=character_id)
        return self._letta_gateway.get_memory_snapshot(
            user_id=user_id,
            character_id=character_id,
            session=session,
            shared_memory_blocks=character.seed_shared_memory_blocks(),
            archival_memory_limit=12,
        )

    def list_sessions(self) -> list[SessionSummary]:
        characters = {
            character.character_id: character.display_name for character in self._loader.load_all()
        }
        return [
            SessionSummary(
                user_id=session.user_id,
                character_id=session.character_id,
                character_display_name=characters.get(session.character_id, session.character_id),
                primary_agent_id=session.primary_agent_id,
                sleep_time_agent_id=session.sleep_time_agent_id,
                managed_group_id=session.managed_group_id,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
            for session in self._letta_gateway.list_sessions()
        ]

    def delete_session(self, *, user_id: str, character_id: str) -> SessionSummary | None:
        session = self._find_session(user_id=user_id, character_id=character_id)
        if session is None:
            return None
        character = self._loader.load_character(character_id)
        self._letta_gateway.delete_session(session=session)
        return SessionSummary(
            user_id=session.user_id,
            character_id=session.character_id,
            character_display_name=(character.display_name if character else character_id),
            primary_agent_id=session.primary_agent_id,
            sleep_time_agent_id=session.sleep_time_agent_id,
            managed_group_id=session.managed_group_id,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    def _build_primary_llm(self, character: CharacterRecord) -> LettaLLMConfig:
        route = character.letta_runtime.primary_agent.model_route
        native_provider = is_native_provider_handle(route)
        return LettaLLMConfig(
            model_route=route,
            endpoint=(None if native_provider else self._settings.letta_gateway_endpoint),
            context_window=self._settings.letta_context_window,
            max_tokens=self._settings.letta_max_tokens,
            native_provider=native_provider,
        )

    def _build_sleep_time_llm(self, character: CharacterRecord) -> LettaLLMConfig | None:
        if not character.letta_runtime.sleep_time_agent.enabled:
            return None
        route = character.letta_runtime.sleep_time_agent.model_route
        native_provider = is_native_provider_handle(route)
        return LettaLLMConfig(
            model_route=route,
            endpoint=(None if native_provider else self._settings.letta_gateway_endpoint),
            context_window=self._settings.letta_context_window,
            max_tokens=self._settings.letta_max_tokens,
            native_provider=native_provider,
        )

    def _build_embedding_config(self) -> LettaEmbeddingConfig:
        return LettaEmbeddingConfig(
            model_route=self._settings.letta_embedding_route,
            endpoint=self._settings.letta_embedding_endpoint,
            embedding_dim=self._settings.letta_embedding_dim,
        )

    def _find_session(self, *, user_id: str, character_id: str) -> LettaSession | None:
        for session in self._letta_gateway.list_sessions():
            if session.user_id == user_id and session.character_id == character_id:
                return session
        return None

    def _new_steps(self, *, agent_id: str, baseline_ids: set[str]) -> list[LettaStepDebug]:
        return [
            step
            for step in self._letta_gateway.list_recent_steps(
                agent_id=agent_id,
                limit=self._settings.debug_step_limit,
            )
            if step.step_id not in baseline_ids
        ]

    def _pick_prompt_trace(
        self,
        traces: list[dict[str, Any]],
        primary_route: str,
    ) -> dict[str, Any] | None:
        for trace in reversed(traces):
            if (
                trace.get("phase") == "direct_chat_route_call"
                and trace.get("route_name") == primary_route
            ):
                return trace
        return None

    def _pick_final_provider_trace(
        self,
        traces: list[dict[str, Any]],
        primary_route: str,
    ) -> dict[str, Any] | None:
        for trace in reversed(traces):
            if trace.get("phase") == "surface_route_call":
                return trace
        for trace in reversed(traces):
            if (
                trace.get("phase") == "direct_chat_route_call"
                and trace.get("route_name") == primary_route
            ):
                return trace
        return None

    def _build_prompt_pipeline(
        self,
        *,
        character: CharacterRecord,
        memory_blocks: list[MemoryBlock],
        archival_memory: list[Any],
        prompt_trace: dict[str, Any] | None,
    ) -> PromptPipelineDebug:
        messages: list[ChatMessage] = []
        final_payload: object = None
        if prompt_trace is not None:
            final_payload = prompt_trace.get("payload")
            payload_messages = (prompt_trace.get("payload") or {}).get("messages", [])
            for message in payload_messages:
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role", "assistant"))
                if role not in {"system", "user", "assistant", "tool"}:
                    continue
                messages.append(
                    ChatMessage(
                        role=role,
                        content=self._message_content_to_text(message.get("content")),
                        name=message.get("name"),
                        tool_call_id=message.get("tool_call_id"),
                    )
                )
        return PromptPipelineDebug(
            system_instructions=character.system_instructions,
            working_context=_split_working_context(memory_blocks),
            conversation_window=messages,
            retrieved_archival_memory=list(archival_memory),
            final_provider_payload=final_payload,
        )

    def _build_final_provider_call(self, trace: dict[str, Any] | None) -> ProviderCallDebug | None:
        if trace is None:
            return None
        return ProviderCallDebug(
            route_name=trace.get("route_name"),
            phase=trace.get("phase"),
            method=str(trace.get("method", "POST")),
            url=str(trace.get("url", "")),
            headers=dict(trace.get("headers", {})),
            payload=trace.get("payload"),
            response=trace.get("response"),
        )

    def _build_native_provider_payload(
        self,
        *,
        character: CharacterRecord,
        request: ChatRequest,
    ) -> dict[str, Any]:
        return {
            "source": "derived_from_letta_native_provider",
            "model": character.letta_runtime.primary_agent.model_route,
            "system_instructions": character.system_instructions,
            "messages": [
                {"role": "user", "content": request.message},
            ],
            "note": (
                "Letta does not expose the raw provider HTTP payload for native provider handles. "
                "This view shows the app-visible parts of the prompt pipeline."
            ),
        }

    def _build_native_provider_call(
        self,
        *,
        route_name: str,
        payload: dict[str, Any],
        reply: str,
    ) -> ProviderCallDebug:
        return ProviderCallDebug(
            route_name=route_name,
            phase="native_provider_call_derived",
            method="LETTA-NATIVE",
            url=f"letta://provider/{route_name}",
            headers={},
            payload=payload,
            response={
                "reply": reply,
                "source": "derived_from_letta_native_provider",
            },
        )

    def _build_native_prompt_pipeline(
        self,
        *,
        character: CharacterRecord,
        memory_blocks: list[MemoryBlock],
        archival_memory: list[Any],
        payload: dict[str, Any],
    ) -> PromptPipelineDebug:
        messages = [
            ChatMessage(
                role="user",
                content=self._message_content_to_text(message.get("content")),
                name=message.get("name"),
                tool_call_id=message.get("tool_call_id"),
            )
            for message in payload.get("messages", [])
            if isinstance(message, dict)
        ]
        return PromptPipelineDebug(
            system_instructions=character.system_instructions,
            working_context=_split_working_context(memory_blocks),
            conversation_window=messages,
            retrieved_archival_memory=list(archival_memory),
            final_provider_payload=payload,
        )

    def _trace_to_debug(self, trace: dict[str, Any]) -> GatewayTraceDebug:
        return GatewayTraceDebug.model_validate(trace)

    @staticmethod
    def _message_content_to_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(part for part in parts if part)
        if content is None:
            return ""
        return str(content)

    def _synthesize_memory_traces(
        self,
        *,
        character: CharacterRecord,
        request: ChatRequest,
    ) -> list[dict[str, Any]]:
        return [
            {
                "phase": "direct_chat_route_call",
                "route_name": character.letta_runtime.primary_agent.model_route,
                "method": "POST",
                "url": "memory://model-gateway/v1/chat/completions",
                "headers": {},
                "payload": {
                    "model": character.letta_runtime.primary_agent.model_route,
                    "messages": [
                        {"role": "system", "content": character.system_instructions},
                        {"role": "user", "content": request.message},
                    ],
                },
                "response": {
                    "choices": [
                        {"message": {"role": "assistant", "content": f"letta::{request.message}"}}
                    ]
                },
                "status_code": 200,
            }
        ]
