from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path


class UserDictionary:
    """Persistent local dictionary shared by the UI and processing pipeline."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self._default_path()
        self._lock = threading.RLock()

    @staticmethod
    def _default_path() -> Path:
        if getattr(sys, "frozen", False):
            root = Path(sys.executable).resolve().parent
        else:
            root = Path(__file__).resolve().parents[2]
        data = root / "data"
        data.mkdir(parents=True, exist_ok=True)
        return data / "dictionary.json"

    def load(self) -> list[dict[str, str]]:
        with self._lock:
            try:
                if not self.path.exists():
                    return []
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except (OSError, json.JSONDecodeError, TypeError):
                return []

    def save(self, entries: list[dict[str, str]]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def add_word(self, word: str) -> None:
        word = word.strip()
        if not word:
            return
        entries = self.load()
        if any(
            e.get("type") == "word"
            and e.get("word", "").casefold() == word.casefold()
            for e in entries
        ):
            return
        entries.insert(0, {"word": word, "type": "word"})
        self.save(entries)

    def add_correction(self, source: str, replacement: str) -> None:
        source = source.strip()
        replacement = replacement.strip()
        if not source or not replacement or source.casefold() == replacement.casefold():
            return

        entries = self.load()
        for entry in entries:
            if (
                entry.get("type") == "correction"
                and entry.get("source", "").casefold() == source.casefold()
            ):
                entry["replacement"] = replacement
                self.save(entries)
                return

        entries.insert(
            0,
            {
                "type": "correction",
                "source": source,
                "replacement": replacement,
            },
        )
        self.save(entries)

    def delete(self, index: int) -> None:
        entries = self.load()
        if 0 <= index < len(entries):
            entries.pop(index)
            self.save(entries)

    def corrections(self) -> list[tuple[str, str]]:
        return [
            (e.get("source", ""), e.get("replacement", ""))
            for e in self.load()
            if e.get("type") == "correction"
            and e.get("source")
            and e.get("replacement")
        ]

    def words(self) -> list[str]:
        return [
            e.get("word", "")
            for e in self.load()
            if e.get("type") == "word" and e.get("word")
        ]

    def apply(self, text: str) -> str:
        """Apply learned corrections to recognized text, case-insensitively."""
        if not text:
            return text

        result = text
        corrections = self.corrections()

        # Longest source first prevents a short correction from consuming
        # part of a longer phrase correction.
        corrections.sort(key=lambda pair: len(pair[0]), reverse=True)

        for source, replacement in corrections:
            pattern = re.compile(rf"(?<!\w){re.escape(source)}(?!\w)", re.IGNORECASE | re.UNICODE)
            result = pattern.sub(lambda _: replacement, result)

        return result
