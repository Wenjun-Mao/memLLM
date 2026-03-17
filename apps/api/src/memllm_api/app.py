from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from memllm_domain import CharacterNotFoundError, ChatRequest, LettaGatewayError, MemLLMError
from memllm_letta_integration import InMemoryLettaGateway, RealLettaGateway

from memllm_api.manifests import CharacterManifestLoader
from memllm_api.model_gateway_client import (
    InMemoryModelGatewayDebugClient,
    ModelGatewayDebugClient,
)
from memllm_api.registry import FileBootstrapRegistry
from memllm_api.services import CharacterSeeder, ChatOrchestrator
from memllm_api.settings import ApiSettings


@dataclass
class AppContainer:
    settings: ApiSettings
    loader: CharacterManifestLoader
    registry: FileBootstrapRegistry
    seeder: CharacterSeeder
    orchestrator: ChatOrchestrator


def create_container(settings: ApiSettings | None = None) -> AppContainer:
    settings = settings or ApiSettings()
    registry = FileBootstrapRegistry(settings.bootstrap_registry_path)
    loader = CharacterManifestLoader(settings.manifest_dir, registry=registry)
    if settings.letta_mode == 'real':
        letta_gateway = RealLettaGateway(
            base_url=settings.letta_base_url,
            api_key=settings.letta_api_key,
        )
        model_gateway_debug = ModelGatewayDebugClient(base_url=settings.model_gateway_base_url)
    else:
        letta_gateway = InMemoryLettaGateway()
        model_gateway_debug = InMemoryModelGatewayDebugClient()

    seeder = CharacterSeeder(loader=loader, registry=registry, letta_gateway=letta_gateway)
    orchestrator = ChatOrchestrator(
        settings=settings,
        loader=loader,
        registry=registry,
        letta_gateway=letta_gateway,
        model_gateway_debug=model_gateway_debug,
    )
    return AppContainer(
        settings=settings,
        loader=loader,
        registry=registry,
        seeder=seeder,
        orchestrator=orchestrator,
    )


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
        return JSONResponse(status_code=404, content={'detail': str(exc)})

    @app.exception_handler(LettaGatewayError)
    def handle_upstream_error(_: Request, exc: MemLLMError) -> JSONResponse:
        return JSONResponse(status_code=502, content={'detail': str(exc)})

    @app.get('/health')
    def health() -> dict[str, str]:
        return {'status': 'ok'}

    @app.get('/characters')
    def list_characters(request: Request) -> list[dict]:
        container = request.app.state.container
        return [
            character.model_dump(mode='json')
            for character in container.orchestrator.list_characters()
        ]

    @app.post('/seed/characters')
    def seed_characters(request: Request) -> dict:
        container = request.app.state.container
        return container.seeder.seed_all().model_dump(mode='json')

    @app.post('/chat')
    def chat(request: Request, payload: ChatRequest) -> dict:
        container = request.app.state.container
        return container.orchestrator.chat(payload).model_dump(mode='json')

    @app.get('/memory/{user_id}/{character_id}')
    def get_memory(request: Request, user_id: str, character_id: str) -> dict:
        container = request.app.state.container
        snapshot = container.orchestrator.get_memory_snapshot(
            user_id=user_id,
            character_id=character_id,
        )
        return snapshot.model_dump(mode='json')

    @app.get('/sessions')
    def list_sessions(request: Request) -> list[dict]:
        container = request.app.state.container
        return [
            session.model_dump(mode='json') for session in container.orchestrator.list_sessions()
        ]

    @app.delete('/sessions/{user_id}/{character_id}')
    def delete_session(request: Request, user_id: str, character_id: str) -> JSONResponse:
        container = request.app.state.container
        deleted = container.orchestrator.delete_session(
            user_id=user_id,
            character_id=character_id,
        )
        if deleted is None:
            return JSONResponse(
                status_code=404,
                content={'detail': f'Unknown session: {user_id}/{character_id}'},
            )
        return JSONResponse(status_code=200, content=deleted.model_dump(mode='json'))

    return app
