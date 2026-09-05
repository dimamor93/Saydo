from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk


class SaydoOverlay:
    """Static Saydo overlay with fixed width and max three text lines."""

    # Размеры оверлея
    WINDOW_WIDTH = 720
    MIN_HEIGHT = 82
    MAX_HEIGHT = 132

    # Размер логотипа
    LOGO_SIZE = 48

    # Отступы
    HORIZONTAL_PADDING = 20
    VERTICAL_PADDING = 14
    LOGO_TEXT_GAP = 18

    def __init__(self) -> None:
        self._root: tk.Tk | None = None
        self._window: tk.Toplevel | None = None

        self._logo_image: ImageTk.PhotoImage | None = None
        self._text_label: tk.Label | None = None

    def start(self) -> None:
        """Start Tkinter event loop. Must run in a dedicated thread."""
        self._root = tk.Tk()
        self._root.withdraw()

        self._create_window()

        self._root.mainloop()

    def _create_window(self) -> None:
        assert self._root is not None

        window = tk.Toplevel(self._root)
        self._window = window

        window.withdraw()
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.attributes("-alpha", 0.95)
        window.configure(bg="#111111")

        # ---------------------------------------------------------
        # Main horizontal container
        # ---------------------------------------------------------

        container = tk.Frame(
            window,
            bg="#111111",
            padx=self.HORIZONTAL_PADDING,
            pady=self.VERTICAL_PADDING,
        )
        container.pack(
            fill="both",
            expand=True,
        )

        # ---------------------------------------------------------
        # Logo — LEFT
        # ---------------------------------------------------------

        logo_frame = tk.Frame(
            container,
            bg="#111111",
            width=self.LOGO_SIZE,
        )
        logo_frame.pack(
            side="left",
            fill="y",
            padx=(0, self.LOGO_TEXT_GAP),
        )

        # Prevent the frame from changing width because of contents.
        logo_frame.pack_propagate(False)

        logo_path = self._get_logo_path()

        try:
            image = Image.open(logo_path).convert("RGBA")

            image.thumbnail(
                (self.LOGO_SIZE, self.LOGO_SIZE),
                Image.Resampling.LANCZOS,
            )

            self._logo_image = ImageTk.PhotoImage(image)

            logo_label = tk.Label(
                logo_frame,
                image=self._logo_image,
                bg="#111111",
                bd=0,
                highlightthickness=0,
            )

            logo_label.place(
                relx=0.5,
                rely=0.5,
                anchor="center",
            )

        except Exception as exc:
            print(f"[Saydo] Failed to load logo: {exc}")

        # ---------------------------------------------------------
        # Text — RIGHT
        # ---------------------------------------------------------

        text_frame = tk.Frame(
            container,
            bg="#111111",
        )

        text_frame.pack(
            side="left",
            fill="both",
            expand=True,
        )

        self._text_label = tk.Label(
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

        self._text_label.pack(
            fill="both",
            expand=True,
        )

        # ---------------------------------------------------------
        # Fixed width
        # ---------------------------------------------------------

        window.geometry(
            f"{self.WINDOW_WIDTH}x{self.MIN_HEIGHT}"
        )

        window.update_idletasks()

        self._resize_and_center()

    def _get_logo_path(self) -> Path:
        """Return logo path for normal Python and PyInstaller builds."""

        if getattr(sys, "frozen", False):
            base_dir = Path(sys._MEIPASS)
        else:
            base_dir = Path(__file__).resolve().parents[2]

        return base_dir / "assets" / "saydo-logo.png"

    def _get_max_text_lines(self) -> int:
        """Maximum number of visible text lines."""
        return 3

    def _limit_text_to_three_lines(self, text: str) -> str:
        """
        Keep the displayed text within approximately three lines.

        The actual line wrapping is handled by Tkinter. We use a
        character-based approximation here so the overlay never
        grows indefinitely during realtime transcription.
        """

        if not text:
            return ""

        # Approximate number of characters fitting on one line.
        # This is intentionally conservative for Segoe UI 11.
        chars_per_line = 72
        max_chars = chars_per_line * self._get_max_text_lines()

        if len(text) <= max_chars:
            return text

        # Keep the newest part of the transcription.
        return "…" + text[-(max_chars - 1):]

    def _calculate_height(self, text: str) -> int:
        """
        Calculate overlay height based on the number of text lines.

        Width stays fixed. Only height changes.
        """

        if not text:
            return self.MIN_HEIGHT

        # Approximate line count.
        chars_per_line = 72

        lines = 0

        for paragraph in text.split("\n"):
            if not paragraph:
                lines += 1
                continue

            lines += max(
                1,
                (len(paragraph) + chars_per_line - 1)
                // chars_per_line,
            )

        lines = min(lines, self._get_max_text_lines())

        # Text line height for Segoe UI 11 is roughly 20 px.
        text_height = lines * 20

        height = (
            self.VERTICAL_PADDING * 2
            + max(self.LOGO_SIZE, text_height)
        )

        return max(
            self.MIN_HEIGHT,
            min(height, self.MAX_HEIGHT),
        )

    def _resize_and_center(self, text: str = "") -> None:
        """
        Resize vertically while keeping width fixed.
        """

        if self._window is None:
            return

        height = self._calculate_height(text)

        self._window.geometry(
            f"{self.WINDOW_WIDTH}x{height}"
        )

        self._window.update_idletasks()

        screen_width = self._window.winfo_screenwidth()
        screen_height = self._window.winfo_screenheight()

        x = (screen_width - self.WINDOW_WIDTH) // 2
        y = screen_height - height - 80

        self._window.geometry(
            f"{self.WINDOW_WIDTH}x{height}+{x}+{y}"
        )

    def show_recording(self) -> None:
        """Show overlay when recording starts."""

        if self._root is None or self._window is None:
            return

        def update() -> None:
            if self._text_label is not None:
                self._text_label.config(text="")

            self._resize_and_center("")

            self._window.deiconify()
            self._window.lift()
            self._window.attributes("-topmost", True)

        self._root.after(0, update)

    def update_text(self, text: str) -> None:
        """Update live or final transcription text."""

        if self._root is None or self._window is None:
            return

        def update() -> None:
            if self._text_label is None:
                return

            display_text = self._limit_text_to_three_lines(text)

            self._text_label.config(
                text=display_text,
            )

            # Width remains fixed.
            # Only height changes.
            self._resize_and_center(display_text)

            if not self._window.winfo_viewable():
                self._window.deiconify()
                self._window.lift()
                self._window.attributes("-topmost", True)

        self._root.after(0, update)

    def hide(self) -> None:
        """Hide overlay."""

        if self._root is None or self._window is None:
            return

        self._root.after(
            0,
            self._window.withdraw,
        )

    def close(self) -> None:
        """Close overlay and Tkinter."""

        if self._root is None:
            return

        def destroy() -> None:
            if self._window is not None:
                self._window.destroy()

            self._root.quit()

        try:
            self._root.after(0, destroy)
        except Exception:
            pass