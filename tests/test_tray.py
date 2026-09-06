from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from app.ui.tray import SaydoTray


def test_load_image_uses_existing_asset() -> None:
    tray = SaydoTray()

    fake_image = Mock()

    with patch("app.ui.tray.Path.exists", return_value=True), \
         patch("app.ui.tray.Image.open", return_value=fake_image) as image_open:
        result = tray._load_image()

    assert result is fake_image
    image_open.assert_called_once()


def test_load_image_uses_fallback_when_asset_missing() -> None:
    tray = SaydoTray()

    fake_image = Mock()

    with patch("app.ui.tray.Path.exists", return_value=False), \
         patch("app.ui.tray.Image.new", return_value=fake_image) as image_new:
        result = tray._load_image()

    assert result is fake_image
    image_new.assert_called_once_with(
        "RGBA",
        (64, 64),
        (20, 20, 20, 255),
    )


def test_show_calls_callback() -> None:
    callback = Mock()
    tray = SaydoTray(on_show=callback)

    tray._show(None, None)

    callback.assert_called_once()


def test_show_without_callback_is_safe() -> None:
    tray = SaydoTray()

    tray._show(None, None)


def test_exit_calls_callback() -> None:
    callback = Mock()
    tray = SaydoTray(on_exit=callback)

    tray._exit(None, None)

    callback.assert_called_once()


def test_exit_without_callback_is_safe() -> None:
    tray = SaydoTray()

    tray._exit(None, None)


def test_start_creates_icon_and_thread() -> None:
    tray = SaydoTray()

    fake_image = Mock()
    fake_icon = Mock()
    fake_thread = Mock()

    with patch.object(tray, "_load_image", return_value=fake_image), \
         patch("app.ui.tray.pystray.MenuItem") as menu_item, \
         patch("app.ui.tray.pystray.Menu") as menu, \
         patch("app.ui.tray.pystray.Icon", return_value=fake_icon) as icon_class, \
         patch("app.ui.tray.threading.Thread", return_value=fake_thread) as thread_class:

        tray.start()

    assert tray._icon is fake_icon
    assert tray._thread is fake_thread

    assert menu_item.call_count == 2
    menu.assert_called_once()

    icon_class.assert_called_once_with(
        "Saydo",
        fake_image,
        "Saydo",
        menu.return_value,
    )

    thread_class.assert_called_once_with(
        target=fake_icon.run,
        name="SaydoTray",
        daemon=True,
    )
    fake_thread.start.assert_called_once()


def test_stop_stops_icon_and_clears_reference() -> None:
    tray = SaydoTray()
    fake_icon = Mock()
    tray._icon = fake_icon

    tray.stop()

    fake_icon.stop.assert_called_once()
    assert tray._icon is None


def test_stop_without_icon_is_safe() -> None:
    tray = SaydoTray()

    tray.stop()

    assert tray._icon is None