# Runtime Stack

## Purpose

This document explains the current phase-1 runtime in Letta-first terms, how memory reaches the
final provider call, what the Dev UI panels mean, and where the current implementation still differs
from the MemGPT paper's full agent loop.

## Stack Roles

- `Streamlit Dev UI`: operator-facing chat and debug surface.
- `FastAPI API`: orchestration layer for character resolution, session resolution, retrieval,
  final-provider calls, and post-turn memory writeback.
- `Letta`: long-term memory layer. It stores shared memory blocks plus per-pair user memory and
  archival memory.
- `Ollama`: local model runtime. In the current phase it powers the app's post-turn memory
  extractor and Letta-side memory/model configuration.
- `External reply provider`: optional user-facing reply model. For example, `winter_poet` and
  `lin_xiaotang` send the final reply request to the DouBao endpoint.
- `Postgres/pgvector`: Docker-hosted storage for Letta and app metadata.

## One Chat Round

1. The UI sends `user_id`, `character_id`, and `message` to the API.
2. The API resolves or creates the Letta agent for that exact `(user_id, character_id)` pair.
3. If the pair is new, the app seeds:
   - shared Letta memory blocks from `shared_memory_blocks`
   - per-agent archival memory from `archival_memory_seed`
4. Letta returns the current live memory context for the turn:
   - shared memory blocks
   - the pair-specific `human` memory block
   - top-k retrieved archival-memory items relevant to the new user message
5. The API loads the recent conversation window from app metadata.
6. The API assembles the final provider request from:
   - `system_instructions`
   - working-context memory blocks
   - retrieved archival memory
   - the recent conversation window
7. The configured final reply provider generates the user-visible answer.
8. In the dev stack, the app then runs the local memory extractor inline and writes the resulting
   updates back to Letta so the same `/chat` response can include the full write trace.
9. The app records the completed turn in its metadata store.

## Letta Terms Used in This Repo

### Shared memory blocks

Seeded from `shared_memory_blocks` and attached to every Letta agent for that character.

### User memory block

The Letta `human` block for one `(user_id, character_id)` pair. The manifest field
`memory.initial_user_memory` is the starting value.

### Archival memory

Retrievable long-term snippets stored in Letta passage storage.

In this repo there are two sources:

- `archival_memory_seed` copied into each new agent once
- post-turn writebacks produced by the local memory extractor

### Conversation window

Recent user/assistant turns loaded from the app metadata store and included in the final call.
This is the closest current analogue to the paper's FIFO queue.

## Dev UI Panels

- `Final Provider Call`: the exact last outbound request to DouBao or local Ollama.
- `Prompt Pipeline`: the assembled `System Instructions`, `Working Context`, `Conversation Window`,
  and retrieved `Archival Memory`.
- `Current-Round Memory Work`: the live trace of Letta reads/searches, the local memory extractor,
  and Letta write operations.
- `Memory Snapshot`: the current live Letta state for the selected pair.
- `User-Agent Pair`: the Letta agent currently backing one user talking to one character.

## What Differs from Full MemGPT Today

This repo is Letta-backed, but it is not yet a full Letta-native multi-agent or single-agent
MemGPT loop.

Current phase-1 behavior:

- Letta stores and retrieves memory.
- The app still performs its own post-turn memory extraction with local Ollama.
- The final user-facing reply still goes straight to the configured provider.

That means the Dev UI uses Letta terminology first, then maps those pieces to the MemGPT paper
where that mapping is honest.

## Length Controls

### Controls that already exist

- `system_instructions` length:
  - shorten the manifest text directly
- Shared working-context size:
  - shorten or split `shared_memory_blocks`
- Seeded archival-memory size:
  - shorten `archival_memory_seed`
- Initial user-memory size:
  - shorten `memory.initial_user_memory`
- Retrieved archival-memory count:
  - `memory.archival_memory_search_limit`
- Snapshot archival-memory count:
  - `memory.snapshot_archival_memory_limit`
- Conversation-window size:
  - `memory.conversation_history_window`
- Local Letta-side model generation size:
  - `MEMLLM_API_LETTA_MODEL_MAX_TOKENS`
  - `MEMLLM_API_LETTA_MODEL_CONTEXT_WINDOW`
- Local Ollama final-reply generation size:
  - provider options such as `num_predict` under `reply_provider.extra`
- External provider-specific generation size:
  - `custom_simple_http` forwards `reply_provider.extra` as-is to the endpoint

### Controls that do not exist yet

- No hard token or character cap per memory block before final prompt assembly
- No hard token or character cap per archival-memory item before final prompt assembly
- No single total-budget truncation pass across the final provider payload
- No strict cap on memory-extractor output beyond prompt guidance and model behavior

## Recommended Next Phase

The immediate next architectural phase is to move from this app-managed post-turn extractor toward a
Letta-native multi-agent memory architecture. See:

- `docs/planning/letta_native_next_phase.md`
