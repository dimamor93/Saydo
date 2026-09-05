from __future__ import annotations

import threading
import time
from collections.abc import Callable

import keyboard


class HotkeyManager:
    """Global hotkey manager with hold and double-tap support."""

    def __init__(self, hotkey_name: str = "right ctrl", double_tap_window: float = 0.30) -> None:
        self.hotkey_name = hotkey_name
        self.double_tap_window = double_tap_window
        self._hook = None
        self._lock = threading.Lock()
        self._last_release_time = 0.0
        self._pending_stop: threading.Timer | None = None
        self._pressed_at = 0.0
        self._on_press: Callable[[], None] | None = None
        self._on_release: Callable[[], None] | None = None
        self._on_double_tap: Callable[[], None] | None = None

    def start(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        on_double_tap: Callable[[], None] | None = None,
    ) -> None:
        self._on_press = on_press
        self._on_release = on_release
        self._on_double_tap = on_double_tap

        def handle_event(event: keyboard.KeyboardEvent) -> None:
            if event.name != self.hotkey_name:
                return

            if event.event_type == "down":
                now = time.monotonic()
                with self._lock:
                    previous_release = self._last_release_time
                    pending = self._pending_stop
                    if pending is not None:
                        pending.cancel()
                        self._pending_stop = None
                    self._pressed_at = now

                if (
                    previous_release > 0
                    and now - previous_release <= self.double_tap_window
                    and self._on_double_tap is not None
                ):
                    self._on_double_tap()
                    return

                if self._on_press is not None:
                    self._on_press()

            elif event.event_type == "up":
                now = time.monotonic()
                with self._lock:
                    pressed_for = now - self._pressed_at
                    self._last_release_time = now

                # A short release may be the first half of a double tap.
                # Delay its stop just long enough to detect the second press.
                if pressed_for <= self.double_tap_window:
                    timer = threading.Timer(
                        self.double_tap_window,
                        self._finish_short_release,
                    )
                    timer.daemon = True
                    with self._lock:
                        self._pending_stop = timer
                    timer.start()
                elif self._on_release is not None:
                    self._on_release()

        self._hook = keyboard.hook(handle_event)

    def _finish_short_release(self) -> None:
        with self._lock:
            self._pending_stop = None
        if self._on_release is not None:
            self._on_release()

    def stop(self) -> None:
        if self._pending_stop is not None:
            self._pending_stop.cancel()
            self._pending_stop = None
        if self._hook is not None:
            keyboard.unhook(self._hook)
            self._hook = None

    def wait_for_exit(self) -> None:
        keyboard.wait("esc")
