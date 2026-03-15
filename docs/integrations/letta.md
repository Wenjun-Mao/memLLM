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
