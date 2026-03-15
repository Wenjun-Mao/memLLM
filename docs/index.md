# memLLM Docs Index

This directory is the project memory for phase 1 and beyond. The goal is to keep design intent,
integration notes, and deferred work in the repo so later phases do not depend on chat history.

## Current Phase

- Phase: `phase_1`
- Status: monorepo scaffold in progress
- Canonical dev topology: Docker-based Letta + Postgres/pgvector + Ollama on Ubuntu
- Memory operations UI: Letta Desktop or ADE in self-hosted server mode
- Product chat UI: local Streamlit app backed by the FastAPI service

## Start Here

- [Phase 1 Scope](planning/phase_1_scope.md)
- [Monorepo Structure](architecture/monorepo_structure.md)
- [Chat Flow](architecture/chat_flow.md)
- [Memory Model](architecture/memory_model.md)
- [Ubuntu Dev Stack](runbooks/ubuntu_dev_stack.md)
- [Phase 2 Prep](planning/phase_2_prep.md)

## Planning

- [planning/phase_1_scope.md](planning/phase_1_scope.md)
- [planning/phase_2_prep.md](planning/phase_2_prep.md)
- [planning/roadmap.md](planning/roadmap.md)

## Architecture

- [architecture/monorepo_structure.md](architecture/monorepo_structure.md)
- [architecture/chat_flow.md](architecture/chat_flow.md)
- [architecture/memory_model.md](architecture/memory_model.md)

## Integrations

- [integrations/letta.md](integrations/letta.md)
- [integrations/provider_adapters.md](integrations/provider_adapters.md)

## Runbooks

- [runbooks/ubuntu_dev_stack.md](runbooks/ubuntu_dev_stack.md)
- [runbooks/dev_workflow.md](runbooks/dev_workflow.md)

## Decisions

- [decisions/0001-monorepo-layout.md](decisions/0001-monorepo-layout.md)
- [decisions/0002-memory-reply-split.md](decisions/0002-memory-reply-split.md)

## Reference

- [style_guide.md](style_guide.md)
- [uv_monorepo_notes.md](uv_monorepo_notes.md)
- [reference/style_guide.md](reference/style_guide.md)
- [reference/uv_monorepo_notes.md](reference/uv_monorepo_notes.md)
