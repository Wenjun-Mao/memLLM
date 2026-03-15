from __future__ import annotations

import httpx
from memllm_domain import ChatRequest


class ApiClient:
    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds)

    def list_characters(self) -> list[dict]:
        response = self._client.get("/characters")
        response.raise_for_status()
        return response.json()

    def seed_characters(self) -> dict:
        response = self._client.post("/seed/characters")
        response.raise_for_status()
        return response.json()

    def get_memory(self, *, user_id: str, character_id: str) -> dict:
        response = self._client.get(f"/memory/{user_id}/{character_id}")
        response.raise_for_status()
        return response.json()

    def send_chat(self, *, user_id: str, character_id: str, message: str) -> dict:
        payload = ChatRequest(user_id=user_id, character_id=character_id, message=message)
        response = self._client.post("/chat", json=payload.model_dump(mode="json"))
        response.raise_for_status()
        return response.json()
