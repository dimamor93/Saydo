from __future__ import annotations

import time

import keyboard
import pyperclip


class TextInjector:
    """Injects text into the currently focused Windows application."""

    def inject(self, text: str) -> None:
        if not text:
            return

        try:
            pyperclip.copy(text)

            time.sleep(0.05)
            keyboard.press_and_release("ctrl+v")

            # Keep the injected text in the clipboard.
            # This makes failed/unavailable insertion recoverable.
            time.sleep(0.05)

        except Exception as exc:
            print(f"[Saydo] Text injection error: {exc}")
            # Do not overwrite the clipboard here.
            # If pyperclip.copy() succeeded, the recognized text remains available.