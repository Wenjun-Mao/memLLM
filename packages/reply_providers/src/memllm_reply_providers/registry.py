from __future__ import annotations

from memllm_domain import ProviderConfig, ProviderError, ProviderResponse, ReplyRequest

from memllm_reply_providers.providers import (
    CustomSimpleHttpReplyProvider,
    OllamaChatReplyProvider,
    ReplyProvider,
)


class ReplyProviderRegistry:
    def __init__(self, providers: list[ReplyProvider] | None = None) -> None:
        provider_items = providers or [
            CustomSimpleHttpReplyProvider(),
            OllamaChatReplyProvider(),
        ]
        self._providers = {provider.kind: provider for provider in provider_items}

    def generate(self, config: ProviderConfig, request: ReplyRequest) -> ProviderResponse:
        provider = self._providers.get(config.kind)
        if not provider:
            raise ProviderError(f"Unsupported reply provider: {config.kind}")
        return provider.generate(config=config, request=request)
