from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from memllm_domain import CharacterManifest, CharacterRecord

from memllm_api.registry import FileBootstrapRegistry


def _manifest_checksum(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


class CharacterManifestLoader:
    def __init__(
        self, manifest_dir: Path, *, registry: FileBootstrapRegistry | None = None
    ) -> None:
        self._manifest_dir = manifest_dir
        self._registry = registry

    def load_all(self) -> list[CharacterRecord]:
        if not self._manifest_dir.exists():
            return []

        records: list[CharacterRecord] = []
        seen_ids: set[str] = set()
        for path in sorted(self._manifest_dir.glob("*.y*ml")):
            record = self._load_path(path)
            if record.character_id in seen_ids:
                raise ValueError(f"Duplicate character_id found: {record.character_id}")
            seen_ids.add(record.character_id)
            records.append(record)
        return records

    def load_character(self, character_id: str) -> CharacterRecord | None:
        for path in sorted(self._manifest_dir.glob("*.y*ml")):
            record = self._load_path(path)
            if record.character_id == character_id:
                return record
        return None

    def _load_path(self, path: Path) -> CharacterRecord:
        raw_text = path.read_text(encoding="utf-8")
        payload = yaml.safe_load(raw_text) or {}
        manifest = CharacterManifest.model_validate(payload)
        shared_block_ids: dict[str, str] = {}
        if self._registry is not None:
            entry = self._registry.get(manifest.character_id)
            if entry is not None:
                shared_block_ids = dict(entry.shared_block_ids)
        return CharacterRecord(
            **manifest.model_dump(),
            manifest_path=str(path.as_posix()),
            manifest_checksum=_manifest_checksum(raw_text),
            shared_block_ids=shared_block_ids,
        )
