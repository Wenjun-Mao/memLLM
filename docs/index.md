# memLLM Docs Index

This directory is the durable project memory for the current Letta-native runtime and the follow-on work that will build on it.

## Current Phase

- Phase: `step_2`
- Status source: [planning/current_status.md](planning/current_status.md)
- Canonical dev topology: Dockerized `postgres` + `ollama` + `letta` + `model_gateway` + `api` + `dev_ui`
- Memory inspection UI: Letta Desktop or ADE in self-hosted server mode
- Product chat UI: local Streamlit app backed by the FastAPI service
- Canonical vocabulary: Letta terms first, MemGPT paper mapping second

## Start Here

- [Current Status](planning/current_status.md)
- [Runtime Stack](architecture/runtime_stack.md)
- [Letta vs MemGPT Mapping](architecture/letta_memgpt_mapping.md)
- [Model Gateway](integrations/model_gateway.md)
- [Manifest Guide](reference/character_manifest_guide.md)
- [Ubuntu Dev Stack](runbooks/ubuntu_dev_stack.md)
- [Post-Step-2 Follow-Ups](planning/post_step2_followups.md)

## Planning

- [planning/current_status.md](planning/current_status.md)
- [planning/post_step2_followups.md](planning/post_step2_followups.md)
- [planning/phase_2_prep.md](planning/phase_2_prep.md)
- [planning/roadmap.md](planning/roadmap.md)

## Architecture

- [architecture/monorepo_structure.md](architecture/monorepo_structure.md)
- [architecture/chat_flow.md](architecture/chat_flow.md)
- [architecture/runtime_stack.md](architecture/runtime_stack.md)
- [architecture/memory_model.md](architecture/memory_model.md)
- [architecture/letta_memgpt_mapping.md](architecture/letta_memgpt_mapping.md)
- [architecture/MemGPT/](architecture/MemGPT)

## Integrations

- [integrations/letta.md](integrations/letta.md)
- [integrations/model_gateway.md](integrations/model_gateway.md)
- [integrations/provider_adapters.md](integrations/provider_adapters.md)

## Runbooks

- [runbooks/ubuntu_dev_stack.md](runbooks/ubuntu_dev_stack.md)
- [runbooks/dev_workflow.md](runbooks/dev_workflow.md)

## Reference

- [reference/character_manifest_guide.md](reference/character_manifest_guide.md)
- [style_guide.md](style_guide.md)
- [reference/style_guide.md](reference/style_guide.md)
- [uv_monorepo_notes.md](uv_monorepo_notes.md)
- [reference/uv_monorepo_notes.md](reference/uv_monorepo_notes.md)
