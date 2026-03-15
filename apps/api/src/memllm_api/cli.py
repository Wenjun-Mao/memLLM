from __future__ import annotations

import uvicorn

from memllm_api.settings import ApiSettings


def main() -> None:
    settings = ApiSettings()
    uvicorn.run(
        "memllm_api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )
