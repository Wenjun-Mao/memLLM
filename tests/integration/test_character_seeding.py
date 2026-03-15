from __future__ import annotations

from pathlib import Path

from memllm_api.manifests import CharacterManifestLoader
from memllm_api.services import CharacterSeeder
from memllm_api.store import InMemoryMetadataStore
from memllm_letta_integration import InMemoryLettaGateway


def _write_manifest(path: Path, *, character_id: str, display_name: str) -> None:
    path.write_text(
        f"""
character_id: {character_id}
display_name: {display_name}
description: test character
persona: test persona
reply_provider:
  kind: ollama_chat
  base_url: http://localhost:11434
  model: qwen3.5:9b
shared_blocks:
  - label: style
    value: calm and direct
""".strip(),
        encoding="utf-8",
    )


def test_character_seeding_is_idempotent(tmp_path: Path) -> None:
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    _write_manifest(manifests_dir / "guide.yaml", character_id="guide", display_name="Guide")

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
    assert store.get_character("guide") is not None
