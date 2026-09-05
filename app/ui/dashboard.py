from __future__ import annotations

import json
import queue
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.dictionary import UserDictionary
from app.core.snippets import SnippetStore
from app.core.style import StyleStore
from app.llm.hardware import has_cuda_gpu
from app.llm.ollama import OllamaService
from app.llm.settings import LLMSettingsStore

APP_NAME = "Saydo"
ACCENT = "#6C63FF"
ACCENT_HOVER = "#7B73FF"

LIGHT = {
    "bg": "#F6F6F8",
    "sidebar": "#FBFBFC",
    "card": "#FFFFFF",
    "card_alt": "#F1F1F4",
    "border": "#E7E7EB",
    "text": "#18181B",
    "muted": "#777783",
    "subtle": "#A0A0AA",
    "hover": "#F0F0F5",
}

DARK = {
    "bg": "#111113",
    "sidebar": "#151518",
    "card": "#1B1B1F",
    "card_alt": "#242429",
    "border": "#2B2B31",
    "text": "#F4F4F5",
    "muted": "#A1A1AA",
    "subtle": "#71717A",
    "hover": "#222228",
}


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def data_path(name: str) -> Path:
    path = app_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path / name


class HistoryStore:
    def __init__(self) -> None:
        self.path = data_path("history.json")
        self._lock = threading.RLock()

    def load(self) -> list[dict[str, Any]]:
        with self._lock:
            try:
                if not self.path.exists():
                    return []
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []

    def add(
        self,
        text: str,
        duration: float,
        mode: str,
        raw_text: str | None = None,
    ) -> None:
        item = {
            "text": text,
            "raw_text": raw_text if raw_text is not None else text,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "duration": round(duration, 2),
            "mode": mode,
        }
        with self._lock:
            entries = self.load()
            entries.insert(0, item)
            entries = entries[:500]
            self.path.write_text(
                json.dumps(entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def update(self, target: dict[str, Any], text: str) -> None:
        """Persist an edited transcription."""
        with self._lock:
            entries = self.load()
            for entry in entries:
                if entry is target:
                    entry["text"] = text
                    break
            else:
                # Fallback for a copied dict: match stable timestamp.
                timestamp = target.get("timestamp")
                for entry in entries:
                    if timestamp and entry.get("timestamp") == timestamp:
                        entry["text"] = text
                        break
            self.path.write_text(
                json.dumps(entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )


class _Bridge(QObject):
    command = Signal(object)


class SaydoDesktopUI:
    """Modern desktop dashboard running independently from the recorder/overlay."""

    def __init__(self, hotkey: str = "right ctrl", mode: str = "instant", on_mode_change=None, on_model_change=None) -> None:
        self.hotkey = hotkey
        self.mode = mode
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._app: QApplication | None = None
        self._window: MainWindow | None = None
        self._started = threading.Event()
        self._history = HistoryStore()
        self._on_mode_change = on_mode_change
        self._on_model_change = on_model_change
    def start(self) -> None:
        self._thread = threading.current_thread()
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setApplicationName(APP_NAME)
        self._app.setOrganizationName(APP_NAME)

        self._window = MainWindow(
            history=self._history,
            hotkey=self.hotkey,
            mode=self.mode,
            on_mode_change=self._on_mode_change,
            on_model_change=self._on_model_change,
        )
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

        timer = QTimer()
        timer.timeout.connect(self._drain_queue)
        timer.start(80)

        self._started.set()
        self._app.exec()

    def _drain_queue(self) -> None:
        if self._window is None:
            return
        while True:
            try:
                command, payload = self._queue.get_nowait()
            except queue.Empty:
                break

            if command == "history":
                if len(payload) == 3:
                    text, duration, mode = payload
                    raw_text = text
                else:
                    text, duration, mode, raw_text = payload

                self._history.add(
                    text,
                    duration,
                    mode,
                    raw_text=raw_text,
                )
                self._window.refresh()
            elif command == "live":
                self._window.set_live_text(payload)
            elif command == "state":
                self._window.set_runtime_state(payload)
            elif command == "show":
                self._show_window()
            elif command == "stop":
                self._window.allow_close = True
                self._window.close()
                self._app.quit()

    def _show_window(self) -> None:
        if self._window is None:
            return
        self._window.show()
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()

    def show(self) -> None:
        self._queue.put(("show", None))

    def add_transcription(
        self,
        text: str,
        duration: float,
        mode: str,
        raw_text: str | None = None,
    ) -> None:
        self._queue.put(
            (
                "history",
                (
                    text,
                    duration,
                    mode,
                    raw_text if raw_text is not None else text,
                ),
            )
        )

    def set_live_text(self, text: str) -> None:
        self._queue.put(("live", text))

    def set_runtime_state(self, state: str) -> None:
        self._queue.put(("state", state))

    def stop(self) -> None:
        self._queue.put(("stop", None))


class DictionaryPromptDialog(QDialog):
    """Themed, rounded confirmation dialog for dictionary learning."""

    def __init__(
        self,
        parent: QWidget,
        candidates: list[tuple[str, str]],
        palette: dict[str, str],
    ) -> None:
        super().__init__(parent)
        self._palette = palette

        self.setWindowTitle("Добавить в словарь?")
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(440)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        card = QFrame()
        card.setObjectName("DictionaryDialogCard")
        card.setStyleSheet(f"""
            QFrame#DictionaryDialogCard {{
                background: {palette["card"]};
                border: 1px solid {palette["border"]};
                border-radius: 18px;
            }}
            QLabel#DialogTitle {{
                color: {palette["text"]};
                font-size: 18px;
                font-weight: 700;
            }}
            QLabel#DialogSubtitle {{
                color: {palette["muted"]};
                font-size: 13px;
            }}
            QFrame#PairCard {{
                background: {palette["card_alt"]};
                border: 1px solid {palette["border"]};
                border-radius: 10px;
            }}
            QLabel#PairText {{
                color: {palette["text"]};
                font-size: 13px;
            }}
            QPushButton#DialogNo {{
                background: transparent;
                color: {palette["muted"]};
                border: 1px solid {palette["border"]};
                border-radius: 10px;
                padding: 9px 18px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#DialogNo:hover {{
                background: {palette["hover"]};
                color: {palette["text"]};
            }}
            QPushButton#DialogYes {{
                background: {ACCENT};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 9px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#DialogYes:hover {{
                background: {ACCENT_HOVER};
            }}
        """)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Добавить в словарь?")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Saydo обнаружил исправление слова. "
            "Добавить его в ваш словарь?"
        )
        subtitle.setObjectName("DialogSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        for source, replacement in candidates:
            pair = QFrame()
            pair.setObjectName("PairCard")
            pair_layout = QHBoxLayout(pair)
            pair_layout.setContentsMargins(14, 10, 14, 10)
            pair_layout.setSpacing(10)

            left = QLabel(source)
            left.setObjectName("PairText")
            left.setSizePolicy(
                QSizePolicy.Expanding,
                QSizePolicy.Preferred,
            )

            arrow = QLabel("→")
            arrow.setStyleSheet(
                f"color: {ACCENT}; font-size: 14px; font-weight: 700;"
            )

            right = QLabel(replacement)
            right.setObjectName("PairText")
            right.setSizePolicy(
                QSizePolicy.Expanding,
                QSizePolicy.Preferred,
            )

            pair_layout.addWidget(left)
            pair_layout.addWidget(arrow)
            pair_layout.addWidget(right)
            layout.addWidget(pair)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        no_btn = QPushButton("Нет")
        no_btn.setObjectName("DialogNo")
        no_btn.setCursor(Qt.PointingHandCursor)

        yes_btn = QPushButton("Да")
        yes_btn.setObjectName("DialogYes")
        yes_btn.setCursor(Qt.PointingHandCursor)
        yes_btn.setDefault(True)

        buttons.addWidget(no_btn)
        buttons.addWidget(yes_btn)
        layout.addLayout(buttons)

        no_btn.clicked.connect(self.reject)
        yes_btn.clicked.connect(self.accept)

    def showEvent(self, event) -> None:
        super().showEvent(event)

        if self.parentWidget() is not None:
            parent = self.parentWidget()
            x = parent.x() + (parent.width() - self.width()) // 2
            y = parent.y() + (parent.height() - self.height()) // 2
            self.move(max(0, x), max(0, y))




class AIWarningDialog(QDialog):
    """Themed confirmation shown before enabling CPU-only AI processing."""

    def __init__(self, parent: QWidget, palette: dict[str, str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Mode")
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(470)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        card = QFrame()
        card.setObjectName("AIWarningCard")
        card.setStyleSheet(f"""
            QFrame#AIWarningCard {{
                background: {palette["card"]};
                border: 1px solid {palette["border"]};
                border-radius: 18px;
            }}
            QLabel#AIWarningTitle {{
                color: {palette["text"]};
                font-size: 19px;
                font-weight: 700;
            }}
            QLabel#AIWarningText {{
                color: {palette["muted"]};
                font-size: 13px;
            }}
            QLabel#AIWarningHint {{
                color: {palette["text"]};
                background: {palette["card_alt"]};
                border: 1px solid {palette["border"]};
                border-radius: 10px;
                padding: 11px 12px;
                font-size: 12px;
            }}
            QPushButton#AIWarningCancel {{
                background: transparent;
                color: {palette["muted"]};
                border: 1px solid {palette["border"]};
                border-radius: 10px;
                padding: 9px 16px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#AIWarningConfirm {{
                background: {ACCENT};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 9px 18px;
                font-size: 13px;
                font-weight: 600;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        title = QLabel("AI Mode может работать медленнее")
        title.setObjectName("AIWarningTitle")
        layout.addWidget(title)

        text = QLabel(
            "На этом компьютере не обнаружен совместимый GPU. "
            "Локальная AI-обработка будет выполняться на процессоре "
            "и может заметно увеличить время обработки диктовки."
        )
        text.setObjectName("AIWarningText")
        text.setWordWrap(True)
        layout.addWidget(text)

        hint = QLabel(
            "Вы всё равно можете включить AI Mode — Saydo продолжит работать, "
            "но результат может появляться с задержкой."
        )
        hint.setObjectName("AIWarningHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.setObjectName("AIWarningCancel")
        confirm = QPushButton("Всё равно включить")
        confirm.setObjectName("AIWarningConfirm")
        confirm.setDefault(True)
        cancel.clicked.connect(self.reject)
        confirm.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.parentWidget() is not None:
            parent = self.parentWidget()
            self.move(
                max(0, parent.x() + (parent.width() - self.width()) // 2),
                max(0, parent.y() + (parent.height() - self.height()) // 2),
            )

class AIUnavailableDialog(QDialog):
    """Themed informational dialog shown when local AI cannot be started."""

    def __init__(self, parent: QWidget, palette: dict[str, str], title: str, text: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Mode")
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(470)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        card = QFrame()
        card.setObjectName("AIUnavailableCard")
        card.setStyleSheet(f"""
            QFrame#AIUnavailableCard {{
                background: {palette["card"]};
                border: 1px solid {palette["border"]};
                border-radius: 18px;
            }}
            QLabel#AIUnavailableTitle {{
                color: {palette["text"]};
                font-size: 19px;
                font-weight: 700;
            }}
            QLabel#AIUnavailableText {{
                color: {palette["muted"]};
                font-size: 13px;
                line-height: 1.35;
            }}
            QLabel#AIUnavailableHint {{
                color: {palette["text"]};
                background: {palette["card_alt"]};
                border: 1px solid {palette["border"]};
                border-radius: 10px;
                padding: 11px 12px;
                font-size: 12px;
            }}
            QPushButton#AIUnavailableOk {{
                background: {ACCENT};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 9px 22px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#AIUnavailableOk:hover {{
                background: {ACCENT_HOVER};
            }}
        """)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("AIUnavailableTitle")
        layout.addWidget(title_label)

        text_label = QLabel(text)
        text_label.setObjectName("AIUnavailableText")
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        hint = QLabel("AI Mode будет отключён. Вы сможете включить его снова после установки и настройки Ollama.")
        hint.setObjectName("AIUnavailableHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok = QPushButton("ОК")
        ok.setObjectName("AIUnavailableOk")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.parentWidget() is not None:
            parent = self.parentWidget()
            self.move(
                max(0, parent.x() + (parent.width() - self.width()) // 2),
                max(0, parent.y() + (parent.height() - self.height()) // 2),
            )



class AIModelLoadingDialog(QDialog):
    """Themed modal shown while Ollama loads the selected model into memory."""

    def __init__(self, parent: QWidget, palette: dict[str, str], model: str, ollama: OllamaService) -> None:
        super().__init__(parent)
        self.model = model
        self.ollama = ollama
        self._cancel_event = threading.Event()
        self._result: dict[str, Any] = {"done": False, "ok": False, "error": ""}
        self._worker: threading.Thread | None = None
        self._dots = 0

        self.setWindowTitle("AI Mode")
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(470)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        card = QFrame()
        card.setObjectName("AIModelLoadingCard")
        card.setStyleSheet(f"""
            QFrame#AIModelLoadingCard {{
                background: {palette["card"]};
                border: 1px solid {palette["border"]};
                border-radius: 18px;
            }}
            QLabel#AIModelLoadingTitle {{
                color: {palette["text"]};
                font-size: 19px;
                font-weight: 700;
            }}
            QLabel#AIModelLoadingText {{
                color: {palette["muted"]};
                font-size: 13px;
            }}
            QLabel#AIModelLoadingModel {{
                color: {palette["text"]};
                background: {palette["card_alt"]};
                border: 1px solid {palette["border"]};
                border-radius: 10px;
                padding: 11px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton#AIModelLoadingCancel {{
                background: transparent;
                color: {palette["muted"]};
                border: 1px solid {palette["border"]};
                border-radius: 10px;
                padding: 9px 18px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#AIModelLoadingCancel:hover {{
                background: {palette["hover"]};
                color: {palette["text"]};
            }}
        """)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Готовим AI Mode")
        title.setObjectName("AIModelLoadingTitle")
        layout.addWidget(title)

        self.text_label = QLabel("Saydo загружает языковую модель в память. Это может занять некоторое время при первом запуске.")
        self.text_label.setObjectName("AIModelLoadingText")
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)

        model_label = QLabel(model)
        model_label.setObjectName("AIModelLoadingModel")
        model_label.setWordWrap(True)
        layout.addWidget(model_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.setObjectName("AIModelLoadingCancel")
        cancel.clicked.connect(self._cancel)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(150)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.parentWidget() is not None:
            parent = self.parentWidget()
            self.move(
                max(0, parent.x() + (parent.width() - self.width()) // 2),
                max(0, parent.y() + (parent.height() - self.height()) // 2),
            )
        if self._worker is None:
            self._worker = threading.Thread(target=self._load_model, daemon=True)
            self._worker.start()

    def _load_model(self) -> None:
        if self._cancel_event.is_set():
            self._result.update(done=True, ok=False)
            return
        try:
            ok, error = self.ollama.load_model(self.model)
            self._result.update(done=True, ok=ok, error=error)
        except Exception as exc:
            self._result.update(done=True, ok=False, error=str(exc))

        # If cancellation happened while Ollama was loading, explicitly unload
        # the model once the load request has returned.
        if self._cancel_event.is_set():
            self.ollama.unload_model(self.model)
            self._result.update(done=True, ok=False)

    def _poll(self) -> None:
        if self._cancel_event.is_set():
            self.text_label.setText("Останавливаем загрузку и освобождаем память…")
            return
        self._dots = (self._dots + 1) % 4
        self.text_label.setText(
            "Saydo загружает языковую модель в память"
            + "." * self._dots
            + "\nЭто может занять некоторое время при первом запуске."
        )
        if self._result["done"]:
            self._timer.stop()
            self.done(QDialog.Accepted if self._result["ok"] else QDialog.Rejected)

    def _cancel(self) -> None:
        self._cancel_event.set()
        self.text_label.setText("Останавливаем загрузку и освобождаем память…")
        # Keep the dialog open until the worker confirms that the model has
        # been unloaded. This guarantees AI Mode is not left half-enabled.
        if self._worker is None:
            self.done(QDialog.Rejected)


class MainWindow(QMainWindow):
    def __init__(
        self,
        history: HistoryStore,
        hotkey: str,
        mode: str,
        on_mode_change=None,
        on_model_change=None,
    ) -> None:
        super().__init__()
        self.history = history
        # The UI and processing pipeline use the same persistent dictionary
        # file. Keeping a UI-side instance here avoids coupling the window to
        # the desktop controller while still sharing all learned entries.
        self._dictionary = UserDictionary()
        self._snippets = SnippetStore()
        self._styles = StyleStore()
        self.allow_close = False
        self.hotkey = hotkey
        self.mode = mode
        self._on_mode_change = on_mode_change
        self._on_model_change = on_model_change
        self._llm_settings = LLMSettingsStore()
        self._ollama = OllamaService()
        self.current_theme = "system"
        self.runtime_state = "idle"

        self.setWindowTitle("Saydo")
        self.setMinimumSize(980, 680)
        self.resize(1180, 760)
        self.setWindowIcon(self._make_icon())

        self._build()
        self._load_theme()
        self._apply_windows_titlebar()
        self.refresh()

    def _make_icon(self) -> QIcon:
        logo_path = self._asset_path("assets/saydo-logo.png")
        if logo_path.exists():
            return QIcon(str(logo_path))
        return QIcon()

    def _asset_path(self, relative: str) -> Path:
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).resolve().parents[2]
        return base / relative

    def _apply_windows_titlebar(self) -> None:
        """Blend the native Windows title bar into the Saydo dark/light UI."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = wintypes.HWND(int(self.winId()))
            dwmapi = ctypes.windll.dwmapi
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36

            dark = self.current_theme == "dark" or (
                self.current_theme == "system" and self._palette_for_theme("system") is DARK
            )
            enabled = wintypes.BOOL(1 if dark else 0)
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(enabled), ctypes.sizeof(enabled)
            )

            palette = self._palette_for_theme(self.current_theme)
            rgb = palette["bg"].lstrip("#")
            value = int(rgb, 16)
            color = wintypes.DWORD(value)
            text = palette["text"].lstrip("#")
            text_value = wintypes.DWORD(int(text, 16))
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(color), ctypes.sizeof(color)
            )
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_TEXT_COLOR, ctypes.byref(text_value), ctypes.sizeof(text_value)
            )
        except Exception:
            pass

    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(238)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(18, 20, 18, 18)
        side.setSpacing(6)

        brand = QHBoxLayout()
        brand.setContentsMargins(8, 4, 8, 18)
        brand.setSpacing(10)

        brand_icon = QLabel()
        brand_icon.setObjectName("BrandIcon")
        brand_icon.setFixedSize(34, 34)
        logo_path = self._asset_path("assets/saydo-logo.png")
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                brand_icon.setPixmap(
                    pixmap.scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        brand.addWidget(brand_icon)

        brand_name = QLabel("Saydo")
        brand_name.setObjectName("BrandName")
        brand.addWidget(brand_name)
        brand.addStretch()
        side.addLayout(brand)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}

        nav = [
            ("dashboard", "◉", "Диктовка"),
            ("history", "◷", "История"),
            ("insights", "▥", "Insights"),
            ("dictionary", "▤", "Словарь"),
            ("snippets", "⌘", "Сниппеты"),
            ("style", "Tt", "Стиль"),
        ]
        for key, icon, label in nav:
            button = self._nav_button(key, icon, label)
            self.nav_buttons[key] = button
            side.addWidget(button)

        side.addStretch()

        settings = self._nav_button("settings", "⚙", "Настройки")
        self.nav_buttons["settings"] = settings
        side.addWidget(settings)

        help_button = self._nav_button("help", "?", "Помощь")
        self.nav_buttons["help"] = help_button
        side.addWidget(help_button)

        version = QLabel("Saydo 0.1  •  Local-first")
        version.setObjectName("Version")
        version.setContentsMargins(8, 12, 8, 0)
        side.addWidget(version)

        outer.addWidget(self.sidebar)

        content = QFrame()
        content.setObjectName("Content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 26, 30, 28)
        content_layout.setSpacing(20)

        top = QHBoxLayout()
        self.page_title = QLabel("Добро пожаловать в Saydo")
        self.page_title.setObjectName("PageTitle")
        top.addWidget(self.page_title)
        top.addStretch()

        self.status_pill = QLabel("● Готов")
        self.status_pill.setObjectName("StatusPill")
        top.addWidget(self.status_pill)
        content_layout.addLayout(top)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        outer.addWidget(content, 1)

        self._pages: dict[str, QWidget] = {}
        self._pages["dashboard"] = self._dashboard_page()
        self._pages["history"] = self._history_page()
        self._pages["insights"] = self._insights_page()
        self._pages["dictionary"] = self._dictionary_page()
        self._pages["snippets"] = self._snippets_page()
        self._pages["style"] = self._style_page()
        self._pages["settings"] = self._settings_page()
        self._pages["help"] = self._help_page()

        for widget in self._pages.values():
            self.stack.addWidget(widget)

        for key, button in self.nav_buttons.items():
            button.clicked.connect(lambda checked=False, k=key: self.navigate(k))

        self.nav_buttons["dashboard"].setChecked(True)

    def _nav_button(self, key: str, icon: str, text: str) -> QPushButton:
        button = QPushButton(f"{icon}    {text}")
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setFixedHeight(42)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.nav_group.addButton(button)
        return button

    def _card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        return frame

    def _dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("Hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(28, 24, 28, 24)

        left = QVBoxLayout()
        welcome = QLabel("Говорите. Saydo напечатает.")
        welcome.setObjectName("HeroTitle")
        sub = QLabel(
            "Удерживайте Right Ctrl, говорите и отпускайте.\n"
            "Текст появится в активном приложении."
        )
        sub.setObjectName("HeroText")
        left.addWidget(welcome)
        left.addSpacing(8)
        left.addWidget(sub)
        left.addStretch()

        self.live_label = QLabel("Готов к диктовке")
        self.live_label.setObjectName("LiveLabel")
        self.live_label.setWordWrap(True)
        self.live_label.setMinimumWidth(280)
        self.live_label.setMaximumWidth(420)
        hero_layout.addLayout(left, 1)
        hero_layout.addWidget(self.live_label)

        ai_panel = QFrame()
        ai_panel.setObjectName("AIModePanel")
        ai_layout = QHBoxLayout(ai_panel)
        ai_layout.setContentsMargins(16, 12, 16, 12)
        ai_layout.setSpacing(10)

        ai_text = QVBoxLayout()
        ai_title = QLabel("AI Mode")
        ai_title.setObjectName("AIHeading")
        ai_desc = QLabel("Улучшенная обработка текста с помощью ИИ")
        ai_desc.setObjectName("MutedText")
        ai_text.addWidget(ai_title)
        ai_text.addWidget(ai_desc)
        ai_layout.addLayout(ai_text, 1)

        self.ai_switch = QPushButton("Выкл.")
        self.ai_switch.setObjectName("AISwitch")
        self.ai_switch.setCheckable(True)
        self.ai_switch.setFixedSize(76, 34)
        self.ai_switch.setCursor(Qt.PointingHandCursor)
        self.ai_switch.clicked.connect(self._toggle_ai_mode)
        ai_layout.addWidget(self.ai_switch)

        # AI Mode is intentionally off by default. The persisted value is
        # restored only after the user has explicitly accepted it before.
        self._set_ai_switch(self.mode == "ai")

        layout.addWidget(ai_panel)
        layout.addWidget(hero)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.stat_words = self._stat_card("0", "слов сегодня")
        self.stat_sessions = self._stat_card("0", "диктовок сегодня")
        self.stat_speed = self._stat_card("—", "средняя скорость")
        self.stat_total = self._stat_card("0", "всего слов")
        for card in (self.stat_words, self.stat_sessions, self.stat_speed, self.stat_total):
            stats.addWidget(card)
        layout.addLayout(stats)

        recent_header = QHBoxLayout()
        title = QLabel("Последние диктовки")
        title.setObjectName("SectionTitle")
        recent_header.addWidget(title)
        recent_header.addStretch()
        all_btn = QPushButton("Открыть историю  →")
        all_btn.setObjectName("LinkButton")
        all_btn.clicked.connect(lambda: self.navigate("history"))
        recent_header.addWidget(all_btn)
        layout.addLayout(recent_header)

        recent_scroll = QScrollArea()
        recent_scroll.setObjectName("RecentScroll")
        recent_scroll.setWidgetResizable(True)
        recent_scroll.setFrameShape(QFrame.NoFrame)
        recent_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        recent_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        recent_scroll.viewport().setAutoFillBackground(False)

        recent_content = QWidget()
        recent_content.setObjectName("RecentContent")
        recent_content.setAttribute(Qt.WA_StyledBackground, True)
        self.recent_list = QVBoxLayout(recent_content)
        self.recent_list.setContentsMargins(0, 0, 4, 0)
        self.recent_list.setSpacing(8)
        self.recent_list.setAlignment(Qt.AlignTop)
        recent_scroll.setWidget(recent_content)

        layout.addWidget(recent_scroll, 1)
        return page

    def _set_ai_switch(self, enabled: bool) -> None:
        self.ai_switch.blockSignals(True)
        self.ai_switch.setChecked(enabled)
        self.ai_switch.setText("Вкл." if enabled else "Выкл.")
        self.ai_switch.blockSignals(False)

    def _toggle_ai_mode(self, checked: bool) -> None:
        if not checked:
            self._disable_ai_mode()
            return

        palette = self._palette_for_theme(self.current_theme)

        # CPU-only AI can work, but may be noticeably slower. Ask for an
        # explicit confirmation before allowing it.
        if not has_cuda_gpu():
            dialog = AIWarningDialog(self, palette)
            if dialog.exec() != QDialog.Accepted:
                self._set_ai_switch(False)
                return

        # GPU availability is not enough: local AI also requires Ollama and
        # at least one installed model. Check both before changing the mode.
        ollama_status, models = self._ollama.status()
        if ollama_status == "unavailable":
            AIUnavailableDialog(
                self,
                palette,
                "Ollama не найдена",
                "Saydo не может запустить AI Mode, потому что Ollama не установлена или недоступна на этом компьютере.",
            ).exec()
            self._disable_ai_mode()
            return

        if ollama_status == "no_models" or not models:
            AIUnavailableDialog(
                self,
                palette,
                "В Ollama нет моделей",
                "Ollama установлена, но в ней пока нет ни одной доступной языковой модели. Установите модель через Ollama и попробуйте снова.",
            ).exec()
            self._disable_ai_mode()
            return

        selected_model = self._llm_settings.get_model() or models[0]
        if selected_model not in models:
            selected_model = models[0]
            self._llm_settings.save_model(selected_model)

        # Load the selected model into Ollama memory before enabling AI Mode.
        # This makes the first dictation predictable and avoids a long,
        # unexplained delay inside the normal processing path.
        loading = AIModelLoadingDialog(self, palette, selected_model, self._ollama)
        if loading.exec() != QDialog.Accepted:
            self._disable_ai_mode()
            return

        self.mode = "ai"
        self._llm_settings.save_ai_mode(True)
        self._set_ai_switch(True)
        if self._on_mode_change is not None:
            try:
                self._on_mode_change(self.mode)
            except Exception as exc:
                print(f"[Saydo] Mode callback error: {exc}")
        self._update_mode_label()

    def _disable_ai_mode(self) -> None:
        """Force AI Mode back to Instant and release the local LLM memory."""
        selected_model = self._llm_settings.get_model()
        if selected_model:
            try:
                # Wait for Ollama to acknowledge keep_alive=0 before finishing
                # the transition, so the model is not left resident in memory.
                unloaded = self._ollama.unload_model(selected_model)
                if not unloaded:
                    print(f"[Saydo] Could not confirm unloading model: {selected_model}")
            except Exception as exc:
                print(f"[Saydo] LLM unload error: {exc}")
        self.mode = "instant"
        self._llm_settings.save_ai_mode(False)
        self._set_ai_switch(False)
        self._update_mode_label()
        if self._on_mode_change is not None:
            try:
                self._on_mode_change(self.mode)
            except Exception as exc:
                print(f"[Saydo] Mode callback error: {exc}")

    def _update_mode_label(self) -> None:
        if hasattr(self, "mode_value_label"):
            self.mode_value_label.setText(
                "AI" if self.mode == "ai" else "Instant"
            )

    def _stat_card(self, value: str, label: str) -> QFrame:
        card = self._card()
        card.setMinimumHeight(106)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 15, 18, 15)
        value_label = QLabel(value)
        value_label.setObjectName("StatValue")
        label_widget = QLabel(label)
        label_widget.setObjectName("StatLabel")
        layout.addWidget(value_label)
        layout.addWidget(label_widget)
        card.value_label = value_label  # type: ignore[attr-defined]
        return card

    def _history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        search = QLineEdit()
        search.setPlaceholderText("Поиск по истории…")
        search.setObjectName("Search")
        search.textChanged.connect(self._filter_history)
        layout.addWidget(search)

        self.history_list = QListWidget()
        self.history_list.setObjectName("HistoryList")
        self.history_list.setSpacing(5)
        layout.addWidget(self.history_list, 1)
        self.history_search = search
        return page

    def _insights_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Ваш голосовой рабочий ритм")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        card = self._card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        text = QLabel(
            "Здесь будут отображаться скорость речи, объём диктовки,\n"
            "экономия времени и динамика использования Saydo."
        )
        text.setObjectName("MutedText")
        card_layout.addWidget(text)
        card_layout.addSpacing(12)
        self.insights_summary = QLabel("")
        self.insights_summary.setObjectName("InsightBig")
        card_layout.addWidget(self.insights_summary)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _snippets_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        add_card = self._card()
        add_layout = QVBoxLayout(add_card)
        add_layout.setContentsMargins(18, 16, 18, 16)
        add_layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Новый сниппет")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch()
        add_layout.addLayout(header)

        self.snippet_name_input = QLineEdit()
        self.snippet_name_input.setPlaceholderText("Название")
        self.snippet_name_input.setObjectName("Search")

        self.snippet_trigger_input = QLineEdit()
        self.snippet_trigger_input.setPlaceholderText("Фраза-триггер")
        self.snippet_trigger_input.setObjectName("Search")

        self.snippet_text_input = QPlainTextEdit()
        self.snippet_text_input.setPlaceholderText("Текст сниппета…")
        self.snippet_text_input.setObjectName("SnippetEditor")
        self.snippet_text_input.setFixedHeight(96)

        add_layout.addWidget(self.snippet_name_input)
        add_layout.addWidget(self.snippet_trigger_input)
        add_layout.addWidget(self.snippet_text_input)

        add_button = QPushButton("Добавить")
        add_button.setObjectName("PrimaryButton")
        add_button.setCursor(Qt.PointingHandCursor)
        add_button.setFixedWidth(120)
        add_button.clicked.connect(self._add_snippet)
        add_layout.addWidget(add_button, 0, Qt.AlignRight)

        layout.addWidget(add_card)

        self.snippet_list = QListWidget()
        self.snippet_list.setObjectName("HistoryList")
        self.snippet_list.setSpacing(8)
        layout.addWidget(self.snippet_list, 1)

        return page

    def _add_snippet(self) -> None:
        try:
            self._snippets.add(
                self.snippet_name_input.text(),
                self.snippet_trigger_input.text(),
                self.snippet_text_input.toPlainText(),
            )
        except ValueError:
            QMessageBox.warning(
                self,
                "Не удалось добавить",
                "Укажите фразу-триггер и текст сниппета.",
            )
            return

        self.snippet_name_input.clear()
        self.snippet_trigger_input.clear()
        self.snippet_text_input.clear()
        self._refresh_snippets()

    def _refresh_snippets(self) -> None:
        if not hasattr(self, "snippet_list"):
            return

        self.snippet_list.clear()
        entries = self._snippets.load()

        for index, entry in enumerate(entries):
            item = QListWidgetItem()
            widget = self._snippet_card(entry, index)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.UserRole, index)
            self.snippet_list.addItem(item)
            self.snippet_list.setItemWidget(item, widget)

    def _snippet_card(self, entry: dict[str, str], index: int) -> QFrame:
        card = self._card()
        card.setMinimumHeight(92)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(5)

        top = QHBoxLayout()
        name = QLabel(entry.get("name") or entry.get("trigger", ""))
        name.setObjectName("HistoryText")
        name.setStyleSheet("font-weight: 650;")
        top.addWidget(name, 1)

        edit = QPushButton("✎")
        edit.setObjectName("IconButton")
        edit.setFixedSize(40, 40)
        edit.setToolTip("Редактировать")
        edit.clicked.connect(
            lambda checked=False, i=index: self._edit_snippet(i)
        )

        delete = QPushButton("×")
        delete.setObjectName("IconButton")
        delete.setFixedSize(40, 40)
        delete.setToolTip("Удалить")
        delete.clicked.connect(
            lambda checked=False, i=index: self._delete_snippet(i)
        )

        top.addWidget(edit)
        top.addWidget(delete)
        layout.addLayout(top)

        trigger = QLabel(f"Триггер: {entry.get('trigger', '')}")
        trigger.setObjectName("TimeLabel")
        layout.addWidget(trigger)

        preview = entry.get("text", "").replace("\n", " ")
        if len(preview) > 180:
            preview = preview[:177] + "…"
        body = QLabel(preview)
        body.setObjectName("MutedText")
        body.setWordWrap(True)
        layout.addWidget(body)

        return card

    def _edit_snippet(self, index: int) -> None:
        entries = self._snippets.load()
        if not 0 <= index < len(entries):
            return

        entry = entries[index]
        dialog = QDialog(self)
        dialog.setWindowTitle("Редактировать сниппет")
        dialog.setModal(True)
        dialog.setMinimumWidth(460)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        title = QLabel("Редактировать сниппет")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        name = QLineEdit(entry.get("name", ""))
        name.setPlaceholderText("Название")
        name.setObjectName("Search")
        trigger = QLineEdit(entry.get("trigger", ""))
        trigger.setPlaceholderText("Фраза-триггер")
        trigger.setObjectName("Search")
        body = QPlainTextEdit()
        body.setPlainText(entry.get("text", ""))
        body.setPlaceholderText("Текст сниппета…")
        body.setObjectName("SnippetEditor")
        body.setMinimumHeight(130)

        layout.addWidget(name)
        layout.addWidget(trigger)
        layout.addWidget(body)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Отмена")
        cancel.setObjectName("ThemeButton")
        save = QPushButton("Сохранить")
        save.setObjectName("PrimaryButton")
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        cancel.clicked.connect(dialog.reject)

        def save_changes() -> None:
            try:
                self._snippets.update(
                    index,
                    name.text(),
                    trigger.text(),
                    body.toPlainText(),
                )
            except ValueError:
                QMessageBox.warning(
                    dialog,
                    "Не удалось сохранить",
                    "Укажите фразу-триггер и текст сниппета.",
                )
                return
            dialog.accept()

        save.clicked.connect(save_changes)

        if dialog.exec() == QDialog.Accepted:
            self._refresh_snippets()

    def _delete_snippet(self, index: int) -> None:
        entries = self._snippets.load()
        if not 0 <= index < len(entries):
            return

        answer = QMessageBox.question(
            self,
            "Удалить сниппет?",
            f"Удалить «{entries[index].get('name') or entries[index].get('trigger')}»?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._snippets.delete(index)
            self._refresh_snippets()

    def _simple_page(self, title: str, description: str, action: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        card = self._card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(26, 26, 26, 26)

        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        desc = QLabel(description)
        desc.setObjectName("MutedText")
        desc.setWordWrap(True)
        button = QPushButton(action)
        button.setObjectName("PrimaryButton")
        button.setFixedWidth(180)
        card_layout.addWidget(heading)
        card_layout.addSpacing(8)
        card_layout.addWidget(desc)
        card_layout.addSpacing(18)
        card_layout.addWidget(button)
        card_layout.addStretch()

        layout.addWidget(card)
        layout.addStretch()
        return page

    def _style_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        intro = QLabel("Выберите, как Saydo должен формулировать текст в AI Mode.")
        intro.setObjectName("MutedText")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.style_list = QVBoxLayout()
        self.style_list.setSpacing(8)
        layout.addLayout(self.style_list)

        create = QPushButton("+  Создать свой стиль")
        create.setObjectName("PrimaryButton")
        create.setCursor(Qt.PointingHandCursor)
        create.clicked.connect(self._create_style)
        layout.addWidget(create, 0, Qt.AlignLeft)
        layout.addStretch()
        self._refresh_styles()
        return page

    def _refresh_styles(self) -> None:
        if not hasattr(self, "style_list"):
            return
        self._clear_layout(self.style_list)
        selected_id = self._styles.get_selected_id()

        for style in self._styles.load():
            style_id = str(style.get("id", ""))
            card = self._card()
            card.setMinimumHeight(78)
            row = QHBoxLayout(card)
            row.setContentsMargins(18, 14, 14, 14)
            row.setSpacing(14)

            info = QVBoxLayout()
            info.setSpacing(3)
            name = QLabel(str(style.get("name", "Без названия")))
            name.setObjectName("SectionTitle")
            info.addWidget(name)
            desc = QLabel(str(style.get("description", "")))
            desc.setObjectName("MutedText")
            desc.setWordWrap(True)
            info.addWidget(desc)
            row.addLayout(info, 1)

            if style_id == selected_id:
                check = QLabel("✓")
                check.setStyleSheet(f"color: {ACCENT}; font-size: 20px; font-weight: 700;")
                row.addWidget(check)

            button = QPushButton("Выбрано" if style_id == selected_id else "Выбрать")
            button.setObjectName("PrimaryButton" if style_id == selected_id else "SecondaryButton")
            button.setCursor(Qt.PointingHandCursor)
            button.setEnabled(style_id != selected_id)
            button.clicked.connect(lambda checked=False, sid=style_id: self._select_style(sid))
            row.addWidget(button)

            if not bool(style.get("builtin")):
                delete = QPushButton("×")
                delete.setObjectName("IconButton")
                delete.setToolTip("Удалить стиль")
                delete.clicked.connect(lambda checked=False, sid=style_id: self._delete_style(sid))
                row.addWidget(delete)

            self.style_list.addWidget(card)

    def _style_blocked_dialog(self) -> None:
        AIUnavailableDialog(
            self,
            self._palette_for_theme(self.current_theme),
            "Стиль доступен только в AI Mode",
            "Стили меняют подачу текста с помощью языковой модели. Включите AI Mode на главной странице, чтобы выбрать или создать стиль.",
        ).exec()

    def _select_style(self, style_id: str) -> None:
        if self.mode != "ai":
            self._style_blocked_dialog()
            return
        if self._styles.select(style_id):
            self._refresh_styles()

    def _delete_style(self, style_id: str) -> None:
        self._styles.delete(style_id)
        self._refresh_styles()

    def _create_style(self) -> None:
        if self.mode != "ai":
            self._style_blocked_dialog()
            return

        palette = self._palette_for_theme(self.current_theme)
        dialog = QDialog(self)
        dialog.setWindowTitle("Создать стиль")
        dialog.setModal(True)
        dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        dialog.setAttribute(Qt.WA_TranslucentBackground)
        dialog.setFixedWidth(520)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(10, 10, 10, 10)

        card = QFrame()
        card.setStyleSheet(
            f'QFrame {{ background: {palette["card"]}; border: 1px solid {palette["border"]}; border-radius: 18px; }}'
            f'QLineEdit, QPlainTextEdit {{ background: {palette["card_alt"]}; color: {palette["text"]}; border: 1px solid {palette["border"]}; border-radius: 10px; padding: 9px 11px; }}'
            f'QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}'
        )
        outer.addWidget(card)

        form = QVBoxLayout(card)
        form.setContentsMargins(24, 22, 24, 20)
        form.setSpacing(10)

        title = QLabel("Создать свой стиль")
        title.setStyleSheet(f"color: {palette['text']}; font-size: 19px; font-weight: 700; border: none;")
        form.addWidget(title)

        help_text = QLabel("Опишите своими словами, как Saydo должен формулировать текст.")
        help_text.setStyleSheet(f"color: {palette['muted']}; font-size: 13px; border: none;")
        help_text.setWordWrap(True)
        form.addWidget(help_text)

        name = QLineEdit()
        name.setPlaceholderText("Название, например «Мои сообщения»")
        form.addWidget(name)

        description = QLineEdit()
        description.setPlaceholderText("Короткое описание")
        form.addWidget(description)

        prompt = QPlainTextEdit()
        prompt.setPlaceholderText("Например: пиши спокойно и уверенно, избегай канцелярита, сохраняй короткие предложения…")
        prompt.setFixedHeight(120)
        form.addWidget(prompt)

        error = QLabel("")
        error.setStyleSheet(f"color: {palette['muted']}; font-size: 12px; border: none;")
        error.setWordWrap(True)
        form.addWidget(error)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel = QPushButton("Отмена")
        cancel.setObjectName("SecondaryButton")
        cancel.clicked.connect(dialog.reject)

        save = QPushButton("Создать")
        save.setObjectName("PrimaryButton")
        save.setDefault(True)

        def save_style() -> None:
            try:
                self._styles.add(name.text(), description.text(), prompt.toPlainText())
            except ValueError as exc:
                error.setText(str(exc))
                return
            dialog.accept()
            self._refresh_styles()

        save.clicked.connect(save_style)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        form.addLayout(buttons)

        dialog.exec()

    def _settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        appearance = self._card()
        a = QVBoxLayout(appearance)
        a.setContentsMargins(24, 22, 24, 22)

        heading = QLabel("Внешний вид")
        heading.setObjectName("SectionTitle")
        desc = QLabel("Выберите тему интерфейса Saydo.")
        desc.setObjectName("MutedText")
        a.addWidget(heading)
        a.addWidget(desc)
        a.addSpacing(16)

        theme_row = QHBoxLayout()
        self.theme_buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)

        for key, label in (
            ("light", "☀  Светлая"),
            ("dark", "☾  Тёмная"),
            ("system", "◐  Системная"),
        ):
            button = QPushButton(label)
            button.setObjectName("ThemeButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, k=key: self.set_theme(k))
            group.addButton(button)
            self.theme_buttons[key] = button
            theme_row.addWidget(button)

        a.addLayout(theme_row)
        layout.addWidget(appearance)

        controls = self._card()
        c = QVBoxLayout(controls)
        c.setContentsMargins(24, 22, 24, 22)
        h = QLabel("Диктовка")
        h.setObjectName("SectionTitle")
        c.addWidget(h)
        c.addSpacing(6)
        c.addWidget(QLabel(f"Горячая клавиша:  {self.hotkey}"))
        mode_row = QHBoxLayout()
        mode_title = QLabel("Режим обработки:")
        self.mode_value_label = QLabel("AI" if self.mode == "ai" else "Instant")
        self.mode_value_label.setObjectName("SettingsValue")
        mode_row.addWidget(mode_title)
        mode_row.addStretch()
        mode_row.addWidget(self.mode_value_label)
        c.addLayout(mode_row)
        c.addWidget(QLabel("STT:  GigaAM-v3 e2e-CTC"))
        layout.addWidget(controls)

        llm_card = self._card()
        lc = QVBoxLayout(llm_card)
        lc.setContentsMargins(24, 22, 24, 22)
        lh = QLabel("AI / Языковая модель")
        lh.setObjectName("SectionTitle")
        ld = QLabel("Локальные модели загружаются из установленного Ollama.")
        ld.setObjectName("MutedText")
        lc.addWidget(lh)
        lc.addWidget(ld)
        lc.addSpacing(12)

        model_row = QHBoxLayout()
        self.llm_model_combo = QComboBox()
        self.llm_model_combo.setObjectName("ModelCombo")
        self.llm_model_combo.setMinimumHeight(40)
        self.llm_model_combo.currentTextChanged.connect(self._model_changed)
        refresh_btn = QPushButton("Обновить")
        refresh_btn.setObjectName("SecondaryButton")
        refresh_btn.clicked.connect(self._refresh_llm_models)
        model_row.addWidget(self.llm_model_combo, 1)
        model_row.addWidget(refresh_btn)
        lc.addLayout(model_row)

        self.llm_status = QLabel("")
        self.llm_status.setObjectName("MutedText")
        lc.addWidget(self.llm_status)
        layout.addWidget(llm_card)
        self._refresh_llm_models()
        layout.addStretch()
        return page

    def _refresh_llm_models(self) -> None:
        if not hasattr(self, "llm_model_combo"):
            return
        current = self._llm_settings.get_model()
        models = self._ollama.list_models()

        self.llm_model_combo.blockSignals(True)
        self.llm_model_combo.clear()
        self.llm_model_combo.addItems(models)
        if current and current in models:
            self.llm_model_combo.setCurrentText(current)
        elif models:
            self.llm_model_combo.setCurrentIndex(0)
            current = models[0]
            self._llm_settings.save_model(current)
        self.llm_model_combo.blockSignals(False)

        if models:
            self.llm_status.setText(f"Найдено моделей: {len(models)}")
        elif self._ollama.is_available():
            self.llm_status.setText("В Ollama пока нет установленных моделей.")
        else:
            self.llm_status.setText("Ollama не запущена или не установлена.")

    def _model_changed(self, model: str) -> None:
        model = model.strip()
        if not model:
            return
        self._llm_settings.save_model(model)
        if self._on_model_change is not None:
            try:
                self._on_model_change(model)
            except Exception as exc:
                print(f"[Saydo] Model callback error: {exc}")

    def _help_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card = self._card()
        c = QVBoxLayout(card)
        c.setContentsMargins(26, 26, 26, 26)
        h = QLabel("Как пользоваться Saydo")
        h.setObjectName("SectionTitle")
        body = QLabel(
            "1. Откройте любое приложение с текстовым полем.\n"
            "2. Удерживайте Right Ctrl.\n"
            "3. Говорите естественно.\n"
            "4. Отпустите клавишу — Saydo распознает и вставит текст.\n\n"
            "Откройте Saydo из системного трея, чтобы посмотреть историю и настройки."
        )
        body.setObjectName("MutedText")
        body.setWordWrap(True)
        c.addWidget(h)
        c.addSpacing(10)
        c.addWidget(body)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def navigate(self, key: str) -> None:
        if key not in self._pages:
            return
        self.stack.setCurrentWidget(self._pages[key])
        titles = {
            "dashboard": "Добро пожаловать в Saydo",
            "history": "История диктовок",
            "insights": "Insights",
            "dictionary": "Словарь",
            "snippets": "Сниппеты",
            "style": "Стиль",
            "settings": "Настройки",
            "help": "Помощь",
        }
        self.page_title.setText(titles.get(key, "Saydo"))
        if key in self.nav_buttons:
            self.nav_buttons[key].setChecked(True)

    def set_live_text(self, text: str) -> None:
        if hasattr(self, "live_label"):
            self.live_label.setText(text or "Готов к диктовке")

    def set_runtime_state(self, state: str) -> None:
        self.runtime_state = state
        labels = {
            "idle": "● Готов",
            "recording": "● Запись",
            "processing": "● Обработка",
        }
        self.status_pill.setText(labels.get(state, "● Готов"))

    def refresh(self) -> None:
        entries = self.history.load()
        self._refresh_stats(entries)
        self._refresh_recent(entries)
        self._refresh_dictionary()
        self._refresh_snippets()
        if hasattr(self, "history_list"):
            self._refresh_history(entries)
        if hasattr(self, "insights_summary"):
            total_words = sum(len(e.get("text", "").split()) for e in entries)
            self.insights_summary.setText(f"{total_words:,} слов обработано".replace(",", " "))
        self._apply_filter_from_search()

    def _refresh_stats(self, entries: list[dict[str, Any]]) -> None:
        today = datetime.now().date().isoformat()
        todays = [e for e in entries if str(e.get("timestamp", "")).startswith(today)]
        today_words = sum(len(e.get("text", "").split()) for e in todays)
        total_words = sum(len(e.get("text", "").split()) for e in entries)

        speeds: list[float] = []
        for e in todays:
            duration = float(e.get("duration") or 0)
            words = len(e.get("text", "").split())
            if duration > 0:
                speeds.append(words / duration * 60)

        avg_speed = f"{round(sum(speeds) / len(speeds))} wpm" if speeds else "—"

        self.stat_words.value_label.setText(f"{today_words:,}".replace(",", " "))
        self.stat_sessions.value_label.setText(str(len(todays)))
        self.stat_speed.value_label.setText(avg_speed)
        self.stat_total.value_label.setText(f"{total_words:,}".replace(",", " "))

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_recent(self, entries: list[dict[str, Any]]) -> None:
        self._clear_layout(self.recent_list)
        for entry in entries[:5]:
            self.recent_list.addWidget(self._history_card(entry, editable=True))

    def _history_card(self, entry: dict[str, Any], editable: bool = False) -> QFrame:
        card = self._card()
        # Keep every history row tall enough for a wrapped two-line
        # transcription. A fixed height smaller than the label's contents
        # causes the next card to visually overlap the previous one.
        card.setFixedHeight(82)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 10, 12, 10)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignVCenter)

        ts = str(entry.get("timestamp", ""))
        try:
            dt = datetime.fromisoformat(ts)
            stamp = dt.strftime("%H:%M")
        except Exception:
            stamp = "--:--"

        time_label = QLabel(stamp)
        time_label.setObjectName("TimeLabel")
        time_label.setFixedWidth(52)
        layout.addWidget(time_label)

        original_text = str(entry.get("text", ""))

        if editable:
            text_label = QLabel(original_text)
            text_label.setObjectName("HistoryText")
            text_label.setWordWrap(True)
            text_label.setMaximumHeight(42)
            text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            editor = QPlainTextEdit()
            editor.setObjectName("HistoryEditor")
            editor.setPlainText(original_text)
            editor.setPlaceholderText("Исправьте текст…")
            editor.setFixedHeight(44)
            editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            editor.hide()

            layout.addWidget(text_label, 1)
            layout.addWidget(editor, 1)

            copy_button = QPushButton("⧉")
            copy_button.setObjectName("IconButton")
            copy_button.setFixedSize(40, 40)
            copy_button.setToolTip("Скопировать")

            edit_button = QPushButton("✎")
            edit_button.setObjectName("IconButton")
            edit_button.setFixedSize(40, 40)
            edit_button.setToolTip("Редактировать")

            def copy_current() -> None:
                self._copy(editor.toPlainText() if editor.isVisible() else text_label.text())
                copy_button.setText("✓")
                copy_button.setObjectName("ConfirmButton")
                copy_button.setToolTip("Скопировано")
                copy_button.style().unpolish(copy_button)
                copy_button.style().polish(copy_button)
                token = int(copy_button.property("copy_feedback_token") or 0) + 1
                copy_button.setProperty("copy_feedback_token", token)

                def restore() -> None:
                    if copy_button.property("copy_feedback_token") != token:
                        return
                    copy_button.setText("⧉")
                    copy_button.setObjectName("IconButton")
                    copy_button.setToolTip("Скопировать")
                    copy_button.style().unpolish(copy_button)
                    copy_button.style().polish(copy_button)

                QTimer.singleShot(1000, restore)

            def toggle_edit() -> None:
                if not editor.isVisible():
                    # Enter edit mode without changing the card geometry.
                    text_label.hide()
                    editor.show()
                    edit_button.setText("✓")
                    edit_button.setObjectName("ConfirmButton")
                    edit_button.setToolTip("Завершить редактирование")
                    edit_button.style().unpolish(edit_button)
                    edit_button.style().polish(edit_button)
                    editor.setFocus()
                    editor.selectAll()
                else:
                    # The checkmark always exits edit mode. If the text was
                    # changed, _save_edited_transcription also learns the
                    # correction; otherwise this is simply a cancel/finish.
                    edited = editor.toPlainText().strip()
                    original = original_text.strip()
                    if edited and edited != original:
                        self._save_edited_transcription(entry, edited)
                        text_label.setText(edited)

                    # Always leave edit mode, even when the confirmation
                    # dialog was shown or the text was unchanged.
                    editor.hide()
                    text_label.show()
                    edit_button.setText("✎")
                    edit_button.setObjectName("IconButton")
                    edit_button.setToolTip("Редактировать")
                    edit_button.style().unpolish(edit_button)
                    edit_button.style().polish(edit_button)

            copy_button.clicked.connect(copy_current)
            edit_button.clicked.connect(toggle_edit)
            layout.addWidget(copy_button)
            layout.addWidget(edit_button)
        else:
            text = QLabel(original_text)
            text.setObjectName("HistoryText")
            text.setWordWrap(True)
            text.setMaximumHeight(42)
            text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout.addWidget(text, 1)

            copy_button = QPushButton("⧉")
            copy_button.setObjectName("IconButton")
            copy_button.setFixedSize(40, 40)
            copy_button.setToolTip("Скопировать")
            def copy_current() -> None:
                self._copy(original_text)
                copy_button.setText("✓")
                copy_button.setObjectName("ConfirmButton")
                copy_button.setToolTip("Скопировано")
                copy_button.style().unpolish(copy_button)
                copy_button.style().polish(copy_button)
                token = int(copy_button.property("copy_feedback_token") or 0) + 1
                copy_button.setProperty("copy_feedback_token", token)

                def restore() -> None:
                    if copy_button.property("copy_feedback_token") != token:
                        return
                    copy_button.setText("⧉")
                    copy_button.setObjectName("IconButton")
                    copy_button.setToolTip("Скопировать")
                    copy_button.style().unpolish(copy_button)
                    copy_button.style().polish(copy_button)

                QTimer.singleShot(1000, restore)

            copy_button.clicked.connect(copy_current)
            layout.addWidget(copy_button)

        return card

    @staticmethod
    def _extract_word_tokens(text: str) -> list[str]:
        """Extract words while ignoring punctuation and whitespace."""
        return re.findall(
            r"[\w]+(?:[-’'][\w]+)*",
            text,
            flags=re.UNICODE,
        )

    def _find_dictionary_candidates(
        self,
        original: str,
        edited: str,
    ) -> list[tuple[str, str]]:
        """
        Find conservative word substitutions.

        Punctuation-only edits are deliberately ignored. We only propose a
        dictionary entry when a SequenceMatcher replacement changes the same
        number of word tokens, which prevents unrelated insertions/deletions
        from becoming dictionary entries.
        """
        import difflib

        old_words = self._extract_word_tokens(original)
        new_words = self._extract_word_tokens(edited)

        if not old_words or not new_words:
            return []

        matcher = difflib.SequenceMatcher(
            a=[word.casefold() for word in old_words],
            b=[word.casefold() for word in new_words],
        )

        candidates: list[tuple[str, str]] = []
        existing = {
            (source.casefold(), replacement.casefold())
            for source, replacement in self._dictionary.corrections()
        }

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "replace":
                continue

            # Conservative by design: only equal-sized replacements are
            # considered word corrections.
            if (i2 - i1) != (j2 - j1):
                continue

            for old, new in zip(old_words[i1:i2], new_words[j1:j2], strict=False):
                if old.casefold() == new.casefold():
                    continue

                pair = (old, new)
                if (old.casefold(), new.casefold()) not in existing:
                    candidates.append(pair)

        # De-duplicate while preserving the order in which corrections
        # appeared in the user's edit.
        unique: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for pair in candidates:
            key = (pair[0].casefold(), pair[1].casefold())
            if key not in seen:
                seen.add(key)
                unique.append(pair)

        return unique

    def _ask_add_dictionary(
        self,
        candidates: list[tuple[str, str]],
    ) -> bool:
        """Ask whether detected word corrections should enter the dictionary."""
        if not candidates:
            return False

        palette = self._palette_for_theme(self.current_theme)
        dialog = DictionaryPromptDialog(
            self,
            candidates,
            palette,
        )
        return dialog.exec() == QDialog.Accepted

    def _save_edited_transcription(self, entry: dict[str, Any], edited: str) -> None:
        original = str(entry.get("text", "")).strip()
        edited = edited.strip()
        if not edited or edited == original:
            return

        candidates = self._find_dictionary_candidates(original, edited)

        # Ask only when actual word substitutions were detected.
        if candidates and self._ask_add_dictionary(candidates):
            for source, replacement in candidates:
                self._dictionary.add_correction(source, replacement)

        # The user's corrected transcription is always persisted, regardless
        # of the dictionary answer.
        self.history.update(entry, edited)
        entry["text"] = edited
    def _dictionary_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        add_card = self._card()
        add_layout = QVBoxLayout(add_card)
        add_layout.setContentsMargins(18, 16, 18, 16)
        add_layout.setSpacing(10)

        title = QLabel("Добавить исправление")
        title.setObjectName("SectionTitle")
        add_layout.addWidget(title)

        fields = QHBoxLayout()
        fields.setSpacing(10)

        self.dictionary_source_input = QLineEdit()
        self.dictionary_source_input.setPlaceholderText(
            "Как Saydo распознаёт…"
        )
        self.dictionary_source_input.setObjectName("Search")

        self.dictionary_replacement_input = QLineEdit()
        self.dictionary_replacement_input.setPlaceholderText(
            "Как должно быть…"
        )
        self.dictionary_replacement_input.setObjectName("Search")

        fields.addWidget(self.dictionary_source_input, 1)
        fields.addWidget(self.dictionary_replacement_input, 1)
        add_layout.addLayout(fields)

        add_button = QPushButton("Добавить")
        add_button.setObjectName("PrimaryButton")
        add_button.setCursor(Qt.PointingHandCursor)
        add_button.clicked.connect(self._add_dictionary_correction)
        add_button.setFixedWidth(120)
        add_layout.addWidget(
            add_button,
            0,
            Qt.AlignRight,
        )

        layout.addWidget(add_card)

        self.dictionary_search = QLineEdit()
        self.dictionary_search.setPlaceholderText(
            "Поиск в словаре…"
        )
        self.dictionary_search.setObjectName("Search")
        self.dictionary_search.textChanged.connect(
            self._filter_dictionary
        )
        layout.addWidget(self.dictionary_search)

        self.dictionary_list = QListWidget()
        self.dictionary_list.setObjectName("HistoryList")
        self.dictionary_list.setSpacing(5)
        layout.addWidget(self.dictionary_list, 1)

        return page

    def _add_dictionary_correction(self) -> None:
        source = self.dictionary_source_input.text().strip()
        replacement = self.dictionary_replacement_input.text().strip()

        if not source or not replacement:
            return

        self._dictionary.add_correction(
            source,
            replacement,
        )

        self.dictionary_source_input.clear()
        self.dictionary_replacement_input.clear()
        self._refresh_dictionary()
    def _refresh_dictionary(self) -> None:
        if not hasattr(self, "dictionary_list"):
            return
        entries = self._dictionary.load()
        self.dictionary_list.clear()
        for index, entry in enumerate(entries):
            item = QListWidgetItem()
            item.setSizeHint(self._dictionary_card(entry, index).sizeHint())
            item.setData(Qt.UserRole, index)
            self.dictionary_list.addItem(item)
            self.dictionary_list.setItemWidget(item, self._dictionary_card(entry, index))
        self._filter_dictionary(self.dictionary_search.text())

    def _dictionary_card(self, entry: dict[str, str], index: int) -> QFrame:
        card = self._card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 10, 12, 10)
        if entry.get("type") == "correction":
            label = QLabel(f"{entry.get('source', '')}  →  {entry.get('replacement', '')}")
        else:
            label = QLabel(entry.get("word", ""))
        label.setObjectName("HistoryText")
        layout.addWidget(label, 1)
        kind = QLabel("Исправление" if entry.get("type") == "correction" else "Слово")
        kind.setObjectName("TimeLabel")
        layout.addWidget(kind)
        delete = QPushButton("×")
        delete.setObjectName("IconButton")
        delete.setToolTip("Удалить из словаря")
        delete.clicked.connect(lambda checked=False, i=index: self._delete_dictionary(i))
        layout.addWidget(delete)
        return card

    def _delete_dictionary(self, index: int) -> None:
        self._dictionary.delete(index)
        self._refresh_dictionary()

    def _filter_dictionary(self, text: str) -> None:
        if not hasattr(self, "dictionary_list"):
            return
        query = text.strip().casefold()
        entries = self._dictionary.load()
        for index in range(self.dictionary_list.count()):
            item = self.dictionary_list.item(index)
            entry = entries[index] if index < len(entries) else {}
            haystack = " ".join(str(entry.get(k, "")) for k in ("word", "source", "replacement")).casefold()
            item.setHidden(bool(query and query not in haystack))

    def _refresh_history(self, entries: list[dict[str, Any]]) -> None:
        self.history_list.clear()
        for entry in entries:
            item = QListWidgetItem()
            widget = self._history_card(entry, editable=True)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.UserRole, entry)
            self.history_list.addItem(item)
            self.history_list.setItemWidget(item, widget)

    def _filter_history(self, text: str) -> None:
        query = text.strip().lower()
        for index in range(self.history_list.count()):
            item = self.history_list.item(index)
            data = item.data(Qt.UserRole) or {}
            value = str(data.get("text", "")).lower()
            item.setHidden(bool(query and query not in value))

    def _apply_filter_from_search(self) -> None:
        if hasattr(self, "history_search"):
            self._filter_history(self.history_search.text())

    def _copy(self, text: str) -> None:
        QApplication.clipboard().setText(text)

    def _load_theme(self) -> None:
        settings_file = data_path("settings.json")
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            self.current_theme = settings.get("theme", "system")
        except Exception:
            self.current_theme = "system"
        self.set_theme(self.current_theme, persist=False)

    def _save_theme(self) -> None:
        path = data_path("settings.json")
        try:
            path.write_text(
                json.dumps({"theme": self.current_theme}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def set_theme(self, theme: str, persist: bool = True) -> None:
        self.current_theme = theme
        if persist:
            self._save_theme()

        palette = self._palette_for_theme(theme)
        self.setStyleSheet(self._stylesheet(palette))

        if hasattr(self, "theme_buttons"):
            for key, button in self.theme_buttons.items():
                button.setChecked(key == theme)

        # Reapply native Windows titlebar colors after every theme change.
        self._apply_windows_titlebar()

    def _palette_for_theme(self, theme: str) -> dict[str, str]:
        if theme == "dark":
            return DARK
        if theme == "light":
            return LIGHT

        # Windows dark-mode hint. Fall back to light.
        try:
            if sys.platform == "win32":
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                )
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return LIGHT if value else DARK
        except Exception:
            pass
        return LIGHT

    def _stylesheet(self, c: dict[str, str]) -> str:
        return f"""
        QWidget {{
            font-family: "Segoe UI";
            color: {c["text"]};
        }}
        QMainWindow, #Content {{
            background: {c["bg"]};
        }}
        #Sidebar {{
            background: {c["sidebar"]};
            border-right: 1px solid {c["border"]};
        }}
        #BrandIcon {{
            background: transparent;
        }}
        #BrandName {{
            font-size: 20px;
            font-weight: 700;
        }}
        #Version {{
            color: {c["subtle"]};
            font-size: 11px;
        }}
        QPushButton#NavButton {{
            border: none;
            border-radius: 10px;
            background: transparent;
            color: {c["muted"]};
            text-align: left;
            padding: 10px 12px;
            font-size: 13px;
            min-width: 0;
        }}
        QPushButton#NavButton:hover {{
            background: {c["hover"]};
            color: {c["text"]};
        }}
        QPushButton#NavButton:checked {{
            background: {ACCENT};
            color: white;
            font-weight: 600;
        }}
        #PageTitle {{
            font-size: 25px;
            font-weight: 700;
        }}
        #StatusPill {{
            background: {c["card"]};
            border: 1px solid {c["border"]};
            border-radius: 14px;
            padding: 6px 12px;
            color: {c["muted"]};
        }}
        #Hero {{
            background: {c["card"]};
            border: 1px solid {c["border"]};
            border-radius: 18px;
        }}
        #HeroTitle {{
            font-size: 25px;
            font-weight: 700;
        }}
        #HeroText, #MutedText {{
            color: {c["muted"]};
            font-size: 13px;
            line-height: 1.4;
        }}
        #LiveLabel {{
            background: {c["card_alt"]};
            border-radius: 14px;
            padding: 16px;
            color: {c["text"]};
            font-size: 14px;
        }}
        #Card {{
            background: {c["card"]};
            border: 1px solid {c["border"]};
            border-radius: 14px;
        }}
        #StatValue {{
            font-size: 25px;
            font-weight: 700;
        }}
        #StatLabel, #TimeLabel {{
            color: {c["muted"]};
            font-size: 12px;
        }}
        #SectionTitle {{
            font-size: 18px;
            font-weight: 650;
        }}
        #HistoryText {{
            font-size: 13px;
        }}
        #HistoryEditor {{
            background: {c["card_alt"]};
            border: 1px solid {c["border"]};
            border-radius: 10px;
            padding: 8px;
            font-size: 13px;
        }}
        #HistoryEditor {{
            min-height: 0px;
            max-height: 44px;
        }}
        #SnippetEditor {{
            background: {c["card_alt"]};
            border: 1px solid {c["border"]};
            border-radius: 10px;
            padding: 9px 12px;
            font-size: 13px;
        }}
        #SnippetEditor:focus {{
            border-color: {ACCENT};
        }}
        #HistoryEditor:focus {{
            border-color: {ACCENT};
        }}
        QPushButton#LinkButton {{
            border: none;
            color: {ACCENT};
            background: transparent;
            font-weight: 600;
        }}
        QPushButton#IconButton {{
            border: none;
            background: transparent;
            color: {c["muted"]};
            font-size: 16px;
            padding: 7px;
            border-radius: 8px;
        }}
        QPushButton#IconButton:hover {{
            background: {c["hover"]};
            color: {c["text"]};
        }}
        QPushButton#ConfirmButton {{
            border: none;
            background: transparent;
            color: {c["muted"]};
            font-size: 18px;
            font-weight: 700;
            padding: 7px;
            border-radius: 8px;
        }}
        QPushButton#ConfirmButton:hover {{
            background: {c["hover"]};
            color: {c["text"]};
        }}
        #AIModePanel {{
            background: {c["card_alt"]};
            border: 1px solid {c["border"]};
            border-radius: 14px;
        }}
        #AIHeading {{
            font-size: 15px;
            font-weight: 650;
        }}
        QPushButton#AISwitch {{
            background: {c["border"]};
            color: {c["muted"]};
            border: none;
            border-radius: 17px;
            font-size: 12px;
            font-weight: 700;
        }}
        QPushButton#AISwitch:checked {{
            background: {ACCENT};
            color: white;
        }}
        QComboBox#ModelCombo {{
            background: {c["card"]};
            border: 1px solid {c["border"]};
            border-radius: 10px;
            padding: 8px 12px;
        }}
        QPushButton#SecondaryButton {{
            background: {c["card_alt"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 9px;
            padding: 9px 16px;
            font-weight: 600;
        }}
        QPushButton#SecondaryButton:hover {{
            background: {c["hover"]};
        }}
        #SettingsValue {{
            color: {ACCENT};
            font-weight: 650;
        }}
        QPushButton#PrimaryButton {{
            background: {ACCENT};
            color: white;
            border: none;
            border-radius: 9px;
            padding: 9px 16px;
            font-weight: 600;
        }}
        QPushButton#PrimaryButton:hover {{
            background: {ACCENT_HOVER};
        }}
        QLineEdit#Search {{
            background: {c["card"]};
            border: 1px solid {c["border"]};
            border-radius: 10px;
            padding: 10px 12px;
        }}
        QListWidget#HistoryList {{
            background: transparent;
            border: none;
        }}
        QListWidget#HistoryList::item {{
            background: transparent;
            border: none;
        }}
        QScrollArea#RecentScroll {{
            background: {c["bg"]};
            border: none;
        }}
        QScrollArea#RecentScroll > QWidget#qt_scrollarea_viewport {{
            background: {c["bg"]};
        }}
        QWidget#RecentContent {{
            background: {c["bg"]};
        }}
        QPushButton#ThemeButton {{
            background: {c["card_alt"]};
            border: 1px solid {c["border"]};
            border-radius: 10px;
            padding: 10px 14px;
        }}
        QPushButton#ThemeButton:checked {{
            background: {ACCENT};
            color: white;
            border-color: {ACCENT};
        }}
        #InsightBig {{
            font-size: 24px;
            font-weight: 700;
        }}
        """

    def closeEvent(self, event) -> None:
        if getattr(self, "allow_close", False):
            event.accept()
            return

        # Closing the window only hides the dashboard. Saydo keeps running
        # in the system tray and continues listening for the global hotkey.
        event.ignore()
        self.hide()

