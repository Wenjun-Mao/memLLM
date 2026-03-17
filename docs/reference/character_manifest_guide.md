# Character Manifest Guide

## Purpose

Character manifests now describe only two things:

- character identity and memory seed
- Letta-facing runtime route choices

They no longer carry raw provider endpoints, headers, or app-managed memory policy knobs.

## Current Schema

### `system_instructions`

The full Letta system layer for the primary conversational agent.

Use it for:

- identity and stable behavior
- language rules
- honesty constraints
- formatting bans
- style boundaries

### `shared_memory_blocks`

Shared Letta memory blocks attached to every session for the same character.

Use them for reusable facets such as:

- `style`
- `background`
- `relationship_rules`
- `safety_overrides`

Supported fields per block:

- `label`
- `value`
- optional `description`
- optional `limit`
- optional `read_only`

### `archival_memory_seed`

Short archival-memory entries copied into each new user/character session exactly once.

These are real archival-memory items, not synthesized lore blocks.

Use them for durable snippets that should be searchable later.

### `letta_runtime`

Selects either native Letta provider handles or named `model_gateway` routes for the character.

- `primary_agent.model_route`
- `sleep_time_agent.enabled`
- `sleep_time_agent.model_route`
- `sleep_time_agent.frequency`

Use slashless names such as `doubao_primary`, `ollama_primary`, and `ollama_sleep_time` for the standard dev stack. Native `provider/model` strings such as `ollama/memllm-qwen3.5-9b-q4km:latest` remain supported for experiments, but they are not the default because the current Qwen GGUF path needs gateway-side shaping like `think: false`.

The manifest should not contain raw provider URLs or auth data. Those belong in the gateway route config.

## Old to New Mapping

| Old key | Step 2 replacement |
|---|---|
| `persona` + `system_prompt` | `system_instructions` |
| `shared_blocks` | `shared_memory_blocks` |
| `shared_passages` | `archival_memory_seed` |
| `reply_provider.*` | `letta_runtime.primary_agent.model_route` plus gateway config |
| `memory.*` | removed from the manifest; Letta owns the live runtime behavior |
| `initial_user_memory` | removed; the API creates a standard `human` block for each new session |

## Authoring Guidance

- Keep `system_instructions` coherent. Do not recreate the old `persona` vs `system_prompt` split manually.
- Keep `shared_memory_blocks` focused. Each block should have one job.
- Keep `archival_memory_seed` short and durable. Think searchable snippets, not essays.
- For Chinese characters, keep perspective consistent. Usually that means direct instructions use `你` and archival snippets stay neutral and concise.
- Choose route types intentionally:
  - `doubao_primary` for the mediated external surface route through `model_gateway`
  - `ollama_primary` for the default local chat route in the dev stack
  - `ollama_sleep_time` for the default local sleep-time route in the dev stack
  - native `ollama/...` handles only when you have verified that Letta-native calls do not need extra gateway shaping

## Template

Use the commented template at:

- `characters/templates/character_manifest.template.yaml`
