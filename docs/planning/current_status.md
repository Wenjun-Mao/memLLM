# Current Status

This file tracks what is actually built, what has been verified, and what still needs a real
environment smoke test.

## Built and Verified

- [x] The `uv` workspace installs from the repo root with `apps/*` and `packages/*`.
- [x] The FastAPI app exposes `GET /health`, `GET /characters`, `POST /seed/characters`,
  `POST /chat`, and `GET /memory/{user_id}/{character_id}`.
- [x] Character seeding is idempotent in the current integration coverage.
- [x] Chat sessions are isolated per `(user_id, character_id)` pair in the current integration
  coverage.
- [x] The repo contains a Docker Compose topology for `postgres`/`pgvector`, `ollama`, and
  `letta`.
- [x] The repo contains Ubuntu operator scripts for bootstrap, status inspection, and shutdown.
- [x] The Qwen 3.5 9B `Q4_K_M` GGUF import path is standardized through `hf` into
  `infra/ollama/models/`.

## Implemented but Not Yet Validated End-to-End

- [ ] Run `bash scripts/bootstrap_ubuntu.sh --mode infra` on the Ubuntu 4090 host.
- [ ] Validate that the Docker-hosted Ollama service can create `memllm-qwen3.5-9b-q4km` from the
  downloaded GGUF.
- [ ] Validate that the Docker-hosted Letta service is reachable and can create session agents
  against the Docker-hosted Postgres/pgvector instance.
- [ ] Validate that `bash scripts/bootstrap_ubuntu.sh --mode api` leaves the API healthy and seeds
  characters successfully.
- [ ] Validate that `bash scripts/bootstrap_ubuntu.sh --mode full` leaves the Streamlit UI reachable
  against the real backend stack.
- [ ] Confirm Letta Desktop in self-hosted server mode can inspect the Docker-hosted Letta server
  during a real dev session.

## How To Run Right Now

### Repo Checks

1. `uv sync --all-packages`
2. `uv run pytest`

### Ubuntu Stack

1. Ensure Docker, Docker Compose, the NVIDIA runtime, Git, and `uv` are already installed.
2. `bash scripts/bootstrap_ubuntu.sh --mode infra`
3. `bash scripts/bootstrap_ubuntu.sh --mode api` or `bash scripts/bootstrap_ubuntu.sh --mode full`
4. `bash scripts/status_dev_stack.sh`
5. `bash scripts/stop_dev_stack.sh`

## Next Steps

- [ ] Run the new bootstrap flow on the Ubuntu host and record the exact result here.
- [ ] Add at least one Docker-backed smoke test once a suitable runner or manual environment is
  available.
- [ ] Decide later whether the FastAPI app and Streamlit UI should remain host processes or move
  into Compose for later phases.
- [ ] Keep this file updated whenever the implementation or verification state changes.
