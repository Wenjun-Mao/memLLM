# memLLM

`memLLM` is a Python `uv` workspace for a Letta-native multi-character chatbot runtime.

The current stack is:

- `Letta` as the live system of record for sessions, conversations, runs, steps, memory blocks, and archival memory
- `model_gateway` for the default chat routes in the current dev stack, including DouBao mediation and shaped local Qwen routes
- `Ollama` for local model execution behind the gateway plus direct local embedding calls
- `DouBao` as the default final surface model for selected characters
- `FastAPI` as the thin product/API layer
- `Streamlit` as the development UI
- `Postgres/pgvector` in Docker for Letta storage

## What Works Today

The repo now supports the Step 2 Letta-native runtime:

- character manifests use `system_instructions`, `shared_memory_blocks`, `archival_memory_seed`, and `letta_runtime`
- one Letta primary agent plus one sleep-time agent per `(user_id, character_id)` pair
- a Dockerized `model_gateway` that exposes `/v1/models`, `/v1/chat/completions`, and `/v1/embeddings` for mediated/fallback routes
- Letta-backed `/chat`, `/sessions`, and `/memory` APIs
- a dev UI with `Final Provider Call`, `Prompt Pipeline`, `Current-Round Memory Work`, `Memory Snapshot`, and `User-Agent Pair`

Run the local checks from the workspace root:

```bash
uv sync --all-packages
uv run ruff check .
uv run pytest
```

## Current Vocabulary

The canonical runtime vocabulary is now:

- `system_instructions`
- `shared_memory_blocks`
- `archival_memory_seed`
- `primary agent`
- `sleep-time agent`
- `memory blocks`
- `archival memory`
- `model route`

This is a breaking dev-phase cutover. If you were already running an older stack, reset and reseed instead of trying to reuse old runtime data:

```bash
bash scripts/clean_dev_stack.sh --yes
bash scripts/bootstrap_ubuntu.sh --mode full
```

## Ubuntu Dev Stack

The canonical Docker topology is:

- `postgres` / `pgvector`
- `ollama`
- `letta`
- `model_gateway`
  - used by default for the current chat routes, including mediated DouBao routes and shaped local Qwen routes
- `api`
- `dev_ui`

Bootstrap modes:

- `infra`: sync workspace, ensure GGUF + NLTK assets, start `postgres` + `ollama`, prepare local Ollama models and aliases, then start `letta` + `model_gateway`
- `api`: do everything in `infra`, then start the FastAPI container on `http://localhost:8000`
- `full`: do everything in `api`, then start the Streamlit dev UI on `http://localhost:8501`

Use:

```bash
bash scripts/bootstrap_ubuntu.sh --mode infra
bash scripts/bootstrap_ubuntu.sh --mode api
bash scripts/bootstrap_ubuntu.sh --mode full
```

Then inspect, stop, or reset the environment with:

```bash
bash scripts/status_dev_stack.sh
bash scripts/stop_dev_stack.sh
bash scripts/clean_dev_stack.sh --yes
```

`clean_dev_stack.sh --yes` preserves the Ollama cache by default, so `qwen3-embedding:0.6b` and the local chat alias do not need to be downloaded again after a normal reset. Use `--preserve-memory` when you want to rebuild containers without wiping Letta state.

## GPU Note

The Ubuntu host must already have Docker GPU support working. The bootstrap uses a real Docker GPU smoke test:

```bash
docker run --rm --gpus all nvidia/cuda:12.9.0-base-ubuntu24.04 nvidia-smi
```

This is intentionally more portable than a hard `/run/nvidia-persistenced/socket` check because WSL2 and native Ubuntu expose GPU support differently.

## Docs

See [docs/index.md](docs/index.md) for the living documentation, especially:

- [docs/planning/current_status.md](docs/planning/current_status.md)
- [docs/architecture/runtime_stack.md](docs/architecture/runtime_stack.md)
- [docs/architecture/letta_memgpt_mapping.md](docs/architecture/letta_memgpt_mapping.md)
- [docs/integrations/model_gateway.md](docs/integrations/model_gateway.md)
- [docs/reference/character_manifest_guide.md](docs/reference/character_manifest_guide.md)
