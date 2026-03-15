class MemLLMError(Exception):
    """Base exception for workspace-level failures."""


class CharacterNotFoundError(MemLLMError):
    """Raised when a requested character does not exist in the metadata store."""


class ProviderError(MemLLMError):
    """Raised when a reply provider cannot produce a response."""


class LettaGatewayError(MemLLMError):
    """Raised when Letta operations fail."""
