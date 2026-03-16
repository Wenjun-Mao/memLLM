# Character Manifest Guide

## Why This Exists

Character manifests are doing two jobs at once:

- defining the character and reply-provider behavior
- seeding the Letta memory that every user-agent session starts from

That is why some fields can look similar if the authoring split is not clear.

## Important Definitions

### `shared_blocks`

`shared_blocks` are shared across every Letta agent for the same character.

For example, if three different users talk to `lin_xiaotang`, they each get a separate Letta
agent, but all three agents attach the same shared blocks for that character.

They are not shared across different characters.

### `shared_passages`

`shared_passages` in the manifest are not the same thing as archival conversation passages.

In the current code, the manifest loader converts `shared_passages` into a single shared Letta
block called `lore`.

So this:

```yaml
shared_passages:
  - fact A
  - fact B
```

becomes one shared block whose label is `lore` and whose value is a bullet list.

### `lore`

`lore` is just the block label the app currently uses for synthesized evergreen character facts
coming from `shared_passages`.

It is not a special Letta primitive. It is an app convention.

### `Passages` in the UI

The `Passages` section in the dev UI memory snapshot is different from manifest
`shared_passages`.

Those UI passages are real archival memory items retrieved from previous conversations for the
current `(user_id, character_id)` pair.

## Recommended Split Between Fields

### `persona`

Use `persona` for identity and durable character truth.

Good fit:

- who the character is
- age, background, temperament
- the stable relationship style the character should maintain

Avoid putting too many hard formatting rules here.

### `system_prompt`

Use `system_prompt` for runtime behavior rules.

Good fit:

- output language
- style constraints
- forbidden formats
- safety or honesty rules
- length preferences

This is the best place for instructions like "do not write stage directions in parentheses."

### `shared_blocks`

Use `shared_blocks` for reusable, separately inspectable memory facets that you want Letta to carry
for every user of that character.

Good fit:

- `style`
- `background`
- `relationship_rules`
- `safety_overrides`

Try to keep each block focused on one job. If a block just restates the full `persona`, it is
usually redundant.

### `shared_passages`

Use `shared_passages` for short evergreen lore facts that do not need their own labeled block.

Good fit:

- likes and dislikes
- recurring motifs
- standing interaction principles

If the facts are large or conceptually separate, prefer a named `shared_block` instead.

## What The Current Runtime Actually Does

The current prompt builder does two important things:

1. `system_content` includes `persona` plus `system_prompt`
2. `user_content` includes the flattened Letta memory blocks, which includes the seeded `persona`
   block again

So yes: some overlap in the final provider call is real today.

That does not mean manifests should be sloppy, but it does mean you will see `persona` twice in the
captured final call unless we later change the prompt-building code.

## Writing Perspective: `你` vs `她`

For Chinese characters, mixed perspective is usually a prompt-authoring mistake unless it is very
intentional.

Recommended rule:

- use `你` for instructions addressed to the model
- use neutral noun phrases for factual notes when possible
- avoid mixing `你` and `她` across adjacent fields unless the distinction is deliberate

For example, these are cleaner than third-person prose in `background` or `lore`:

```yaml
- label: background
  value: |
    你出生在苏州旧巷，外婆开过点心铺，也因此很会做中式甜点。
```

or:

```yaml
shared_passages:
  - 偏好：桂花、白山茶、茉莉、雨后石板路、傍晚冒热气的甜汤。
```

If a manifest mixes `你` and `她` without a clear reason, that is usually not a code bug, but it is prompt-style inconsistency. Treat it as authoring debt and clean it up.

## Authoring Checklist

Before adding a new character, check:

- `persona` explains identity, not formatting rules
- `system_prompt` explains behavior constraints, not biography
- each `shared_block` has one clear purpose
- `shared_passages` are evergreen facts, not long paragraphs
- Chinese perspective is consistent
- there is minimal repetition across `persona`, `system_prompt`, and shared memory

## Template

Use the commented template at:

- `characters/templates/character_manifest.template.yaml`
