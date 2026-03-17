# Memory Model

## Shared Memory Blocks

Each manifest seeds `shared_memory_blocks` that are attached to every Letta session for the same character.

## User Memory Block

Each session gets a standard Letta `human` block. This is the pair-specific working-context memory surface.

## Archival Memory

Each session starts with `archival_memory_seed`, copied into that session once. Later Letta-managed memory work can add more archival memory.

## Session Boundary

The isolation boundary is the `(user_id, character_id)` pair.

That means:

- same user, different character -> separate Letta sessions
- same character, different user -> separate Letta sessions
- shared character context comes from shared memory blocks, not shared live session memory
