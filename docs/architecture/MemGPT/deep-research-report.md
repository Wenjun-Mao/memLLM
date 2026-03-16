# MemGPT and Letta Multi-LLM Routing for Memory vs User-Facing Responses

## Executive summary

The MemGPT paper’s core design uses **a single “LLM processor”** whose completion tokens are interpreted as function calls that (a) move information across memory tiers (working context, FIFO queue, recall storage, archival storage) and (b) control when to yield a user-facing response. In other words, **memory management and response generation are architecturally intertwined within one LLM loop** (even though the loop can call tools/functions). citeturn45view1turn45view4

In the Letta codebase (Letta is “formerly MemGPT”), the primary agent loop likewise instantiates a single `LLMClient` from `agent_state.llm_config` and uses it to drive tool-calling steps and eventually produce the user-visible output; there is **no first-class, per-turn “memory model != response model” switch** inside the single-agent loop. citeturn6search4turn40view4turn15view0

However, Letta *does* support **multi-agent architectures that separate responsibilities across agents**, and those agents can each be configured with different models. In particular:

- **Sleep-time agents**: Letta docs describe an architecture where enabling `enable_sleeptime` creates a **primary agent** (the user-facing conversational agent) and a **sleep-time agent** that runs **in the background** and can update shared memory blocks asynchronously. citeturn21view0  
- In the open-source code, `SleeptimeMultiAgent` orchestrates a main `LettaAgent` plus “participant agents” launched asynchronously; each participant agent is instantiated with its own `AgentState` (therefore its own model configuration). citeturn37view0  
- Letta’s summarization subsystem can also offload work to a `summarizer_agent` (triggered “fire-and-forget”); if that summarizer is a distinct agent, it can use a distinct model. citeturn42view0  

So, **Letta supports “memory-management LLM != response LLM” as a *multi-agent* pattern (sleep-time / background memory agents)**, but **does not appear to support it directly as a *single-agent*, same-turn pipeline** where one model performs internal memory management and another model produces the final reply *for that same user message*—at least not in the default `LettaAgent` loop as implemented in the open-source repo examined here. citeturn40view4turn37view0turn21view0

Assumptions and scope notes:
- Letta version was **unspecified**; this report references the **current `main` branch** behavior and Letta Docs/pages accessible on **2026-03-16 (America/Toronto)**. (For reproducibility, pin a commit SHA when you validate in your environment.) citeturn6search4turn21view0  
- The user-provided local PDF could not be searched with `file_search` in this environment; the analysis treats the **arXiv PDF** as the primary MemGPT paper source. citeturn22search3turn44view0  

## MemGPT paper architecture and what it implies for multi-LLM separation

### Virtual context management and the “LLM processor” as the central coordinator

MemGPT proposes “virtual context management,” explicitly inspired by OS virtual memory/paging, to provide the illusion of extended context while using fixed-context models. citeturn44view0turn22search0 The paper describes a hierarchical memory system and function-calling interface that lets the model move information between in-context “main memory” and out-of-context stores. citeturn44view0turn45view1

A key architectural detail for your question is that MemGPT’s **LLM completion tokens are interpreted as function calls**, and MemGPT uses these calls to:
- move data between context and external memory stores; and  
- manage control flow (when to continue tool-calling vs when to yield/wait). citeturn45view1turn45view4  

This implies that, in the MemGPT reference design, **the same LLM instance** is responsible for both “thinking about memory” (what to store/retrieve, when to page, when to compact) and “thinking about the user reply,” because both actions occur as part of the same function-calling loop. citeturn45view1turn45view4

### Memory hierarchy components relevant to “memory model vs response model”

The paper’s Figure 3 description includes:
- prompt tokens composed of system instructions, working context, and a FIFO queue;  
- recall storage and archival storage as external databases;  
- a queue manager that writes messages to recall storage and manages eviction;  
- a function executor that interprets completion tokens as function calls;  
- an explicit mechanism for function chaining via a special argument like `request heartbeat=true`. citeturn45view1  

The “interrupt”/yield behavior (control returned to the processor immediately vs pausing until an external event) is also described as part of the function-call mechanism. citeturn45view4

Why this matters: the MemGPT paper doesn’t frame “memory management” as an external pre/post-processing stage; it frames it as **agentic control inside the model’s loop**. Therefore, a clean split—LLM-A manages memory, LLM-B writes the final user-facing answer—would be a *departure* from the paper’s base architecture and would require an explicit routing/interface boundary between these roles.

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["MemGPT Figure 3 hierarchical memory system diagram","MemGPT virtual context management paging diagram","MemGPT function calling memory hierarchy"],"num_per_query":1}

