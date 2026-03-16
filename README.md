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
- the renamed Letta-aligned debug payload shape

Run them from the workspace root:

```bash
uv sync --all-packages
uv run pytest
```

## Current Vocabulary

The repo now uses Letta-aligned terms as the canonical vocabulary:

- `system_instructions`
- `shared_memory_blocks`
- `archival_memory_seed`
- `memory blocks`
- `archival memory`
- `conversation window`

This was a clean dev-phase break. If you were already running an older copy of the stack, do a clean reset and reseed instead of trying to reuse old metadata rows.

## Ubuntu Dev Stack

The canonical phase-1 topology is:

- `postgres`/`pgvector` in Docker
- `ollama` in Docker
- `letta` in Docker
- `api` in Docker
- `dev_ui` in Docker

Bootstrap modes:

- `infra`: prepare the Python workspace, download the GGUF if needed, start `postgres`, `ollama`, and `letta`, pull the embedding model, create the local Ollama alias, and try to preload the chat model.
- `api`: do everything in `infra`, then start the FastAPI container on `http://localhost:8000`.
- `full`: do everything in `api`, then start the Streamlit dev UI on `http://localhost:8501`.

Bootstrap it with:

```bash
bash scripts/bootstrap_ubuntu.sh --mode infra
bash scripts/bootstrap_ubuntu.sh --mode api
bash scripts/bootstrap_ubuntu.sh --mode full
```

The Ubuntu host must already have Docker GPU support working. The bootstrap uses a real `docker run --gpus all ... nvidia-smi` smoke test as the portable GPU preflight because Docker Desktop on WSL2 may not expose the native Linux `nvidia-persistenced` socket inside the distro even when GPU containers work. The bootstrap also preloads Letta's required NLTK `punkt_tab` data into `infra/letta/nltk_data/` and the project builds a small Letta wrapper image so cached NLTK data is used without relying on an online NLTK index during app startup.

Then inspect, stop, or fully reset it with:

```bash
bash scripts/status_dev_stack.sh
bash scripts/stop_dev_stack.sh
bash scripts/clean_dev_stack.sh --yes
```

`clean_dev_stack.sh --yes` preserves the Ollama model cache by default, so the embedding model and local chat alias do not need to be re-downloaded after a normal reset. Use `--preserve-memory` when you want to rebuild containers and networks without wiping Letta/app memory, and use `--include-ollama-cache` only when you intentionally want a full Ollama wipe.

See [docs/index.md](docs/index.md) for the living documentation, especially:

- [docs/planning/current_status.md](docs/planning/current_status.md)
- [docs/architecture/runtime_stack.md](docs/architecture/runtime_stack.md)
- [docs/architecture/letta_memgpt_mapping.md](docs/architecture/letta_memgpt_mapping.md)
- [docs/reference/character_manifest_guide.md](docs/reference/character_manifest_guide.md)
