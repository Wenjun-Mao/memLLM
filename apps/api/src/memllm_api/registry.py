from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from memllm_domain.models import DomainModel
from pydantic import Field


class CharacterBootstrapEntry(DomainModel):
    character_id: str
    manifest_checksum: str
    shared_block_ids: dict[str, str] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BootstrapRegistryDocument(DomainModel):
    version: int = 2
    characters: dict[str, CharacterBootstrapEntry] = Field(default_factory=dict)


class FileBootstrapRegistry:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def get(self, character_id: str) -> CharacterBootstrapEntry | None:
        return self._load().characters.get(character_id)

    def list_entries(self) -> list[CharacterBootstrapEntry]:
        return list(self._load().characters.values())

    def upsert(self, entry: CharacterBootstrapEntry) -> CharacterBootstrapEntry:
        document = self._load()
        document.characters[entry.character_id] = entry
        self._save(document)
        return entry

    def prune(self, valid_character_ids: set[str]) -> None:
        document = self._load()
        document.characters = {
            key: value
            for key, value in document.characters.items()
            if key in valid_character_ids
        }
        self._save(document)

    def _load(self) -> BootstrapRegistryDocument:
        if not self._path.exists():
            return BootstrapRegistryDocument()
        payload = json.loads(self._path.read_text(encoding='utf-8'))
        return BootstrapRegistryDocument.model_validate(payload)

    def _save(self, document: BootstrapRegistryDocument) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(f'{self._path.suffix}.tmp')
        temp_path.write_text(document.model_dump_json(indent=2), encoding='utf-8')
        temp_path.replace(self._path)
