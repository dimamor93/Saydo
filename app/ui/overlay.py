from __future__ import annotations

import multiprocessing as mp
import queue
import sys
from pathlib import Path

import tkinter as tk
from PIL import Image, ImageTk


def _get_logo_path() -> Path:
    if getattr(sys, "frozen", False):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).resolve().parents[2]
    return base_dir / "assets" / "saydo-logo.png"


def _limit_text(text: str) -> str:
    if not text:
        return ""
    max_chars = 72 * 3
    if len(text) <= max_chars:
        return text
    return "…" + text[-(max_chars - 1):]


def _calculate_height(text: str) -> int:
    MIN_HEIGHT = 82
    MAX_HEIGHT = 132
    PAD = 14
    if not text:
        return MIN_HEIGHT

    chars_per_line = 72
    lines = 0
    for paragraph in text.split("\n"):
        lines += max(1, (len(paragraph) + chars_per_line - 1) // chars_per_line)
    lines = min(lines, 3)

    text_height = lines * 20
    height = PAD * 2 + max(48, text_height)
    return max(MIN_HEIGHT, min(height, MAX_HEIGHT))


def _position(window: tk.Toplevel, text: str) -> None:
    width = 720
    height = _calculate_height(text)

    window.geometry(f"{width}x{height}")
    window.update_idletasks()

    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            screen_width = user32.GetSystemMetrics(0)
            screen_height = user32.GetSystemMetrics(1)
        except Exception:
            screen_width = window.winfo_screenwidth()
            screen_height = window.winfo_screenheight()
    else:
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()

    x = (screen_width - width) // 2
    y = screen_height - height - 80
    window.geometry(f"{width}x{height}+{x}+{y}")


def _overlay_process(commands: mp.Queue) -> None:
    """Own the complete Tkinter lifecycle in a dedicated process."""
    try:
        root = tk.Tk()
        root.withdraw()

        window = tk.Toplevel(root)
        window.withdraw()
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.attributes("-alpha", 0.95)
        window.configure(bg="#111111")

        container = tk.Frame(
            window,
            bg="#111111",
            padx=20,
            pady=14,
        )
        container.pack(fill="both", expand=True)

        logo_frame = tk.Frame(
            container,
            bg="#111111",
            width=48,
        )
        logo_frame.pack(
            side="left",
            fill="y",
            padx=(0, 18),
        )
        logo_frame.pack_propagate(False)

        logo_image = None
        try:
            image = Image.open(_get_logo_path()).convert("RGBA")
            image.thumbnail((48, 48), Image.Resampling.LANCZOS)
            logo_image = ImageTk.PhotoImage(image)

            logo_label = tk.Label(
                logo_frame,
                image=logo_image,
                bg="#111111",
                bd=0,
                highlightthickness=0,
            )
            logo_label.place(relx=0.5, rely=0.5, anchor="center")
        except Exception as exc:
            print(f"[Saydo] Overlay logo error: {exc}", flush=True)

        text_frame = tk.Frame(container, bg="#111111")
        text_frame.pack(side="left", fill="both", expand=True)

        text_label = tk.Label(
            text_frame,
            text="",
            font=("Segoe UI", 11),
            fg="#FFFFFF",
            bg="#111111",
            justify="left",
            anchor="w",
            wraplength=620,
            bd=0,
            highlightthickness=0,
        )
        text_label.pack(fill="both", expand=True)

        _position(window, "")
        root.update_idletasks()

        def process_commands() -> None:
            try:
                while True:
                    command, value = commands.get_nowait()

                    if command == "show":
                        text_label.config(text="")
                        _position(window, "")
                        window.deiconify()
                        window.lift()
                        window.attributes("-topmost", True)

                    elif command == "text":
                        value = _limit_text(str(value))
                        text_label.config(text=value)
                        _position(window, value)
                        if not window.winfo_viewable():
                            window.deiconify()
                            window.lift()
                            window.attributes("-topmost", True)

                    elif command == "hide":
                        window.withdraw()

                    elif command == "close":
                        window.destroy()
                        root.quit()
                        return

            except queue.Empty:
                pass
            except Exception as exc:
                print(f"[Saydo] Overlay command error: {exc}", flush=True)

            root.after(20, process_commands)

        root.after(20, process_commands)
        print("[Saydo] Overlay process ready.", flush=True)
        root.mainloop()

    except Exception as exc:
        print(f"[Saydo] Overlay process failed: {exc}", flush=True)


class SaydoOverlay:
    """Saydo overlay isolated in its own process so Tkinter cannot conflict with Qt."""

    def __init__(self) -> None:
        self._root = None
        self._window = None
        self._process: mp.Process | None = None
        self._commands: mp.Queue | None = None

    def start(self) -> None:
        if self._process is not None and self._process.is_alive():
            return

        self._commands = mp.Queue()
        self._process = mp.Process(
            target=_overlay_process,
            args=(self._commands,),
            name="SaydoOverlayProcess",
            daemon=True,
        )
        self._process.start()

        # main.py waits for _root to become non-None before continuing.
        self._root = True
        self._window = True

    def show(self) -> None:
        self.show_recording()

    def set_state(self, state: str) -> None:
        if state == "recording":
            self.show_recording()
        elif state == "idle":
            self.hide()
        # Keep the overlay visible during processing.

    def show_recording(self) -> None:
        if self._commands is not None:
            self._commands.put(("show", ""))

    def set_text(self, text: str) -> None:
        self.update_text(text)

    def update_text(self, text: str) -> None:
        if self._commands is not None and text:
            self._commands.put(("text", text))

    def hide(self) -> None:
        if self._commands is not None:
            self._commands.put(("hide", ""))

    def close(self) -> None:
        if self._commands is not None:
            try:
                self._commands.put(("close", ""))
            except Exception:
                pass

        if self._process is not None:
            self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=1.0)

        self._process = None
        self._commands = None
        self._root = None
        self._window = None
