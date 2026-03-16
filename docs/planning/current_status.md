# Current Status

This file tracks what is actually built, what has been verified, and what still needs follow-up.

## Built and Verified

- [x] The `uv` workspace installs from the repo root with `apps/*` and `packages/*`.
- [x] The FastAPI app exposes `GET /health`, `GET /characters`, `POST /seed/characters`,
  `POST /chat`, `GET /memory/{user_id}/{character_id}`, `GET /sessions`, and session deletion.
- [x] The repo now uses a Letta-aligned manifest/API schema with:
  - `system_instructions`
  - `shared_memory_blocks`
  - `archival_memory_seed`
  - `memory_blocks` and `archival_memory` in memory snapshots
- [x] Old manifest keys such as `persona`, `system_prompt`, `shared_blocks`, and `shared_passages`
  are rejected in integration coverage.
- [x] `archival_memory_seed` is now stored as real per-agent archival memory instead of being
  synthesized into a fake `lore` block.
- [x] `/chat` now returns a structured debug payload with:
  - `final_provider_call`
  - `prompt_pipeline`
  - `trace_events`
  - `memory_writeback`
- [x] In the dev stack, memory writeback runs inline by default so the current round trace includes
  the local extractor call and Letta write operations.
- [x] The Streamlit Dev UI has dedicated panels for `Final Provider Call`, `Prompt Pipeline`,
  `Current-Round Memory Work`, `Memory Snapshot`, and `User-Agent Pair`.
- [x] The repo contains a Docker Compose topology for `postgres`/`pgvector`, `ollama`, `letta`,
  the FastAPI API, and the Streamlit dev UI.
- [x] The repo contains Ubuntu operator scripts for bootstrap, status inspection, shutdown, and cleanup.
- [x] The phase-1 Letta embedding default is `qwen3-embedding:0.6b`.

## Implemented but Not Yet Fully Validated

- [ ] Click through the renamed Streamlit UI end to end against the real Docker-backed stack after this schema break.
- [ ] Confirm the structured debug panels are easy to follow in a real coworker demo.
- [ ] Confirm Letta Desktop in self-hosted server mode can inspect the Docker-hosted Letta server during a real dev session.
- [ ] Repeat the smoke test on the target Ubuntu machine with the 24 GB RTX 4090 after the schema rename reset.

## How To Run Right Now

### Repo Checks

1. `uv sync --all-packages`
2. `uv run pytest`
3. `uv run ruff check .`

### Clean Reset After This Schema Break

1. `bash scripts/clean_dev_stack.sh --yes`
2. `bash scripts/bootstrap_ubuntu.sh --mode full`
3. Open `http://localhost:8501`
4. Reseed if needed from the UI or `POST /seed/characters`

## Next Steps

- [ ] Validate the redesigned Dev UI against the real Docker stack.
- [ ] Start the next Letta-native migration phase described in `planning/letta_native_next_phase.md`.
- [ ] Keep this file updated whenever the implementation or verification state changes.
