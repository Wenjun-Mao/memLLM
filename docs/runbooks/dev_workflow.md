# Development Workflow

## Typical Loop

1. Start the Ubuntu Docker stack.
2. Start the FastAPI service.
3. Seed characters.
4. Open the Streamlit dev UI and talk to characters.
5. Open Letta Desktop or ADE to inspect memory behavior.
6. Capture any durable findings in [../planning/phase_2_prep.md](../planning/phase_2_prep.md).

## Commands

```bash
uv sync --all-packages
uv run --package memllm-api memllm-api
uv run streamlit run apps/dev_ui/src/memllm_dev_ui/app.py
uv run python scripts/seed_characters.py
uv run pytest
```

## Documentation Rule

If an implementation or environment detail matters for future work, document it before closing the task.
