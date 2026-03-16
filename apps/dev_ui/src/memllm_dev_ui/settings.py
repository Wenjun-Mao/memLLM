from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

SECRETS_DIR = Path("/run/secrets")


class DevUiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEMLLM_DEV_UI_",
        env_nested_delimiter="__",
        secrets_dir=str(SECRETS_DIR) if SECRETS_DIR.exists() else None,
        extra="ignore",
    )

    api_base_url: str = "http://127.0.0.1:8000"
    default_user_id: str = "dev-user-001"
    request_timeout_seconds: float = 300.0

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
