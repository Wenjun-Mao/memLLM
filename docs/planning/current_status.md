# Current Status

This file tracks what is actually built, what has been verified, and what still needs follow-up.

## Built and Verified

- [x] The `uv` workspace installs from the repo root with `apps/*` and `packages/*`.
- [x] Character manifests now use the Step 2 schema:
  - `system_instructions`
  - `shared_memory_blocks`
  - `archival_memory_seed`
  - `letta_runtime`
- [x] Old manifest keys such as `reply_provider`, `memory.*`, `persona`, and `system_prompt` are rejected.
- [x] The API runtime no longer uses the SQLAlchemy metadata/chat-turn path.
- [x] The API now resolves one Letta primary agent plus one sleep-time agent per `(user_id, character_id)` pair.
- [x] The API exposes Letta-backed `GET /characters`, `POST /seed/characters`, `POST /chat`, `GET /memory/{user_id}/{character_id}`, `GET /sessions`, and `DELETE /sessions/{user_id}/{character_id}`.
- [x] `/chat` returns a Letta-native debug payload with:
  - `final_provider_call`
  - `prompt_pipeline`
  - `trace_events`
  - `memory_writeback`
- [x] A dedicated Dockerized `model_gateway` now exposes:
  - `GET /v1/models`
  - `POST /v1/chat/completions`
  - `POST /v1/embeddings`
  - debug trace endpoints for the Dev UI and API
- [x] The default embedding path is direct Letta -> local Ollama `/v1` using `qwen3-embedding:0.6b`.
- [x] The default local chat and sleep-time routes now go through `model_gateway`, while direct Letta -> Ollama embeddings stay native to the Letta runtime. Native Letta chat handles remain available only as experimental routes.
- [x] The Docker bootstrap/status/reset scripts support the Step 2 stack, including `model_gateway`.
- [x] `bash scripts/clean_dev_stack.sh --yes` followed by `bash scripts/bootstrap_ubuntu.sh --mode full` succeeds on the local Ubuntu/WSL2 dev stack after the Step 2 gateway fixes.
- [x] Live post-reset gateway traces show the expected route split: local primary replies use `ollama_primary`, Chinese surface-rendered replies use `doubao_primary`/`doubao_surface`, and the sleep-time follow-up path now completes its Ollama tool-message round trip without the earlier `400 Bad Request`.

## Implemented but Not Yet Fully Validated

- [ ] Do a full real-stack click-through of all Step 2 Dev UI panels after a destructive reset.
- [ ] Validate real tool-call passthrough behavior through the mediated DouBao route with a Letta run that actually invokes tools.
- [ ] Confirm the real Letta sleep-time agent behavior on the target 24 GB RTX 4090 machine under longer sessions.
- [ ] Validate Letta Desktop/ADE against the Step 2 runtime during a real debugging session.

## How To Run Right Now

### Repo Checks

1. `uv sync --all-packages`
2. `uv run ruff check .`
3. `uv run pytest`

### Clean Reset For This Runtime Cutover

1. `bash scripts/clean_dev_stack.sh --yes`
2. `bash scripts/bootstrap_ubuntu.sh --mode full`
3. Open `http://localhost:8501`
4. Seed from the UI if needed or call `POST /seed/characters`

## Next Steps

- [ ] Validate the Step 2 Docker stack end to end after a destructive reset on both local and remote Ubuntu machines.
- [ ] Decide what the next chunk should focus on from [post_step2_followups.md](post_step2_followups.md).
- [ ] Keep this file updated whenever verification state changes.
