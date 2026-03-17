from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

SECRETS_DIR = Path('/run/secrets')


class ModelGatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='MEMLLM_MODEL_GATEWAY_',
        env_nested_delimiter='__',
        secrets_dir=str(SECRETS_DIR) if SECRETS_DIR.exists() else None,
        extra='ignore',
    )

    host: str = '127.0.0.1'
    port: int = 9100
    reload: bool = False
    routes_path: Path = Path('infra/model_gateway/routes.yaml')
    trace_retention_limit: int = 500

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
