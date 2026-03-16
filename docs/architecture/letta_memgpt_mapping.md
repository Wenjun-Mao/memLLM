# Letta Terms vs MemGPT Paper Terms vs Current App Behavior

## Purpose

This file keeps the repo honest about which labels come from Letta today, which labels come from the
MemGPT paper, and where the current phase-1 app still differs from the paper's architecture.

## Mapping Table

| Repo / Dev UI term | MemGPT paper analogue | What it means in this repo |
|---|---|---|
| `System Instructions` | `System Instructions` | The manifest's `system_instructions` text sent to the final reply provider |
| `Working Context` | `Working Context` | Letta memory blocks included in the live turn |
| `Conversation Window` | `FIFO Queue` analogue | Recent turn history from app metadata sent with the final provider call |
| `Archival Memory` | `Archival Storage` / retrieved external memory | Letta passage memory retrieved by search |
| `Current-Round Memory Work` | function calls / memory operations | The app's live trace for retrieval, extraction, and writeback |

## What Matches the Paper Closely

- The final prompt assembly is explained as `System Instructions + Working Context + Conversation Window`.
- Long-term retrievable memory is treated as archival memory.
- Memory updates are visible as explicit operations rather than hidden side effects.

## What Does Not Match Yet

- The app does not yet use a full Letta-native multi-agent or single-agent MemGPT loop for the
  final answer.
- The post-turn memory extractor is still an app-managed Ollama call.
- The final user-visible reply is still sent directly to DouBao or Ollama by the app.
- The conversation window is app-managed, not a first-class Letta recall-store UI surface.

## Operator Guidance

Use Letta terms first in demos and docs.
Use MemGPT paper terms as secondary explanation only when they illuminate the architecture.
Do not describe the current app as already having a distinct recall-storage product surface.
