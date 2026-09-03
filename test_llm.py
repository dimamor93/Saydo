from __future__ import annotations

import time

from app.llm.local import LocalLLMProvider


def main() -> None:
    print("[Saydo] Testing local LLM...")

    provider = LocalLLMProvider()

    text = (
        "так ну короче надо написать что завтра в три часа "
        "встречаемся и обсудим проект"
    )

    print(f"[Saydo] Input: {text}")
    print("[Saydo] Processing...")

    started = time.perf_counter()

    result = provider.process(text)

    elapsed = time.perf_counter() - started

    print(f"[Saydo] Output: {result}")
    print(f"[Saydo] LLM latency: {elapsed:.2f} seconds")


if __name__ == "__main__":
    main()