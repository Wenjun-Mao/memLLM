from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from memllm_domain import CharacterManifest, CharacterRecord


def _manifest_checksum(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


class CharacterManifestLoader:
    def __init__(self, manifest_dir: Path) -> None:
        self._manifest_dir = manifest_dir

    def load_all(self) -> list[CharacterRecord]:
        if not self._manifest_dir.exists():
            return []

        records: list[CharacterRecord] = []
        seen_ids: set[str] = set()
        for path in sorted(self._manifest_dir.glob("*.y*ml")):
            raw_text = path.read_text(encoding="utf-8")
            payload = yaml.safe_load(raw_text) or {}
            manifest = CharacterManifest.model_validate(payload)
            if manifest.character_id in seen_ids:
                raise ValueError(f"Duplicate character_id found: {manifest.character_id}")
            seen_ids.add(manifest.character_id)
            records.append(
                CharacterRecord(
                    **manifest.model_dump(),
                    manifest_path=str(path.as_posix()),
                    manifest_checksum=_manifest_checksum(raw_text),
                )
            )
        return records
