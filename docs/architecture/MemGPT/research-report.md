Based on a thorough inspection of the [letta-ai/letta](https://github.com/letta-ai/letta) repository's core agent schema and agent types, here is the verified answer:

## No Single-Agent Native Split Exists (But a Pattern Does)

Letta does **not** have a built-in, single-agent configuration field that lets you specify "Model A for memory management, Model B for user-facing replies." A single `AgentState` or `CreateAgent` object has only one `llm_config` / `model` field for its LLM. 

## How the Split IS Achieved: `sleeptime_agent`

The idiomatic way Letta achieves this pattern is through a **multi-agent architecture** using dedicated agent types, not a per-agent config split:

- **`sleeptime_agent`** — A background agent specifically responsible for memory consolidation/management. It runs asynchronously outside the main conversation loop. 
- **`voice_sleeptime_agent`** — A voice-conversation variant with the same background memory agent pattern. 
- **`enable_sleeptime: bool`** — A flag on `CreateAgent`/`AgentState` that, when `True`, spins up a separate background agent thread for memory management. 

This means the "memory LLM" and "response LLM" are literally **two separate agent objects**, each with their own independent `model` field. You can assign a cheap/fast model (e.g., `openai/gpt-4o-mini`) to the sleeptime memory agent and a more capable model to the main user-facing agent.

## `split_thread_agent` Type

There is also a dedicated [`split_thread_agent`](https://github.com/letta-ai/letta/blob/fc21581edc95bf8577e6821c1f93695e36b9173f/letta/schemas/agent.py) enum value in the `AgentType` class — explicitly named for the split-thread pattern, confirming this is a first-class, native concept in the framework. 

## What Is NOT Present

There is no single-agent field like `memory_llm_config` vs `response_llm_config` on `CreateAgent`. The split is architectural (two agent objects communicating), not a per-field config within one agent. The `llm_config` / `model` field on each agent is singular. 

**In summary:** The split is **natively supported** in Letta, but implemented as a **two-agent pattern** (`split_thread_agent` / `sleeptime_agent`) where each agent independently carries its own model config — not as a dual-model field within a single agent.