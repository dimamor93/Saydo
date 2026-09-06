from __future__ import annotations

import time
from unittest.mock import Mock, patch

from app.hotkey.manager import HotkeyManager


def test_start_after_hold_starts_recording() -> None:
    callback = Mock()
    manager = HotkeyManager()
    manager._on_press = callback
    manager._is_pressed = True
    manager._pressed_at = time.monotonic() - manager.min_hold_time - 0.01

    manager._start_after_hold()

    assert manager._recording_started is True
    callback.assert_called_once()


def test_start_after_hold_does_nothing_if_key_was_released() -> None:
    callback = Mock()
    manager = HotkeyManager()
    manager._on_press = callback
    manager._is_pressed = False

    manager._start_after_hold()

    assert manager._recording_started is False
    callback.assert_not_called()


def test_start_after_hold_does_not_start_too_early() -> None:
    callback = Mock()
    manager = HotkeyManager()
    manager._on_press = callback
    manager._is_pressed = True
    manager._pressed_at = time.monotonic()

    manager._start_after_hold()

    assert manager._recording_started is False
    callback.assert_not_called()


def test_finish_short_release_calls_release_callback() -> None:
    callback = Mock()
    manager = HotkeyManager()
    manager._on_release = callback
    manager._pending_stop = Mock()

    manager._finish_short_release()

    assert manager._pending_stop is None
    callback.assert_called_once()


def test_stop_resets_recording_state() -> None:
    manager = HotkeyManager()
    manager._is_pressed = True
    manager._recording_started = True
    manager._pending_press = Mock()
    manager._pending_stop = Mock()

    with patch('app.hotkey.manager.keyboard.unhook') as unhook:
        manager._hook = Mock()
        manager.stop()

    assert manager._is_pressed is False
    assert manager._recording_started is False
    assert manager._pending_press is None
    assert manager._pending_stop is None
    assert manager._hook is None
    unhook.assert_called_once()


def test_stop_without_hook_is_safe() -> None:
    manager = HotkeyManager()
    manager.stop()

    assert manager._is_pressed is False
    assert manager._recording_started is False


def make_event(event_type: str):
    event = Mock()
    event.name = "right ctrl"
    event.event_type = event_type
    return event


def wait_for_events(
    events: list[str],
    expected: list[str],
    timeout: float = 1.0,
) -> None:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if events == expected:
            return
        time.sleep(0.01)

    assert events == expected


def test_hold_and_release_cycle() -> None:
    events: list[str] = []
    hook_callback = None

    def fake_hook(callback):
        nonlocal hook_callback
        hook_callback = callback
        return "fake-hook"

    with patch("app.hotkey.manager.keyboard.hook", side_effect=fake_hook), \
         patch("app.hotkey.manager.keyboard.unhook"):
        manager = HotkeyManager()
        manager.start(
            on_press=lambda: events.append("press"),
            on_release=lambda: events.append("release"),
        )

        assert hook_callback is not None

        hook_callback(make_event("down"))
        time.sleep(manager.min_hold_time + 0.05)
        hook_callback(make_event("up"))

        wait_for_events(events, ["press", "release"])

        manager.stop()


def test_repeated_down_does_not_start_second_recording() -> None:
    events: list[str] = []
    hook_callback = None

    def fake_hook(callback):
        nonlocal hook_callback
        hook_callback = callback
        return "fake-hook"

    with patch("app.hotkey.manager.keyboard.hook", side_effect=fake_hook), \
         patch("app.hotkey.manager.keyboard.unhook"):
        manager = HotkeyManager()
        manager.start(
            on_press=lambda: events.append("press"),
            on_release=lambda: events.append("release"),
        )

        assert hook_callback is not None

        hook_callback(make_event("down"))
        hook_callback(make_event("down"))

        time.sleep(manager.min_hold_time + 0.05)

        assert events == ["press"]

        hook_callback(make_event("up"))
        time.sleep(manager.double_tap_window + 0.05)

        assert events == ["press", "release"]
        manager.stop()


def test_release_before_minimum_hold_does_not_start_recording() -> None:
    events: list[str] = []
    hook_callback = None

    def fake_hook(callback):
        nonlocal hook_callback
        hook_callback = callback
        return "fake-hook"

    with patch("app.hotkey.manager.keyboard.hook", side_effect=fake_hook), \
         patch("app.hotkey.manager.keyboard.unhook"):
        manager = HotkeyManager()
        manager.start(
            on_press=lambda: events.append("press"),
            on_release=lambda: events.append("release"),
        )

        assert hook_callback is not None

        hook_callback(make_event("down"))
        time.sleep(0.03)
        hook_callback(make_event("up"))

        time.sleep(manager.min_hold_time + 0.05)

        assert events == []
        manager.stop()


def test_double_tap_triggers_double_tap_callback() -> None:
    events: list[str] = []
    hook_callback = None

    def fake_hook(callback):
        nonlocal hook_callback
        hook_callback = callback
        return "fake-hook"

    with patch("app.hotkey.manager.keyboard.hook", side_effect=fake_hook), \
         patch("app.hotkey.manager.keyboard.unhook"):
        manager = HotkeyManager()
        manager.start(
            on_press=lambda: events.append("press"),
            on_release=lambda: events.append("release"),
            on_double_tap=lambda: events.append("double"),
        )

        assert hook_callback is not None

        hook_callback(make_event("down"))
        time.sleep(manager.min_hold_time + 0.05)
        hook_callback(make_event("up"))

        time.sleep(0.05)

        hook_callback(make_event("down"))

        assert events == ["press", "double"]

        hook_callback(make_event("up"))
        manager.stop()
