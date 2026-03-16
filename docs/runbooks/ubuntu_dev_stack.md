# Ubuntu Dev Stack

## Goal

Run the phase-1 development stack on the Ubuntu development machine:

- Postgres with pgvector in Docker
- Ollama in Docker
- Letta in Docker
- FastAPI in Docker
- Streamlit in Docker

## Files

- Compose file: [../../infra/compose/ubuntu-dev-stack.yml](../../infra/compose/ubuntu-dev-stack.yml)
  This file now sets the Compose project name to `memllm-dev`, so Docker networks and volumes are easier to recognize.
- Example env: [../../infra/env/ubuntu-dev.example.env](../../infra/env/ubuntu-dev.example.env)
- Bootstrap script: [../../scripts/bootstrap_ubuntu.sh](../../scripts/bootstrap_ubuntu.sh)
- Status script: [../../scripts/status_dev_stack.sh](../../scripts/status_dev_stack.sh)
- Stop script: [../../scripts/stop_dev_stack.sh](../../scripts/stop_dev_stack.sh)
- Cleanup script: [../../scripts/clean_dev_stack.sh](../../scripts/clean_dev_stack.sh)

## Canonical Flow

The Ubuntu host is responsible for:

- running the repo bootstrap script
- providing Docker, Compose, NVIDIA runtime support, Git, `curl`, and `uv`
- allowing `docker run --gpus all ... nvidia-smi` to succeed

All phase-1 services run inside the Docker stack.

The canonical startup path is:

```bash
bash scripts/bootstrap_ubuntu.sh --mode infra
bash scripts/bootstrap_ubuntu.sh --mode api
bash scripts/bootstrap_ubuntu.sh --mode full
```

## Mode Differences

### `infra`

What it does:

- runs preflight checks for Docker, `uv`, Git, `curl`, and NVIDIA support
- syncs the `uv` workspace
- downloads the Qwen GGUF into `infra/ollama/models/` if it is missing
- starts the core Docker services: `postgres`, `ollama`, and `letta`
- rebuilds the repo-managed Letta image when needed before startup
- waits for those core services to become healthy
  The Letta wait is configurable with `LETTA_READY_TIMEOUT_SECONDS` and can take several minutes on first boot, especially if the container is doing one-time startup work. The bootstrap now prints periodic progress lines while it waits.
- pulls the Ollama embedding model `qwen3-embedding:0.6b` if needed
- creates the project Ollama alias `memllm-qwen3.5-9b-q4km` if needed
- attempts to preload the local chat model with Ollama's documented empty-request `keep_alive` path and asks Ollama to keep it resident

What it does not do:

- does not start the FastAPI container
- does not start the Streamlit dev UI container

Use it when:

- you want the Letta/Ollama/Postgres layer ready first
- you want to debug the core infra separately from the app layer
- you want Letta Desktop or ADE available without bringing up the app UI

### `api`

What it does:

- does everything in `infra`
- starts the FastAPI container
- rebuilds the API image when needed before startup
- waits for `http://localhost:8000/health` to succeed

What it does not do:

- does not start the Streamlit dev UI container

Use it when:

- you want to test the HTTP API directly
- you want to use `curl`, Swagger, or scripts without the UI
- you want the backend running but do not need the browser chat surface

### `full`

What it does:

- does everything in `api`
- starts the Streamlit dev UI container
- rebuilds the dev UI image when needed before startup
- waits for `http://localhost:8501` to respond

Use it when:

- you want the normal phase-1 development experience
- you want both the backend API and the browser chat UI available

### Practical Rule

- `infra`: core services only
- `api`: core services plus backend
- `full`: core services plus backend plus UI

Use the helper scripts during development:

```bash
bash scripts/status_dev_stack.sh
bash scripts/stop_dev_stack.sh
bash scripts/clean_dev_stack.sh --yes
```

`clean_dev_stack.sh` is the destructive reset path. It removes the stack containers and networks, wipes the Postgres volume so Letta memory and app metadata are rebuilt from scratch, and preserves the Ollama cache by default so pulled embedding/chat models and aliases do not need to be downloaded again. By default it also preserves `infra/ollama/models/Qwen3.5-9B-Q4_K_M.gguf`, `infra/letta/nltk_data/`, and `infra/env/.env`. Use `--include-ollama-cache` only when you want to wipe Ollama's cached models and aliases too.

## GPU Runtime Check

Before the bootstrap script can start Ollama with `gpus: all`, the host must satisfy these GPU-container prerequisites:

- Docker must report an NVIDIA runtime.
- A real Docker GPU smoke test must succeed:

```bash
docker run --rm --gpus all nvidia/cuda:12.9.0-base-ubuntu24.04 nvidia-smi
```

The bootstrap uses that containerized `nvidia-smi` check as the source of truth because WSL2 and native Ubuntu expose GPU support differently:

