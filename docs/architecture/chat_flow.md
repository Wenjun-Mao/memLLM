# Chat Flow

1. Resolve the character manifest and its `system_instructions`.
2. Resolve or create the Letta agent for `(user_id, character_id)`.
3. Read Letta memory blocks for the pair.
4. Search Letta archival memory for top-k relevant items.
5. Load the recent conversation window from app metadata.
6. Assemble the final provider request from:
   - `system_instructions`
   - working-context memory blocks
   - retrieved archival memory
   - conversation window
7. Send the final provider call.
8. Run the local post-turn memory extractor.
9. Write the resulting user-memory and archival-memory updates back to Letta.
10. Persist the finished turn in app metadata.
