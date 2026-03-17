# Chat Flow

1. The Dev UI sends `user_id`, `character_id`, and `message` to the API.
2. The API resolves or creates the Letta session for that pair.
3. The API records baseline Letta step ids and gateway trace sequence numbers.
4. The API sends the message into the Letta primary agent.
5. In the standard dev stack, Letta calls the configured `model_gateway` route.
6. The gateway either proxies a shaped local Qwen route or mediates between a local tool-policy route and the DouBao surface route.
7. Letta returns the user-visible reply.
8. In dev mode, the API waits for the sleep-time agent so the current-round trace is complete.
9. The API returns the reply plus the structured debug payload.
