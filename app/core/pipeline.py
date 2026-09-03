from __future__ import annotations

from app.core.modes import ProcessingMode
from app.llm.base import LLMProvider
from app.text.processor import TextProcessor


class ProcessingPipeline:
    """Processes transcribed text according to the selected mode."""

    def __init__(
        self,
        text_processor: TextProcessor,
        mode: ProcessingMode = ProcessingMode.INSTANT,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.text_processor = text_processor
        self.mode = mode
        self.llm_provider = llm_provider

    def process(self, text: str) -> str:
        """Process text using the selected mode."""

        text = self.text_processor.process(text)

        if self.mode == ProcessingMode.INSTANT:
            return text

        if self.mode == ProcessingMode.AI:
            if self.llm_provider is None:
                raise RuntimeError(
                    "AI mode is enabled, but no LLM provider is available."
                )

            return self.llm_provider.process(text)

        raise ValueError(
            f"Unsupported processing mode: {self.mode}"
        )

    def set_mode(self, mode: ProcessingMode) -> None:
        """Change the active processing mode."""

        self.mode = mode