# Memory Model

## Session Mapping

- One Letta agent per `(user_id, character_id)` pair
- One app metadata session row for the same pair

## Shared Character Context

Each character manifest seeds shared Letta blocks such as:

- `persona`
- `style`
- `role`
- optional synthesized `lore`

These shared blocks are attached to every user-agent for that character.

## User-Specific Context

Each user-character pair stores:

- a `human` block with durable user preferences and facts
- archival passages produced from conversation turns
- chat turn history in the app metadata store

## Retrieval and Update

- retrieval uses Letta block reads plus passage search
- updates use a memory delta produced by the local extractor
- the app writes block updates and new passages back to Letta after each turn
