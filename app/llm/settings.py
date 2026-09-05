from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


class LLMSettingsStore:
    """Persistent settings shared by the dashboard and runtime."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self._default_path()

    @staticmethod
    def _default_path() -> Path:
        if getattr(sys, "frozen", False):
            root = Path(sys.executable).resolve().parent
        else:
            root = Path(__file__).resolve().parents[2]
        data = root / "data"
        data.mkdir(parents=True, exist_ok=True)
        return data / "settings.json"

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get_model(self, default: str = "qwen3.8:27b") -> str:
        value = self.load().get("llm_model", default)
        return value if isinstance(value, str) and value.strip() else default

    def get_ai_mode(self, default: bool = False) -> bool:
        value = self.load().get("ai_mode", default)
        return bool(value)

    def save_model(self, model: str) -> None:
        data = self.load()
        data["llm_model"] = model
        self._write(data)

    def save_ai_mode(self, enabled: bool) -> None:
        data = self.load()
        data["ai_mode"] = bool(enabled)
        self._write(data)

    def _write(self, data: dict[str, Any]) -> None:
        try:
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
