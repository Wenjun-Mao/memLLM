# Model Gateway

## Purpose

`model_gateway` is the place that knows raw connection details for mediated or vendor-specific routes.

Character manifests can use either native Letta provider handles like `ollama/...` or slashless named routes that resolve through `model_gateway`. In the standard dev stack, the gateway remains the default for DouBao and for the current local Qwen chat/sleep-time routes because it applies request shaping that Letta-native Ollama calls do not currently expose.
That shaping currently includes two Qwen/Ollama-specific behaviors that matter in practice: forcing `think: false` on the native Ollama chat call, and normalizing Letta/OpenAI-style tool follow-up messages into the exact Ollama tool-message shape (`function.arguments` as objects and tool responses keyed by `tool_name`).

## Public Surface

The gateway exposes the minimum OpenAI-compatible surface needed by Letta:

- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/embeddings`

For debugging it also exposes:

- `GET /debug/sequence`
- `GET /debug/traces`

## Route Config

The operator-facing route config lives at:

- `infra/model_gateway/routes.yaml`

Supported route kinds:

- `openai_chat_proxy`
- `ollama_embedding_proxy`
- `custom_simple_http_surface`
- `tool_mediated_surface`

## Default Routes

- `doubao_primary`: mediated primary route
- `ollama_primary`: default local chat route and the local policy route used by the mediated DouBao path
- `ollama_sleep_time`: default local sleep-time route
- `doubao_surface`: final external surface-render route
- `qwen3-embedding`: optional fallback embedding route

## Mediated DouBao Flow

1. Letta calls `doubao_primary` like a normal OpenAI chat-completions model.
2. The gateway first calls `ollama_primary`.
3. If the policy route emits tool calls, the gateway passes them through to Letta.
4. If the policy route emits a final answer, the gateway sends that draft plus context to `doubao_surface`.
5. The gateway returns the rendered final answer to Letta as a normal chat-completions response.

## Route Ownership Rule

Keep these in the gateway config, not in character manifests, whenever a route actually uses the gateway:

- raw endpoints
- auth headers
- timeouts
- temperature / max-token defaults
- vendor-specific request-shape quirks
