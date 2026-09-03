from __future__ import annotations

from app.core.modes import ProcessingMode
from app.text.processor import TextProcessor


class ProcessingPipeline:
    """Processes transcribed text according to the selected mode."""

    def __init__(
        self,
        text_processor: TextProcessor,
        mode: ProcessingMode = ProcessingMode.INSTANT,
    ) -> None:
        self.text_processor = text_processor
        self.mode = mode

    def process(self, text: str) -> str:
        """Process text using the selected mode."""

        text = self.text_processor.process(text)

        if self.mode == ProcessingMode.INSTANT:
            return text

        if self.mode == ProcessingMode.AI:
            raise NotImplementedError(
                "AI processing is not implemented yet."
            )

        raise ValueError(f"Unsupported processing mode: {self.mode}")

    def set_mode(self, mode: ProcessingMode) -> None:
        """Change the active processing mode."""
        self.mode = mode