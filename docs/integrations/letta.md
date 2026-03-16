# Letta Integration

## Phase 1 Decision

Run Letta as a self-hosted Docker service on the Ubuntu machine. Treat Letta as the memory backend
for the project.

## Developer Memory Tooling

Use Letta Desktop or the ADE for:

- inspecting blocks and passages
- editing memory directly
- validating retrieval behavior
- debugging specific agents

As of March 15, 2026, the official docs describe Letta Desktop as a beta desktop frontend that can
connect to a self-hosted Letta server. For this project, that makes it a good operator tool, not a
replacement for our own app UI.

Official docs:

- https://docs.letta.com/guides/selfhosting/
- https://docs.letta.com/guides/ade/setup/
- https://docs.letta.com/guides/ade/desktop/

## Project Assumptions

- Letta runs in Docker on Ubuntu
- Postgres/pgvector runs in Docker on the same host
- Ollama runs in Docker on the same host and is available to Letta and to the memory-extraction
  pipeline
- developers can expose Letta locally via SSH port forwarding when needed

## App Integration Surface

The project uses the Letta Python SDK for:

- shared block seeding
- agent creation
- block listing and updates
- passage search and passage creation

## Current Integration Notes

- Letta v0.16.6 did not register the imported Ollama GGUF alias as a synced LLM model in the WSL2
  smoke test because the alias was exposed by Ollama as `completion`-only instead of advertising
  `tools` capability.
- The application therefore creates agents with explicit `llm_config` and `embedding_config`
  pointing at Ollama's internal Docker-network endpoint instead of depending on a Letta provider
  handle for the chat model.
- This keeps the Letta layer offline while still allowing imported local models to be used for
  phase-1 memory-backed development.
