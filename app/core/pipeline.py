from __future__ import annotations

from typing import Protocol

from app.core.dictionary import UserDictionary
from app.core.modes import ProcessingMode


class TextProcessorProtocol(Protocol):
    def process(self, text: str) -> str: ...


class LLMProviderProtocol(Protocol):
    def process(self, text: str) -> str: ...


class ProcessingPipeline:
    def __init__(
        self,
        text_processor: TextProcessorProtocol,
        mode: ProcessingMode = ProcessingMode.INSTANT,
        llm_provider: LLMProviderProtocol | None = None,
        dictionary: UserDictionary | None = None,
    ) -> None:
        self.text_processor = text_processor
        self.mode = mode
        self.llm_provider = llm_provider
        self.dictionary = dictionary or UserDictionary()

    def process(self, text: str) -> str:
        text = self.text_processor.process(text)

        # The user dictionary is part of Instant processing: it is a fast,
        # deterministic local correction layer and adds no LLM latency.
        if self.mode == ProcessingMode.INSTANT:
            return self.dictionary.apply(text)

        if self.mode == ProcessingMode.AI:
            if self.llm_provider is None:
                raise RuntimeError("AI mode requires an LLM provider")
            return self.llm_provider.process(text)

        raise ValueError(f"Unsupported processing mode: {self.mode}")

    def set_mode(self, mode: ProcessingMode) -> None:
        self.mode = mode
