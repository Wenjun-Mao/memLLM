# Next Phase: Letta-Native Memory Architecture

## Goal

Replace the current app-managed post-turn memory extractor path with a more Letta-native memory
architecture, most likely through Letta multi-agent patterns such as sleep-time/background agents.

## Why This Is A Separate Phase

The current phase-1 chunk intentionally focused on:

- cleaning up the schema around Letta terminology
- making archival-memory semantics correct
- exposing the current runtime honestly in the Dev UI

It did not change the live reply architecture.

## Expected Follow-On Work

- evaluate Letta multi-agent patterns for memory-management separation
- decide whether the final user-facing reply stays on an external provider or moves into a more
  Letta-native path
- replace the current app-managed local memory extractor when that architecture is ready
- update the Dev UI to surface real Letta-native multi-agent traces instead of the current
  app-managed writeback trace

## Constraint

Do not blur this phase boundary in docs or demos. The current runtime is Letta-backed and uses
Letta terminology, but it is still an app-orchestrated pipeline.
