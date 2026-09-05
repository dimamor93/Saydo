from __future__ import annotations

import threading
from pathlib import Path

import pystray
from PIL import Image


class SaydoTray:
    """System tray integration for the persistent Saydo background app."""

    def __init__(self, on_show=None, on_exit=None) -> None:
        self.on_show = on_show
        self.on_exit = on_exit
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def _load_image(self) -> Image.Image:
        path = Path(__file__).resolve().parents[2] / "assets" / "saydo-tray.ico"
        if path.exists():
            return Image.open(path)

        # Fallback for development builds without the asset.
        return Image.new("RGBA", (64, 64), (20, 20, 20, 255))

    def _show(self, icon, item) -> None:
        if self.on_show:
            self.on_show()

    def _exit(self, icon, item) -> None:
        if self.on_exit:
            self.on_exit()

    def start(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Открыть Saydo", self._show, default=True),
            pystray.MenuItem("Выйти", self._exit),
        )
        self._icon = pystray.Icon(
            "Saydo",
            self._load_image(),
            "Saydo",
            menu,
        )
        self._thread = threading.Thread(
            target=self._icon.run,
            name="SaydoTray",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
            self._icon = None
