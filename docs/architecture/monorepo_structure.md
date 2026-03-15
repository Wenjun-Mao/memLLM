# Monorepo Structure

## Layout

```text
apps/
  api/          FastAPI orchestration service
  dev_ui/       Streamlit development chat UI
packages/
  domain/       Shared Pydantic models and exceptions
  letta_integration/   Letta gateway interfaces and implementations
  memory_pipeline/     Local memory extraction logic
  reply_providers/     Provider adapters for user-facing responses
characters/
  manifests/    Versioned character definitions
  seeds/        Reserved for generated seed artifacts
infra/
  compose/      Ubuntu Docker stack for Letta, Postgres, and Ollama
  env/          Example environment files
scripts/        Small helper scripts
tests/          Integration and API tests
docs/           Planning, runbooks, ADRs, and references
```

## Why This Shape

- `apps/` keeps user-facing entrypoints isolated from reusable code
- `packages/` makes the memory, provider, and domain layers testable in isolation
- `characters/` keeps persona definitions versioned with the code
- `infra/` makes the Ubuntu stack part of the project rather than tribal knowledge
- `docs/` keeps architecture and next-phase information in repo truth
