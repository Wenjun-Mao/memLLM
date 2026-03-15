# memLLM

`memLLM` is a Python `uv` workspace for building a Letta-backed multi-character chatbot.

Phase 1 includes:

- a FastAPI orchestration service
- a Streamlit development UI
- shared packages for domain models, Letta integration, memory ingestion, and reply providers
- versioned character manifests
- structured docs for architecture, operations, and follow-on phases

## Workspace commands

```bash
uv sync --all-packages
uv run pytest
uv run --package memllm-api memllm-api
uv run streamlit run apps/dev_ui/src/memllm_dev_ui/app.py
```

See [docs/index.md](docs/index.md) for the living project documentation.
