from __future__ import annotations

from collections.abc import Callable

import keyboard


class HotkeyManager:
    """Manages global keyboard shortcuts."""

    def __init__(self, hotkey_name: str = "right ctrl") -> None:
        self.hotkey_name = hotkey_name
        self._hook = None

    def start(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        """Start listening for the configured hotkey."""

        def handle_event(event: keyboard.KeyboardEvent) -> None:
            if event.name != self.hotkey_name:
                return

            if event.event_type == "down":
                on_press()

            elif event.event_type == "up":
                on_release()

        self._hook = keyboard.hook(handle_event)

    def stop(self) -> None:
        """Stop listening for keyboard events."""

        if self._hook is not None:
            keyboard.unhook(self._hook)
            self._hook = None

    def wait_for_exit(self) -> None:
        """Wait until Escape is pressed."""

        keyboard.wait("esc")