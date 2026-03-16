# Development Workflow

## Typical Loop

1. Bootstrap the environment with the mode that matches what you need:
   - `bash scripts/bootstrap_ubuntu.sh --mode infra` for core services only
   - `bash scripts/bootstrap_ubuntu.sh --mode api` for core services plus the backend API
   - `bash scripts/bootstrap_ubuntu.sh --mode full` for core services plus the backend API plus the Streamlit UI
2. Use `bash scripts/status_dev_stack.sh` to confirm the Docker services are healthy.
3. Open the Streamlit dev UI when using `--mode full`.
4. Open Letta Desktop or ADE to inspect memory behavior.
5. Capture durable findings in [../planning/phase_2_prep.md](../planning/phase_2_prep.md) and keep [../planning/current_status.md](../planning/current_status.md) current.

## Command Reference

```bash
uv sync --all-packages
bash scripts/bootstrap_ubuntu.sh --mode infra
bash scripts/bootstrap_ubuntu.sh --mode api
bash scripts/bootstrap_ubuntu.sh --mode full
bash scripts/status_dev_stack.sh
bash scripts/stop_dev_stack.sh
uv run pytest
```

## Bootstrap Modes

- `infra`: prepares the workspace, models, and core Docker services only.
- `api`: does everything in `infra`, then starts `memllm-api` on `http://localhost:8000`.
- `full`: does everything in `api`, then starts `memllm-dev-ui` on `http://localhost:8501`.

## Documentation Rule

If an implementation or environment detail matters for future work, document it before closing the task.
