from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path
from typing import Any


class SnippetStore:
    """Persistent local storage and trigger expansion for Saydo snippets."""

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
        return data / "snippets.json"

    def load(self) -> list[dict[str, str]]:
        with self._lock:
            try:
                if not self.path.exists():
                    return []
                data: Any = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    return []
                return [
                    {
                        "name": str(item.get("name", "")).strip(),
                        "trigger": str(item.get("trigger", "")).strip(),
                        "text": str(item.get("text", "")),
                    }
                    for item in data
                    if isinstance(item, dict)
                    and str(item.get("trigger", "")).strip()
                    and str(item.get("text", ""))
                ]
            except Exception:
                return []

    def save(self, entries: list[dict[str, str]]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def add(self, name: str, trigger: str, text: str) -> None:
        name = name.strip()
        trigger = trigger.strip()
        text = text.strip()
        if not trigger or not text:
            raise ValueError("Snippet trigger and text are required.")

        with self._lock:
            entries = self.load()
            entries.append(
                {
                    "name": name or trigger,
                    "trigger": trigger,
                    "text": text,
                }
            )
            self.save(entries)

    def update(self, index: int, name: str, trigger: str, text: str) -> None:
        name = name.strip()
        trigger = trigger.strip()
        text = text.strip()
        if not trigger or not text:
            raise ValueError("Snippet trigger and text are required.")

        with self._lock:
            entries = self.load()
            if not 0 <= index < len(entries):
                raise IndexError("Snippet index out of range.")
            entries[index] = {
                "name": name or trigger,
                "trigger": trigger,
                "text": text,
            }
            self.save(entries)

    def delete(self, index: int) -> None:
        with self._lock:
            entries = self.load()
            if 0 <= index < len(entries):
                entries.pop(index)
                self.save(entries)

    def find(self, trigger: str) -> dict[str, str] | None:
        needle = trigger.strip().casefold()
        if not needle:
            return None
        for entry in self.load():
            if entry["trigger"].casefold() == needle:
                return entry
        return None

    def apply(self, text: str) -> str:
        """Expand snippets when their trigger occurs as a whole phrase."""
        result = text
        entries = sorted(
            self.load(),
            key=lambda item: len(item["trigger"]),
            reverse=True,
        )

        for entry in entries:
            trigger = entry["trigger"]
            replacement = entry["text"]
            pattern = re.compile(
                rf"(?<!\w){re.escape(trigger)}(?!\w)",
                re.IGNORECASE | re.UNICODE,
            )
            result = pattern.sub(replacement, result)

        return result
