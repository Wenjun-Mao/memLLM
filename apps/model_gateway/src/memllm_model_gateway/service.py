from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import httpx
from loguru import logger

from memllm_model_gateway.config import (
    GatewayRoute,
    GatewayRoutesDocument,
    OllamaEmbeddingRoute,
    OpenAIChatRoute,
    SimpleSurfaceRoute,
    ToolMediatedSurfaceRoute,
)


class ModelGatewayError(Exception):
    pass


class UnknownModelRouteError(ModelGatewayError):
    pass


class UnsupportedRouteError(ModelGatewayError):
    pass


class TraceStore:
    def __init__(self, *, retention_limit: int) -> None:
        self._retention_limit = retention_limit
        self._sequence = 0
        self._items: deque[dict[str, Any]] = deque(maxlen=retention_limit)

    def append(
        self,
        *,
        phase: str,
        route_name: str,
        method: str,
        url: str,
        headers: dict[str, str],
        payload: object,
        response: object,
        status_code: int | None,
    ) -> dict[str, Any]:
        self._sequence += 1
        item = {
            "sequence": self._sequence,
            "created_at": datetime.now(UTC).isoformat(),
            "phase": phase,
            "route_name": route_name,
            "method": method,
            "url": url,
            "headers": headers,
            "payload": payload,
            "response": response,
            "status_code": status_code,
        }
        self._items.append(item)
        return item

    def latest_sequence(self) -> int:
        return self._sequence

    def list_since(self, *, since_sequence: int, limit: int) -> list[dict[str, Any]]:
        return [item for item in self._items if item["sequence"] > since_sequence][-limit:]


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        normalized = key.lower()
        if any(token in normalized for token in ("authorization", "api-key", "token", "secret")):
            sanitized[key] = "[redacted]"
        else:
            sanitized[key] = value
    return sanitized


def _content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return str(content)


def _openai_route_url(base_url: str, suffix: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}{suffix}"
    return f"{normalized}/v1{suffix}"


def _flatten_messages(messages: Iterable[dict[str, Any]]) -> str:
    rendered: list[str] = []
    for message in messages:
        role = str(message.get("role", "unknown"))
        name = message.get("name")
        prefix = f"{role}" if not name else f"{role}:{name}"
        content_text = _content_to_text(message.get("content"))
        if content_text:
            rendered.append(f"{prefix}: {content_text}")
        tool_calls = message.get("tool_calls") or []
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            rendered.append(
                "assistant_tool_call:"
                f"{function.get('name', 'unknown')} "
                f"{function.get('arguments', '')}"
            )
    return "\n".join(rendered)


def _parse_simple_payload(response: httpx.Response) -> tuple[str, object]:
    if "application/json" in response.headers.get("content-type", ""):
        payload = response.json()
    else:
        text = response.text.strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text, text
    content = _extract_content_from_object(payload)
    if content is not None:
        return content, payload
    if isinstance(payload, str):
        return payload, payload
    return json.dumps(payload, ensure_ascii=False), payload


def _extract_content_from_object(payload: object) -> str | None:
    if isinstance(payload, str):
        stripped = payload.strip()
        if stripped.startswith(("{", "[")):
            try:
                nested = json.loads(stripped)
            except json.JSONDecodeError:
                return payload
            return _extract_content_from_object(nested)
        return payload
    if isinstance(payload, list):
        for item in payload:
            extracted = _extract_content_from_object(item)
            if extracted:
                return extracted
        return None
    if isinstance(payload, dict):
        for key in ("content", "reply", "message", "answer", "response"):
            value = payload.get(key)
            extracted = _extract_content_from_object(value)
            if extracted:
                return extracted
        return _extract_content_from_object(payload.get("data"))
    return None


def _extract_completion_message(response_body: dict[str, Any]) -> dict[str, Any]:
    try:
        message = response_body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelGatewayError(
            "Model response did not include a valid choice.message payload."
        ) from exc
    if not isinstance(message, dict):
        raise ModelGatewayError("Model response choice.message was not an object.")
    return message


