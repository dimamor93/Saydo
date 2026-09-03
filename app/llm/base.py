from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Base interface for text post-processing providers."""

    @abstractmethod
    def process(self, text: str) -> str:
        """Process recognized text and return the final text."""
        raise NotImplementedError