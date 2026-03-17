# Monorepo Structure

## Active Runtime Pieces

```text
apps/
  api/             Thin product/API layer over Letta + model_gateway
  dev_ui/          Streamlit Dev UI
  model_gateway/   OpenAI-compatible route layer for Letta

packages/
  domain/              Shared runtime types
  letta_integration/   Letta client and in-memory test gateway
```

## Supporting Directories

```text
characters/
  manifests/      Character definitions
  templates/      Commented manifest template
  seeds/          File-backed bootstrap registry

infra/
  compose/        Docker stack
  docker/         Service Dockerfiles
  model_gateway/  Gateway route config
  ollama/         GGUF/Modelfile assets
  letta/          Cached NLTK assets

scripts/          Bootstrap, status, stop, and cleanup helpers
docs/             Architecture, runbooks, and planning notes
tests/            Integration and e2e placeholders
```

## Legacy Packages

`packages/memory_pipeline` and `packages/reply_providers` remain in the repo only as historical artifacts from the pre-Step-2 runtime. The active runtime no longer depends on them.
