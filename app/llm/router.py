from __future__ import annotations

from enum import Enum

from app.llm.base import LLMProvider


class LLMStrategy(str, Enum):
    """How Saydo should choose an LLM provider."""

    AUTO = "auto"
    LOCAL = "local"
    CLOUD = "cloud"


class LLMRouter:
    """Selects the appropriate LLM provider."""

    def __init__(
        self,
        local_provider: LLMProvider | None = None,
        cloud_provider: LLMProvider | None = None,
        strategy: LLMStrategy = LLMStrategy.AUTO,
    ) -> None:
        self.local_provider = local_provider
        self.cloud_provider = cloud_provider
        self.strategy = strategy

    def process(self, text: str) -> str:
        """Process text using the configured provider strategy."""

        if self.strategy == LLMStrategy.LOCAL:
            if self.local_provider is None:
                raise RuntimeError(
                    "Local LLM provider is not available."
                )

            return self.local_provider.process(text)

        if self.strategy == LLMStrategy.CLOUD:
            if self.cloud_provider is None:
                raise RuntimeError(
                    "Cloud LLM provider is not available."
                )

            return self.cloud_provider.process(text)

        if self.strategy == LLMStrategy.AUTO:
            if self.local_provider is not None:
                try:
                    return self.local_provider.process(text)
                except Exception as exc:
                    print(
                        f"[Saydo] Local LLM failed: {exc}"
                    )

            if self.cloud_provider is not None:
                return self.cloud_provider.process(text)

            raise RuntimeError(
                "No LLM provider is available."
            )

        raise ValueError(
            f"Unsupported LLM strategy: {self.strategy}"
        )

    def set_strategy(self, strategy: LLMStrategy) -> None:
        """Change the provider selection strategy."""
        self.strategy = strategy