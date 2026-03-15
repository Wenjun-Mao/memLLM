from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from memllm_domain import CharacterRecord, ChatTurn, SessionRecord
from sqlalchemy import JSON, DateTime, Engine, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def utc_now() -> datetime:
    return datetime.now(UTC)


class MetadataStore(Protocol):
    def list_characters(self) -> list[CharacterRecord]: ...

    def get_character(self, character_id: str) -> CharacterRecord | None: ...

    def upsert_character(self, record: CharacterRecord) -> tuple[CharacterRecord, bool]: ...

    def get_session(self, user_id: str, character_id: str) -> SessionRecord | None: ...

    def upsert_session(self, record: SessionRecord) -> SessionRecord: ...

    def list_recent_chat_turns(
        self, user_id: str, character_id: str, limit: int
    ) -> list[ChatTurn]: ...

    def add_chat_turn(self, turn: ChatTurn) -> ChatTurn: ...


class InMemoryMetadataStore:
    def __init__(self) -> None:
        self._characters: dict[str, CharacterRecord] = {}
        self._sessions: dict[tuple[str, str], SessionRecord] = {}
        self._turns: list[ChatTurn] = []

    def list_characters(self) -> list[CharacterRecord]:
        return sorted(self._characters.values(), key=lambda item: item.character_id)

    def get_character(self, character_id: str) -> CharacterRecord | None:
        return self._characters.get(character_id)

    def upsert_character(self, record: CharacterRecord) -> tuple[CharacterRecord, bool]:
        created = record.character_id not in self._characters
        self._characters[record.character_id] = record
        return record, created

    def get_session(self, user_id: str, character_id: str) -> SessionRecord | None:
        return self._sessions.get((user_id, character_id))

    def upsert_session(self, record: SessionRecord) -> SessionRecord:
        self._sessions[(record.user_id, record.character_id)] = record
        return record

    def list_recent_chat_turns(self, user_id: str, character_id: str, limit: int) -> list[ChatTurn]:
        turns = [
            turn
            for turn in self._turns
            if turn.user_id == user_id and turn.character_id == character_id
        ]
        return turns[-limit:]

    def add_chat_turn(self, turn: ChatTurn) -> ChatTurn:
        self._turns.append(turn)
        return turn


class Base(DeclarativeBase):
    pass


class CharacterRow(Base):
    __tablename__ = "characters"

    character_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text())
    persona: Mapped[str] = mapped_column(Text())
    system_prompt: Mapped[str | None] = mapped_column(Text(), nullable=True)
    reply_provider: Mapped[dict] = mapped_column(JSON())
    memory_settings: Mapped[dict] = mapped_column(JSON())
    shared_blocks: Mapped[list] = mapped_column(JSON())
    shared_passages: Mapped[list] = mapped_column(JSON())
    manifest_path: Mapped[str] = mapped_column(String(500))
    manifest_checksum: Mapped[str] = mapped_column(String(128))
    shared_block_ids: Mapped[dict] = mapped_column(JSON())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SessionRow(Base):
    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    character_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(200))
    provider_override: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ChatTurnRow(Base):
    __tablename__ = "chat_turns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True)
    character_id: Mapped[str] = mapped_column(String(120), index=True)
    agent_id: Mapped[str] = mapped_column(String(200))
    user_message: Mapped[str] = mapped_column(Text())
    assistant_message: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


def _row_to_character(row: CharacterRow) -> CharacterRecord:
    return CharacterRecord(
        character_id=row.character_id,
        display_name=row.display_name,
        description=row.description,
        persona=row.persona,
        system_prompt=row.system_prompt,
        reply_provider=row.reply_provider,
        memory=row.memory_settings,
        shared_blocks=row.shared_blocks,
        shared_passages=row.shared_passages,
        manifest_path=row.manifest_path,
        manifest_checksum=row.manifest_checksum,
        shared_block_ids=row.shared_block_ids,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _character_to_payload(record: CharacterRecord) -> dict:
    payload = record.model_dump()
    payload["memory_settings"] = payload.pop("memory")
    return payload


def _row_to_session(row: SessionRow) -> SessionRecord:
    return SessionRecord(
        user_id=row.user_id,
        character_id=row.character_id,
        agent_id=row.agent_id,
        provider_override=row.provider_override,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_turn(row: ChatTurnRow) -> ChatTurn:
    return ChatTurn(
        user_id=row.user_id,
        character_id=row.character_id,
        agent_id=row.agent_id,
        user_message=row.user_message,
        assistant_message=row.assistant_message,
        created_at=row.created_at,
    )


class SQLAlchemyMetadataStore:
    def __init__(self, *, database_url: str) -> None:
        self._engine = create_sqlalchemy_engine(database_url)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)
        self.create_schema()

    @property
    def engine(self) -> Engine:
        return self._engine

    def create_schema(self) -> None:
        Base.metadata.create_all(self._engine)

    def list_characters(self) -> list[CharacterRecord]:
        with self._session_factory() as session:
            rows = session.scalars(select(CharacterRow).order_by(CharacterRow.character_id)).all()
            return [_row_to_character(row) for row in rows]

    def get_character(self, character_id: str) -> CharacterRecord | None:
        with self._session_factory() as session:
            row = session.get(CharacterRow, character_id)
            return _row_to_character(row) if row else None

    def upsert_character(self, record: CharacterRecord) -> tuple[CharacterRecord, bool]:
        payload = _character_to_payload(record)
        with self._session_factory() as session:
            row = session.get(CharacterRow, record.character_id)
            created = row is None
            if row is None:
                row = CharacterRow(**payload)
                session.add(row)
            else:
                for key, value in payload.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _row_to_character(row), created

    def get_session(self, user_id: str, character_id: str) -> SessionRecord | None:
        with self._session_factory() as session:
            row = session.get(SessionRow, {"user_id": user_id, "character_id": character_id})
            return _row_to_session(row) if row else None

    def upsert_session(self, record: SessionRecord) -> SessionRecord:
        payload = record.model_dump()
        with self._session_factory() as session:
            row = session.get(
                SessionRow, {"user_id": record.user_id, "character_id": record.character_id}
            )
            if row is None:
                row = SessionRow(**payload)
                session.add(row)
            else:
                for key, value in payload.items():
                    setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return _row_to_session(row)

    def list_recent_chat_turns(self, user_id: str, character_id: str, limit: int) -> list[ChatTurn]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ChatTurnRow)
                .where(ChatTurnRow.user_id == user_id, ChatTurnRow.character_id == character_id)
                .order_by(ChatTurnRow.created_at.desc())
                .limit(limit)
            ).all()
            return list(reversed([_row_to_turn(row) for row in rows]))

    def add_chat_turn(self, turn: ChatTurn) -> ChatTurn:
        payload = turn.model_dump()
        with self._session_factory() as session:
            row = ChatTurnRow(**payload)
            session.add(row)
            session.commit()
            session.refresh(row)
            return _row_to_turn(row)


def create_sqlalchemy_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    kwargs: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        Path(".data").mkdir(exist_ok=True)
    if database_url.endswith(":memory:"):
        kwargs["poolclass"] = StaticPool
    return create_engine(database_url, connect_args=connect_args, **kwargs)


def build_metadata_store(*, backend: str, database_url: str) -> MetadataStore:
    if backend == "memory":
        return InMemoryMetadataStore()
    return SQLAlchemyMetadataStore(database_url=database_url)
