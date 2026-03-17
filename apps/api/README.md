# memllm-api

FastAPI product/API layer for the Letta-native memLLM runtime.

It is intentionally thin:

- loads character manifests
- seeds shared Letta blocks
- resolves or creates Letta sessions
- sends chat turns into Letta
- returns Letta and model-gateway debug data for the Dev UI
