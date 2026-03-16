from __future__ import annotations

from memllm_domain import CharacterRecord, MemoryContext, MemoryExtractionResult

from memllm_memory_pipeline.extractors import (
    HeuristicMemoryExtractor,
    MemoryExtractor,
    OllamaJsonMemoryExtractor,
)


class MemoryExtractorRegistry:
    def __init__(self, extractors: list[MemoryExtractor] | None = None) -> None:
        self._extractors = {
            extractor.kind: extractor for extractor in extractors or [HeuristicMemoryExtractor()]
        }

    def register(self, extractor: MemoryExtractor) -> None:
        self._extractors[extractor.kind] = extractor

    def extract(
        self,
        *,
        kind: str,
        character: CharacterRecord,
        memory_context: MemoryContext,
        user_message: str,
        assistant_message: str,
    ) -> MemoryExtractionResult:
        extractor = self._extractors[kind]
        return extractor.extract(
            character=character,
            memory_context=memory_context,
            user_message=user_message,
            assistant_message=assistant_message,
        )

    @classmethod
    def with_defaults(
        cls,
        *,
        ollama_base_url: str,
        ollama_model: str,
        timeout_seconds: float,
    ) -> MemoryExtractorRegistry:
        registry = cls([HeuristicMemoryExtractor()])
        registry.register(
            OllamaJsonMemoryExtractor(
                base_url=ollama_base_url,
                model=ollama_model,
                timeout_seconds=timeout_seconds,
            )
        )
        return registry
