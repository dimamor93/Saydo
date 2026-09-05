from __future__ import annotations

import threading
import time
from collections.abc import Callable

import keyboard


class HotkeyManager:
    """Global hotkey manager with hold and double-tap support."""

    def __init__(
        self,
        hotkey_name: str = "right ctrl",
        double_tap_window: float = 0.30,
    ) -> None:
        self.hotkey_name = hotkey_name
        self.double_tap_window = double_tap_window
        self.min_hold_time = 0.20

        self._hook = None
        self._lock = threading.Lock()

        self._last_release_time = 0.0
        self._pending_stop: threading.Timer | None = None
        self._pending_press: threading.Timer | None = None

        self._pressed_at = 0.0
        self._is_pressed = False
        self._recording_started = False

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
                    # Ignore repeated DOWN events generated while the key
                    # is being held. Only the first DOWN starts a new cycle.
                    if self._is_pressed:
                        return

                    previous_release = self._last_release_time

                    if self._pending_stop is not None:
                        self._pending_stop.cancel()
                        self._pending_stop = None

                    if self._pending_press is not None:
                        self._pending_press.cancel()
                        self._pending_press = None

                    self._pressed_at = now
                    self._is_pressed = True
                    self._recording_started = False

                # Double tap has priority over normal dictation.
                if (
                    previous_release > 0
                    and now - previous_release <= self.double_tap_window
                    and self._on_double_tap is not None
                ):
                    with self._lock:
                        self._recording_started = False

                    self._on_double_tap()
                    return

                # Wait 200 ms before starting recording.
                # If the key is released earlier, the timer is cancelled.
                timer = threading.Timer(
                    self.min_hold_time,
                    self._start_after_hold,
                )
                timer.daemon = True

                with self._lock:
                    self._pending_press = timer

                timer.start()

            elif event.event_type == "up":
                now = time.monotonic()

                with self._lock:
                    # Ignore stray UP events when we don't have an active
                    # press cycle.
                    if not self._is_pressed:
                        return

                    pressed_for = now - self._pressed_at
                    self._last_release_time = now
                    self._is_pressed = False

                    pending_press = self._pending_press
                    if pending_press is not None:
                        pending_press.cancel()
                        self._pending_press = None

                    recording_started = self._recording_started
                    self._recording_started = False

                # Released before 200 ms: nothing was started.
                if not recording_started:
                    return

                # A short release may be the first half of a double tap.
                # Delay stopping so a second press can turn this into
                # hands-free mode.
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

    def _start_after_hold(self) -> None:
        with self._lock:
            self._pending_press = None

            # The key must still be held.
            if not self._is_pressed:
                return

            pressed_for = time.monotonic() - self._pressed_at

            if pressed_for < self.min_hold_time:
                return

            self._recording_started = True

        if self._on_press is not None:
            self._on_press()

    def _finish_short_release(self) -> None:
        with self._lock:
            self._pending_stop = None

        if self._on_release is not None:
            self._on_release()

    def stop(self) -> None:
        with self._lock:
            if self._pending_stop is not None:
                self._pending_stop.cancel()
                self._pending_stop = None

            if self._pending_press is not None:
                self._pending_press.cancel()
                self._pending_press = None

            self._is_pressed = False
            self._recording_started = False

        if self._hook is not None:
            keyboard.unhook(self._hook)
            self._hook = None

    def wait_for_exit(self) -> None:
        keyboard.wait("esc")
