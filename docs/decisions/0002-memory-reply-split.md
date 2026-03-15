# ADR 0002: Split Memory from Reply Generation

## Decision

Use Letta for memory management and a separate provider layer for user-facing replies.

## Rationale

- it keeps reply-provider switching practical
- it isolates nonstandard upstream APIs behind adapters
- it allows local Ollama models to focus on memory extraction if desired
- it preserves Letta as the source of truth for memory without forcing it to own the user-facing reply path
