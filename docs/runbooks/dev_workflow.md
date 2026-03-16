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

## Character Prompt Tuning

- Edit `persona` for stable identity, background, and relationship tone.
- Edit `system_prompt` for hard behavior rules and output-format constraints. This is where you ban things like bracketed narration, roleplay actions, or made-up real-time claims.
- Edit `shared_blocks.style` to reinforce the writing texture across turns.
- When you want to remove a behavior, write both the negative rule and the replacement behavior. Example: `不要写括号旁白... 如果想表达温柔，就直接用自然口语说出来。`
- Retest with a fresh `User ID` in the dev UI when evaluating prompt changes. Old assistant replies are replayed into later turns, so a dirty session can make a prompt fix look weaker than it is.
- After changing a manifest, reseed characters. In the current Dockerized setup, rebuild the `api` container before reseeding so the container sees the updated manifest file.

## Documentation Rule

If an implementation or environment detail matters for future work, document it before closing the task.
