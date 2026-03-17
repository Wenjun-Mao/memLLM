from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from memllm_model_gateway.config import load_gateway_routes
from memllm_model_gateway.service import (
    ModelGatewayError,
    ModelGatewayService,
    UnknownModelRouteError,
    UnsupportedRouteError,
)
from memllm_model_gateway.settings import ModelGatewaySettings


@dataclass
class GatewayContainer:
    settings: ModelGatewaySettings
    service: ModelGatewayService


def create_container(settings: ModelGatewaySettings | None = None) -> GatewayContainer:
    settings = settings or ModelGatewaySettings()
    routes_document = load_gateway_routes(settings.routes_path)
    service = ModelGatewayService(
        routes_document=routes_document,
        trace_retention_limit=settings.trace_retention_limit,
    )
    return GatewayContainer(settings=settings, service=service)


def create_app(settings: ModelGatewaySettings | None = None) -> FastAPI:
    container = create_container(settings)
    app = FastAPI(title='memllm-model-gateway')
    app.state.container = container

    @app.exception_handler(UnknownModelRouteError)
    def handle_unknown_route(_: object, exc: UnknownModelRouteError) -> JSONResponse:
        return JSONResponse(status_code=404, content={'detail': str(exc)})

    @app.exception_handler(UnsupportedRouteError)
    def handle_unsupported_route(_: object, exc: UnsupportedRouteError) -> JSONResponse:
        return JSONResponse(status_code=400, content={'detail': str(exc)})

    @app.exception_handler(ModelGatewayError)
    def handle_gateway_error(_: object, exc: ModelGatewayError) -> JSONResponse:
        return JSONResponse(status_code=502, content={'detail': str(exc)})

    @app.get('/health')
    def health() -> dict[str, str]:
        return {'status': 'ok'}

    @app.get('/v1/models')
    def list_models() -> dict:
        return container.service.list_models()

    @app.post('/v1/chat/completions')
    def chat_completions(payload: dict) -> dict:
        return container.service.chat_completions(payload)

    @app.post('/v1/embeddings')
    def embeddings(payload: dict) -> dict:
        return container.service.embeddings(payload)

    @app.get('/debug/traces')
    def debug_traces(since_sequence: int = 0, limit: int = 200) -> dict:
        return container.service.list_traces(since_sequence=since_sequence, limit=limit)

    @app.get('/debug/sequence')
    def debug_sequence() -> dict[str, int]:
        return {'latest_sequence': container.service.latest_sequence()}

    return app
