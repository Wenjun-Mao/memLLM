from __future__ import annotations

import json
from typing import Protocol

import httpx
from loguru import logger
from memllm_domain import (
    ProviderCallDebug,
    ProviderConfig,
    ProviderError,
    ProviderResponse,
    ReplyRequest,
)


def _format_memory_context(request: ReplyRequest) -> str:
    block_lines = [f"{block.label}: {block.value}" for block in request.memory_context.blocks]
    passage_lines = [f"- {passage.text}" for passage in request.memory_context.passages]
    sections = [
        f"Character: {request.character.display_name}",
        'Memory blocks:\n' + ('\n'.join(block_lines) if block_lines else '- none'),
        'Relevant passages:\n' + ('\n'.join(passage_lines) if passage_lines else '- none'),
    ]
    return '\n\n'.join(sections)


def _format_user_content(request: ReplyRequest) -> str:
    history = '\n'.join(
        f"{message.role.title()}: {message.content}" for message in request.messages
    )
    return f"{_format_memory_context(request)}\n\nConversation:\n{history}"


def _format_system_content(request: ReplyRequest) -> str:
    prompt_parts = [request.character.persona]
    if request.character.system_prompt:
        prompt_parts.append(request.character.system_prompt)
    prompt_parts.append('Stay consistent with the character and the provided memory context.')
    return '\n\n'.join(prompt_parts)


def _format_ollama_generate_prompt(request: ReplyRequest) -> str:
    prompt_parts = [f"<|im_start|>system\n{_format_system_content(request)}<|im_end|>"]
    for message in request.messages:
        prompt_parts.append(
            f"<|im_start|>{message.role}\n{message.content}<|im_end|>"
        )
    prompt_parts.append('<|im_start|>assistant\n')
    return '\n'.join(prompt_parts)


def _cleanup_ollama_generate_response(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith('<think>') and '</think>' in cleaned:
        cleaned = cleaned.split('</think>', 1)[1].lstrip()
    for marker in ('<|im_end|>', '<|endoftext|>', '<|im_start|>assistant'):
        cleaned = cleaned.replace(marker, '')
    return cleaned.strip()


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        normalized = key.lower()
        if any(token in normalized for token in ('authorization', 'api-key', 'token', 'secret')):
            sanitized[key] = '[redacted]'
        else:
            sanitized[key] = value
    return sanitized


def _extract_content_from_simple_payload(payload: object) -> str | None:
    if isinstance(payload, str):
        stripped = payload.strip()
        if stripped.startswith(('{', '[')):
            try:
                nested_payload = json.loads(stripped)
            except json.JSONDecodeError:
                return payload
            extracted = _extract_content_from_simple_payload(nested_payload)
            if extracted:
                return extracted
        return payload
    if isinstance(payload, dict):
        for key in ('content', 'reply', 'message', 'answer', 'response'):
            value = payload.get(key)
            extracted = _extract_content_from_simple_payload(value)
            if extracted:
                return extracted
        data = payload.get('data')
        extracted = _extract_content_from_simple_payload(data)
        if extracted:
            return extracted
        return None
    if isinstance(payload, list):
        for item in payload:
            extracted = _extract_content_from_simple_payload(item)
            if extracted:
                return extracted
        return None
    return None


def _parse_simple_payload(response: httpx.Response) -> tuple[str, object]:
    if 'application/json' in response.headers.get('content-type', ''):
        payload = response.json()
        extracted = _extract_content_from_simple_payload(payload)
        if extracted:
            return extracted, payload
        return json.dumps(payload, ensure_ascii=False), payload

    text = response.text.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text, text
    extracted = _extract_content_from_simple_payload(payload)
    if extracted:
        return extracted, payload
    if isinstance(payload, str):
        return payload, payload
    return json.dumps(payload, ensure_ascii=False), payload


class ReplyProvider(Protocol):
    kind: str

    def generate(self, config: ProviderConfig, request: ReplyRequest) -> ProviderResponse: ...


class CustomSimpleHttpReplyProvider:
    kind = 'custom_simple_http'

    def generate(self, config: ProviderConfig, request: ReplyRequest) -> ProviderResponse:
        if not config.endpoint:
            raise ProviderError('custom_simple_http requires an endpoint.')

        system_content = _format_system_content(request)
        user_content = _format_user_content(request)
        timeout = config.timeout_seconds
        params = {'system_content': system_content, 'user_content': user_content, **config.extra}
        method = 'POST' if config.transport == 'post' else 'GET'
        request_debug = ProviderCallDebug(
            provider_kind=self.kind,
            method=method,
            url=config.endpoint,
            headers=_sanitize_headers(config.headers),
            payload=params,
        )

        with httpx.Client(timeout=timeout, headers=config.headers) as client:
            if config.transport == 'post':
                response = client.post(config.endpoint, json=params)
            else:
                response = client.get(config.endpoint, params=params)
            response.raise_for_status()

        content, payload = _parse_simple_payload(response)
        request_debug = request_debug.model_copy(update={'response': payload})
        logger.debug(
            'custom_simple_http reply received for character={character_id}',
            character_id=request.character.character_id,
        )
        return ProviderResponse(
            provider_kind=self.kind,
            content=content,
            raw_payload=payload,
            request_debug=request_debug,
        )


class OllamaChatReplyProvider:
    kind = 'ollama_chat'

    def generate(self, config: ProviderConfig, request: ReplyRequest) -> ProviderResponse:
        base_url = (config.base_url or 'http://localhost:11434').rstrip('/')
        model = config.model
        if not model:
            raise ProviderError('ollama_chat requires a model name.')

        api_mode = str(config.extra.get('api_mode', 'native_generate'))
        keep_alive = config.extra.get('keep_alive', -1)
        generation_options = {
            key: value
            for key, value in config.extra.items()
            if key not in {'api_mode', 'keep_alive'}
        }

        with httpx.Client(timeout=config.timeout_seconds, headers=config.headers) as client:
            if api_mode == 'chat_completions':
                messages = [{'role': 'system', 'content': _format_system_content(request)}]
                messages.extend(message.model_dump() for message in request.messages)
                payload = {
                    'model': model,
                    'messages': messages,
                    'stream': False,
                    **generation_options,
                }
                url = f'{base_url}/v1/chat/completions'
                response = client.post(url, json=payload)
                response.raise_for_status()
                body = response.json()
                try:
                    content = body['choices'][0]['message']['content']
                except (KeyError, IndexError, TypeError) as exc:
                    raise ProviderError(
                        'Ollama response did not contain a chat completion.'
                    ) from exc
            else:
                payload = {
                    'model': model,
                    'prompt': _format_ollama_generate_prompt(request),
                    'stream': False,
                    'raw': True,
                    'keep_alive': keep_alive,
                }
                if generation_options:
                    payload['options'] = generation_options
                url = f'{base_url}/api/generate'
                response = client.post(url, json=payload)
                response.raise_for_status()
                body = response.json()
                try:
                    content = _cleanup_ollama_generate_response(body['response'])
                except KeyError as exc:
                    raise ProviderError(
                        'Ollama response did not contain generated text.'
                    ) from exc

        logger.debug(
            'ollama_chat reply received for character={character_id}',
            character_id=request.character.character_id,
        )
        return ProviderResponse(
            provider_kind=self.kind,
            content=content,
            raw_payload=body,
            request_debug=ProviderCallDebug(
                provider_kind=self.kind,
                method='POST',
                url=url,
                headers=_sanitize_headers(config.headers),
                payload=payload,
                response=body,
            ),
        )