## Letta architecture surfaces relevant to memory management and model selection

### Letta positioning and relationship to MemGPT

The official repository describes Letta as **“formerly MemGPT”** and positions it as a platform for “stateful agents” with advanced memory. citeturn6search4 Letta Docs present core memory abstractions (memory blocks, archival memory) and multi-agent patterns (shared memory blocks, background agents). citeturn20view0turn21view0turn19view0

### LLM selection in code: `LLMConfig` and single-agent client creation

In the open-source repo, model selection (for a given agent) is represented via `LLMConfig` in `letta/schemas/llm_config.py`. Key fields include (non-exhaustive):
- `model` (string model name)  
- `model_endpoint_type` (provider selector like `"openai"`, `"anthropic"`, `"google_ai"`, etc.)  
- `model_endpoint` (optional base URL)  
- `context_window`  
- generation controls like `temperature`, `max_tokens`  
- tool-calling/format flags like `put_inner_thoughts_in_kwargs`, `strict`, `response_format`. citeturn10view0turn15view0  

In the primary agent loop (`letta/agents/letta_agent.py`), Letta constructs an `LLMClient` directly from the agent’s `llm_config` (provider determined by `agent_state.llm_config.model_endpoint_type`). citeturn40view4 This is the core reason the single-agent architecture is, by default, **single-model per agent**: the same `LLMClient` is used to drive the step logic and interpret responses. citeturn40view4  

### Memory management mechanisms in Letta

Letta’s memory management in the sources reviewed is implemented via several cooperating mechanisms:

- **Memory blocks (core memory)**: Docs describe memory blocks as structured sections prepended to the agent prompt in an XML-like format, always in context, editable via built-in memory tools. citeturn20view0  
- **Archival memory**: Docs describe archival memory as a long-term, out-of-context store accessed via tool calls and semantic search. citeturn16search2turn16search4  
- **Conversation/history compaction (summarization)**: `letta/services/summarizer/summarizer.py` implements message eviction/compaction strategies. It includes both a “partial evict + inline recursive summary message” path and a “static buffer + trigger background summarization” path. citeturn41view0turn42view0  
- **Recall/conversation search**: Letta’s docs mention searchable message history pooled across conversations and accessible by tools such as `conversation_search`. citeturn16search7turn21view0  

## Evidence in Letta for using different models across internal memory operations and user-facing responses

This section answers your question in the most literal way possible: “Does Letta let me run internal memory management with LLM-A while the final user-visible reply is generated by LLM-B?”

### What is directly supported today

#### Sleep-time agents provide a built-in “memory agent” vs “conversation agent” split

Letta Docs explicitly describe **sleep-time agents** as background agents that share memory blocks with the primary agent, run asynchronously, and “process data such as conversation history … to manage the memory blocks of the primary agent.” citeturn21view0

The docs state that enabling sleeptime (`enable_sleeptime: true`) automatically creates:
- a **primary agent** (user-facing) with tools for search over history and archival memory; and  
- a **sleep-time agent** “with tools to manage the memory blocks of the primary agent.” citeturn21view0  

This is conceptually close to “memory management model” vs “response model,” except that the memory agent runs on a schedule (every N steps) rather than *before every single response*.

The open-source orchestration logic supports this view: `letta/groups/sleeptime_multi_agent.py` runs the main agent step, then conditionally spawns background tasks for each participant agent. Participant agents are created by loading their own `AgentState` and constructing `LettaAgent(agent_state=participant_agent_state, ...)`. citeturn37view0  

Because each participant has its own `AgentState`, and the `LettaAgent` uses `agent_state.llm_config` to pick the provider/model, the architecture inherently allows **different models per agent**—including a different model for the background memory manager agent than the model used by the user-facing main agent. citeturn37view0turn15view0  

Also, Letta’s API documentation surfaces `enable_sleeptime` as: “If set to True, memory management will move to a background agent thread.” citeturn18search2turn17view1

#### Voice sleep-time agent demonstrates a concrete “memory worker agent” implementation

The file `letta/agents/voice_sleeptime_agent.py` implements a specialized `VoiceSleeptimeAgent` that:
- subclasses `LettaAgent`;  
- constrains tool rules to memory-related tools like `"store_memories"` and `"rethink_user_memory"`;  
- stores summaries/passages into the *conversation agent’s* archival memory via passage insertion (see `store_memory` calling `insert_passage`). citeturn29view0  

