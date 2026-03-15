# Ubuntu Dev Stack

## Goal

Run the phase-1 infrastructure on the Ubuntu 4090 machine:

- Postgres with pgvector in Docker
- Ollama in Docker
- Letta in Docker

## Files

- Compose file: [../../infra/compose/ubuntu-dev-stack.yml](../../infra/compose/ubuntu-dev-stack.yml)
- Example env: [../../infra/env/ubuntu-dev.example.env](../../infra/env/ubuntu-dev.example.env)
- Bootstrap script: [../../scripts/bootstrap_ubuntu.sh](../../scripts/bootstrap_ubuntu.sh)
- Status script: [../../scripts/status_dev_stack.sh](../../scripts/status_dev_stack.sh)
- Stop script: [../../scripts/stop_dev_stack.sh](../../scripts/stop_dev_stack.sh)

## Canonical Flow

The Ubuntu host is responsible for:

- running the Docker stack
- running the repo bootstrap script
- optionally running the FastAPI app and Streamlit UI as host processes

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
- `api`: do everything in `infra`, then start the FastAPI app and seed characters
- `full`: do everything in `api`, then start the Streamlit dev UI

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
docker compose --env-file infra/env/.env -f infra/compose/ubuntu-dev-stack.yml up -d
docker exec -it memllm-ollama ollama pull mxbai-embed-large
docker exec -it memllm-ollama ollama create memllm-qwen3.5-9b-q4km -f /workspace/ollama/Modelfile.qwen3.5-9b-q4km
```

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
