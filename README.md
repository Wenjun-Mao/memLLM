# memLLM

`memLLM` is a Python `uv` workspace for building a Letta-backed multi-character chatbot.

Phase 1 includes:

- a FastAPI orchestration service
- a Streamlit development UI
- shared packages for domain models, Letta integration, memory ingestion, and reply providers
- versioned character manifests
- a Docker-based Ubuntu stack for Postgres/pgvector, Ollama, Letta, the API, and the dev UI
- Ubuntu bootstrap/status scripts for the development environment
- structured docs for architecture, operations, and follow-on phases

## What Works Today

The repo-level integration tests already cover:

- manifest seeding
- chat flow orchestration
- memory persistence in the in-memory test mode
- session isolation per `(user_id, character_id)` pair

Run them from the workspace root:

```bash
uv sync --all-packages
uv run pytest
```

## Ubuntu Dev Stack

The canonical phase-1 topology is:

- `postgres`/`pgvector` in Docker
- `ollama` in Docker
- `letta` in Docker
- `api` in Docker
- `dev_ui` in Docker

Bootstrap modes:

- `infra`: prepare the Python workspace, download the GGUF if needed, start `postgres`, `ollama`, and `letta`, pull the embedding model, create the local Ollama alias, and try to preload the chat model. If Ollama warm-up fails, the bootstrap now logs the failure and continues so the rest of the stack can still start. This is the right mode if you only want the core services ready.
- `api`: do everything in `infra`, then start the FastAPI container on `http://localhost:8000`. Use this when you want the backend up but do not need the Streamlit UI.
- `full`: do everything in `api`, then start the Streamlit dev UI on `http://localhost:8501`. Use this for the normal interactive development flow.

Bootstrap it with:

```bash
bash scripts/bootstrap_ubuntu.sh --mode infra
bash scripts/bootstrap_ubuntu.sh --mode api
bash scripts/bootstrap_ubuntu.sh --mode full
```

The Ubuntu host must already have Docker GPU support working. In particular, the NVIDIA runtime must be visible to Docker, `nvidia-persistenced` must be running before the Ollama container can start, and `curl` must be available for health checks. The bootstrap also preloads Letta's required NLTK `punkt_tab` data into `infra/letta/nltk_data/` and the project builds a small Letta wrapper image so cached NLTK data is used without relying on an online NLTK index during app startup. For Ollama, the bootstrap uses the documented empty-request `keep_alive` preload path, retries it a few times, and can be tuned with `OLLAMA_PRELOAD_ATTEMPTS` and `OLLAMA_PRELOAD_DELAY_SECONDS` in `infra/env/.env`.

If Letta is slow to initialize on a given machine, increase `LETTA_READY_TIMEOUT_SECONDS` in `infra/env/.env`.

Then inspect or stop it with:

```bash
bash scripts/status_dev_stack.sh
bash scripts/stop_dev_stack.sh
```

See [docs/index.md](docs/index.md) for the living documentation, especially
[docs/planning/current_status.md](docs/planning/current_status.md) for the current checklist and
verification state.
