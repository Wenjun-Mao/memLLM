from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse
from memllm_domain import (
    CharacterNotFoundError,
    ChatRequest,
    LettaGatewayError,
    MemLLMError,
    ProviderError,
)
from memllm_letta_integration import InMemoryLettaGateway, RealLettaGateway
from memllm_memory_pipeline import MemoryExtractorRegistry
from memllm_reply_providers import ReplyProviderRegistry

from memllm_api.manifests import CharacterManifestLoader
from memllm_api.services import CharacterSeeder, ChatOrchestrator
from memllm_api.settings import ApiSettings
from memllm_api.store import build_metadata_store


@dataclass
class AppContainer:
    settings: ApiSettings
    seeder: CharacterSeeder
    orchestrator: ChatOrchestrator


def create_container(settings: ApiSettings | None = None) -> AppContainer:
    settings = settings or ApiSettings()
    store = build_metadata_store(
        backend=settings.database_backend, database_url=settings.database_url
    )
    letta_gateway = (
        RealLettaGateway(base_url=settings.letta_base_url, api_key=settings.letta_api_key)
        if settings.letta_mode == "real"
        else InMemoryLettaGateway()
    )
    memory_extractors = MemoryExtractorRegistry.with_defaults(
        ollama_base_url=settings.memory_extractor_base_url,
        ollama_model=settings.memory_extractor_model,
        timeout_seconds=settings.memory_extractor_timeout_seconds,
    )
    reply_providers = ReplyProviderRegistry()
    loader = CharacterManifestLoader(settings.manifest_dir)
    seeder = CharacterSeeder(loader=loader, store=store, letta_gateway=letta_gateway)
    orchestrator = ChatOrchestrator(
        settings=settings,
        store=store,
        letta_gateway=letta_gateway,
        reply_providers=reply_providers,
        memory_extractors=memory_extractors,
    )
    return AppContainer(settings=settings, seeder=seeder, orchestrator=orchestrator)


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    container = create_container(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if container.settings.seed_on_startup:
            container.seeder.seed_all()
        yield

    app = FastAPI(title=container.settings.app_name, lifespan=lifespan)
    app.state.container = container

    @app.exception_handler(CharacterNotFoundError)
    def handle_not_found(_: Request, exc: CharacterNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    @app.exception_handler(LettaGatewayError)
    def handle_upstream_error(_: Request, exc: MemLLMError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/characters")
    def list_characters(request: Request) -> list[dict]:
        container = request.app.state.container
        return [
            character.model_dump(mode="json")
            for character in container.orchestrator.list_characters()
        ]

    @app.post("/seed/characters")
    def seed_characters(request: Request) -> dict:
        container = request.app.state.container
        return container.seeder.seed_all().model_dump(mode="json")

    @app.post("/chat")
    def chat(request: Request, payload: ChatRequest, background_tasks: BackgroundTasks) -> dict:
        container = request.app.state.container
        response, pending = container.orchestrator.prepare_chat(payload)
        if container.settings.debug_inline_memory_writeback:
            persisted = container.orchestrator.persist_turn(pending, capture_debug=True)
            if response.debug is not None and persisted is not None:
                response.debug.memory_writeback = persisted.memory_writeback
                response.debug.trace_events.extend(persisted.trace_events)
        else:
            background_tasks.add_task(container.orchestrator.persist_turn, pending)
        return response.model_dump(mode="json")

    @app.get("/memory/{user_id}/{character_id}")
    def get_memory(request: Request, user_id: str, character_id: str) -> dict:
        container = request.app.state.container
        snapshot = container.orchestrator.get_memory_snapshot(
            user_id=user_id, character_id=character_id
        )
        return snapshot.model_dump(mode="json")

    @app.get("/sessions")
    def list_sessions(request: Request) -> list[dict]:
        container = request.app.state.container
        return [
            session.model_dump(mode="json") for session in container.orchestrator.list_sessions()
        ]

    @app.delete("/sessions/{user_id}/{character_id}")
    def delete_session(request: Request, user_id: str, character_id: str) -> JSONResponse:
        container = request.app.state.container
        deleted = container.orchestrator.delete_session(
            user_id=user_id, character_id=character_id
        )
        if deleted is None:
            return JSONResponse(
                status_code=404,
                content={"detail": f"Unknown session: {user_id}/{character_id}"},
            )
        return JSONResponse(status_code=200, content=deleted.model_dump(mode="json"))

    return app
