# Runtime Stack

## Purpose

This document explains the current Step 2 runtime: who owns what, how a live turn flows, what the Dev UI panels mean, and where the Dev UI is showing a derived view rather than a private Letta internal.

## Stack Roles

- `Streamlit Dev UI`: operator-facing chat and debug surface.
- `FastAPI API`: thin product layer that resolves characters, resolves or creates Letta sessions, and returns Letta/gateway debug info.
- `Letta`: the live system of record for sessions, conversations, runs, steps, memory blocks, and archival memory.
- `model_gateway`: the OpenAI-compatible route layer used by the default chat routes in the current dev stack.
- `Ollama`: local model execution behind the gateway plus direct local embedding runtime.
- `DouBao`: external final surface model for selected characters.
- `Postgres/pgvector`: Letta storage in Docker.

## One Chat Round

1. The UI sends `user_id`, `character_id`, and `message` to the API.
2. The API resolves or creates the Letta session for that exact `(user_id, character_id)` pair.
3. If the pair is new, the API creates a Letta primary agent, enables a sleep-time agent if configured, attaches shared memory blocks, seeds archival memory, and initializes the `human` block.
4. The API records baseline Letta step ids and gateway trace sequence numbers for the current round.
5. The API sends the user message into Letta.
6. In the standard dev stack, `primary_agent.model_route` is a slashless gateway route such as `ollama_primary` or `doubao_primary`, so Letta calls `model_gateway`.
7. The gateway either proxies the shaped local Qwen route or mediates the route and may render the final text through DouBao.
8. Native `provider/model` handles such as `ollama/...` are still supported experimentally, but they are not the default because the current Qwen GGUF path needs gateway-side `think: false` shaping.
9. In dev mode, the API waits for the Letta sleep-time agent so the current response can include the full current-round trace.
10. The API returns the user-visible reply plus the structured debug payload.

## Memory Surfaces

### Shared memory blocks

Seeded from `shared_memory_blocks` and attached to every Letta session for that character.

### User memory block

The standard Letta `human` block for one `(user_id, character_id)` pair.

### Archival memory

Retrievable long-term snippets stored in Letta passage storage.

There are two sources:

- `archival_memory_seed` copied into the session once at creation time
- later Letta-managed memory work, including sleep-time behavior

## Dev UI Panels

- `Final Provider Call`: the last outbound model call for the current round. For the standard dev stack this is a real gateway trace; for experimental native Letta handles it becomes a derived view because Letta does not expose the raw HTTP payload.
- `Prompt Pipeline`: a derived view from the actual Letta-to-gateway request or, in the native-handle case, the app-visible parts of a Letta provider call.
- `Current-Round Memory Work`: Letta steps, model-gateway calls when present, and sleep-time/background work for this round.
- `Memory Snapshot`: the current live Letta memory blocks and archival memory for this pair.
- `User-Agent Pair`: the Letta primary agent and sleep-time partner for the current session.

## What Is Derived vs Direct

The Dev UI does not claim access to hidden Letta internals.

Directly observed:

- Letta step/message surfaces exposed by the Letta API
- model_gateway request/response traces when the chosen route actually goes through the gateway
- live memory snapshot surfaces from Letta

Derived for operator understanding:

- the `Prompt Pipeline` panel
- the MemGPT `System Instructions + Working Context + FIFO analogue` explanation

## Length Controls

### Controls that already exist

- `system_instructions` length in the manifest
- `shared_memory_blocks` length in the manifest
- `archival_memory_seed` length in the manifest
- Letta request budget via:
  - `MEMLLM_API_LETTA_CONTEXT_WINDOW`
  - `MEMLLM_API_LETTA_MAX_TOKENS`
  - `MEMLLM_API_LETTA_MESSAGE_MAX_STEPS`
- gateway route generation settings in `infra/model_gateway/routes.yaml`, such as:
  - `temperature`
  - `max_tokens`
  - route-specific timeouts

### Controls that do not exist yet

- No hard per-block truncation pass before Letta prompt assembly
- No hard per-archival-item truncation pass before Letta prompt assembly
- No global token-budget optimizer across the full Letta + gateway path
