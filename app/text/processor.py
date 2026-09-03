from __future__ import annotations

import json
import re
from pathlib import Path


class TextProcessor:
    """Lightweight local text post-processing."""

    def __init__(
        self,
        dictionary_path: str | Path = "data/dictionary.json",
    ) -> None:
        self.dictionary_path = Path(dictionary_path)
        self.dictionary = self._load_dictionary()

    def _load_dictionary(self) -> dict[str, str]:
        if not self.dictionary_path.exists():
            return {}

        try:
            with self.dictionary_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

            if not isinstance(data, dict):
                return {}

            return {
                str(source): str(target)
                for source, target in data.items()
            }

        except (OSError, json.JSONDecodeError):
            return {}

    def process(self, text: str) -> str:
        """Clean recognized text without using an LLM."""
        text = text.strip()

        if not text:
            return ""

        # Normalize whitespace.
        text = " ".join(text.split())

        # Apply dictionary, ignoring letter case.
        for source, target in self.dictionary.items():
            pattern = re.compile(
                rf"\b{re.escape(source)}\b",
                re.IGNORECASE,
            )
            text = pattern.sub(target, text)

        return text