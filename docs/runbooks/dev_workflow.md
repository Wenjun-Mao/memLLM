# Development Workflow

## Typical Loop

1. Bootstrap the environment with the mode you need:
   - `bash scripts/bootstrap_ubuntu.sh --mode infra`
   - `bash scripts/bootstrap_ubuntu.sh --mode api`
   - `bash scripts/bootstrap_ubuntu.sh --mode full`
2. Check health with `bash scripts/status_dev_stack.sh`.
3. Open the Dev UI when using `--mode full`.
4. Open Letta Desktop or ADE when you need direct memory inspection.
5. Capture durable findings in `docs/` instead of relying on chat history.

## Command Reference

```bash
uv sync --all-packages
bash scripts/bootstrap_ubuntu.sh --mode infra
bash scripts/bootstrap_ubuntu.sh --mode api
bash scripts/bootstrap_ubuntu.sh --mode full
bash scripts/status_dev_stack.sh
bash scripts/stop_dev_stack.sh
bash scripts/clean_dev_stack.sh --yes
uv run ruff check .
uv run pytest
```

## Character Tuning

- Edit `system_instructions` for identity, stable behavior, language rules, and output constraints.
- Edit `shared_memory_blocks` for reusable working-context facets.
- Edit `archival_memory_seed` for durable archival snippets that each new session should start with.
- Edit `letta_runtime` to choose a model route. Use slashless `model_gateway` routes such as `ollama_primary`, `ollama_sleep_time`, and `doubao_primary` for the standard dev stack. Native Letta handles (`provider/model`) remain available for experiments when the provider needs no extra shaping. Keep raw provider details in `infra/model_gateway/routes.yaml`.
- Retest with a fresh `User ID` when evaluating character behavior.

## Runtime Debugging

When a turn looks wrong, inspect in this order:

1. `Final Provider Call`
2. `Prompt Pipeline`
3. `Current-Round Memory Work`
4. `Memory Snapshot`
5. Letta Desktop / ADE for the same session

## Reset Rule

This runtime is a breaking dev-phase cutover. If you pull a newer version of the repo and the stack behavior looks inconsistent, reset and reseed before debugging:

```bash
bash scripts/clean_dev_stack.sh --yes
bash scripts/bootstrap_ubuntu.sh --mode full
```
