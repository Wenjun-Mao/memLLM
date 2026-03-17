# Ubuntu Dev Stack

## Goal

Run the Step 2 development stack on Ubuntu:

- Postgres with pgvector in Docker
- Ollama in Docker
- Letta in Docker
- model_gateway in Docker
- FastAPI in Docker
- Streamlit in Docker

## Canonical Flow

The Ubuntu host is responsible for:

- Docker, Compose, NVIDIA runtime support, Git, `curl`, and `uv`
- allowing `docker run --gpus all ... nvidia-smi` to succeed
- running the repo bootstrap script

All Step 2 services run inside Docker.

Use:

```bash
bash scripts/bootstrap_ubuntu.sh --mode infra
bash scripts/bootstrap_ubuntu.sh --mode api
bash scripts/bootstrap_ubuntu.sh --mode full
```

After a schema or runtime cutover, do a destructive reset before reusing an older stack:

```bash
bash scripts/clean_dev_stack.sh --yes
bash scripts/bootstrap_ubuntu.sh --mode full
```

## Mode Differences

### `infra`

What it does:

- runs preflight checks for Docker, `uv`, Git, `curl`, and NVIDIA support
- syncs the `uv` workspace
- downloads the Qwen GGUF if needed
- ensures Letta NLTK data is present
- starts `postgres` and `ollama` first
- waits for them to become healthy
- pulls `qwen3-embedding:0.6b` if needed
- rebuilds the local Ollama alias before Letta starts
- preloads the local chat model and asks Ollama to keep it resident
- starts `letta` and `model_gateway` only after the local Ollama models and alias are ready

### `api`

Does everything in `infra`, then starts `memllm-api`.

### `full`

Does everything in `api`, then starts `memllm-dev-ui`.

## Helper Scripts

```bash
bash scripts/status_dev_stack.sh
bash scripts/stop_dev_stack.sh
bash scripts/clean_dev_stack.sh --yes
```

`clean_dev_stack.sh --yes` preserves the Ollama cache by default, so pulled embedding/chat models and aliases do not need to be re-downloaded after a normal reset. Use `--preserve-memory` when you want a container/network cleanup without wiping Letta state.

## Model Assets

The bootstrap standardizes the local Qwen download with Hugging Face CLI and stores it under `infra/ollama/models/`.

It uses:

```bash
hf download unsloth/Qwen3.5-9B-GGUF Qwen3.5-9B-Q4_K_M.gguf --local-dir infra/ollama/models
```

If `hf` is not installed separately, the bootstrap falls back to `uvx --from huggingface_hub hf`.

## GPU Runtime Check

The bootstrap validates Docker GPU access with:

```bash
docker run --rm --gpus all nvidia/cuda:12.9.0-base-ubuntu24.04 nvidia-smi
```

This is the real source of truth because WSL2 and native Ubuntu expose GPU support differently.

## Letta Startup Note

- Letta can take noticeably longer than Postgres and Ollama to become API-ready on first boot.
- The bootstrap waits on `http://localhost:8283/v1/health/`.
- The repo preloads Letta's `punkt_tab` NLTK data into `infra/letta/nltk_data/` and builds a small Letta wrapper image so startup does not depend on an online NLTK fetch.
- If Letta still times out, inspect it directly:

```bash
docker logs --tail 120 memllm-letta
```

## model_gateway Note

The gateway is part of the core infra for the default chat routes. If `infra` is healthy but a local Qwen or DouBao-backed character still fails, check:

```bash
curl -sS http://127.0.0.1:9100/health
curl -sS http://127.0.0.1:9100/v1/models
```

## Letta Desktop / ADE

Use Letta Desktop in self-hosted server mode against the Docker Letta server.

If you are developing from another machine, forward the Letta port:

```bash
ssh -L 8283:localhost:8283 user@ubuntu-host
```

Then point Letta Desktop to `http://localhost:8283`.
