from unittest.mock import MagicMock, patch

import pytest

from app.core.autostart import AutostartManager


def test_build_command_for_python() -> None:
    with patch("app.core.autostart.sys.executable", r"C:\Python\python.exe"):
        manager = AutostartManager()

    assert manager._command.startswith(r'"C:\Python\python.exe" "')
    assert manager._command.endswith(r'main.py"')


def test_build_command_for_frozen_application() -> None:
    with (
        patch("app.core.autostart.sys.frozen", True, create=True),
        patch("app.core.autostart.sys.executable", r"C:\Saydo\Saydo.exe"),
    ):
        manager = AutostartManager()

    assert manager._command == r'"C:\Saydo\Saydo.exe"'


def test_is_enabled_returns_false_when_value_is_missing() -> None:
    manager = AutostartManager()

    with patch(
        "app.core.autostart.winreg.OpenKey",
        side_effect=FileNotFoundError,
    ):
        assert manager.is_enabled() is False


def test_is_enabled_returns_false_on_registry_error() -> None:
    manager = AutostartManager()

    with patch(
        "app.core.autostart.winreg.OpenKey",
        side_effect=OSError,
    ):
        assert manager.is_enabled() is False


def test_is_enabled_returns_true_for_matching_command() -> None:
    manager = AutostartManager()
    key = MagicMock()
    key.__enter__.return_value = key

    with (
        patch(
            "app.core.autostart.winreg.OpenKey",
            return_value=key,
        ) as open_key,
        patch(
            "app.core.autostart.winreg.QueryValueEx",
            return_value=(manager._command, 1),
        ) as query,
    ):
        assert manager.is_enabled() is True

    open_key.assert_called_once()
    query.assert_called_once_with(key, "Saydo")


def test_is_enabled_returns_false_for_different_command() -> None:
    manager = AutostartManager()
    key = MagicMock()
    key.__enter__.return_value = key

    with (
        patch(
            "app.core.autostart.winreg.OpenKey",
            return_value=key,
        ),
        patch(
            "app.core.autostart.winreg.QueryValueEx",
            return_value=("different command", 1),
        ),
    ):
        assert manager.is_enabled() is False


def test_enable_writes_command_to_registry() -> None:
    manager = AutostartManager()
    key = MagicMock()
    key.__enter__.return_value = key

    with (
        patch(
            "app.core.autostart.winreg.OpenKey",
            return_value=key,
        ) as open_key,
        patch("app.core.autostart.winreg.SetValueEx") as set_value,
    ):
        manager.enable()

    open_key.assert_called_once()
    set_value.assert_called_once_with(
        key,
        "Saydo",
        0,
        1,
        manager._command,
    )


def test_enable_propagates_registry_error() -> None:
    manager = AutostartManager()

    with patch(
        "app.core.autostart.winreg.OpenKey",
        side_effect=OSError("registry unavailable"),
    ):
        with pytest.raises(OSError, match="registry unavailable"):
            manager.enable()


def test_disable_removes_registry_value() -> None:
    manager = AutostartManager()
    key = MagicMock()
    key.__enter__.return_value = key

    with (
        patch(
            "app.core.autostart.winreg.OpenKey",
            return_value=key,
        ) as open_key,
        patch("app.core.autostart.winreg.DeleteValue") as delete_value,
    ):
        manager.disable()

    open_key.assert_called_once()
    delete_value.assert_called_once_with(key, "Saydo")


def test_disable_ignores_missing_value() -> None:
    manager = AutostartManager()

    with patch(
        "app.core.autostart.winreg.OpenKey",
        side_effect=FileNotFoundError,
    ):
        manager.disable()


def test_non_windows_is_disabled() -> None:
    manager = AutostartManager()

    with patch("app.core.autostart.sys.platform", "linux"):
        assert manager.is_enabled() is False

        manager.disable()

        with pytest.raises(OSError, match="Windows"):
            manager.enable()
