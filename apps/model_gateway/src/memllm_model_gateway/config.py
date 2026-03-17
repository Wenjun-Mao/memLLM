from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class GatewayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpenAIChatRoute(GatewayModel):
    kind: Literal["openai_chat_proxy"]
    base_url: str
    model: str
    timeout_seconds: float = 45.0
    headers: dict[str, str] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)
    visible: bool = True


class OllamaEmbeddingRoute(GatewayModel):
    kind: Literal["ollama_embedding_proxy"]
    base_url: str
    model: str
    timeout_seconds: float = 45.0
    headers: dict[str, str] = Field(default_factory=dict)
    visible: bool = True


class SimpleSurfaceRoute(GatewayModel):
    kind: Literal["custom_simple_http_surface"]
    endpoint: str
    transport: Literal["get", "post"] = "get"
    timeout_seconds: float = 45.0
    headers: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)
    visible: bool = False


class ToolMediatedSurfaceRoute(GatewayModel):
    kind: Literal["tool_mediated_surface"]
    policy_route: str
    surface_route: str
    visible: bool = True
    passthrough_tool_calls: bool = True
    surface_fallback_to_policy_text: bool = True


GatewayRoute = (
    OpenAIChatRoute | OllamaEmbeddingRoute | SimpleSurfaceRoute | ToolMediatedSurfaceRoute
)


class GatewayRoutesDocument(GatewayModel):
    routes: dict[str, GatewayRoute]


_ENV_VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand_env_vars(value: object) -> object:
    if isinstance(value, str):
        return _ENV_VAR_RE.sub(lambda match: os.environ.get(match.group(1), ""), value)
    if isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env_vars(item) for key, item in value.items()}
    return value


def load_gateway_routes(path: Path) -> GatewayRoutesDocument:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    expanded = _expand_env_vars(payload)
    return GatewayRoutesDocument.model_validate(expanded)
