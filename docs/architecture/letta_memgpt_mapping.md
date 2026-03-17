# Letta Terms vs MemGPT Paper Terms vs Current App Behavior

## Purpose

This file keeps the repo honest about which labels come from Letta today, which labels come from the MemGPT paper, and where the current runtime is showing a derived analogy rather than a literal paper primitive.

## Mapping Table

| Repo / Dev UI term | MemGPT paper analogue | What it means here |
|---|---|---|
| `System Instructions` | `System Instructions` | The Letta system layer for the primary agent |
| `Working Context` | `Working Context` | Letta memory blocks visible for the live turn |
| `Conversation Window` | FIFO queue analogue | The message window visible in the Letta-to-gateway request |
| `Archival Memory` | archival / recall storage | Letta archival memory retrieved for the turn or shown in snapshot views |
| `Primary Agent` | main conversational loop | The user-facing Letta agent |
| `Sleep-Time Agent` | background memory worker | The Letta background agent that consolidates memory |
| `Current-Round Memory Work` | function calls / memory operations | The observed Letta steps plus gateway traces for one round |

## What Matches Closely

- There is a real primary conversational agent.
- There is a real sleep-time/background agent.
- There is a real separation between working-context memory blocks and archival memory.
- The final prompt explanation maps cleanly to `System Instructions + Working Context + Conversation Window`.

## What Is Still Only an Analogy

- The Dev UI does not expose a first-class paper-style recall-storage product surface.
- The `Prompt Pipeline` panel is reconstructed from observable request/trace surfaces; it is not a dump of a private internal Letta prompt-builder object.

## Demo Guidance

Use Letta terms first. Use MemGPT paper terms as a secondary explanation when they help people understand why there is a primary agent, a sleep-time agent, working context, and archival memory.
