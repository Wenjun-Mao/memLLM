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
bash scripts/clean_dev_stack.sh --yes
uv run pytest
```

## Character Tuning

- Edit `system_instructions` for identity, stable behavior, output constraints, honesty rules, and language choice.
- Edit `shared_memory_blocks` for reusable Letta working-context facets such as `style` or `background`.
- Edit `archival_memory_seed` for evergreen facts that should behave like retrievable archival memory.
- When you want to remove a behavior, write both the negative rule and the replacement behavior.
- Retest with a fresh `User ID` in the dev UI when evaluating prompt changes. Old assistant replies are replayed into later turns, so a dirty session can make a prompt fix look weaker than it is.
- After changing a manifest, reseed characters. After the schema rename in this phase, do a clean reset and reseed instead of trying to reuse old metadata rows.

## Schema-Break Rule

This schema rename is a clean dev-phase break.

If you pull these changes into an older running stack, reset and reseed before testing:

```bash
bash scripts/clean_dev_stack.sh --yes
bash scripts/bootstrap_ubuntu.sh --mode full
```

## Documentation Rule

If an implementation or environment detail matters for future work, document it before closing the task.
