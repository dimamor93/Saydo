from __future__ import annotations

import json
import os
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


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

    def add(self, text: str, duration: float, mode: str) -> None:
        item = {
            "text": text,
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


class _Bridge(QObject):
    command = Signal(object)


class SaydoDesktopUI:
    """Modern desktop dashboard running independently from the recorder/overlay."""

    def __init__(self, hotkey: str = "right ctrl", mode: str = "instant") -> None:
        self.hotkey = hotkey
        self.mode = mode
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._app: QApplication | None = None
        self._window: MainWindow | None = None
        self._started = threading.Event()
        self._history = HistoryStore()

    def start(self) -> None:
        self._thread = threading.current_thread()
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setApplicationName(APP_NAME)
        self._app.setOrganizationName(APP_NAME)

        self._window = MainWindow(
            history=self._history,
            hotkey=self.hotkey,
            mode=self.mode,
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
                text, duration, mode = payload
                self._history.add(text, duration, mode)
                self._window.refresh()
            elif command == "live":
                self._window.set_live_text(payload)
            elif command == "state":
                self._window.set_runtime_state(payload)
            elif command == "stop":
                self._window.close()

    def add_transcription(self, text: str, duration: float, mode: str) -> None:
        self._queue.put(("history", (text, duration, mode)))

    def set_live_text(self, text: str) -> None:
        self._queue.put(("live", text))

    def set_runtime_state(self, state: str) -> None:
        self._queue.put(("state", state))

    def stop(self) -> None:
        self._queue.put(("stop", None))


class MainWindow(QMainWindow):
    def __init__(
        self,
        history: HistoryStore,
        hotkey: str,
        mode: str,
    ) -> None:
        super().__init__()
        self.history = history
        self.hotkey = hotkey
        self.mode = mode
        self.current_theme = "system"
        self.runtime_state = "idle"

        self.setWindowTitle("Saydo")
        self.setMinimumSize(980, 680)
        self.resize(1180, 760)
        self.setWindowIcon(self._make_icon())

        self._build()
        self._load_theme()
        self.refresh()

    def _make_icon(self) -> QIcon:
        # Avoid a hard dependency on image assets for the dashboard.
        return QIcon()

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
        brand_icon = QLabel("◉")
        brand_icon.setObjectName("BrandIcon")
        brand_icon.setFixedWidth(28)
        brand_name = QLabel("Saydo")
        brand_name.setObjectName("BrandName")
        brand.addWidget(brand_icon)
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
        self._pages["dictionary"] = self._simple_page(
            "Словарь",
            "Добавляйте слова и названия, которые Saydo должен распознавать без ошибок.",
            "Добавить слово",
        )
        self._pages["snippets"] = self._simple_page(
            "Сниппеты",
            "Готовые фразы для повторяющихся задач. Позже привяжем их к горячим клавишам.",
            "Создать сниппет",
        )
        self._pages["style"] = self._simple_page(
            "Стиль",
            "Настройте, как Saydo форматирует вашу речь: обычный текст, деловой стиль или более свободная подача.",
            "Создать стиль",
        )
        self._pages["settings"] = self._settings_page()
        self._pages["help"] = self._help_page()

        for widget in self._pages.values():
            self.stack.addWidget(widget)

        for key, button in self.nav_buttons.items():
            button.clicked.connect(lambda checked=False, k=key: self.navigate(k))

        self.nav_buttons["dashboard"].setChecked(True)

    def _nav_button(self, key: str, icon: str, text: str) -> QPushButton:
        button = QPushButton(f"  {icon}    {text}")
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
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

        self.recent_list = QVBoxLayout()
        self.recent_list.setSpacing(8)
        layout.addLayout(self.recent_list)
        layout.addStretch()
        return page

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
        c.addWidget(QLabel("Режим обработки:  Instant"))
        c.addWidget(QLabel("STT:  GigaAM-v3 e2e-CTC"))
        layout.addWidget(controls)
        layout.addStretch()
        return page

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
            self.recent_list.addWidget(self._history_card(entry))

    def _history_card(self, entry: dict[str, Any]) -> QFrame:
        card = self._card()
        card.setMinimumHeight(66)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 10, 16, 10)

        ts = str(entry.get("timestamp", ""))
        try:
            dt = datetime.fromisoformat(ts)
            stamp = dt.strftime("%H:%M")
        except Exception:
            stamp = "--:--"

        time_label = QLabel(stamp)
        time_label.setObjectName("TimeLabel")
        time_label.setFixedWidth(52)

        text = QLabel(str(entry.get("text", "")))
        text.setObjectName("HistoryText")
        text.setWordWrap(True)
        text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        copy_button = QPushButton("⧉")
        copy_button.setObjectName("IconButton")
        copy_button.setToolTip("Скопировать")
        copy_button.clicked.connect(
            lambda checked=False, value=str(entry.get("text", "")): self._copy(value)
        )

        layout.addWidget(time_label)
        layout.addWidget(text, 1)
        layout.addWidget(copy_button)
        return card

    def _refresh_history(self, entries: list[dict[str, Any]]) -> None:
        self.history_list.clear()
        for entry in entries:
            item = QListWidgetItem()
            item.setSizeHint(self._history_card(entry).sizeHint())
            item.setData(Qt.UserRole, entry)
            self.history_list.addItem(item)

            widget = self._history_card(entry)
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
            color: {ACCENT};
            font-size: 24px;
            font-weight: 800;
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
        event.accept()
