from __future__ import annotations

import time

import keyboard
import pyperclip


class TextInjector:
    """Injects text into the currently focused Windows application."""

    def inject(self, text: str) -> None:
        if not text:
            return

        previous_clipboard = pyperclip.paste()

        try:
            pyperclip.copy(text)

            time.sleep(0.05)
            keyboard.press_and_release("ctrl+v")
            time.sleep(0.1)

        finally:
            try:
                pyperclip.copy(previous_clipboard)
            except Exception:
                pass