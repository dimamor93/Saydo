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

            # Give the target application time to consume the clipboard.
            time.sleep(0.05)

        except Exception as exc:
            print(f"[Saydo] Text injection error: {exc}")

        finally:
            try:
                pyperclip.copy(previous_clipboard)
            except Exception as exc:
                print(f"[Saydo] Clipboard restore error: {exc}")