This is strong code-level evidence that Letta supports a pattern where **a separate agent** performs memory computation/storage, which can (in principle) run on a different model from the main conversation agent, since it is its own agent instance driven by its own `llm_config`. citeturn29view0turn37view0  

#### Compaction documentation describes selecting a separate summarizer model handle

Letta Docs’ compaction guide states that `compaction_settings` can specify a separate `model` (a “summarizer model handle”) and that defaults may be provider-specific, with a fallback to the agent’s model. The guide also explicitly suggests using a “cheaper/faster model for summarization.” citeturn17view0

Even if you *don’t* use sleep-time agents, this means Letta’s documented behavior supports **at least one internal memory-adjacent operation (history summarization/compaction)** using a model that can differ from the agent’s main model. citeturn17view0

Caveat on implementation parity: In the open-source summarizer code path examined, `simple_summary(...)` accepts an `llm_config`, and the “partial evict” path passes `agent_state.llm_config` directly; the “compaction_settings” dict is passed into telemetry, not used to override the model inside that function. citeturn41view0turn23view0 This suggests either (a) model override is applied upstream (not in the snippets inspected), or (b) the docs describe behavior implemented in another layer/product path. This should be validated in your target deployment.

### What is not directly supported in the single-agent loop

#### No first-class “memory LLM” vs “response LLM” inside `LettaAgent.step`

In `letta/agents/letta_agent.py`, `LLMClient.create(...)` is called using the single `agent_state.llm_config.model_endpoint_type`, and the subsequent request/response conversion uses `agent_state.llm_config` as well. citeturn40view4turn40view0

No code path identified in the inspected excerpt suggests routing:
- “tool-calling / memory management steps” to one model; and  
- “final user-visible message text generation” to another model  
*within the same agent step*.

#### Ephemeral summary agent explicitly notes the lack of multi-model support

`letta/agents/ephemeral_summary_agent.py` contains a docstring describing it as a summarization agent that “utilizes the caller’s LLM client,” and includes a TODO: “allow the summarizer to use another llm_config from the main agent maybe?” citeturn14view0

This is explicit evidence that, at least for that component, separate model selection for the summarizer was considered but not implemented in the code shown. citeturn14view0

## Determination for your specific requirement

### Interpretation of the requirement

You asked whether Letta supports:

> “running internal memory management with one LLM while using a different LLM to generate the final user-facing reply.”

There are two materially different ways to interpret this:

- **Single-agent, same-turn dual-model pipeline**: one inbound user message triggers an internal memory-management pass (LLM-A), then a separate response-generation pass (LLM-B) whose output is what the user sees, for the *same turn*.  
- **Multi-agent separation of concerns**: a user-facing agent (LLM-B) answers the user, while one or more background/worker agents (LLM-A) perform memory updates (core memory blocks, archival ingestion, etc.) asynchronously or periodically.

### Conclusion

- **Single-agent, same-turn dual-model pipeline:** Not supported as a clearly exposed, first-class feature in the open-source Letta `LettaAgent` loop as examined; the agent loop is driven by a single `agent_state.llm_config`. citeturn40view4turn15view0  
- **Multi-agent split (memory agent vs user agent):** Supported as a built-in architectural pattern via sleep-time agents / multi-agent groups, where memory updates are performed by a separate agent that can be configured to use a different model than the primary agent. citeturn21view0turn37view0turn39view0  
- **Internal summarization/compaction on a separate model:** Documented for compaction via `compaction_settings.model` (summarizer model handle). Implementation details may differ by deployment path; validate in your stack. citeturn17view0turn41view0  

### Mermaid diagrams of the relevant interaction patterns

#### Current `LettaAgent` single-model loop

```mermaid
flowchart LR
  U[User message] --> LC[Letta core: LettaAgent loop]
  LC -->|LLMClient(agent_state.llm_config)| M[Same LLM performs tool calls + reasoning]
  M --> T[Tool executor: memory tools / searches / writes]
  T --> M
  M --> R[Final user-facing reply (tool call / assistant message)]
```

This matches the MemGPT paper’s core idea that function calling + control flow is driven by the same LLM processor. citeturn45view1turn40view4

#### Letta sleep-time architecture enabling different models

```mermaid
flowchart LR
  U[User message] --> A[Primary agent (LLM-B)]
  A --> Reply[User-facing reply]
  A -->|every N steps| ST[Sleep-time agent (LLM-A)]
  ST --> MB[Shared memory blocks / archival insertion]
  MB --> A
```

