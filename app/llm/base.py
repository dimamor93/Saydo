from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Base interface for LLM text processing providers."""

    @abstractmethod
    def process(self, text: str) -> str:
        """Process text and return the final result."""
        raise NotImplementedError