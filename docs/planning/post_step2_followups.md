# Post-Step-2 Follow-Ups

Step 2 moved the repo onto a Letta-native runtime. The next chunk should build on that instead of reintroducing app-side orchestration.

## Candidate Next Priorities

- Streaming support from Letta through the API and Dev UI.
- Better Dev UI trace ergonomics for long Letta runs and tool-heavy sessions.
- A clearer operator view of real Letta step boundaries, rather than only the currently reconstructed prompt pipeline.
- Production-oriented auth and multi-user API hardening.
- Better route-level controls in `model_gateway`, including per-route budgets and safer fallback policies.
- Re-evaluate native Letta -> Ollama chat handles when Letta or Ollama expose enough control to suppress imported-Qwen reasoning/tool-shape issues without the gateway translation layer.
- Optional structured export of real Letta and gateway traces for offline debugging.

## Guardrails

- Keep Letta as the only runtime system of record.
- Keep `model_gateway` as the only place that knows raw provider credentials, headers, and vendor-specific request shapes.
- Do not reintroduce a parallel SQL session/chat-turn store.
