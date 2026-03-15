from __future__ import annotations

import json
from typing import Protocol

import httpx
from loguru import logger
from memllm_domain import ProviderConfig, ProviderError, ProviderResponse, ReplyRequest


def _format_memory_context(request: ReplyRequest) -> str:
    block_lines = [f"{block.label}: {block.value}" for block in request.memory_context.blocks]
    passage_lines = [f"- {passage.text}" for passage in request.memory_context.passages]
    sections = [
        f"Character: {request.character.display_name}",
        "Memory blocks:\n" + ("\n".join(block_lines) if block_lines else "- none"),
        "Relevant passages:\n" + ("\n".join(passage_lines) if passage_lines else "- none"),
    ]
    return "\n\n".join(sections)


def _format_user_content(request: ReplyRequest) -> str:
    history = "\n".join(
        f"{message.role.title()}: {message.content}" for message in request.messages
    )
    return f"{_format_memory_context(request)}\n\nConversation:\n{history}"


def _format_system_content(request: ReplyRequest) -> str:
    prompt_parts = [request.character.persona]
    if request.character.system_prompt:
        prompt_parts.append(request.character.system_prompt)
    prompt_parts.append("Stay consistent with the character and the provided memory context.")
    return "\n\n".join(prompt_parts)


def _parse_simple_payload(response: httpx.Response) -> tuple[str, object]:
    if "application/json" in response.headers.get("content-type", ""):
        payload = response.json()
        if isinstance(payload, str):
            return payload, payload
        if isinstance(payload, dict):
            for key in ("content", "reply", "message", "answer", "response"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value, payload
                if isinstance(value, dict):
                    nested = value.get("content")
                    if isinstance(nested, str):
                        return nested, payload
            return json.dumps(payload, ensure_ascii=False), payload
        return json.dumps(payload, ensure_ascii=False), payload

    text = response.text.strip()
    return text, text


class ReplyProvider(Protocol):
    kind: str

    def generate(self, config: ProviderConfig, request: ReplyRequest) -> ProviderResponse: ...


class CustomSimpleHttpReplyProvider:
    kind = "custom_simple_http"

    def generate(self, config: ProviderConfig, request: ReplyRequest) -> ProviderResponse:
        if not config.endpoint:
            raise ProviderError("custom_simple_http requires an endpoint.")

        system_content = _format_system_content(request)
        user_content = _format_user_content(request)
        timeout = config.timeout_seconds
        params = {"system_content": system_content, "user_content": user_content, **config.extra}

        with httpx.Client(timeout=timeout, headers=config.headers) as client:
            if config.transport == "post":
                response = client.post(config.endpoint, json=params)
            else:
                response = client.get(config.endpoint, params=params)
            response.raise_for_status()

        content, payload = _parse_simple_payload(response)
        logger.debug(
            "custom_simple_http reply received for character={character_id}",
            character_id=request.character.character_id,
        )
        return ProviderResponse(provider_kind=self.kind, content=content, raw_payload=payload)


class OllamaChatReplyProvider:
    kind = "ollama_chat"

    def generate(self, config: ProviderConfig, request: ReplyRequest) -> ProviderResponse:
        base_url = (config.base_url or "http://localhost:11434").rstrip("/")
        model = config.model
        if not model:
            raise ProviderError("ollama_chat requires a model name.")

        messages = [{"role": "system", "content": _format_system_content(request)}]
        messages.extend(message.model_dump() for message in request.messages)
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            **config.extra,
        }

        with httpx.Client(timeout=config.timeout_seconds, headers=config.headers) as client:
            response = client.post(f"{base_url}/v1/chat/completions", json=payload)
            response.raise_for_status()

        body = response.json()
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Ollama response did not contain a chat completion.") from exc

        logger.debug(
            "ollama_chat reply received for character={character_id}",
            character_id=request.character.character_id,
        )
        return ProviderResponse(provider_kind=self.kind, content=content, raw_payload=body)
