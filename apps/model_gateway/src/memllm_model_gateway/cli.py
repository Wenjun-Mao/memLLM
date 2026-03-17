from __future__ import annotations

import uvicorn

from memllm_model_gateway.app import create_app
from memllm_model_gateway.settings import ModelGatewaySettings


def main() -> None:
    settings = ModelGatewaySettings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == '__main__':
    main()
