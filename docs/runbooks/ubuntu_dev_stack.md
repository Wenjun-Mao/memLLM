# Ubuntu Dev Stack

## Goal

Run the phase-1 infrastructure on the Ubuntu 4090 machine:

- Postgres with pgvector
- Ollama
- Letta

## Files

- Compose file: [../../infra/compose/ubuntu-dev-stack.yml](../../infra/compose/ubuntu-dev-stack.yml)
- Example env: [../../infra/env/ubuntu-dev.example.env](../../infra/env/ubuntu-dev.example.env)

## Startup

```bash
cp infra/env/ubuntu-dev.example.env infra/env/.env
docker compose --env-file infra/env/.env -f infra/compose/ubuntu-dev-stack.yml up -d
```

## Pull Recommended Models

```bash
docker exec -it memllm-ollama ollama pull mxbai-embed-large
```

## Import a Custom GGUF Build

If you want the exact `Q4_K_M` build of Qwen 3.5 9B, import the GGUF into Ollama and use the
project alias `memllm-qwen3.5-9b-q4km`.

Place the GGUF file at:

```text
infra/ollama/models/qwen3.5-9b-q4_k_m.gguf
```

Then create the model inside the Ollama container:

```bash
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
- Add TLS and a stricter exposure model before any shared-environment deployment.
