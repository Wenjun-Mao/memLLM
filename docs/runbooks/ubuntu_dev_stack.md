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
- Example env: [../../infra/env/ubuntu-dev.example.env](../../infra/env/ubuntu-dev.example.env)
- Bootstrap script: [../../scripts/bootstrap_ubuntu.sh](../../scripts/bootstrap_ubuntu.sh)
- Status script: [../../scripts/status_dev_stack.sh](../../scripts/status_dev_stack.sh)
- Stop script: [../../scripts/stop_dev_stack.sh](../../scripts/stop_dev_stack.sh)

## Canonical Flow

The Ubuntu host is responsible for:

- running the repo bootstrap script
- providing Docker, Compose, NVIDIA runtime support, Git, and `uv`

All phase-1 services now run inside the Docker stack.

The canonical startup path is:

```bash
bash scripts/bootstrap_ubuntu.sh --mode infra
bash scripts/bootstrap_ubuntu.sh --mode api
bash scripts/bootstrap_ubuntu.sh --mode full
```

Modes:

- `infra`: sync the workspace, ensure the GGUF is present, start Docker services, wait for
  Postgres/Ollama/Letta, pull `mxbai-embed-large`, and create the
  `memllm-qwen3.5-9b-q4km` alias if needed
- `api`: do everything in `infra`, then build/start the FastAPI container and seed characters
- `full`: do everything in `api`, then build/start the Streamlit container

Use the helper scripts during development:

```bash
bash scripts/status_dev_stack.sh
bash scripts/stop_dev_stack.sh
```

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
docker exec -it memllm-ollama ollama pull mxbai-embed-large
docker exec -it memllm-ollama ollama create memllm-qwen3.5-9b-q4km -f /workspace/ollama/Modelfile.qwen3.5-9b-q4km
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
- On smaller GPUs, expect higher first-response latency because Ollama may need to swap between the
  embedding model and the 9B chat model.

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