def _strip_thinking_content(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("<think>") and "</think>" in cleaned:
        cleaned = cleaned.split("</think>", 1)[1].lstrip()
    return cleaned


def _extract_completion_text(response_body: dict[str, Any]) -> str:
    message = _extract_completion_message(response_body)
    return _strip_thinking_content(_content_to_text(message.get("content")))


def _has_tool_calls(response_body: dict[str, Any]) -> bool:
    message = _extract_completion_message(response_body)
    return bool(message.get("tool_calls"))


def _build_chat_completion_response(
    *, model: str, content: str, usage: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-memllm-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                },
            }
        ],
        "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _is_ollama_chat_route(route: OpenAIChatRoute) -> bool:
    return "ollama" in route.base_url.lower()


def _ollama_chat_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return f"{normalized}/api/chat"


def _normalize_ollama_tool_arguments(arguments: object) -> object:
    if isinstance(arguments, str):
        stripped = arguments.strip()
        if not stripped:
            return {}
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return {"raw_arguments": arguments}
    if arguments is None:
        return {}
    return arguments


def _convert_openai_messages_to_ollama(messages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    tool_call_names: dict[str, str] = {}

    for message in messages:
        role = str(message.get("role", "user"))
        ollama_message: dict[str, Any] = {"role": role}

        if role == "tool":
            tool_call_id = str(message.get("tool_call_id") or "")
            tool_name = str(message.get("tool_name") or tool_call_names.get(tool_call_id) or "")
            ollama_message["content"] = _content_to_text(message.get("content"))
            if tool_name:
                ollama_message["tool_name"] = tool_name
            converted.append(ollama_message)
            continue

        content = _content_to_text(message.get("content"))
        if content or role != "assistant":
            ollama_message["content"] = content

        tool_calls_payload = []
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function") or {}
            tool_name = str(function.get("name") or "")
            call_id = str(tool_call.get("id") or "")
            if call_id and tool_name:
                tool_call_names[call_id] = tool_name
            tool_calls_payload.append(
                {
                    "function": {
                        "name": tool_name,
                        "arguments": _normalize_ollama_tool_arguments(function.get("arguments")),
                    }
                }
            )
        if tool_calls_payload:
            ollama_message["tool_calls"] = tool_calls_payload

        converted.append(ollama_message)

    return converted


def _build_ollama_chat_payload(payload: dict[str, Any], route: OpenAIChatRoute) -> dict[str, Any]:
    outbound_payload: dict[str, Any] = {
        "model": route.model,
        "messages": _convert_openai_messages_to_ollama(payload.get("messages") or []),
        "stream": bool(payload.get("stream", False)),
    }
    tools = payload.get("tools")
    if tools:
        outbound_payload["tools"] = tools

    if "think" in payload:
        outbound_payload["think"] = payload["think"]

    options: dict[str, Any] = {}
    if "temperature" in payload:
        options["temperature"] = payload["temperature"]
    max_tokens = payload.get("max_completion_tokens", payload.get("max_tokens"))
    if max_tokens is not None:
        options["num_predict"] = max_tokens
    if options:
        outbound_payload["options"] = options
    return outbound_payload


def _translate_ollama_chat_response(
    *,
    route_name: str,
    response_body: dict[str, Any],
) -> dict[str, Any]:
    message = response_body.get("message") or {}
    content = _strip_thinking_content(_content_to_text(message.get("content")))
    tool_calls_payload = []
    for index, tool_call in enumerate(message.get("tool_calls") or []):
        function = tool_call.get("function") or {}
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments or {}, ensure_ascii=False)
        tool_calls_payload.append(
            {
                "id": tool_call.get("id") or f"call_{index}",
                "type": "function",
                "function": {
                    "name": function.get("name", ""),
                    "arguments": arguments,
                },
            }
        )

    assistant_message: dict[str, Any] = {
        "role": "assistant",
        # When Ollama emits both reasoning text and tool calls, Letta should follow the
        # tool path instead of surfacing the reasoning blob as the assistant reply.
        "content": "" if tool_calls_payload else content,
    }
    finish_reason = "stop"
    if tool_calls_payload:
        assistant_message["tool_calls"] = tool_calls_payload
        finish_reason = "tool_calls"

    return {
        "id": f"chatcmpl-memllm-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": route_name,
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": assistant_message,
            }
        ],
        "usage": {
            "prompt_tokens": response_body.get("prompt_eval_count", 0),
            "completion_tokens": response_body.get("eval_count", 0),
            "total_tokens": (response_body.get("prompt_eval_count", 0) or 0)
            + (response_body.get("eval_count", 0) or 0),
        },
    }


