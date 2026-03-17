from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from memllm_model_gateway.app import create_app
from memllm_model_gateway.settings import ModelGatewaySettings


class FakeHttpClient:
    handler = None

    def __init__(
        self,
        *,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        del timeout
        self._headers = headers or {}

    def __enter__(self) -> FakeHttpClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def post(self, url: str, json: dict | None = None) -> httpx.Response:
        assert self.handler is not None
        return self.handler("POST", url, json, dict(self._headers))

    def get(self, url: str, params: dict | None = None) -> httpx.Response:
        assert self.handler is not None
        return self.handler("GET", url, params, dict(self._headers))


def _response(
    method: str,
    url: str,
    *,
    status_code: int = 200,
    json_body=None,
    text: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request = httpx.Request(method, url)
    if json_body is not None:
        return httpx.Response(status_code, json=json_body, headers=headers, request=request)
    return httpx.Response(status_code, text=text or "", headers=headers, request=request)


def _settings_for(routes_path: Path) -> ModelGatewaySettings:
    return ModelGatewaySettings(routes_path=routes_path, trace_retention_limit=50)


def test_gateway_supports_direct_chat_and_embeddings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import memllm_model_gateway.service as service_module

    monkeypatch.setenv("MEMLLM_OLLAMA_OPENAI_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setenv("MEMLLM_DOUBAO_ENDPOINT", "https://example.invalid/doubao")
    monkeypatch.setenv("OLLAMA_MODEL_ALIAS", "memllm-qwen3.5-9b-q4km")
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b")

    routes_path = tmp_path / "routes.yaml"
    routes_path.write_text(
        """
routes:
  ollama_primary:
    kind: openai_chat_proxy
    base_url: ${MEMLLM_OLLAMA_OPENAI_BASE_URL}
    model: ${OLLAMA_MODEL_ALIAS}:latest
    defaults:
      stream: false
  qwen3-embedding:
    kind: ollama_embedding_proxy
    base_url: ${MEMLLM_OLLAMA_OPENAI_BASE_URL}
    model: ${OLLAMA_EMBED_MODEL}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def handler(
        method: str,
        url: str,
        payload: dict | None,
        headers: dict[str, str],
    ) -> httpx.Response:
        del headers
        if method == "POST" and url == "http://ollama:11434/api/chat":
            content = f"local::{payload['messages'][-1]['content']}"
            assert payload["options"]["temperature"] == 0.2
            assert payload["options"]["num_predict"] == 33
            assert payload["think"] is False
            return _response(
                method,
                url,
                json_body={
                    "model": "memllm-qwen3.5-9b-q4km:latest",
                    "created_at": "2026-03-16T00:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": f"<think>internal\n</think>\n\n{content}",
                    },
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 1,
                    "eval_count": 1,
                },
            )
        if method == "POST" and url == "http://ollama:11434/v1/embeddings":
            return _response(
                method,
                url,
                json_body={
                    "object": "list",
                    "data": [{"object": "embedding", "embedding": [0.1, 0.2], "index": 0}],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                },
            )
        raise AssertionError(f"unexpected request: {method} {url} {payload}")

    FakeHttpClient.handler = staticmethod(handler)
    monkeypatch.setattr(service_module.httpx, "Client", FakeHttpClient)

    app = create_app(_settings_for(routes_path))
    with TestClient(app) as client:
        models = client.get("/v1/models")
        assert models.status_code == 200
        assert {item["id"] for item in models.json()["data"]} == {
            "ollama_primary",
            "qwen3-embedding",
        }

        chat = client.post(
            "/v1/chat/completions",
            json={
                "model": "ollama_primary",
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": 0.2,
                "max_tokens": 33,
                "think": False,
            },
        )
        assert chat.status_code == 200
        assert chat.json()["model"] == "ollama_primary"
        assert chat.json()["choices"][0]["message"]["content"] == "local::hi"

        embeddings = client.post(
            "/v1/embeddings",
            json={"model": "qwen3-embedding", "input": "hello"},
        )
        assert embeddings.status_code == 200
        assert embeddings.json()["model"] == "qwen3-embedding"


def test_gateway_normalizes_openai_tool_messages_for_ollama(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import memllm_model_gateway.service as service_module

    monkeypatch.setenv("MEMLLM_OLLAMA_OPENAI_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setenv("OLLAMA_MODEL_ALIAS", "memllm-qwen3.5-9b-q4km")

    routes_path = tmp_path / "routes.yaml"
    routes_path.write_text(
        """
routes:
  ollama_sleep_time:
    kind: openai_chat_proxy
    base_url: ${MEMLLM_OLLAMA_OPENAI_BASE_URL}
    model: ${OLLAMA_MODEL_ALIAS}:latest
    defaults:
      stream: false
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def handler(
        method: str,
        url: str,
        payload: dict | None,
        headers: dict[str, str],
    ) -> httpx.Response:
        del headers
        assert method == "POST"
        assert url == "http://ollama:11434/api/chat"
        assert payload is not None
        assistant_message = payload["messages"][1]
        assert assistant_message["role"] == "assistant"
        assert assistant_message["tool_calls"][0]["function"]["arguments"] == {"label": "human"}
        tool_message = payload["messages"][2]
        assert tool_message == {
            "role": "tool",
            "content": '{"status": "OK"}',
            "tool_name": "memory_replace",
        }
        return _response(
            method,
            url,
            json_body={
                "model": "memllm-qwen3.5-9b-q4km:latest",
                "created_at": "2026-03-16T00:00:00Z",
                "message": {"role": "assistant", "content": "done"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 1,
                "eval_count": 1,
            },
        )

    FakeHttpClient.handler = staticmethod(handler)
    monkeypatch.setattr(service_module.httpx, "Client", FakeHttpClient)

    app = create_app(_settings_for(routes_path))
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "ollama_sleep_time",
                "messages": [
                    {"role": "system", "content": "system"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "memory_replace",
                                    "arguments": '{"label": "human"}',
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call_1",
                        "content": '{"status": "OK"}',
                    },
                ],
            },
        )
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "done"


def test_gateway_mediates_doubao_surface_and_passthrough_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import memllm_model_gateway.service as service_module

    monkeypatch.setenv("MEMLLM_OLLAMA_OPENAI_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setenv("MEMLLM_DOUBAO_ENDPOINT", "https://example.invalid/doubao")
    monkeypatch.setenv("OLLAMA_MODEL_ALIAS", "memllm-qwen3.5-9b-q4km")
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b")

    routes_path = tmp_path / "routes.yaml"
    routes_path.write_text(
        """
routes:
  doubao_primary:
    kind: tool_mediated_surface
    policy_route: ollama_primary
    surface_route: doubao_surface
  ollama_primary:
    kind: openai_chat_proxy
    base_url: ${MEMLLM_OLLAMA_OPENAI_BASE_URL}
    model: ${OLLAMA_MODEL_ALIAS}:latest
    defaults:
      stream: false
  doubao_surface:
    kind: custom_simple_http_surface
    endpoint: ${MEMLLM_DOUBAO_ENDPOINT}
    transport: get
""".strip()
        + "\n",
        encoding="utf-8",
    )

    calls: list[tuple[str, str, dict | None]] = []

    def handler(
        method: str,
        url: str,
        payload: dict | None,
        headers: dict[str, str],
    ) -> httpx.Response:
        del headers
        calls.append((method, url, payload))
        if method == "POST" and url == "http://ollama:11434/api/chat":
            user_text = payload["messages"][-1]["content"]
            if user_text == "use_tool":
                return _response(
                    method,
                    url,
                    json_body={
                        "model": "memllm-qwen3.5-9b-q4km:latest",
                        "created_at": "2026-03-16T00:00:00Z",
                        "message": {
                            "role": "assistant",
                            "content": "<think>tool reasoning</think>",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "lookup_weather",
                                        "arguments": {"city": "Toronto"},
                                    },
                                }
                            ],
                        },
                        "done": True,
                        "done_reason": "stop",
                        "prompt_eval_count": 1,
                        "eval_count": 1,
                    },
                )
            return _response(
                method,
                url,
                json_body={
                    "model": "memllm-qwen3.5-9b-q4km:latest",
                    "created_at": "2026-03-16T00:00:00Z",
                    "message": {"role": "assistant", "content": "draft from policy"},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 1,
                    "eval_count": 1,
                },
            )
        if method == "GET" and url == "https://example.invalid/doubao":
            return _response(
                method,
                url,
                json_body={
                    "status": 1001,
                    "data": {"content": "final text from doubao", "role": "assistant"},
                },
                headers={"content-type": "application/json"},
            )
        raise AssertionError(f"unexpected request: {method} {url} {payload}")

    FakeHttpClient.handler = staticmethod(handler)
    monkeypatch.setattr(service_module.httpx, "Client", FakeHttpClient)

    app = create_app(_settings_for(routes_path))
    with TestClient(app) as client:
        tool_call_response = client.post(
            "/v1/chat/completions",
            json={
                "model": "doubao_primary",
                "messages": [{"role": "user", "content": "use_tool"}],
            },
        )
        assert tool_call_response.status_code == 200
        assert tool_call_response.json()["model"] == "doubao_primary"
        assert tool_call_response.json()["choices"][0]["message"]["content"] == ""
        tool_call = tool_call_response.json()["choices"][0]["message"]["tool_calls"][0]
        assert tool_call["function"]["name"] == "lookup_weather"

        final_response = client.post(
            "/v1/chat/completions",
            json={"model": "doubao_primary", "messages": [{"role": "user", "content": "say hi"}]},
        )
        assert final_response.status_code == 200
        assert final_response.json()["model"] == "doubao_primary"
        assert final_response.json()["choices"][0]["message"]["content"] == "final text from doubao"

        traces = client.get("/debug/traces", params={"since_sequence": 0, "limit": 20})
        assert traces.status_code == 200
        phases = [item["phase"] for item in traces.json()["traces"]]
        assert "direct_chat_route_call" in phases
        assert "surface_route_call" in phases
        assert "mediated_final_response" in phases
        assert any(url == "https://example.invalid/doubao" for _, url, _ in calls)
