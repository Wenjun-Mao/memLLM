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
    bootstrap_registry_path: Path = Path('characters/seeds/bootstrap_registry.json')
    seed_on_startup: bool = False

    letta_mode: Literal['real', 'memory'] = 'real'
    letta_base_url: str = 'http://localhost:8283'
    letta_api_key: str | None = None
    letta_gateway_endpoint: str = 'http://localhost:9100/v1'
    letta_gateway_endpoint_type: Literal['openai'] = 'openai'
    letta_embedding_route: str = 'qwen3-embedding:0.6b'
    letta_embedding_endpoint: str = 'http://localhost:11434/v1'
    letta_embedding_dim: int = 1024
    letta_context_window: int = 262144
    letta_max_tokens: int = 1024
    letta_message_max_steps: int = 16
    letta_default_user_memory_block: str = 'No durable user memory has been captured yet.'

    model_gateway_base_url: str = 'http://localhost:9100'
    model_gateway_trace_limit: int = 200

    debug_wait_for_sleep_time: bool = True
    debug_sleep_time_timeout_seconds: float = 60.0
    debug_sleep_time_poll_interval_seconds: float = 1.0
    debug_step_limit: int = 12
