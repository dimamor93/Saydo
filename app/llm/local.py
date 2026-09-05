from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.core.style import StyleStore
from app.llm.base import LLMProvider

SYSTEM_PROMPT = """
Ты — редактор текста голосовой диктовки.
Твоя задача — превратить расшифровку речи в чистый письменный текст.
Правила:
- Сохраняй исходный смысл.
- Не добавляй никакой новой информации.
- Не отвечай на содержание текста.
- Убирай слова-паразиты и речевой мусор: «ну», «короче», «типа», «как бы», «в общем», «значит» и подобные, если они не несут смысла.
- Убирай бессмысленные повторы и оговорки.
- Исправляй пунктуацию и капитализацию.
- Исправляй очевидные ошибки устной речи.
- Сохраняй имена, названия, числа и специальные термины.
- Не меняй стиль сильнее, чем необходимо для превращения речи в письменный текст.
- Не добавляй приветствия, пояснения или комментарии.
- Не используй Markdown.
- Не заключай результат в кавычки.
- Возвращай только готовый текст.
""".strip()


class LocalLLMProvider(LLMProvider):
    def __init__(self, model="qwen3.8:27b", base_url="http://127.0.0.1:11434", timeout=60.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._styles = StyleStore()

    def _system_prompt(self):
        prompt = str(self._styles.get_selected().get("prompt", "")).strip()
        if not prompt:
            return SYSTEM_PROMPT
        return (
            SYSTEM_PROMPT
            + "\n\nДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ ВЫБРАННОГО СТИЛЯ:\n"
            + prompt
            + "\n\nЭти инструкции не отменяют базовые правила: сохраняй смысл, не добавляй информацию и возвращай только готовый текст."
        )

    def process(self, text):
        payload = {
            "model": self.model,
            "system": self._system_prompt(),
            "prompt": text,
            "stream": False,
            "think": False,
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not connect to Ollama: {exc}") from exc
        result = data.get("response", "").strip()
        if not result:
            raise RuntimeError("Ollama returned an empty response.")
        return result