Sleep-time agents are described as background agents that share memory and update it asynchronously. citeturn21view0turn37view0

#### Desired same-turn dual-model pipeline

```mermaid
flowchart LR
  U[User message] --> MM[Memory manager LLM (LLM-A)]
  MM -->|writes/reads| Mem[Letta memory systems]
  MM --> Ctx[Context bundle / response brief]
  Ctx --> RM[Response LLM (LLM-B)]
  RM --> Reply[Final user-facing reply]
  Mem --> RM
```

This is not a default Letta architecture today; it would require explicit routing changes in the agent loop. citeturn40view4  

## Code-level inventory and concrete patch suggestions

### Short module/file comparison table

| File path | Key classes/functions | Role in memory/model orchestration | Evidence for multi-LLM separation |
|---|---|---|---|
| `letta/schemas/llm_config.py` | `class LLMConfig` and fields (`model`, `model_endpoint_type`, `context_window`, etc.) | Defines per-agent model/provider selection | Single config per agent; no built-in “memory vs response” split citeturn15view0 |
| `letta/agents/letta_agent.py` | `LLMClient.create(...)` seeded by `agent_state.llm_config` | Core tool-calling loop and response construction | Single-model loop per agent (no dual-model routing found) citeturn40view4turn40view0 |
| `letta/groups/sleeptime_multi_agent.py` | `class SleeptimeMultiAgent`, `_issue_background_task`, `_perform_background_agent_step` | Runs main agent; spawns background participant agents | Participants loaded by `participant_agent_id` → can use different models citeturn37view0 |
| `letta/services/summarizer/summarizer.py` | `class Summarizer`, `summarize`, `_static_buffer_summarization`, `simple_summary` | Message eviction + summarization; can trigger background summarizer agent | `summarizer_agent` can be a separate agent → can use different model citeturn42view0turn41view0 |
| `letta/agents/ephemeral_summary_agent.py` | `class EphemeralSummaryAgent` | Summarizer agent using caller’s LLM config | Explicit TODO for allowing separate `llm_config` citeturn14view0 |
| `letta/agents/voice_sleeptime_agent.py` | `class VoiceSleeptimeAgent`, `_execute_tool`, `store_memory` | Memory worker; inserts passages into archival memory | Concrete memory-agent design; can run on different model than convo agent citeturn29view0 |

### Configuration keys, environment variables, and API calls to know about

#### Model selection and provider connection

- **Agent model selection (code-level):** `LLMConfig.model`, `LLMConfig.model_endpoint_type`, `LLMConfig.model_endpoint`, `LLMConfig.context_window`, `LLMConfig.temperature`, `LLMConfig.max_tokens`, etc. citeturn10view0turn15view0  
- **Provider environment variables (example):** `.env.example` includes provider API keys and/or base URLs (e.g., OpenAI, Anthropic, local endpoints). citeturn3view0  

#### Memory management controls

- **Summarizer configuration (config file):** `enable_summarization`, `mode`, `message_buffer_limit`, `message_buffer_min`, `partial_evict_summarizer_percentage` are present in `letta/configs/conf.yaml`, with environment variable mapping mentioned for summarizer settings. citeturn5view0turn3view1  
- **Sleep-time agent enablement (API/docs):** `enable_sleeptime` toggles creation of a background memory agent. citeturn21view0turn18search2  
- **Sleep-time frequency (docs):** `sleeptime_agent_frequency` configures “every N steps” behavior. citeturn21view0turn39view0  

#### Documented separate model for summarization

- **Compaction settings in docs:** `compaction_settings.model` is documented as “Summarizer model handle (format: provider/model-name)” and explicitly recommended for using a cheaper/faster model for summarization. citeturn17view0  

#### Example code demonstrating multi-model across agents

- Letta includes a simple example script `letta/test_gemini.py` showing agent creation with a specific model handle (Gemini) via `letta_client`. citeturn43view0  
- An official companion repository example (`letta-ai/letta-voice`) shows creation of an agent with `enable_sleeptime=True`, then explicitly updating the sleep-time agent model to a different provider/model. This demonstrates practical multi-model usage across a primary agent and its background memory agent. citeturn18search1  

### If you need true same-turn dual-model routing, where to implement it

To achieve your requirement *inside a single “send message” call*, you need an explicit “handoff boundary” between memory management and final response. The most direct hook point in the open-source code is at the `LettaAgent` layer, because it is where `LLMClient` is instantiated from `agent_state.llm_config`. citeturn40view4

