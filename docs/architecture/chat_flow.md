# Chat Flow

## Runtime Path

1. Resolve the requested character from app metadata.
2. Resolve or create the `(user_id, character_id)` Letta agent session.
3. Pull relevant memory from Letta:
   - current blocks such as `persona`, `style`, `human`
   - top-k relevant passages for the current user message
4. Build a normalized request for the configured reply provider.
5. Generate the user-facing reply through the provider adapter.
6. Return the reply immediately.
7. In the background, run local memory extraction through Ollama and write the resulting delta back to Letta.
8. Record the completed turn in the app metadata store.

## Important Boundary

Letta is the memory system. The reply provider is the user-facing generation system. This keeps
provider switching possible without changing the memory model.

## Development UI Boundary

- The Streamlit app is for chatting, switching characters, and checking snapshots.
- Letta Desktop or ADE is for direct memory inspection and editing.
