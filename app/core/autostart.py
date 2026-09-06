from __future__ import annotations

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class AutostartManager:
    """Manage Saydo autostart through the current user's Windows Run key."""

    VALUE_NAME = "Saydo"

    def __init__(self) -> None:
        self._command = self._build_command()

    def _build_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{Path(sys.executable).resolve()}"'

        python = Path(sys.executable).resolve()
        script = Path(__file__).resolve().parents[2] / "main.py"

        return f'"{python}" "{script}"'

    def is_enabled(self) -> bool:
        if sys.platform != "win32":
            return False

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                RUN_KEY,
                0,
                winreg.KEY_READ,
            ) as key:
                value, _ = winreg.QueryValueEx(key, self.VALUE_NAME)
                return value == self._command
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def enable(self) -> None:
        if sys.platform != "win32":
            raise OSError(
                "Автозапуск Saydo поддерживается только в Windows."
            )

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(
                key,
                self.VALUE_NAME,
                0,
                winreg.REG_SZ,
                self._command,
            )

    def disable(self) -> None:
        if sys.platform != "win32":
            return

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, self.VALUE_NAME)
        except FileNotFoundError:
            pass