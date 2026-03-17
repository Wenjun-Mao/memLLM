from __future__ import annotations

from pathlib import Path

from memllm_api.manifests import CharacterManifestLoader
from memllm_api.model_gateway_client import InMemoryModelGatewayDebugClient
from memllm_api.registry import FileBootstrapRegistry
from memllm_api.services import CharacterSeeder, ChatOrchestrator
from memllm_api.settings import ApiSettings
from memllm_domain import ChatRequest
from memllm_letta_integration import InMemoryLettaGateway


def _write_manifest(path: Path, *, character_id: str, display_name: str, route: str) -> None:
    path.write_text(
        (
            f"""
character_id: {character_id}
display_name: {display_name}
description: test character {character_id}
system_instructions: |
  You are {display_name}.
shared_memory_blocks:
  - label: style
    description: shared style rules
    value: calm and direct
archival_memory_seed:
  - seed memory for {character_id}
letta_runtime:
  primary_agent:
    model_route: {route}
  sleep_time_agent:
    enabled: true
    model_route: ollama_sleep_time
    frequency: 1
""".strip()
        )
        + "\n",
        encoding="utf-8",
    )


def _build_orchestrator(tmp_path: Path) -> ChatOrchestrator:
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    _write_manifest(
        manifests_dir / "alpha.yaml",
        character_id="alpha",
        display_name="Alpha",
        route="ollama_primary",
    )
    _write_manifest(
        manifests_dir / "beta.yaml",
        character_id="beta",
        display_name="Beta",
        route="doubao_primary",
    )

    settings = ApiSettings(
        manifest_dir=manifests_dir,
        bootstrap_registry_path=tmp_path / "bootstrap_registry.json",
        letta_mode="memory",
        seed_on_startup=False,
    )
    registry = FileBootstrapRegistry(settings.bootstrap_registry_path)
    loader = CharacterManifestLoader(settings.manifest_dir, registry=registry)
    letta_gateway = InMemoryLettaGateway()
    seeder = CharacterSeeder(loader=loader, registry=registry, letta_gateway=letta_gateway)
    seeder.seed_all()
    return ChatOrchestrator(
        settings=settings,
        loader=loader,
        registry=registry,
        letta_gateway=letta_gateway,
        model_gateway_debug=InMemoryModelGatewayDebugClient(),
    )


def test_sessions_are_isolated_per_user_character_pair(tmp_path: Path) -> None:
    orchestrator = _build_orchestrator(tmp_path)

    response_a = orchestrator.chat(
        ChatRequest(user_id="u1", character_id="alpha", message="hello alpha")
    )
    response_b = orchestrator.chat(
        ChatRequest(user_id="u1", character_id="beta", message="hello beta")
    )
    response_c = orchestrator.chat(
        ChatRequest(user_id="u2", character_id="alpha", message="hello again")
    )

    assert response_a.agent_id != response_b.agent_id
    assert response_a.agent_id != response_c.agent_id

    sessions = orchestrator.list_sessions()
    assert len(sessions) == 3
    assert {(item.user_id, item.character_id) for item in sessions} == {
        ("u1", "alpha"),
        ("u1", "beta"),
        ("u2", "alpha"),
    }

    snapshot_a = orchestrator.get_memory_snapshot(user_id="u1", character_id="alpha")
    snapshot_b = orchestrator.get_memory_snapshot(user_id="u1", character_id="beta")
    snapshot_c = orchestrator.get_memory_snapshot(user_id="u2", character_id="alpha")

    assert snapshot_a.primary_agent_id != snapshot_b.primary_agent_id
    assert snapshot_a.primary_agent_id != snapshot_c.primary_agent_id
    assert any(item.text == "seed memory for alpha" for item in snapshot_a.archival_memory)
    assert any(item.text == "seed memory for beta" for item in snapshot_b.archival_memory)
    assert "Recent topic: hello alpha" in next(
        block.value for block in snapshot_a.memory_blocks if block.label == "human"
    )
    assert "Recent topic: hello again" in next(
        block.value for block in snapshot_c.memory_blocks if block.label == "human"
    )


def test_chat_returns_letta_native_debug_trace_and_delete_works(tmp_path: Path) -> None:
    orchestrator = _build_orchestrator(tmp_path)

    response = orchestrator.chat(
        ChatRequest(user_id="u1", character_id="alpha", message="trace this round")
    )

    assert response.provider_kind == "ollama_primary"
    assert response.debug is not None
    assert response.debug.final_provider_call is not None
    assert response.debug.final_provider_call.route_name == "ollama_primary"
    assert response.debug.prompt_pipeline is not None
    assert response.debug.prompt_pipeline.system_instructions == "You are Alpha.\n"
    assert any(event.kind == "session_resolution" for event in response.debug.trace_events)
    assert any(event.kind == "gateway_route_call" for event in response.debug.trace_events)
    assert response.debug.memory_writeback is not None
    assert response.debug.memory_writeback.status == "completed"
    assert response.debug.memory_writeback.sleep_time_agent_id is not None

    deleted = orchestrator.delete_session(user_id="u1", character_id="alpha")
    assert deleted is not None
    assert deleted.primary_agent_id == response.agent_id
    assert orchestrator.list_sessions() == []

    snapshot = orchestrator.get_memory_snapshot(user_id="u1", character_id="alpha")
    assert snapshot.primary_agent_id is None
    assert any(block.label == "style" for block in snapshot.memory_blocks)


def test_chat_prefers_primary_gateway_trace_over_sleep_time_trace(tmp_path: Path) -> None:
    orchestrator = _build_orchestrator(tmp_path)
    orchestrator._settings.debug_wait_for_sleep_time = False
    gateway_debug = orchestrator._model_gateway_debug

    def fake_list_traces(*, since_sequence: int, limit: int):
        del since_sequence, limit
        return [
            {
                "sequence": 1,
                "created_at": "2026-03-16T00:00:00Z",
                "phase": "direct_chat_route_call",
                "route_name": "ollama_primary",
                "method": "POST",
                "url": "http://gateway/primary",
                "headers": {},
                "payload": {"messages": [{"role": "user", "content": "trace me"}]},
                "response": {"ok": True},
                "status_code": 200,
            },
            {
                "sequence": 2,
                "created_at": "2026-03-16T00:00:01Z",
                "phase": "direct_chat_route_call",
                "route_name": "ollama_sleep_time",
                "method": "POST",
                "url": "http://gateway/sleep",
                "headers": {},
                "payload": {"messages": [{"role": "user", "content": "sleep trace"}]},
                "response": {"ok": True},
                "status_code": 200,
            },
        ]

    gateway_debug.list_traces = fake_list_traces
    gateway_debug.latest_sequence = lambda: 0

    response = orchestrator.chat(
        ChatRequest(user_id="u1", character_id="alpha", message="trace me")
    )

    assert response.debug is not None
    assert response.debug.final_provider_call is not None
    assert response.debug.final_provider_call.route_name == "ollama_primary"
    assert response.debug.prompt_pipeline is not None
    assert response.debug.prompt_pipeline.final_provider_payload == {
        "messages": [{"role": "user", "content": "trace me"}]
    }
