# Phase 1 Scope

## Goal

Build a development-ready monorepo for a Letta-backed multi-character chatbot with:

- a FastAPI orchestration API
- a Streamlit development chat UI
- Letta-managed memory for each `(user_id, character_id)` pair
- pluggable reply providers, including a non-OpenAI custom HTTP adapter
- local memory extraction through Ollama
- repo-based documentation that preserves decisions and deferred work

## Acceptance Criteria

- `uv` workspace layout is in place with `apps/*` and `packages/*`
- characters can be seeded from `characters/manifests/*.yaml`
- the API exposes `GET /characters`, `POST /seed/characters`, `POST /chat`, and `GET /memory/{user_id}/{character_id}`
- the dev UI can switch characters, send messages, and inspect memory snapshots
- Letta can run self-hosted in Docker and be inspected through Letta Desktop or ADE
- phase-2 carry-forward information is documented in [phase_2_prep.md](phase_2_prep.md)

## Intentionally Deferred

- user authentication and multi-tenant authorization
- production deployment manifests and secret management hardening
- async job queue for memory ingestion
- richer character authoring tools
- full migration tooling for the app metadata database
