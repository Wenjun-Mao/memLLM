# ADR 0001: Monorepo Layout

## Decision

Use a Python `uv` workspace monorepo with:

- `apps/` for runnable entrypoints
- `packages/` for reusable internal libraries
- `characters/` for versioned chatbot definitions
- `infra/` for Docker and environment scaffolding
- `docs/` for architecture and planning records

## Rationale

The project needs clear boundaries between the orchestration app, the dev UI, provider adapters,
memory logic, and long-lived project documentation.
