# Character Manifest Guide

## Why This Exists

Character manifests now define two different things clearly and separately:

- the final reply-provider behavior for a character
- the Letta memory seeded for each user-agent session

The current schema is a clean dev-phase break. Older keys such as `persona`, `system_prompt`,
`shared_blocks`, and `shared_passages` are intentionally no longer supported.

## Old to New Mapping

| Old key | New key | Meaning now |
|---|---|---|
| `persona` + `system_prompt` | `system_instructions` | One instruction layer sent to the final reply provider |
| `shared_blocks` | `shared_memory_blocks` | Shared Letta memory blocks attached to every agent for the character |
| `shared_passages` | `archival_memory_seed` | Real archival-memory items copied into each new agent |
| `memory.archival_search_limit` | `memory.archival_memory_search_limit` | Retrieval count for live turns |
| `memory.snapshot_passage_limit` | `memory.snapshot_archival_memory_limit` | Snapshot count in the Dev UI |
| `memory.recent_message_window` | `memory.conversation_history_window` | Recent turn window included in the final call |
| `memory.initial_human_block` | `memory.initial_user_memory` | Initial Letta `human` block |

## Important Definitions

### `system_instructions`

`system_instructions` is the full instruction layer used for the final reply-provider call.

Good fit:

- identity and stable character truth
- language and tone rules
- honesty constraints
- formatting bans
- output-length preferences

This field is shown in the Dev UI under `Prompt Pipeline -> System Instructions`.

### `shared_memory_blocks`

`shared_memory_blocks` are shared across every Letta agent for the same character.

If three users talk to `lin_xiaotang`, they each get a separate Letta agent, but all three agents
attach the same shared memory blocks for that character.

These blocks are part of the working context.

Use them for reusable, separately inspectable facets such as:

- `style`
- `background`
- `relationship_rules`
- `safety_overrides`

### `archival_memory_seed`

`archival_memory_seed` is no longer a fake lore block.

Each item is copied into the new agent's archival memory once, when that `(user_id, character_id)`
pair is first created.

That means:

- it is not shared live across all users
- it is stored as real archival memory
- it can later appear in retrieval and in the Dev UI's archival-memory views

Use it for evergreen facts or motifs that should behave like retrievable archival memory.

### `memory.initial_user_memory`

This is the starting Letta `human` block for a new user-agent pair.

Use it for a neutral initial summary such as:

- no stable preferences are known yet
- the relationship is new
- no confirmed nickname or long-term context exists yet

## How the Current Runtime Uses These Fields

For the current phase-1 runtime:

- Letta stores and retrieves memory
- the app still performs post-turn memory extraction with local Ollama
- the final user-facing reply still goes to the configured provider, which may be DouBao or Ollama

The final provider call is assembled from:

- `system_instructions`
- working-context memory blocks
- retrieved archival memory
- the recent conversation window

So if you inspect the Dev UI, the pipeline is:

- `System Instructions`
- `Working Context`
- `Conversation Window`
- `Retrieved Archival Memory`
- `Final Provider Call`

## Authoring Guidance

### Put identity and rules in one place

Because `system_instructions` replaced the old `persona` + `system_prompt` split, do not try to
recreate the old split manually. Write one coherent instruction block instead.

### Keep shared blocks focused

Do not duplicate the whole character description into every shared memory block.
Each block should have one clear job.

### Use archival seed only for retrievable facts

`archival_memory_seed` should be a list of short, durable snippets.
Do not use it for long essays or giant instruction paragraphs.

### Chinese perspective rule

For Chinese characters, keep perspective consistent.
Usually that means:

- use `你` for direct instructions to the model
- use concise noun-phrase facts for archival seed items
- avoid mixing `你` and `她` unless the distinction is very deliberate

## Provider Parameter Notes

The template includes brief inline explanations for each reply-provider field, including:

- `kind`: which adapter handles the final reply call
- `base_url`: base server address for providers such as Ollama
- `endpoint`: full target URL for `custom_simple_http`
- `model`: provider-side model identifier
- `transport`: HTTP method for `custom_simple_http`
- `timeout_seconds`: per-request timeout
- `headers`: optional request headers
- `extra.temperature`: randomness control for supported providers
- `extra.num_predict`: output-length cap for Ollama native generation

Remember that `extra` is provider-specific. If a field is not recognized by that adapter, it will
be ignored or passed through depending on the provider implementation.

## Template

Use the commented template at:

- `characters/templates/character_manifest.template.yaml`
