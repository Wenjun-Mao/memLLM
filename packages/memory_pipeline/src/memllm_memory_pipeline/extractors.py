from __future__ import annotations

import json
from typing import Protocol

import httpx
from loguru import logger
from memllm_domain import CharacterRecord, MemoryContext, MemoryDelta


class MemoryExtractor(Protocol):
    kind: str

    def extract(
        self,
        *,
        character: CharacterRecord,
        memory_context: MemoryContext,
        user_message: str,
        assistant_message: str,
    ) -> MemoryDelta: ...


class HeuristicMemoryExtractor:
    kind = 'heuristic'

    def extract(
        self,
        *,
        character: CharacterRecord,
        memory_context: MemoryContext,
        user_message: str,
        assistant_message: str,
    ) -> MemoryDelta:
        current_human = memory_context.block_value('human') or character.memory.initial_human_block
        fact_line = f'- Recent topic: {user_message.strip()}'
        if fact_line not in current_human:
            updated_human = f'{current_human}\n{fact_line}'.strip()
        else:
            updated_human = current_human
        passage = f'User: {user_message.strip()}\nAssistant: {assistant_message.strip()}'
        return MemoryDelta(human_block_value=updated_human, passages=[passage])


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
    ) -> MemoryDelta:
        system_prompt = (
            'You maintain durable user memory for a chatbot. '
            'Return exactly one compact JSON object with keys '
            '`human_block_value` and `passages`. '
            '`human_block_value` must be a concise replacement for the user\'s Letta human block. '
            '`passages` must be a JSON array of durable conversation snippets worth storing. '
            'Do not wrap the JSON in markdown.'
        )
        context_dump = {
            'character': character.display_name,
            'persona': character.persona,
            'existing_human_block': memory_context.block_value('human') or '',
            'relevant_blocks': [block.model_dump() for block in memory_context.blocks],
            'relevant_passages': [passage.model_dump() for passage in memory_context.passages],
            'turn': {
                'user': user_message,
                'assistant': assistant_message,
            },
        }
        prompt = (
            f'<|im_start|>system\n{system_prompt}<|im_end|>\n'
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

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(f'{self._base_url}/api/generate', json=payload)
                response.raise_for_status()
            body = response.json()
            content = self._cleanup_generated_text(body['response'])
            parsed = json.loads(self._extract_json_object(content))
            delta = MemoryDelta(
                human_block_value=parsed.get('human_block_value'),
                passages=[str(item) for item in parsed.get('passages', []) if str(item).strip()],
            )
            if not delta.human_block_value and not delta.passages:
                raise ValueError('extractor returned an empty memory delta')
            return delta
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                'ollama_json extractor failed, falling back to heuristic extractor: {}', exc
            )
            return self._fallback.extract(
                character=character,
                memory_context=memory_context,
                user_message=user_message,
                assistant_message=assistant_message,
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
