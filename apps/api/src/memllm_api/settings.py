from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

SECRETS_DIR = Path('/run/secrets')


class ApiBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='MEMLLM_API_',
        env_nested_delimiter='__',
        secrets_dir=str(SECRETS_DIR) if SECRETS_DIR.exists() else None,
        extra='ignore',
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, file_secret_settings, env_settings, dotenv_settings


class ApiSettings(ApiBaseSettings):
    app_name: str = 'memllm-api'
    host: str = '127.0.0.1'
    port: int = 8000
    reload: bool = False

    manifest_dir: Path = Path('characters/manifests')
    seed_on_startup: bool = False

    database_backend: Literal['sqlalchemy', 'memory'] = 'sqlalchemy'
    database_url: str = 'postgresql+psycopg://memllm:memllm@localhost:5432/memllm'

    letta_mode: Literal['real', 'memory'] = 'real'
    letta_base_url: str = 'http://localhost:8283'
    letta_api_key: str | None = None
    letta_model: str = 'ollama/memllm-qwen3.5-9b-q4km'
    letta_embedding: str = 'ollama/qwen3-embedding:0.6b'
    letta_use_direct_model_config: bool = True
    letta_model_name: str = 'memllm-qwen3.5-9b-q4km:latest'
    letta_model_endpoint: str = 'http://ollama:11434/v1'
    letta_model_context_window: int = 262144
    letta_model_max_tokens: int = 1024
    letta_embedding_name: str = 'qwen3-embedding:0.6b'
    letta_embedding_endpoint: str = 'http://ollama:11434/v1'
    letta_embedding_dim: int = 1024

    memory_extractor_kind: Literal['heuristic', 'ollama_json'] = 'ollama_json'
    memory_extractor_base_url: str = 'http://localhost:11434'
    memory_extractor_model: str = 'memllm-qwen3.5-9b-q4km'
    memory_extractor_timeout_seconds: float = 45.0
    reply_provider_ollama_base_url: str = 'http://localhost:11434'
