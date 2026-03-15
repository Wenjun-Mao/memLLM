# Development Workflow

## Typical Loop

1. Bootstrap the Ubuntu environment with `bash scripts/bootstrap_ubuntu.sh --mode api` or
   `bash scripts/bootstrap_ubuntu.sh --mode full`.
2. Use `bash scripts/status_dev_stack.sh` to confirm Docker services and host processes are healthy.
3. Open the Streamlit dev UI and talk to characters.
4. Open Letta Desktop or ADE to inspect memory behavior.
5. Capture durable findings in [../planning/phase_2_prep.md](../planning/phase_2_prep.md) and keep
   [../planning/current_status.md](../planning/current_status.md) current.

## Commands

```bash
uv sync --all-packages
bash scripts/bootstrap_ubuntu.sh --mode infra
bash scripts/bootstrap_ubuntu.sh --mode api
bash scripts/bootstrap_ubuntu.sh --mode full
bash scripts/status_dev_stack.sh
bash scripts/stop_dev_stack.sh
uv run pytest
```

## Documentation Rule

If an implementation or environment detail matters for future work, document it before closing the task.
