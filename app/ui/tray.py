from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Callable

import pystray
from PIL import Image
from pystray import MenuItem


class SaydoTray:
    """Windows system-tray icon for Saydo."""

    def __init__(self, on_exit: Callable[[], None]) -> None:
        self._on_exit = on_exit
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._thread = threading.Thread(
            target=self._run,
            name="SaydoTray",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass

    def _run(self) -> None:
        if getattr(sys, "frozen", False):
            base_dir = Path(sys._MEIPASS)
        else:
            base_dir = Path(__file__).resolve().parent.parent.parent

        icon_path = base_dir / "assets" / "saydo-tray.ico"

        image = Image.open(icon_path)

        menu = pystray.Menu(
            MenuItem("Saydo", None, enabled=False),
            MenuItem("Выйти", self._exit),
        )

        self._icon = pystray.Icon(
            "Saydo",
            image,
            "Saydo",
            menu,
        )

        self._icon.run()

    def _exit(self, icon: pystray.Icon, item: MenuItem) -> None:
        try:
            icon.stop()
        finally:
            self._on_exit()