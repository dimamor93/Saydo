from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.llm.base import LLMProvider


SYSTEM_PROMPT = """
Ты — редактор текста голосовой диктовки.

Твоя задача — превратить расшифровку речи в чистый письменный текст.

Правила:
- Сохраняй исходный смысл.
- Не добавляй никакой новой информации.
- Не отвечай на содержание текста.
- Убирай слова-паразиты и речевой мусор: «ну», «короче», «типа»,
  «как бы», «в общем», «значит» и подобные, если они не несут смысла.
- Убирай бессмысленные повторы и оговорки.
- Исправляй пунктуацию и капитализацию.
- Исправляй очевидные ошибки устной речи.
- Сохраняй имена, названия, числа и специальные термины.
- Не меняй стиль сильнее, чем необходимо для превращения речи в письменный текст.
- Не добавляй приветствия, пояснения или комментарии.
- Не используй Markdown.
- Не заключай результат в кавычки.
- Возвращай только готовый текст.

Пример:
Вход:
«так ну короче надо написать что завтра в три часа встречаемся и обсудим проект»

Выход:
«Надо написать, что завтра в три часа встречаемся и обсудим проект.»
""".strip()


class LocalLLMProvider(LLMProvider):
    """Local LLM provider using the Ollama HTTP API."""

    def __init__(
        self,
        model: str = "qwen3.8:27b",
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def process(self, text: str) -> str:
        """Process dictated text using the configured Ollama model."""

        payload = {
            "model": self.model,
            "system": SYSTEM_PROMPT,
            "prompt": text,
            "stream": False,
            "think": False,
            # AI Mode preloads the model and keeps it resident in Ollama.
            "keep_alive": -1,
        }

        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                data = json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Could not connect to Ollama: {exc}"
            ) from exc

        result = data.get("response", "").strip()

        if not result:
            raise RuntimeError(
                "Ollama returned an empty response."
            )

        return result