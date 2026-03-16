# Current Status

This file tracks what is actually built, what has been verified, and what still needs follow-up.

## Built and Verified

- [x] The `uv` workspace installs from the repo root with `apps/*` and `packages/*`.
- [x] The FastAPI app exposes `GET /health`, `GET /characters`, `POST /seed/characters`,
  `POST /chat`, and `GET /memory/{user_id}/{character_id}`.
- [x] Character seeding is idempotent in the current integration coverage.
- [x] Chat sessions are isolated per `(user_id, character_id)` pair in the current integration
  coverage.
- [x] The repo contains a Docker Compose topology for `postgres`/`pgvector`, `ollama`, `letta`,
  the FastAPI API, and the Streamlit dev UI.
- [x] The repo contains Ubuntu operator scripts for bootstrap, status inspection, and shutdown.
- [x] The Qwen 3.5 9B `Q4_K_M` GGUF import path is standardized through `hf` into
  `infra/ollama/models/`.
- [x] On a fresh Ubuntu 24.04 WSL2 clone, `bash scripts/bootstrap_ubuntu.sh --mode infra` brought
  up Docker-hosted Postgres/pgvector, Ollama, and Letta, downloaded the GGUF, and created the
  `memllm-qwen3.5-9b-q4km` alias.
- [x] On the same WSL2 environment, the real Letta service created per-session agents against the
  Docker-hosted Postgres instance when given explicit `llm_config` and `embedding_config`.
- [x] On the same WSL2 environment, the Dockerized API and Dockerized Streamlit UI both started
  successfully and exposed `localhost:8000` and `localhost:8501`.
- [x] A live `/chat` request succeeded against the Docker stack for `calm_archivist` using the
  imported Qwen GGUF through Ollama.
- [x] After that live chat, `GET /memory/{user_id}/{character_id}` showed the Letta `human` block
  and archival passages updated for the same `(user_id, character_id)` pair.

## Implemented but Not Yet Fully Validated

- [ ] Confirm `bash scripts/bootstrap_ubuntu.sh --mode api` and `--mode full` in a normal
  interactive Ubuntu shell outside the Codex tool environment.
- [ ] Click through the Streamlit UI end to end against the real Docker-backed stack after the API
  fix, rather than validating only through direct HTTP calls.
- [ ] Confirm Letta Desktop in self-hosted server mode can inspect the Docker-hosted Letta server
  during a real dev session.
- [ ] Repeat the smoke test on the target Ubuntu machine with the 24 GB RTX 4090.

## WSL2 Findings

- Letta v0.16.6 did not sync the imported Ollama GGUF alias as an LLM because Ollama exposed it as
  `completion`-only instead of advertising `tools` capability.
- The app now works around that by creating Letta agents with explicit `llm_config` and
  `embedding_config` instead of relying on Letta's synced provider handle.
- The imported Qwen GGUF produced cleaner replies through Ollama's native `/api/generate` endpoint
  with an explicit ChatML-style prompt than through `/v1/chat/completions`.
- Character manifests can still declare `http://localhost:11434` for `ollama_chat`, but the API now
  rewrites loopback Ollama URLs to the configured runtime override when it is running inside
  Docker.
- The local chat model can be preloaded and held resident in GPU memory; the current verified state
  is `UNTIL Forever` in `ollama ps`.
- On the WSL2 machine used here, the GPU was an 8 GB RTX 3080 Laptop GPU, and first-response
  latency was high because Ollama had to swap between the embedding model and the 9B chat model.

## How To Run Right Now

### Repo Checks

1. `uv sync --all-packages`
2. `uv run pytest`
3. `uv run ruff check .`

### Ubuntu Stack

1. Ensure Docker, Docker Compose, the NVIDIA runtime, Git, and `uv` are already installed.
2. `bash scripts/bootstrap_ubuntu.sh --mode infra`
3. `bash scripts/bootstrap_ubuntu.sh --mode api` or `bash scripts/bootstrap_ubuntu.sh --mode full`
4. Open `http://localhost:8501` for the dev UI or `http://localhost:8000/docs` for the API once
   the stack is healthy.
5. `bash scripts/status_dev_stack.sh`
6. `bash scripts/stop_dev_stack.sh`

## Next Steps

- [ ] Click through the Streamlit UI against the real stack and confirm the browser flow stays
  healthy after the API container fix.
- [ ] Run Letta Desktop/ADE against the Docker-hosted Letta server and document the exact workflow.
- [ ] Benchmark the same flow on the 24 GB RTX 4090 host and tune model choices if needed.
- [ ] Decide whether to keep the current explicit-config Letta workaround or replace it later with a
  Letta/Ollama model-registration path once upstream behavior is clearer.
- [ ] Keep this file updated whenever the implementation or verification state changes.
