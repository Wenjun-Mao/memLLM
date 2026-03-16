from __future__ import annotations

from pathlib import Path

import pytest
from memllm_api.manifests import CharacterManifestLoader
from memllm_api.services import CharacterSeeder
from memllm_api.store import InMemoryMetadataStore
from memllm_letta_integration import InMemoryLettaGateway
from pydantic import ValidationError


def _write_manifest(path: Path, *, body: str) -> None:
    path.write_text(body.strip(), encoding='utf-8')


def test_character_seeding_is_idempotent(tmp_path: Path) -> None:
    manifests_dir = tmp_path / 'manifests'
    manifests_dir.mkdir()
    _write_manifest(
        manifests_dir / 'guide.yaml',
        body="""
character_id: guide
display_name: Guide
description: test character
system_instructions: test instructions
reply_provider:
  kind: ollama_chat
  base_url: http://localhost:11434
  model: qwen3.5:9b
shared_memory_blocks:
  - label: style
    value: calm and direct
archival_memory_seed:
  - durable fact one
""",
    )

    store = InMemoryMetadataStore()
    letta_gateway = InMemoryLettaGateway()
    seeder = CharacterSeeder(
        loader=CharacterManifestLoader(manifests_dir),
        store=store,
        letta_gateway=letta_gateway,
    )

    first = seeder.seed_all()
    second = seeder.seed_all()

    assert first.seeded[0].created is True
    assert second.seeded[0].created is False
    assert first.seeded[0].shared_block_ids == second.seeded[0].shared_block_ids
    assert store.get_character('guide') is not None


def test_manifest_loader_rejects_old_schema_keys(tmp_path: Path) -> None:
    manifests_dir = tmp_path / 'manifests'
    manifests_dir.mkdir()
    _write_manifest(
        manifests_dir / 'legacy.yaml',
        body="""
character_id: legacy
display_name: Legacy
description: old schema test
persona: old field should fail
reply_provider:
  kind: ollama_chat
  base_url: http://localhost:11434
  model: qwen3.5:9b
""",
    )

    loader = CharacterManifestLoader(manifests_dir)

    with pytest.raises(ValidationError):
        loader.load_all()
