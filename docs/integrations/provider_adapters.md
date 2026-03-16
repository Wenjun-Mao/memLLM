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

Used for local model replies through Ollama.

Current default behavior:

- manifest base URL: usually `http://localhost:11434`
- runtime override for Dockerized API: `MEMLLM_API_REPLY_PROVIDER_OLLAMA_BASE_URL`
- default mode: native `/api/generate`
- prompt format: explicit ChatML-style prompt assembled by the app
- current default local model alias: `memllm-qwen3.5-9b-q4km`
- keep-alive: `-1`, so the local chat model stays loaded until Ollama is restarted or removed

Why the native path is the default:

- the imported Qwen 3.5 9B GGUF produced better local replies through `/api/generate`
  with an explicit prompt than through Ollama's OpenAI-compatible `/v1/chat/completions`
  path in the current phase-1 setup

Optional compatibility mode:

- set `reply_provider.extra.api_mode=chat_completions` if a later Ollama-served model works
  better through the OpenAI-compatible endpoint

Official references:

- https://docs.ollama.com/api/generate
- https://docs.ollama.com/api/openai-compatibility

If you want an exact quantized build such as `Q4_K_M`, import the GGUF into Ollama under a stable
project alias and point the app at that alias instead of relying on a generic library tag.

## Future Direction

- add auth-aware providers
- add provider health checks and benchmarking
- support richer response metadata and tool use when needed
