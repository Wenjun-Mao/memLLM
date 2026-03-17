from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from memllm_api.app import create_app
from memllm_api.settings import ApiSettings


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
  - label: role
    value: Keep track of the user carefully.
archival_memory_seed:
  - durable fact for {character_id}
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


def test_seed_chat_memory_and_session_lifecycle(tmp_path: Path) -> None:
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
    app = create_app(settings)

    with TestClient(app) as client:
        seed_response = client.post("/seed/characters")
        assert seed_response.status_code == 200
        seed_payload = seed_response.json()
        assert {item["character_id"] for item in seed_payload["seeded"]} == {"alpha", "beta"}
        assert all(item["shared_block_ids"] for item in seed_payload["seeded"])

        characters_response = client.get("/characters")
        assert characters_response.status_code == 200
        characters = {item["character_id"]: item for item in characters_response.json()}
        assert characters["alpha"]["letta_runtime"]["primary_agent"]["model_route"] == (
            "ollama_primary"
        )
        assert "reply_provider" not in characters["alpha"]

        chat_response = client.post(
            "/chat",
            json={
                "user_id": "dev-user",
                "character_id": "alpha",
                "message": "remember tea",
            },
        )
        assert chat_response.status_code == 200
        chat_payload = chat_response.json()
        assert chat_payload["reply"] == "letta::remember tea"
        assert chat_payload["provider_kind"] == "ollama_primary"
        assert chat_payload["agent_id"]

        debug = chat_payload["debug"]
        assert debug["final_provider_call"]["route_name"] == "ollama_primary"
        assert debug["prompt_pipeline"]["system_instructions"] == "You are Alpha.\n"
        assert debug["prompt_pipeline"]["working_context"]["shared_memory_blocks"]
        assert debug["prompt_pipeline"]["working_context"]["user_memory_blocks"]
        assert any(
            item["text"] == "durable fact for alpha"
            for item in debug["prompt_pipeline"]["retrieved_archival_memory"]
        )
        assert {event["kind"] for event in debug["trace_events"]} >= {
            "session_resolution",
            "primary_agent_response",
            "gateway_route_call",
            "letta_primary_step",
            "sleep_time_wait",
            "letta_sleep_time_step",
        }
        assert debug["memory_writeback"]["status"] == "completed"
        assert debug["memory_writeback"]["sleep_time_agent_id"] is not None

        sessions_response = client.get("/sessions")
        assert sessions_response.status_code == 200
        sessions = sessions_response.json()
        assert len(sessions) == 1
        assert sessions[0]["character_id"] == "alpha"
        assert sessions[0]["primary_agent_id"] == chat_payload["agent_id"]
        assert sessions[0]["sleep_time_agent_id"] is not None

        memory_response = client.get("/memory/dev-user/alpha")
        assert memory_response.status_code == 200
        snapshot = memory_response.json()
        assert snapshot["primary_agent_id"] == chat_payload["agent_id"]
        assert snapshot["sleep_time_agent_id"] is not None
        assert any(block["label"] == "human" for block in snapshot["memory_blocks"])
        assert any(item["text"] == "durable fact for alpha" for item in snapshot["archival_memory"])

        delete_response = client.delete("/sessions/dev-user/alpha")
        assert delete_response.status_code == 200
        deleted = delete_response.json()
        assert deleted["character_id"] == "alpha"
        assert deleted["primary_agent_id"] == chat_payload["agent_id"]

        sessions_after_delete = client.get("/sessions")
        assert sessions_after_delete.status_code == 200
        assert sessions_after_delete.json() == []

        memory_after_delete = client.get("/memory/dev-user/alpha")
        assert memory_after_delete.status_code == 200
        snapshot_after_delete = memory_after_delete.json()
        assert snapshot_after_delete["primary_agent_id"] is None
        assert any(block["label"] == "role" for block in snapshot_after_delete["memory_blocks"])
