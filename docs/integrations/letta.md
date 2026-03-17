# Letta Integration

## Runtime Role

Letta is the live runtime system of record for:

- sessions
- conversations
- runs and steps
- memory blocks
- archival memory

## Session Topology

Each `(user_id, character_id)` pair maps to:

- one primary conversational agent
- one sleep-time/background agent when enabled

The installed Letta client in this repo exposes the runtime primarily through agents plus managed-group metadata, so the app treats the primary agent as the session identity and reads the managed-group metadata to discover the sleep-time partner.

## What the API Does

The API does not mirror chats or sessions into a second runtime database.

It only:

- seeds shared memory blocks
- resolves or creates Letta sessions
- sends user messages into Letta
- reads Letta memory snapshots
- reads Letta step traces for the Dev UI

## Memory Inspection

Use Letta Desktop or ADE in self-hosted server mode against the Docker Letta server when you need direct memory inspection or editing.
