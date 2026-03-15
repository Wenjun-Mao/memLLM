# Provider Adapters

## Purpose

All user-facing reply generation goes through a stable adapter interface so the project can switch
providers without changing the chat orchestration logic.

## Implemented Adapters

### `custom_simple_http`

Used for providers with a simplified nonstandard contract such as:

```text
GET /chat_new_ai?user_content=...&system_content=...
```

The adapter:

- flattens memory context and conversation history into text
- maps those fields into `system_content` and `user_content`
- normalizes the provider response back into a common shape

### `ollama_chat`

Used for local model replies through Ollama's OpenAI-compatible endpoint:

- base URL: `http://localhost:11434/v1`
- endpoint: `/chat/completions`
- current default local model alias: `memllm-qwen3.5-9b-q4km`

Official reference:

- https://docs.ollama.com/api/openai-compatibility

If you want an exact quantized build such as `Q4_K_M`, import the GGUF into Ollama under a stable
project alias and point the app at that alias instead of relying on a generic library tag.

## Future Direction

- add auth-aware providers
- add provider health checks and benchmarking
- support richer response metadata and tool use when needed