Below are two concrete implementation strategies.

#### Strategy A: Add an explicit `response_llm_config` to `AgentState`, and run a second LLM pass to produce the final reply

**Concept:** Keep the existing loop (LLM-A) for tool calls + memory operations. When the loop reaches the point where it would produce a user-facing message, ignore or treat the tool-call text as a “response brief,” and run a final “response LLM” (LLM-B) to generate the actual user-facing content.

**Where to patch:**
- Add fields to agent schema/state (likely `letta/schemas/agent.py`) and persistence (ORM + serializers) to store e.g. `response_model` or `response_llm_config`. (Not cited here because `AgentState` definition was not directly opened in this environment; treat as an engineering task.)  
- In `letta/agents/letta_agent.py`, add a second `LLMClient` creation path using `response_llm_config` (mirroring the existing `LLMClient.create(...)` call). citeturn40view4turn15view0  

**Minimal illustrative patch sketch (conceptual):**
```python
# File: letta/agents/letta_agent.py
# Concept only: names may differ in your branch.

def _make_llm_client(self, llm_config):
    return LLMClient.create(
        provider_type=llm_config.model_endpoint_type,
        put_inner_thoughts_first=True,
        actor=self.actor,
    )

async def step(...):
    # Existing: memory/tool model
    tool_llm = self._make_llm_client(agent_state.llm_config)

    # Run the existing agent loop using tool_llm until it produces a "final" message/tool call.
    result = await self._step(agent_state=agent_state, llm_client=tool_llm, ...)

    # New: if response_llm_config exists, generate the final reply using response model
    if getattr(agent_state, "response_llm_config", None):
        response_llm = self._make_llm_client(agent_state.response_llm_config)

        # Build a response prompt from:
        # - updated memory blocks
        # - latest user message
        # - a compact "response brief" produced by tool_llm
        final_text = await self._generate_response_text(response_llm, agent_state, result)

        # Replace the outward-facing assistant content with final_text
        result = self._replace_final_assistant_content(result, final_text)

    return result
```

**Engineering risks/considerations:**
- You must define **what the “handoff artifact” is** (e.g., a structured “response brief” JSON) so LLM-A and LLM-B interoperate reliably.  
- The response model must not accidentally attempt to call tools unless you explicitly disable tools in the final call (mirroring how the summarizer uses `tools=[]` in its request builder). citeturn12view2turn42view0  
- Token accounting, tracing, and stored message provenance become more complex because the final user text is generated by a different model than the model that drove tool calls. (Letta logs step metadata including model fields from `agent_state.llm_config` in the step manager calls.) citeturn40view0  

#### Strategy B: Implement a “server tool” that invokes the response model, so LLM-A explicitly chooses when to call LLM-B

**Concept:** Add a tool like `compose_final_reply(brief, constraints)` whose implementation is: call LLM-B (response model), return the user-facing string; store it as the assistant message. In this paradigm, the memory manager LLM still controls control flow/tool calling, but delegates the final natural language realization to the response model.

This aligns well with the MemGPT paper’s principle that completion tokens represent function calls, but extends it by adding a function that itself calls another model. citeturn45view1turn45view4

**Where to patch:**
- Add a new tool type in the tool executor pipeline (likely under `letta/services/tool_executor/...`) and define schema/allow-list rules (Letta uses tool rules such as `InitToolRule`, `ContinueToolRule`, etc., in specialized agents). citeturn29view0  
- Provide configuration for tool to locate LLM-B (either per-agent field or per-tool env vars). `LLMConfig` already provides the necessary provider+endpoint fields. citeturn15view0  

**Why Strategy B can be cleaner than Strategy A:**
- LLM-A remains the system’s “OS” and explicitly calls a “render response” function when ready.  
- LLM-B is encapsulated as a tool; you can version it, restrict it, and trace it separately.

### Practical recommendation by use case

If your primary goal is **cost control or latency control** (e.g., cheap model for memory consolidation, expensive model for user replies), the **sleep-time agent approach** is the most “native” Letta pattern: use an expensive/strong conversational model for the main agent and a cheaper model for the sleep-time memory agent, with shared blocks to convey learned context. citeturn21view0turn37view0

If your goal is **per-turn deterministic separation** (memory pass always runs first, then response pass), you likely need **Strategy A or B**, because the built-in sleep-time scheduling is not equivalent to “memory pass before every response.” citeturn21view0turn37view0