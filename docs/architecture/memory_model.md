# Memory Model

## Session Mapping

- One Letta agent per `(user_id, character_id)` pair
- One app metadata session row for the same pair

## Shared Character Memory

Each character manifest seeds shared Letta memory blocks such as:

- `style`
- `background`
- `relationship_rules`

These blocks are attached to every user-agent for that character.

## Pair-Specific Memory

Each user-character pair stores:

- a `human` memory block with durable user preferences and facts
- archival memory items produced from conversation turns
- seeded archival memory copied from `archival_memory_seed` on first creation
- chat-turn history in the app metadata store

## Retrieval and Update

- retrieval uses Letta memory-block reads plus archival-memory search
- the current phase still uses a local app-managed memory extractor after the final reply
- the app writes updated user memory plus new archival-memory items back to Letta after each turn

## Terminology Rule

In the repo and Dev UI:

- use `memory blocks` for Letta block memory
- use `archival memory` for Letta passage memory
- use `conversation window` for the recent-turn slice sent to the final provider
