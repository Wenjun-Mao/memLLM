from __future__ import annotations

import json
from typing import Protocol

import httpx
from loguru import logger
from memllm_domain import (
    CharacterRecord,
    MemoryContext,
    MemoryDelta,
    MemoryExtractionResult,
)


class MemoryExtractor(Protocol):
    kind: str

    def extract(
        self,
        *,
        character: CharacterRecord,
        memory_context: MemoryContext,
        user_message: str,
        assistant_message: str,
    ) -> MemoryExtractionResult: ...


class HeuristicMemoryExtractor:
    kind = 'heuristic'

    def extract(
        self,
        *,
        character: CharacterRecord,
        memory_context: MemoryContext,
        user_message: str,
        assistant_message: str,
    ) -> MemoryExtractionResult:
        current_human = (
            memory_context.block_value('human') or character.memory.initial_user_memory
        )
        fact_line = f'- Recent topic: {user_message.strip()}'
        if fact_line not in current_human:
            updated_human = f'{current_human}\n{fact_line}'.strip()
        else:
            updated_human = current_human
        archival_entry = f'User: {user_message.strip()}\nAssistant: {assistant_message.strip()}'
        delta = MemoryDelta(
            user_memory_block_value=updated_human,
            archival_memory_entries=[archival_entry],
        )
        return MemoryExtractionResult(
            delta=delta,
            request_payload={
                'mode': 'heuristic',
                'existing_user_memory': current_human,
                'turn': {
                    'user': user_message,
                    'assistant': assistant_message,
                },
            },
            response_payload=delta.model_dump(mode='json'),
        )


class OllamaJsonMemoryExtractor:
    kind = 'ollama_json'

    def __init__(self, *, base_url: str, model: str, timeout_seconds: float = 45.0) -> None:
        self._base_url = base_url.rstrip('/')
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._fallback = HeuristicMemoryExtractor()

    def extract(
        self,
        *,
        character: CharacterRecord,
        memory_context: MemoryContext,
        user_message: str,
        assistant_message: str,
    ) -> MemoryExtractionResult:
        extractor_instructions = (
            'You maintain durable Letta user memory for a chatbot. '
            'Return exactly one compact JSON object with keys '
            '`user_memory_block_value` and `archival_memory_entries`. '
            '`user_memory_block_value` must be a concise replacement for the user\'s Letta '
            '`human` memory block. '
            '`archival_memory_entries` must be a JSON array of durable conversation snippets '
            'worth storing in archival memory. '
            'Do not wrap the JSON in markdown.'
        )
        context_dump = {
            'character': character.display_name,
            'system_instructions': character.system_instructions,
            'existing_user_memory': memory_context.block_value('human') or '',
            'memory_blocks': [
                block.model_dump(mode='json') for block in memory_context.memory_blocks
            ],
            'retrieved_archival_memory': [
                item.model_dump(mode='json') for item in memory_context.archival_memory
            ],
            'turn': {
                'user': user_message,
                'assistant': assistant_message,
            },
        }
        prompt = (
            f'<|im_start|>system\n{extractor_instructions}<|im_end|>\n'
            f'<|im_start|>user\n{json.dumps(context_dump, ensure_ascii=False)}<|im_end|>\n'
            '<|im_start|>assistant\n'
        )
        payload = {
            'model': self._model,
            'prompt': prompt,
            'stream': False,
            'raw': True,
            'keep_alive': -1,
            'options': {'temperature': 0},
        }
        request_debug = {
            'url': f'{self._base_url}/api/generate',
            'payload': payload,
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(request_debug['url'], json=payload)
                response.raise_for_status()
            body = response.json()
            content = self._cleanup_generated_text(body['response'])
            parsed = json.loads(self._extract_json_object(content))
            delta = MemoryDelta(
                user_memory_block_value=parsed.get('user_memory_block_value'),
                archival_memory_entries=[
                    str(item)
                    for item in parsed.get('archival_memory_entries', [])
                    if str(item).strip()
                ],
            )
            if not delta.user_memory_block_value and not delta.archival_memory_entries:
                raise ValueError('extractor returned an empty memory delta')
            return MemoryExtractionResult(
                delta=delta,
                request_payload=request_debug,
                response_payload={
                    'raw': body,
                    'parsed': delta.model_dump(mode='json'),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                'ollama_json extractor failed, falling back to heuristic extractor: {}', exc
            )
            fallback = self._fallback.extract(
                character=character,
                memory_context=memory_context,
                user_message=user_message,
                assistant_message=assistant_message,
            )
            return MemoryExtractionResult(
                delta=fallback.delta,
                request_payload=request_debug,
                response_payload={
                    'fallback_reason': str(exc),
                    'fallback_result': fallback.model_dump(mode='json'),
                },
            )

    @staticmethod
    def _cleanup_generated_text(content: str) -> str:
        cleaned = content.strip()
        if cleaned.startswith('<think>') and '</think>' in cleaned:
            cleaned = cleaned.split('</think>', 1)[1].lstrip()
        for marker in ('<|im_end|>', '<|endoftext|>', '<|im_start|>assistant'):
            cleaned = cleaned.replace(marker, '')
        return cleaned.strip()

    @staticmethod
    def _extract_json_object(content: str) -> str:
        start = content.find('{')
        end = content.rfind('}')
        if start == -1 or end == -1 or end < start:
            raise ValueError('no JSON object found in model output')
        return content[start : end + 1]
