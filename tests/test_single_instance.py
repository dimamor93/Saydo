from unittest.mock import MagicMock, patch

import pytest

from app.core.single_instance import (
    SingleInstance,
    show_already_running_message,
)


def test_acquire_creates_mutex_and_stores_handle() -> None:
    instance = SingleInstance("TestSaydo")
    handle = MagicMock()

    with (
        patch(
            "app.core.single_instance.ctypes.WinDLL"
        ) as windll,
        patch(
            "app.core.single_instance.ctypes.get_last_error",
            return_value=0,
        ),
    ):
        kernel32 = windll.return_value
        kernel32.CreateMutexW.return_value = handle

        assert instance.acquire() is True

        kernel32.CreateMutexW.assert_called_once()
        assert instance._handle is handle


def test_acquire_returns_false_when_mutex_already_exists() -> None:
    instance = SingleInstance("TestSaydo")
    handle = MagicMock()

    with (
        patch(
            "app.core.single_instance.ctypes.WinDLL"
        ) as windll,
        patch(
            "app.core.single_instance.ctypes.get_last_error",
            return_value=183,
        ),
    ):
        kernel32 = windll.return_value
        kernel32.CreateMutexW.return_value = handle

        assert instance.acquire() is False

        kernel32.CloseHandle.assert_called_once_with(handle)
        assert instance._handle is None


def test_acquire_raises_when_mutex_creation_fails() -> None:
    instance = SingleInstance("TestSaydo")

    with (
        patch(
            "app.core.single_instance.ctypes.WinDLL"
        ) as windll,
        patch(
            "app.core.single_instance.ctypes.get_last_error",
            return_value=5,
        ),
        patch(
            "app.core.single_instance.ctypes.WinError",
            side_effect=OSError("access denied"),
        ),
    ):
        kernel32 = windll.return_value
        kernel32.CreateMutexW.return_value = None

        with pytest.raises(OSError, match="access denied"):
            instance.acquire()

        assert instance._handle is None


def test_release_closes_handle() -> None:
    instance = SingleInstance("TestSaydo")
    handle = MagicMock()
    instance._handle = handle

    with patch(
        "app.core.single_instance.ctypes.WinDLL"
    ) as windll:
        kernel32 = windll.return_value

        instance.release()

        kernel32.CloseHandle.assert_called_once_with(handle)

    assert instance._handle is None


def test_release_without_handle_is_safe() -> None:
    instance = SingleInstance("TestSaydo")

    with patch(
        "app.core.single_instance.ctypes.WinDLL"
    ) as windll:
        instance.release()

        windll.assert_not_called()


def test_show_already_running_message() -> None:
    with patch(
        "app.core.single_instance.ctypes.WinDLL"
    ) as windll:
        user32 = windll.return_value

        show_already_running_message()

        user32.MessageBoxW.assert_called_once()

        args = user32.MessageBoxW.call_args.args

        assert "Saydo уже запущен." in args[1]
        assert "Вторая копия" in args[1]
        assert args[2] == "Saydo"
