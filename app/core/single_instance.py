from __future__ import annotations

import ctypes
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183
MUTEX_ALL_ACCESS = 0x001F0001


class SingleInstance:
    """Windows named mutex used to prevent multiple Saydo instances."""

    def __init__(self, name: str = "Saydo") -> None:
        self._name = f"Local\\{name}"
        self._handle: wintypes.HANDLE | None = None

    def acquire(self) -> bool:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        kernel32.CreateMutexW.restype = wintypes.HANDLE

        handle = kernel32.CreateMutexW(
            None,
            False,
            self._name,
        )

        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())

        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False

        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        kernel32.CloseHandle(self._handle)
        self._handle = None


def show_already_running_message() -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    user32.MessageBoxW.argtypes = [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.UINT,
    ]
    user32.MessageBoxW.restype = ctypes.c_int

    user32.MessageBoxW(
        None,
        "Saydo уже запущен.\n\nВторая копия не будет запущена.",
        "Saydo",
        0x00000040,
    )