- On Docker Desktop with WSL2, GPU access is typically provided through GPU-PV, and the Linux distro may not expose `/run/nvidia-persistenced/socket` even when GPU containers work.
- On a native Ubuntu host with the NVIDIA Container Toolkit, `/run/nvidia-persistenced/socket` is still a useful troubleshooting signal if the Docker GPU smoke test fails.

So if the bootstrap reports a missing `nvidia-persistenced` socket on a native Ubuntu host, fix that host first:

```bash
sudo systemctl enable --now nvidia-persistenced
sudo systemctl restart docker
```

If `nvidia-persistenced` is not installed on the host yet, install the NVIDIA driver component that provides it, then rerun the smoke test above.

## Model Download

The bootstrap script standardizes the local Qwen model download through the Hugging Face CLI and
stores it under `infra/ollama/models/`.

It uses:

```bash
hf download unsloth/Qwen3.5-9B-GGUF Qwen3.5-9B-Q4_K_M.gguf --local-dir infra/ollama/models
```

If `hf` is not installed separately, the bootstrap script falls back to `uvx --from huggingface_hub
hf`.

## Manual Fallback Commands

If you need to run the steps manually instead of using the bootstrap script:

```bash
cp infra/env/ubuntu-dev.example.env infra/env/.env
uv sync --all-packages
hf download unsloth/Qwen3.5-9B-GGUF Qwen3.5-9B-Q4_K_M.gguf --local-dir infra/ollama/models
docker compose --env-file infra/env/.env -f infra/compose/ubuntu-dev-stack.yml up -d --build
docker exec -it memllm-ollama ollama pull qwen3-embedding:0.6b
docker exec -it memllm-ollama ollama create memllm-qwen3.5-9b-q4km -f /workspace/ollama/Modelfile.qwen3.5-9b-q4km
```

## Letta Startup Note

- On a fresh machine, Letta can take noticeably longer than Postgres and Ollama to become API-ready on its first boot.
- If this phase fails, the bootstrap exits before starting `api` and `dev_ui`, so seeing only the three infra containers is expected.
- The current Letta image calls `nltk.download("punkt_tab")` during app startup. The bootstrap now pre-downloads that data on the host into `infra/letta/nltk_data/`, validates that it is loadable, and mounts it into the Letta container as `/root/nltk_data`.
- The project now builds a small Letta wrapper image that short-circuits `nltk.download("punkt_tab")` when the mounted data is already present, because NLTK may still hit the online index even for an installed package.
- The bootstrap waits on `http://localhost:8283/v1/health/` instead of probing a heavier API route.
- If Letta still times out, inspect the container directly:

```bash
docker logs --tail 120 memllm-letta
```

## Letta and Ollama Notes

- Letta v0.16.6 did not automatically register the imported GGUF alias as an Ollama LLM in this
  project because Ollama exposed the alias as `completion`-only instead of advertising `tools`
  capability.
- The app works around that by creating Letta agents with explicit local `llm_config` and
  `embedding_config` that point at `http://ollama:11434/v1` inside the Docker network.
- For user-facing local replies, the app uses Ollama's native `/api/generate` path with an explicit
  ChatML-style prompt because it produced better results for the imported Qwen GGUF than
  `/v1/chat/completions`.
- The reply-provider layer now rewrites loopback Ollama URLs such as `http://localhost:11434` to
  the configured runtime override when the API itself is running in Docker. This keeps the same
  character manifests usable for both host-run and container-run development.
- The bootstrap and reply-provider paths keep the chat model resident with `keep_alive=-1`, so
  `docker exec memllm-ollama ollama ps` should show `UNTIL Forever` until the Ollama container is
  restarted or removed.
- Bootstrap preloading uses Ollama's documented empty-request load call instead of generating a token.
  If that warm-up still fails, the script retries it, prints recent Ollama logs, and continues so
  `api` and `dev_ui` can still come up. Tune this with `OLLAMA_PRELOAD_ATTEMPTS` and
  `OLLAMA_PRELOAD_DELAY_SECONDS` in `infra/env/.env`.
- On smaller GPUs, expect higher first-response latency because Ollama may need to swap between the
  `qwen3-embedding:0.6b` model and the 9B chat model.

## Letta Desktop / ADE

- Use Letta Desktop in self-hosted server mode against the Docker Letta server.
- If developing from another machine, forward the Letta port:

```bash
ssh -L 8283:localhost:8283 user@ubuntu-host
```

- Then point Letta Desktop to `http://localhost:8283`.

## Notes

- The compose stack uses one Postgres instance with two databases: `letta` and `memllm`.
- `memllm` is for app metadata. `letta` is for Letta.
- `LETTA_DB_NAME` must remain `letta` unless the Postgres init script is updated as well.
- Add TLS and a stricter exposure model before any shared-environment deployment.
