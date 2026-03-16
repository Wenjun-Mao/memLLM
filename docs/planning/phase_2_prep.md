# Phase 2 Prep

Update this file whenever phase 1 reveals work that should be picked up later.

## Deferred Engineering Work

- replace synchronous/background-task memory persistence with a queue-backed worker
- add migrations for the app metadata database
- support provider-specific auth and credential rotation
- add richer character import/export and revision history
- harden remote Ubuntu deployment and TLS strategy for Letta/ADE access
- decide whether the phase-1 all-Docker development topology should remain the default in later phases

## Open Questions

- whether the final deployment keeps the FastAPI service separate from the Letta host
- whether app metadata should stay in a separate database or move to a schema strategy
- whether `memllm-qwen3.5-9b-q4km` remains the default local model after phase-2 benchmarking
- whether a React frontend replaces the Streamlit development UI for phase 2
- whether the Letta explicit-`llm_config` workaround should stay long term or be replaced once the
  Ollama model-registration path is clearer upstream

## Lessons and Findings

- Letta should be treated as the memory system of record, not the only UI surface
- Letta Desktop is useful for memory management, but the project still needs its own chat UX
- the custom simplified provider contract should stay behind a stable adapter boundary
- the current WSL2-validated dev topology is containerized for Postgres/pgvector, Letta, Ollama,
  the FastAPI API, and the Streamlit dev UI
- Letta v0.16.6 filtered the imported Ollama GGUF alias out of synced LLM models because the alias
  did not advertise `tools` capability, even though the underlying Qwen model family does support
  tool use in other serving setups
- the imported Qwen GGUF behaved better through Ollama's native `/api/generate` path with an
  explicit prompt than through `/v1/chat/completions` in the current phase-1 stack
- containerized API calls cannot use manifest-level loopback Ollama URLs directly, so the runtime
  now normalizes loopback `ollama_chat` base URLs to a container-safe override
- keeping the chat model resident with `keep_alive=-1` materially improves repeat-request latency on
  smaller GPUs, at the cost of holding most of the VRAM budget open for that model
- on an 8 GB WSL2 GPU, Ollama had noticeable first-response latency because it had to swap between
  the embedding model and the 9B chat model

## Update Rule

Any phase-1 change that affects future implementation, deployment, or operations should be added here.