class ModelGatewayService:
    def __init__(
        self, *, routes_document: GatewayRoutesDocument, trace_retention_limit: int
    ) -> None:
        self._routes_document = routes_document
        self._traces = TraceStore(retention_limit=trace_retention_limit)

    def latest_sequence(self) -> int:
        return self._traces.latest_sequence()

    def list_traces(self, *, since_sequence: int, limit: int) -> dict[str, Any]:
        return {
            "latest_sequence": self.latest_sequence(),
            "traces": self._traces.list_since(since_sequence=since_sequence, limit=limit),
        }

    def list_models(self) -> dict[str, Any]:
        data = []
        for route_name, route in self._routes_document.routes.items():
            if getattr(route, "visible", True):
                data.append(
                    {
                        "id": route_name,
                        "object": "model",
                        "created": 0,
                        "owned_by": "memllm-model-gateway",
                    }
                )
        return {"object": "list", "data": data}

    def chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        route_name = str(payload.get("model") or "")
        route = self._resolve_route(route_name)
        if isinstance(route, OpenAIChatRoute):
            return self._call_openai_chat_route(route_name=route_name, route=route, payload=payload)
        if isinstance(route, ToolMediatedSurfaceRoute):
            return self._call_mediated_surface_route(
                route_name=route_name, route=route, payload=payload
            )
        raise UnsupportedRouteError(f"Route {route_name} does not support chat completions.")

    def embeddings(self, payload: dict[str, Any]) -> dict[str, Any]:
        route_name = str(payload.get("model") or "")
        route = self._resolve_route(route_name)
        if not isinstance(route, OllamaEmbeddingRoute):
            raise UnsupportedRouteError(f"Route {route_name} does not support embeddings.")

        outbound_payload = {**payload, "model": route.model}
        url = _openai_route_url(route.base_url, "/embeddings")
        with httpx.Client(timeout=route.timeout_seconds, headers=route.headers) as client:
            response = client.post(url, json=outbound_payload)
            body = response.json() if response.content else {}
        response.raise_for_status()
        body["model"] = route_name
        self._record_trace(
            phase="embedding_route_call",
            route_name=route_name,
            method="POST",
            url=url,
            headers=route.headers,
            payload=outbound_payload,
            response=body,
            status_code=response.status_code,
        )
        return body

    def _resolve_route(self, route_name: str) -> GatewayRoute:
        route = self._routes_document.routes.get(route_name)
        if route is None:
            raise UnknownModelRouteError(f"Unknown model route: {route_name}")
        return route

    def _record_trace(
        self,
        *,
        phase: str,
        route_name: str,
        method: str,
        url: str,
        headers: dict[str, str],
        payload: object,
        response: object,
        status_code: int | None,
    ) -> dict[str, Any]:
        trace = self._traces.append(
            phase=phase,
            route_name=route_name,
            method=method,
            url=url,
            headers=_sanitize_headers(headers),
            payload=payload,
            response=response,
            status_code=status_code,
        )
        logger.debug(
            "Recorded gateway trace {} for route {} phase {}", trace["sequence"], route_name, phase
        )
        return trace

    def _call_openai_chat_route(
        self,
        *,
        route_name: str,
        route: OpenAIChatRoute,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        outbound_payload = {**route.defaults, **payload, "model": route.model}
        if _is_ollama_chat_route(route):
            native_payload = _build_ollama_chat_payload(outbound_payload, route)
            url = _ollama_chat_url(route.base_url)
            with httpx.Client(timeout=route.timeout_seconds, headers=route.headers) as client:
                response = client.post(url, json=native_payload)
                if response.content:
                    try:
                        body = response.json()
                    except ValueError:
                        body = response.text
                else:
                    body = {}
            translated = (
                _translate_ollama_chat_response(route_name=route_name, response_body=body)
                if isinstance(body, dict) and response.is_success
                else body
            )
            self._record_trace(
                phase="direct_chat_route_call",
                route_name=route_name,
                method="POST",
                url=url,
                headers=route.headers,
                payload=native_payload,
                response={"raw": body, "translated": translated}
                if response.is_success
                else body,
                status_code=response.status_code,
            )
            response.raise_for_status()
            if not isinstance(translated, dict):
                raise ModelGatewayError("Ollama chat route returned a non-JSON success payload.")
            return translated

        url = _openai_route_url(route.base_url, "/chat/completions")
        with httpx.Client(timeout=route.timeout_seconds, headers=route.headers) as client:
            response = client.post(url, json=outbound_payload)
            if response.content:
                try:
                    body = response.json()
                except ValueError:
                    body = response.text
            else:
                body = {}
        self._record_trace(
            phase="direct_chat_route_call",
            route_name=route_name,
            method="POST",
            url=url,
            headers=route.headers,
            payload=outbound_payload,
            response=body,
            status_code=response.status_code,
        )
        response.raise_for_status()
        if isinstance(body, dict):
            body["model"] = route_name
        return body

    def _call_mediated_surface_route(
        self,
        *,
        route_name: str,
        route: ToolMediatedSurfaceRoute,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        policy_route = self._resolve_route(route.policy_route)
        if not isinstance(policy_route, OpenAIChatRoute):
            raise UnsupportedRouteError(
                f"Policy route {route.policy_route} must be an openai_chat_proxy route."
            )
        policy_response = self._call_openai_chat_route(
            route_name=route.policy_route,
            route=policy_route,
            payload=payload,
        )
        if _has_tool_calls(policy_response) and route.passthrough_tool_calls:
            policy_response["model"] = route_name
            return policy_response

        draft_text = _extract_completion_text(policy_response)
        surface_text = draft_text
        surface_response: object = {"rendered_from_policy": True}
        surface_route = self._resolve_route(route.surface_route)
        if isinstance(surface_route, SimpleSurfaceRoute):
            try:
                surface_text, surface_response = self._render_with_surface_route(
                    route_name=route.surface_route,
                    route=surface_route,
                    request_payload=payload,
                    draft_text=draft_text,
                )
            except Exception as exc:  # noqa: BLE001
                if not route.surface_fallback_to_policy_text:
                    raise
                surface_response = {"fallback_reason": str(exc), "fallback_to_policy_text": True}
        else:
            raise UnsupportedRouteError(
                f"Surface route {route.surface_route} must be a custom_simple_http_surface route."
            )

        mediated_response = _build_chat_completion_response(
            model=route_name,
            content=surface_text,
            usage=policy_response.get("usage"),
        )
        self._record_trace(
            phase="mediated_final_response",
            route_name=route_name,
            method="POST",
            url="memllm://mediated-response",
            headers={},
            payload={"draft_text": draft_text},
            response={"surface_response": surface_response, "final_response": mediated_response},
            status_code=200,
        )
        return mediated_response

    def _render_with_surface_route(
        self,
        *,
        route_name: str,
        route: SimpleSurfaceRoute,
        request_payload: dict[str, Any],
        draft_text: str,
    ) -> tuple[str, object]:
        messages = request_payload.get("messages") or []
        system_messages = [
            _content_to_text(message.get("content"))
            for message in messages
            if isinstance(message, dict) and message.get("role") == "system"
        ]
        system_content = "\n\n".join(
            part
            for part in [
                *system_messages,
                (
                    "You are rendering the final user-facing reply after tool use has already "
                    "been handled. Preserve the facts and intent from the draft. Return only "
                    "the assistant reply text."
                ),
            ]
            if part
        )
        user_content = (
            "Letta draft reply:\n"
            f"{draft_text}\n\n"
            "Conversation and tool context:\n"
            f"{_flatten_messages(message for message in messages if isinstance(message, dict))}"
        )
        params = {"system_content": system_content, "user_content": user_content, **route.extra}
        method = "POST" if route.transport == "post" else "GET"
        with httpx.Client(timeout=route.timeout_seconds, headers=route.headers) as client:
            if route.transport == "post":
                response = client.post(route.endpoint, json=params)
            else:
                response = client.get(route.endpoint, params=params)
        response.raise_for_status()
        parsed_text, raw_payload = _parse_simple_payload(response)
        self._record_trace(
            phase="surface_route_call",
            route_name=route_name,
            method=method,
            url=route.endpoint,
            headers=route.headers,
            payload=params,
            response=raw_payload,
            status_code=response.status_code,
        )
        return parsed_text, raw_payload
