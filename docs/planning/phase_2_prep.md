# Phase 2 Prep

Update this file whenever phase 1 reveals work that should be picked up later.

## Deferred Engineering Work

- replace synchronous/background-task memory persistence with a queue-backed worker
- add migrations for the app metadata database
- support provider-specific auth and credential rotation
- add richer character import/export and revision history
- harden remote Ubuntu deployment and TLS strategy for Letta/ADE access
- decide whether host-side dev processes should stay outside Compose in later phases

## Open Questions

- whether the final deployment keeps the FastAPI service separate from the Letta host
- whether app metadata should stay in a separate database or move to a schema strategy
- whether `memllm-qwen3.5-9b-q4km` remains the default local model after phase-2 benchmarking
- whether a React frontend replaces the Streamlit development UI for phase 2

## Lessons and Findings

- Letta should be treated as the memory system of record, not the only UI surface
- Letta Desktop is useful for memory management, but the project still needs its own chat UX
- the custom simplified provider contract should stay behind a stable adapter boundary
- the dev topology is containerized for Postgres/pgvector, Letta, and Ollama; only the Python app
  processes stay on the host during phase 1

## Update Rule

Any phase-1 change that affects future implementation, deployment, or operations should be added here.
