from __future__ import annotations
from PySide6.QtGui import QShowEvent
from PySide6.QtGui import QIcon

import csv
import json
import os
import queue
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
)

import app.ui.dashboard as dashboard


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app


class FakeHistory:
    def __init__(self, entries=None):
        self.entries = list(entries or [])
        self.updated = []

    def load(self):
        return self.entries

    def add(self, text, duration, mode, raw_text=None):
        item = {
            "text": text,
            "raw_text": text if raw_text is None else raw_text,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "duration": round(duration, 2),
            "words": len(text.split()),
            "wpm": round(len(text.split()) / duration * 60, 1) if duration > 0 else 0.0,
            "mode": mode,
        }
        self.entries.insert(0, item)
        self.entries[:] = self.entries[:500]

    def update(self, target, text):
        for entry in self.entries:
            if entry is target or (
                target.get("timestamp") and
                entry.get("timestamp") == target.get("timestamp")
            ):
                entry["text"] = text
                self.updated.append((entry, text))
                return

    def export_csv(self, target):
        with Path(target).open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f, fieldnames=("timestamp", "words", "wpm", "duration")
            )
            writer.writeheader()
            for e in self.entries:
                writer.writerow({
                    "timestamp": e.get("timestamp", ""),
                    "words": e.get("words", len(str(e.get("text", "")).split())),
                    "wpm": e.get("wpm", 0),
                    "duration": e.get("duration", 0),
                })


class FakeDictionary:
    def __init__(self):
        self.entries = []
        self.added = []

    def load(self):
        return self.entries

    def corrections(self):
        return [
            (e["source"], e["replacement"])
            for e in self.entries
            if e.get("type") == "correction"
        ]

    def add_correction(self, source, replacement):
        self.added.append((source, replacement))
        self.entries.append({
            "type": "correction",
            "source": source,
            "replacement": replacement,
        })

    def delete(self, index):
        del self.entries[index]


class FakeSnippets:
    def __init__(self):
        self.entries = []
        self.calls = []

    def load(self):
        return self.entries

    def add(self, name, trigger, text):
        if not trigger.strip() or not text.strip():
            raise ValueError("invalid")
        self.calls.append(("add", name, trigger, text))
        self.entries.append({"name": name, "trigger": trigger, "text": text})

    def update(self, index, name, trigger, text):
        if not trigger.strip() or not text.strip():
            raise ValueError("invalid")
        self.calls.append(("update", index, name, trigger, text))
        self.entries[index] = {"name": name, "trigger": trigger, "text": text}

    def delete(self, index):
        self.calls.append(("delete", index))
        del self.entries[index]


class FakeStyles:
    def __init__(self):
        self.entries = [
            {
                "id": "builtin",
                "name": "Обычный",
                "description": "Базовый стиль",
                "builtin": True,
            },
            {
                "id": "custom",
                "name": "Мой стиль",
                "description": "Коротко",
                "builtin": False,
            },
        ]
        self.selected = "builtin"
        self.calls = []

    def load(self):
        return self.entries

    def get_selected_id(self):
        return self.selected

    def select(self, style_id):
        self.calls.append(("select", style_id))
        if any(str(x["id"]) == str(style_id) for x in self.entries):
            self.selected = str(style_id)
            return True
        return False

    def delete(self, style_id):
        self.calls.append(("delete", style_id))
        self.entries = [x for x in self.entries if str(x["id"]) != str(style_id)]

    def add(self, name, description, prompt):
        if not name.strip() or not prompt.strip():
            raise ValueError("Название и промпт обязательны")
        self.calls.append(("add", name, description, prompt))
        self.entries.append({
            "id": "new",
            "name": name,
            "description": description,
            "builtin": False,
        })


class FakeAutostart:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.calls = []

    def is_enabled(self):
        return self.enabled

    def enable(self):
        self.calls.append("enable")
        self.enabled = True

    def disable(self):
        self.calls.append("disable")
        self.enabled = False


class FakeLLMSettings:
    def __init__(self, model=""):
        self.model = model
        self.ai = False
        self.calls = []

    def get_model(self):
        return self.model

    def save_model(self, model):
        self.model = model
        self.calls.append(("model", model))

    def save_ai_mode(self, enabled):
        self.ai = enabled
        self.calls.append(("ai", enabled))


class FakeOllama:
    def __init__(self, models=None, available=True, status_value=None):
        self.models = list(models or [])
        self.available = available
        self.status_value = status_value
        self.calls = []

    def list_models(self):
        self.calls.append("list_models")
        return list(self.models)

    def is_available(self):
        self.calls.append("is_available")
        return self.available

    def status(self):
        self.calls.append("status")
        if self.status_value:
            return self.status_value, list(self.models)
        if not self.available:
            return "unavailable", []
        if not self.models:
            return "no_models", []
        return "ok", list(self.models)

    def load_model(self, model):
        self.calls.append(("load", model))
        return True, ""

    def unload_model(self, model):
        self.calls.append(("unload", model))
        return True


@pytest.fixture
def stores(monkeypatch, tmp_path):
    history = FakeHistory()
    dictionary = FakeDictionary()
    snippets = FakeSnippets()
    styles = FakeStyles()
    autostart = FakeAutostart()
    settings = FakeLLMSettings()
    ollama = FakeOllama(models=["qwen3.8:27b"])

    data = tmp_path / "data"
    data.mkdir()

    def data_path(name):
        return data / name

    monkeypatch.setattr(dashboard, "data_path", data_path)
    monkeypatch.setattr(dashboard, "UserDictionary", lambda: dictionary)
    monkeypatch.setattr(dashboard, "SnippetStore", lambda: snippets)
    monkeypatch.setattr(dashboard, "StyleStore", lambda: styles)
    monkeypatch.setattr(dashboard, "AutostartManager", lambda: autostart)
    monkeypatch.setattr(dashboard, "LLMSettingsStore", lambda: settings)
    monkeypatch.setattr(dashboard, "OllamaService", lambda: ollama)

    return history, dictionary, snippets, styles, autostart, settings, ollama


@pytest.fixture
def window(qapp, stores, monkeypatch):
    history, *_ = stores
    monkeypatch.setattr(dashboard, "has_cuda_gpu", lambda: True)
    w = dashboard.MainWindow(history, "right ctrl", "instant")
    yield w
    w.allow_close = True
    w.close()
    qapp.processEvents()


def test_app_root_source_and_frozen(monkeypatch):
    monkeypatch.setattr(dashboard.sys, "frozen", False, raising=False)
    source = dashboard.app_root()
    assert source == Path(dashboard.__file__).resolve().parents[2]

    monkeypatch.setattr(dashboard.sys, "frozen", True, raising=False)
    monkeypatch.setattr(dashboard.sys, "executable", r"C:\Saydo\Saydo.exe", raising=False)
    assert dashboard.app_root() == Path(r"C:\Saydo").resolve()


def test_data_path_creates_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard, "app_root", lambda: tmp_path)
    assert dashboard.data_path("x.json") == tmp_path / "data" / "x.json"
    assert (tmp_path / "data").is_dir()


def test_history_store_missing_and_invalid(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard, "data_path", lambda name: tmp_path / name)
    store = dashboard.HistoryStore()
    assert store.load() == []

    store.path.write_text("{}", encoding="utf-8")
    assert store.load() == []

    store.path.write_text("{bad", encoding="utf-8")
    assert store.load() == []


def test_history_store_add_update_export(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard, "data_path", lambda name: tmp_path / name)
    store = dashboard.HistoryStore()

    store.add("one two", 2.0, "instant", raw_text="one  two")
    assert store.load()[0]["words"] == 2
    assert store.load()[0]["wpm"] == 60.0
    assert store.load()[0]["raw_text"] == "one  two"

    store.add("", 0, "ai")
    assert store.load()[0]["wpm"] == 0.0

    entries = store.load()
    entries[1]["timestamp"] = "2026-01-01T00:00:01"
    store.path.write_text(
        __import__("json").dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    copied = dict(store.load()[1])
    store.update(copied, "edited")
    assert store.load()[1]["text"] == "edited"

    target = tmp_path / "stats.csv"
    store.export_csv(target)
    rows = list(csv.DictReader(target.open(encoding="utf-8-sig")))
    assert rows
    assert set(rows[0]) == {"timestamp", "words", "wpm", "duration"}


def test_history_store_caps_at_500(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard, "data_path", lambda name: tmp_path / name)
    store = dashboard.HistoryStore()
    store.path.write_text(json.dumps([{"text": "x"}] * 500), encoding="utf-8")
    store.add("new", 1, "instant")
    assert len(store.load()) == 500
    assert store.load()[0]["text"] == "new"


def test_desktop_ui_queue_and_commands(qapp):
    history = FakeHistory()
    ui = dashboard.SaydoDesktopUI()
    ui._history = history
    ui._window = Mock()
    ui._app = Mock()

    ui.add_transcription("hello world", 2, "instant", raw_text="raw")
    ui.set_live_text("live")
    ui.set_runtime_state("recording")
    ui.show()
    ui._queue.put(("unknown", None))
    ui._drain_queue()

    ui._window.refresh.assert_called_once()
    ui._window.set_live_text.assert_called_once_with("live")
    ui._window.set_runtime_state.assert_called_once_with("recording")
    ui._window.show.assert_called()

    ui.stop()
    ui._drain_queue()
    assert ui._window.allow_close is True
    ui._app.quit.assert_called_once()


def test_desktop_ui_history_three_tuple():
    ui = dashboard.SaydoDesktopUI()
    ui._window = Mock()
    ui._history = Mock()
    ui._queue.put(("history", ("text", 1.0, "instant")))
    ui._drain_queue()
    ui._history.add.assert_called_once_with("text", 1.0, "instant", raw_text="text")


def test_desktop_ui_no_window_and_show():
    ui = dashboard.SaydoDesktopUI()
    ui._drain_queue()
    ui._show_window()
    ui.show()
    ui.set_live_text("x")
    ui.set_runtime_state("idle")
    ui.stop()
    assert ui._queue.qsize() == 4


def test_dictionary_dialog(qapp):
    dialog = dashboard.DictionaryPromptDialog(None, [("saydo", "Saydo")], dashboard.LIGHT)
    assert dialog.windowTitle() == "Добавить в словарь?"
    assert dialog.isModal()
    assert dialog.findChildren(QLabel)
    dialog.reject()


def test_dialog_show_events(qapp):
    parent = Mock()
    parent.x.return_value = 100
    parent.y.return_value = 50
    parent.width.return_value = 1000
    parent.height.return_value = 700
    parent_widget = Mock()
    parent_widget.x.return_value = 100
    parent_widget.y.return_value = 50
    parent_widget.width.return_value = 1000
    parent_widget.height.return_value = 700

    # Real QWidget parent is used to exercise positioning safely.
    from PySide6.QtWidgets import QWidget
    real_parent = QWidget()
    real_parent.resize(1000, 700)

    for cls, args in (
        (dashboard.DictionaryPromptDialog, ([("a", "b")],)),
        (dashboard.AIWarningDialog, ()),
        (dashboard.AIUnavailableDialog, ("Title", "Text")),
    ):
        if cls is dashboard.DictionaryPromptDialog:
            d = cls(real_parent, *args, dashboard.LIGHT)
        else:
            d = cls(real_parent, dashboard.LIGHT, *args)
        d.showEvent(QShowEvent())
        d.reject()


def test_ai_loading_dialog_all_paths(qapp):
    ollama = FakeOllama(["model"])
    d = dashboard.AIModelLoadingDialog(qapp.activeWindow(), dashboard.LIGHT, "model", ollama)
    d._load_model()
    assert d._result["done"] and d._result["ok"]

    d._result.update(done=False, ok=False)
    d._dots = 0
    d._poll()
    assert d._dots == 1

    d._cancel_event.set()
    d._poll()
    d._timer.stop()
    d.close()


def test_ai_loading_dialog_cancel_before_worker(qapp):
    ollama = FakeOllama(["model"])
    d = dashboard.AIModelLoadingDialog(qapp.activeWindow(), dashboard.LIGHT, "model", ollama)
    d._cancel_event.set()
    d._load_model()
    assert d._result["done"] is True
    d._worker = None
    d._cancel()
    d._timer.stop()
    d.close()


def test_ai_loading_dialog_exception(qapp):
    class Broken:
        def load_model(self, model):
            raise RuntimeError("boom")

        def unload_model(self, model):
            return True

    d = dashboard.AIModelLoadingDialog(qapp.activeWindow(), dashboard.LIGHT, "x", Broken())
    d._load_model()
    assert d._result["error"] == "boom"
    d._timer.stop()
    d.close()


def test_ai_loading_dialog_cancel_during_load(qapp):
    class Cancelled:
        def load_model(self, model):
            d._cancel_event.set()
            return True, ""

        def unload_model(self, model):
            self.unloaded = model
            return True

    c = Cancelled()
    d = dashboard.AIModelLoadingDialog(qapp.activeWindow(), dashboard.LIGHT, "x", c)
    d._load_model()
    assert c.unloaded == "x"
    assert d._result["ok"] is False
    d._timer.stop()
    d.close()


def test_mainwindow_navigation_and_runtime(window):
    for key in ("dashboard", "history", "insights", "dictionary", "snippets", "style", "settings", "help"):
        window.navigate(key)
        assert window.stack.currentWidget() is window._pages[key]
        assert window.page_title.text()

    window.navigate("does-not-exist")
    window.set_live_text("")
    assert window.live_label.text() == "Готов к диктовке"
    window.set_live_text("abc")
    assert window.live_label.text() == "abc"

    for state, expected in (
        ("idle", "● Готов"),
        ("recording", "● Запись"),
        ("processing", "● Обработка"),
        ("other", "● Готов"),
    ):
        window.set_runtime_state(state)
        assert window.status_pill.text() == expected


def test_stats_refresh(window):
    today = datetime.now().date().isoformat()
    entries = [
        {"timestamp": today + "T10:00:00", "text": "one two", "duration": 2},
        {"timestamp": today + "T11:00:00", "text": "three four", "duration": 4},
        {"timestamp": "2020-01-01T00:00:00", "text": "old", "duration": 1},
        {"timestamp": today + "T12:00:00", "text": "", "duration": 0},
    ]
    window._refresh_stats(entries)
    assert window.stat_words.value_label.text() == "4"
    assert window.stat_sessions.value_label.text() == "3"
    assert window.stat_total.value_label.text() == "5"
    assert window.stat_speed.value_label.text() == "45 wpm"


def test_refresh_and_insights(window, stores):
    history, dictionary, snippets, *_ = stores
    history.entries[:] = [
        {"timestamp": "2026-01-01T12:00:00", "text": "hello world", "duration": 2},
        {"timestamp": "2026-01-01T13:00:00", "text": "another", "duration": 1},
    ]
    window.refresh()
    assert window.insights_summary.text() == "3 слов обработано"
    assert window.recent_list.count() == 2
    assert window.history_list.count() == 2


def test_history_filter_and_apply(window, stores):
    history, *_ = stores
    history.entries[:] = [
        {"timestamp": "2026-01-01T12:00:00", "text": "Hello World"},
        {"timestamp": "2026-01-01T12:01:00", "text": "Other"},
    ]
    window.refresh()
    window._filter_history("hello")
    assert not window.history_list.item(0).isHidden()
    assert window.history_list.item(1).isHidden()
    window.history_search.setText("other")
    window._apply_filter_from_search()
    assert window.history_list.item(1).isHidden() is False


def test_dictionary_operations(window, stores):
    _, dictionary, *_ = stores
    window.dictionary_source_input.setText("teh")
    window.dictionary_replacement_input.setText("the")
    window._add_dictionary_correction()
    assert dictionary.added == [("teh", "the")]
    assert window.dictionary_source_input.text() == ""

    window.dictionary_search.setText("zzz")
    assert window.dictionary_list.item(0).isHidden()

    window._delete_dictionary(0)
    assert dictionary.entries == []


def test_dictionary_empty_input(window, stores):
    _, dictionary, *_ = stores
    window.dictionary_source_input.setText("")
    window.dictionary_replacement_input.setText("x")
    window._add_dictionary_correction()
    assert dictionary.added == []


def test_dictionary_candidates(window):
    w = window
    d = FakeDictionary()
    w._dictionary = d

    assert w._extract_word_tokens("Привет, мир! foo-bar don't") == [
        "Привет", "мир", "foo-bar", "don't"
    ]
    assert w._find_dictionary_candidates("", "x") == []
    assert w._find_dictionary_candidates("hello world", "hello world!") == []
    assert w._find_dictionary_candidates("hello world", "hi world") == [("hello", "hi")]
    d.entries.append({"type": "correction", "source": "hello", "replacement": "hi"})
    assert w._find_dictionary_candidates("hello world", "hi world") == []
    assert w._find_dictionary_candidates("a b", "x y z") == []


def test_save_edited_transcription(window, stores, monkeypatch):
    history, dictionary, *_ = stores
    entry = {"timestamp": "2026-01-01T12:00:00", "text": "hello world"}

    monkeypatch.setattr(window, "_ask_add_dictionary", lambda c: True)
    window._save_edited_transcription(entry, "hi world")
    assert entry["text"] == "hi world"
    assert dictionary.added == [("hello", "hi")]

    before = len(dictionary.added)
    window._save_edited_transcription(entry, "hi world")
    assert len(dictionary.added) == before


def test_save_edited_transcription_rejects_empty(window, stores, monkeypatch):
    history, *_ = stores
    entry = {"timestamp": "x", "text": "hello"}
    update = Mock()
    monkeypatch.setattr(window.history, "update", update)
    window._save_edited_transcription(entry, "")
    window._save_edited_transcription(entry, "hello")
    update.assert_not_called()


def test_history_card_noneditable_copy(window, monkeypatch):
    copied = []
    monkeypatch.setattr(window, "_copy", lambda text: copied.append(text))
    card = window._history_card({"timestamp": "bad", "text": "hello"}, editable=False)
    button = card.findChildren(QPushButton)[0]
    button.click()
    assert copied == ["hello"]
    assert button.text() == "✓"


def test_history_card_editable_copy_and_edit(window, monkeypatch):
    copied = []
    saved = []
    monkeypatch.setattr(window, "_copy", lambda text: copied.append(text))
    monkeypatch.setattr(window, "_save_edited_transcription", lambda e, t: saved.append((e, t)))

    entry = {"timestamp": "2026-01-01T12:00:00", "text": "hello"}
    card = window._history_card(entry, editable=True)
    card.show()
    buttons = card.findChildren(QPushButton)
    editor = card.findChildren(QPlainTextEdit)[0]

    buttons[0].click()
    assert copied == ["hello"]
    edit_button = buttons[1]
    edit_button.click()
    assert not editor.isHidden()
    assert edit_button.text() == "✓"

    editor.setPlainText("hello edited")
    edit_button.click()

    assert saved == [(entry, "hello edited")]
    assert not editor.isVisible()


def test_history_card_edit_without_change(window, monkeypatch):
    saved = Mock()
    monkeypatch.setattr(window, "_save_edited_transcription", saved)
    entry = {"timestamp": "x", "text": "hello"}
    card = window._history_card(entry, editable=True)
    buttons = card.findChildren(QPushButton)
    editor = card.findChildren(QPlainTextEdit)[0]
    buttons[1].click()
    editor.setPlainText("hello")
    buttons[1].click()
    saved.assert_not_called()


def test_recent_limit_and_clear_layout(window, stores):
    history, *_ = stores
    entries = [
        {"timestamp": f"2026-01-01T12:0{i}:00", "text": str(i)}
        for i in range(7)
    ]
    window._refresh_recent(entries)
    assert window.recent_list.count() == 5

    window._clear_layout(window.recent_list)
    assert window.recent_list.count() == 0


def test_snippets_add_and_refresh(window, stores, monkeypatch):
    _, _, snippets, *_ = stores
    window.snippet_name_input.setText("Test")
    window.snippet_trigger_input.setText("brb")
    window.snippet_text_input.setPlainText("be right back")
    window._add_snippet()
    assert len(snippets.entries) == 1
    assert window.snippet_name_input.text() == ""

    window._refresh_snippets()
    assert window.snippet_list.count() == 1


def test_snippets_invalid(monkeypatch, window):
    warning = Mock()
    monkeypatch.setattr(dashboard.QMessageBox, "warning", warning)
    window.snippet_name_input.setText("")
    window.snippet_trigger_input.setText("")
    window.snippet_text_input.setPlainText("")
    window._add_snippet()
    warning.assert_called_once()


def test_snippet_card_preview_and_actions(window, stores, monkeypatch):
    _, _, snippets, *_ = stores
    long_text = "x" * 200
    entry = {"name": "N", "trigger": "t", "text": long_text}
    card = window._snippet_card(entry, 0)
    labels = card.findChildren(QLabel)
    assert any("…" in x.text() for x in labels)

    window._snippets.entries[:] = [entry]
    monkeypatch.setattr(window, "_edit_snippet", Mock())
    monkeypatch.setattr(window, "_delete_snippet", Mock())
    buttons = card.findChildren(QPushButton)
    buttons[0].click()
    buttons[1].click()
    window._edit_snippet.assert_called_once_with(0)
    window._delete_snippet.assert_called_once_with(0)


def test_edit_snippet_invalid_and_valid(window, stores, monkeypatch):
    _, _, snippets, *_ = stores
    snippets.entries[:] = [{"name": "N", "trigger": "t", "text": "body"}]
    warning = Mock()
    monkeypatch.setattr(dashboard.QMessageBox, "warning", warning)

    original_exec = dashboard.QDialog.exec

    def fake_exec(dialog):
        fields = dialog.findChildren(QLineEdit)
        body = dialog.findChildren(QPlainTextEdit)[0]
        fields[0].setText("New")
        fields[1].setText("new-trigger")
        body.setPlainText("new body")
        dialog.findChildren(QPushButton)[1].click()
        return QDialog.Accepted

    monkeypatch.setattr(dashboard.QDialog, "exec", fake_exec)
    window._edit_snippet(0)
    assert snippets.entries[0]["name"] == "New"

    def invalid_exec(dialog):
        fields = dialog.findChildren(QLineEdit)
        body = dialog.findChildren(QPlainTextEdit)[0]
        fields[1].setText("")
        body.setPlainText("")
        dialog.findChildren(QPushButton)[1].click()
        return QDialog.Rejected

    monkeypatch.setattr(dashboard.QDialog, "exec", invalid_exec)
    window._edit_snippet(0)
    warning.assert_called()


def test_edit_snippet_bad_index(window, stores):
    window._edit_snippet(999)
    assert True


def test_delete_snippet_yes_no(window, stores, monkeypatch):
    _, _, snippets, *_ = stores
    snippets.entries[:] = [{"name": "N", "trigger": "t", "text": "body"}]

    monkeypatch.setattr(
        dashboard.QMessageBox,
        "question",
        lambda *a, **k: dashboard.QMessageBox.No,
    )
    window._delete_snippet(0)
    assert len(snippets.entries) == 1

    monkeypatch.setattr(
        dashboard.QMessageBox,
        "question",
        lambda *a, **k: dashboard.QMessageBox.Yes,
    )
    window._delete_snippet(0)
    assert snippets.entries == []


def test_delete_snippet_bad_index(window):
    window._delete_snippet(999)


def test_styles_refresh_select_delete(window, stores, monkeypatch):
    _, _, _, styles, *_ = stores
    window._refresh_styles()
    assert window.style_list.count() == 2

    blocked = []
    monkeypatch.setattr(
        window,
        "_style_blocked_dialog",
        lambda: blocked.append(True),
    )

    window.mode = "instant"
    window._select_style("custom")
    assert blocked == [True]

    window.mode = "ai"
    window._select_style("custom")
    assert styles.selected == "custom"

    window._select_style("missing")
    assert styles.selected == "custom"

    window._delete_style("custom")
    assert all(x["id"] != "custom" for x in styles.entries)


def test_create_style_valid(window, stores, monkeypatch):
    _, _, _, styles, *_ = stores
    window.mode = "ai"

    def fake_exec(dialog):
        fields = dialog.findChildren(QLineEdit)
        body = dialog.findChildren(QPlainTextEdit)[0]
        fields[0].setText("Custom")
        fields[1].setText("Desc")
        body.setPlainText("Prompt")
        dialog.findChildren(QPushButton)[1].click()
        return QDialog.Accepted

    monkeypatch.setattr(dashboard.QDialog, "exec", fake_exec)
    window._create_style()
    assert any(x[0] == "add" for x in styles.calls)


def test_create_style_invalid_then_cancel(window, stores, monkeypatch):
    _, _, _, styles, *_ = stores
    window.mode = "ai"

    def fake_exec(dialog):
        fields = dialog.findChildren(QLineEdit)
        body = dialog.findChildren(QPlainTextEdit)[0]
        fields[0].setText("")
        fields[1].setText("Desc")
        body.setPlainText("")
        dialog.findChildren(QPushButton)[1].click()
        dialog.findChildren(QPushButton)[0].click()
        return QDialog.Rejected

    monkeypatch.setattr(dashboard.QDialog, "exec", fake_exec)
    window._create_style()
    assert not any(x[0] == "add" for x in styles.calls)


def test_settings_and_theme(window, stores, monkeypatch, tmp_path):
    window.set_theme("dark")
    assert window.current_theme == "dark"
    window.set_theme("light")
    assert window.current_theme == "light"

    path = dashboard.data_path("settings.json")
    path.write_text(json.dumps({"autostart": True}), encoding="utf-8")
    window.current_theme = "system"
    window._save_theme()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["theme"] == "system"
    assert saved["autostart"] is True

    assert window._palette_for_theme("dark") is dashboard.DARK
    assert window._palette_for_theme("light") is dashboard.LIGHT


def test_load_settings_invalid(window):
    path = dashboard.data_path("settings.json")
    path.write_text("{bad", encoding="utf-8")
    assert window._load_settings() == {}


def test_save_autostart_success_and_error(window, stores, monkeypatch):
    autostart = stores[4]
    window._toggle_autostart(True)
    assert autostart.enabled is True

    autostart.enabled = False
    autostart.enable = Mock(side_effect=OSError("denied"))
    critical = Mock()
    monkeypatch.setattr(dashboard.QMessageBox, "critical", critical)
    window._toggle_autostart(True)
    critical.assert_called_once()

    monkeypatch.setattr(window, "_load_settings", lambda: {"theme": "dark"})
    monkeypatch.setattr(
        Path,
        "write_text",
        Mock(side_effect=OSError("disk")),
    )
    window._save_autostart(True)
    critical.call_count >= 2


def test_export_statistics_cancel_success_error(window, monkeypatch, tmp_path):
    monkeypatch.setattr(
        dashboard.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: ("", ""),
    )
    window._export_statistics()

    target = tmp_path / "x.csv"
    monkeypatch.setattr(
        dashboard.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(target), "CSV"),
    )
    info = Mock()
    monkeypatch.setattr(dashboard.QMessageBox, "information", info)
    window._export_statistics()
    assert target.exists()
    info.assert_called_once()

    monkeypatch.setattr(
        window.history,
        "export_csv",
        Mock(side_effect=OSError("disk")),
    )
    critical = Mock()
    monkeypatch.setattr(dashboard.QMessageBox, "critical", critical)
    window._export_statistics()
    critical.assert_called_once()


def test_refresh_llm_models_all_states(window, stores):
    _, _, _, _, _, settings, ollama = stores
    window._refresh_llm_models()
    assert window.llm_model_combo.count() == 1
    assert settings.model == "qwen3.8:27b"

    ollama.models = []
    ollama.available = True
    window._refresh_llm_models()
    assert "нет установленных" in window.llm_status.text()

    ollama.available = False
    window._refresh_llm_models()
    assert "не запущена" in window.llm_status.text()


def test_model_changed_callback_and_empty(window, stores):
    _, _, _, _, _, settings, _ = stores
    callback = Mock(side_effect=RuntimeError("callback"))
    window._on_model_change = callback
    window._model_changed("")
    window._model_changed(" model ")
    assert settings.model == "model"
    callback.assert_called_once_with("model")


def test_toggle_ai_cpu_warning_cancel(window, stores, monkeypatch):
    monkeypatch.setattr(dashboard, "has_cuda_gpu", lambda: False)

    class Warning:
        def __init__(self, *args):
            pass
        def exec(self):
            return QDialog.Rejected

    monkeypatch.setattr(dashboard, "AIWarningDialog", Warning)
    window._set_ai_switch(True)
    window._toggle_ai_mode(True)
    assert window.mode == "instant"


def test_toggle_ai_unavailable_and_no_models(window, stores, monkeypatch):
    _, _, _, _, _, settings, ollama = stores
    monkeypatch.setattr(dashboard, "has_cuda_gpu", lambda: True)

    class Info:
        def __init__(self, *args):
            pass
        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(dashboard, "AIUnavailableDialog", Info)

    ollama.available = False
    window._toggle_ai_mode(True)
    assert window.mode == "instant"

    ollama.available = True
    ollama.models = []
    window._toggle_ai_mode(True)
    assert window.mode == "instant"


def test_toggle_ai_success_and_invalid_model(window, stores, monkeypatch):
    _, _, _, _, _, settings, ollama = stores
    monkeypatch.setattr(dashboard, "has_cuda_gpu", lambda: True)

    class Loading:
        def __init__(self, *args):
            pass
        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(dashboard, "AIModelLoadingDialog", Loading)
    settings.model = "missing"
    callback = Mock(side_effect=RuntimeError("callback"))
    window._on_mode_change = callback

    window._toggle_ai_mode(True)
    assert window.mode == "ai"
    assert settings.model == "qwen3.8:27b"
    assert settings.ai is True
    callback.assert_called_with("ai")


def test_toggle_ai_loading_rejected(window, stores, monkeypatch):
    monkeypatch.setattr(dashboard, "has_cuda_gpu", lambda: True)

    class Loading:
        def __init__(self, *args):
            pass
        def exec(self):
            return QDialog.Rejected

    monkeypatch.setattr(dashboard, "AIModelLoadingDialog", Loading)
    window._toggle_ai_mode(True)
    assert window.mode == "instant"


def test_toggle_ai_off_and_disable_unload_paths(window, stores, monkeypatch):
    _, _, _, _, _, settings, ollama = stores
    callback = Mock(side_effect=RuntimeError("callback"))
    window._on_mode_change = callback
    settings.model = "qwen3.8:27b"

    window.mode = "ai"
    window._toggle_ai_mode(False)
    assert window.mode == "instant"
    assert ("unload", "qwen3.8:27b") in ollama.calls

    ollama.unload_model = Mock(return_value=False)
    window._disable_ai_mode()
    assert window.mode == "instant"

    ollama.unload_model = Mock(side_effect=RuntimeError("boom"))
    window._disable_ai_mode()
    assert window.mode == "instant"


def test_mode_label_and_ai_switch(window):
    window.mode_value_label.setText("x")
    window.mode = "ai"
    window._update_mode_label()
    assert window.mode_value_label.text() == "AI"
    window.mode = "instant"
    window._update_mode_label()
    assert window.mode_value_label.text() == "Instant"

    window._set_ai_switch(True)
    assert window.ai_switch.isChecked()
    assert window.ai_switch.text() == "Вкл."
    window._set_ai_switch(False)
    assert not window.ai_switch.isChecked()


def test_autostart_switch(window):
    window._set_autostart_switch(True)
    assert window.autostart_switch.text() == "Вкл."
    window._set_autostart_switch(False)
    assert window.autostart_switch.text() == "Выкл."


def test_close_event_hide_and_accept(window, qapp):
    from PySide6.QtGui import QCloseEvent

    event = QCloseEvent()
    window.allow_close = False
    window.closeEvent(event)
    assert event.isAccepted() is False

    event2 = QCloseEvent()
    window.allow_close = True
    window.closeEvent(event2)
    assert event2.isAccepted() is True


def test_make_icon_and_asset_path(window, monkeypatch, tmp_path):
    expected = Path(dashboard.__file__).resolve().parents[2] / "x"
    assert window._asset_path("x") == expected
    icon = window._make_icon()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()

    monkeypatch.setattr(dashboard.sys, "frozen", True, raising=False)
    monkeypatch.setattr(dashboard.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert window._asset_path("assets/x") == tmp_path / "assets/x"


def test_nav_button_and_card_helpers(window):
    button = window._nav_button("x", "X", "Test")
    assert button.isCheckable()
    card = window._card()
    assert card.objectName() == "Card"


def test_simple_help_pages(window):
    page = window._simple_page("Title", "Description", "Action")
    assert page is not None
    help_page = window._help_page()
    assert help_page is not None


def test_style_blocked_dialog(window, monkeypatch):
    calls = []
    class Info:
        def __init__(self, *args):
            pass
        def exec(self):
            calls.append(True)
            return QDialog.Accepted
    monkeypatch.setattr(dashboard, "AIUnavailableDialog", Info)
    window.mode = "instant"
    window._style_blocked_dialog()
    assert calls


def test_refresh_style_without_list(window):
    old = window.style_list
    del window.style_list
    window._refresh_styles()
    window.style_list = old


def test_refresh_dictionary_without_list(window):
    old = window.dictionary_list
    del window.dictionary_list
    window._refresh_dictionary()
    window.dictionary_list = old


def test_refresh_snippets_without_list(window):
    old = window.snippet_list
    del window.snippet_list
    window._refresh_snippets()
    window.snippet_list = old


def test_filter_helpers_without_widgets(window):
    old = window.history_search
    del window.history_search
    window._apply_filter_from_search()
    window.history_search = old


def test_styles_create_blocked(window, monkeypatch):
    called = []
    monkeypatch.setattr(window, "_style_blocked_dialog", lambda: called.append(True))
    window.mode = "instant"
    window._create_style()
    assert called


def test_select_style_blocked(window, monkeypatch):
    called = []
    monkeypatch.setattr(window, "_style_blocked_dialog", lambda: called.append(True))
    window.mode = "instant"
    window._select_style("builtin")
    assert called


def test_apply_windows_titlebar_nonwindows(window, monkeypatch):
    monkeypatch.setattr(dashboard.sys, "platform", "linux")
    window._apply_windows_titlebar()


def test_palette_system_fallback(window, monkeypatch):
    monkeypatch.setattr(dashboard.sys, "platform", "linux")
    assert window._palette_for_theme("system") is dashboard.LIGHT


def test_palette_system_winreg_success_and_failure(window, monkeypatch):
    class FakeKey:
        pass

    class FakeWinreg:
        HKEY_CURRENT_USER = object()
        def OpenKey(self, *args):
            return FakeKey()
        def QueryValueEx(self, key, name):
            return (0, None)

    monkeypatch.setattr(dashboard.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", FakeWinreg())
    assert window._palette_for_theme("system") is dashboard.DARK

    class BrokenWinreg(FakeWinreg):
        def OpenKey(self, *args):
            raise OSError("denied")

    monkeypatch.setitem(sys.modules, "winreg", BrokenWinreg())
    assert window._palette_for_theme("system") is dashboard.LIGHT


def test_stylesheet_contains_palette(window):
    css = window._stylesheet(dashboard.DARK)
    assert "#111113" in css
    assert "#6C63FF" in css
    assert "QPushButton#NavButton" in css


def test_dashboard_remaining_coverage_paths(qapp, monkeypatch, tmp_path):
    """Cover the remaining small/error branches of dashboard.py."""

    # ------------------------------------------------------------------
    # HistoryStore: identity update branch.
    # ------------------------------------------------------------------
    store = dashboard.HistoryStore()
    store.path = tmp_path / "history.json"

    entry = {"timestamp": "2026-01-01T00:00:00", "text": "old"}

    monkeypatch.setattr(store, "load", lambda: [entry])
    store.update(entry, "new")

    assert entry["text"] == "new"
    assert store.path.exists()

    # ------------------------------------------------------------------
    # SaydoDesktopUI.start(): exercise the complete startup path
    # without entering a real Qt event loop.
    # ------------------------------------------------------------------
    class FakeSignal:
        def connect(self, callback):
            self.callback = callback

    class FakeApp:
        @staticmethod
        def instance():
            return None

        def __init__(self, argv):
            self.argv = argv
            self.application_name = None
            self.organization_name = None
            self.exec_called = False

        def setApplicationName(self, value):
            self.application_name = value

        def setOrganizationName(self, value):
            self.organization_name = value

        def exec(self):
            self.exec_called = True
            return 0

    class FakeWindow:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def show(self):
            pass

        def raise_(self):
            pass

        def activateWindow(self):
            pass

    class FakeTimer:
        def __init__(self):
            self.timeout = FakeSignal()
            self.started = False
            self.interval = None

        def start(self, interval):
            self.interval = interval
            self.started = True

    fake_app_holder = {}

    def fake_app_factory(argv):
        app = FakeApp(argv)
        fake_app_holder["app"] = app
        return app

    monkeypatch.setattr(
        dashboard.QApplication,
        "instance",
        staticmethod(lambda: None),
    )
    monkeypatch.setattr(dashboard, "QApplication", type(
        "FakeQApplication",
        (),
        {
            "instance": staticmethod(lambda: None),
            "__new__": staticmethod(lambda cls, argv: fake_app_factory(argv)),
        },
    ))

    # The fake QApplication class above is awkward for normal construction,
    # so provide a callable replacement instead.
    real_qapplication = QApplication
    monkeypatch.setattr(dashboard, "QApplication", FakeApp)
    real_main_window = dashboard.MainWindow
    monkeypatch.setattr(dashboard, "MainWindow", FakeWindow)
    monkeypatch.setattr(dashboard, "QTimer", FakeTimer)

    ui = dashboard.SaydoDesktopUI(
        hotkey="right ctrl",
        mode="ai",
        on_mode_change="mode-callback",
        on_model_change="model-callback",
    )
    ui.start()

    assert ui._thread is not None
    assert isinstance(ui._app, FakeApp)
    assert ui._app.application_name == dashboard.APP_NAME
    assert ui._app.organization_name == dashboard.APP_NAME
    assert ui._started.is_set()
    assert ui._window.kwargs["hotkey"] == "right ctrl"
    assert ui._window.kwargs["mode"] == "ai"
    assert ui._window.kwargs["on_mode_change"] == "mode-callback"
    assert ui._window.kwargs["on_model_change"] == "model-callback"
    assert ui._app.exec_called

    # ------------------------------------------------------------------
    # AIModelLoadingDialog.showEvent(): parent positioning + worker start.
    # ------------------------------------------------------------------
    from PySide6.QtWidgets import QWidget

    class FakeThread:
        instances = []

        def __init__(self, target=None, daemon=None):
            self.target = target
            self.daemon = daemon
            self.started = False
            FakeThread.instances.append(self)

        def start(self):
            self.started = True

    class FakeLoadingTimer:
        def __init__(self, *args, **kwargs):
            self.timeout = FakeSignal()
            self.started = False

        def start(self, interval):
            self.started = True

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(dashboard.threading, "Thread", FakeThread)
    monkeypatch.setattr(dashboard, "QTimer", FakeLoadingTimer)

    parent = QWidget()
    parent.resize(800, 600)

    ollama = Mock()
    ollama.load_model.return_value = (True, "")

    dialog = dashboard.AIModelLoadingDialog(
        parent,
        dashboard.LIGHT,
        "test-model",
        ollama,
    )

    dialog.showEvent(QShowEvent())

    assert len(FakeThread.instances) == 1
    assert FakeThread.instances[0].started
    assert dialog._worker is FakeThread.instances[0]

    dialog._timer.stop()
    dialog.close()
    parent.close()

    # ------------------------------------------------------------------
    # AIModelLoadingDialog._poll(): completed-success path.
    # ------------------------------------------------------------------
    ollama2 = Mock()
    dialog2 = dashboard.AIModelLoadingDialog(
        None,
        dashboard.LIGHT,
        "test-model",
        ollama2,
    )

    stopped = []
    completed = []

    dialog2._timer.stop = lambda: stopped.append(True)
    dialog2.done = lambda result: completed.append(result)
    dialog2._result.update(done=True, ok=True)

    dialog2._poll()

    assert stopped == [True]
    assert completed == [QDialog.Accepted]

    dialog2.close()

    # ------------------------------------------------------------------
    # MainWindow.__init__(): persisted autostart enabled, manager fails.
    # ------------------------------------------------------------------
    class FailingAutostart:
        def is_enabled(self):
            return False

        def enable(self):
            raise OSError("autostart failure")

    monkeypatch.setattr(dashboard, "AutostartManager", FailingAutostart)
    monkeypatch.setattr(real_main_window, "_build", lambda self: None)
    real_load_theme = real_main_window._load_theme
    monkeypatch.setattr(real_main_window, "_load_theme", lambda self: None)
    monkeypatch.setattr(real_main_window, "_apply_windows_titlebar", lambda self: None)
    monkeypatch.setattr(real_main_window, "refresh", lambda self: None)
    monkeypatch.setattr(
        real_main_window,
        "_make_icon",
        lambda self: dashboard.QIcon(),
    )
    monkeypatch.setattr(
        real_main_window,
        "_load_settings",
        lambda self: {"autostart": True},
    )

    autostart_values = []
    monkeypatch.setattr(
        real_main_window,
        "_set_autostart_switch",
        lambda self, enabled: autostart_values.append(enabled),
    )

    test_window = real_main_window(
        Mock(),
        "right ctrl",
        "instant",
    )

    assert autostart_values == [False]
    test_window.close()

    # ------------------------------------------------------------------
    # Missing icon branch.
    # ------------------------------------------------------------------
    real_window = real_main_window.__new__(real_main_window)
    monkeypatch.setattr(
        real_window,
        "_asset_path",
        lambda relative: tmp_path / "missing.png",
    )

    icon = real_window._make_icon()
    assert icon.isNull()

    # ------------------------------------------------------------------
    # Windows titlebar exception branch.
    # ------------------------------------------------------------------
    import builtins

    original_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name == "ctypes":
            raise ImportError("ctypes intentionally unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)

    monkeypatch.setattr(dashboard.sys, "platform", "win32")
    real_main_window._apply_windows_titlebar(real_window)

    # ------------------------------------------------------------------
    # Autostart disable branch.
    # ------------------------------------------------------------------
    class DisableManager:
        def __init__(self):
            self.disabled = False

        def disable(self):
            self.disabled = True

        def enable(self):
            pass

    manager = DisableManager()
    real_window._autostart = manager
    saved = []
    switches = []

    monkeypatch.setattr(
        real_window,
        "_save_autostart",
        lambda enabled: saved.append(enabled),
    )
    monkeypatch.setattr(
        real_window,
        "_set_autostart_switch",
        lambda enabled: switches.append(enabled),
    )

    real_window._toggle_autostart(False)

    assert manager.disabled
    assert saved == [False]
    assert switches == [False]

    # ------------------------------------------------------------------
    # _load_settings(): valid dictionary branch.
    # ------------------------------------------------------------------
    settings_path = tmp_path / "settings-valid.json"
    settings_path.write_text(
        '{"theme": "dark", "autostart": true}',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        dashboard,
        "data_path",
        lambda name: settings_path,
    )

    loaded_settings = real_window._load_settings()
    assert isinstance(loaded_settings, dict)
    assert loaded_settings == {"autostart": True}

    # ------------------------------------------------------------------
    # _refresh_llm_models(): no combo widget branch.
    # ------------------------------------------------------------------
    if hasattr(real_window, "llm_model_combo"):
        del real_window.llm_model_combo

    real_window._refresh_llm_models()

    # ------------------------------------------------------------------
    # Copy feedback restore callbacks:
    # both editable and non-editable history cards.
    # ------------------------------------------------------------------
    callbacks = []

    class SingleShotTimer:
        @staticmethod
        def singleShot(delay, callback):
            callbacks.append(callback)

    monkeypatch.setattr(dashboard, "QTimer", SingleShotTimer)
    original_copy = real_window._copy
    monkeypatch.setattr(real_window, "_copy", lambda text: None)

    editable_card = real_window._history_card(
        {"timestamp": "2026-01-01T12:00:00", "text": "hello"},
        editable=True,
    )
    editable_card.show()

    buttons = editable_card.findChildren(QPushButton)
    copy_button = buttons[0]

    copy_button.click()
    first_callback = callbacks[-1]

    # Generate a new token so the first callback takes the guarded return path.
    copy_button.click()
    second_callback = callbacks[-1]

    first_callback()
    assert copy_button.text() == "✓"

    second_callback()
    assert copy_button.text() == "⧉"

    noneditable_card = real_window._history_card(
        {"timestamp": "2026-01-01T12:00:00", "text": "hello"},
        editable=False,
    )
    noneditable_card.show()

    copy_button2 = noneditable_card.findChildren(QPushButton)[0]
    copy_button2.click()

    callback2 = callbacks[-1]
    callback2()

    assert copy_button2.text() == "⧉"

    editable_card.close()
    noneditable_card.close()

    # ------------------------------------------------------------------
    # _find_dictionary_candidates(): exercise equal-casefold continue.
    # ------------------------------------------------------------------
    import difflib

    original_sequence_matcher = difflib.SequenceMatcher

    class FakeMatcher:
        def __init__(self, *args, **kwargs):
            pass

        def get_opcodes(self):
            return [("replace", 0, 1, 0, 1)]

    monkeypatch.setattr(difflib, "SequenceMatcher", FakeMatcher)

    real_window._dictionary = Mock()
    real_window._dictionary.corrections.return_value = []

    result = real_window._find_dictionary_candidates(
        "foo",
        "FOO",
    )

    assert result == []

    difflib.SequenceMatcher = original_sequence_matcher

    # ------------------------------------------------------------------
    # Empty dictionary dialog candidates.
    # ------------------------------------------------------------------
    assert real_window._ask_add_dictionary([]) is False

    # ------------------------------------------------------------------
    # Dictionary card: ordinary word branch.
    # ------------------------------------------------------------------
    word_card = real_window._dictionary_card(
        {"type": "word", "word": "Saydo"},
        0,
    )
    assert "Saydo" in [
        label.text()
        for label in word_card.findChildren(QLabel)
    ]
    word_card.close()

    # ------------------------------------------------------------------
    # Dictionary filter without widget.
    # ------------------------------------------------------------------
    if hasattr(real_window, "dictionary_list"):
        del real_window.dictionary_list

    real_window._filter_dictionary("test")

    # ------------------------------------------------------------------
    # Clipboard helper.
    # ------------------------------------------------------------------
    clipboard = Mock()

    class ClipboardApp:
        @staticmethod
        def clipboard():
            return clipboard

    original_qapplication = dashboard.QApplication
    dashboard.QApplication = ClipboardApp
    try:
        real_window._copy = original_copy
        real_window._copy("coverage test")
    finally:
        dashboard.QApplication = original_qapplication

    clipboard.setText.assert_called_once_with("coverage test")

    # ------------------------------------------------------------------
    # Theme loading with a valid settings dict.
    # ------------------------------------------------------------------
    theme_path = tmp_path / "theme.json"
    theme_path.write_text('{"theme": "dark"}', encoding="utf-8")

    monkeypatch.setattr(
        dashboard,
        "data_path",
        lambda name: theme_path,
    )

    applied = []
    monkeypatch.setattr(
        real_window,
        "set_theme",
        lambda theme, persist=False: applied.append((theme, persist)),
    )

    real_window.current_theme = "system"
    real_load_theme(real_window)

    assert applied == [("dark", False)]

    # ------------------------------------------------------------------
    # _save_theme(): malformed existing JSON exercises inner except.
    # ------------------------------------------------------------------
    malformed = tmp_path / "theme-malformed.json"
    malformed.write_text("{not-json", encoding="utf-8")

    monkeypatch.setattr(
        dashboard,
        "data_path",
        lambda name: malformed,
    )

    real_window.current_theme = "light"
    real_window._save_theme()

    saved_theme = json.loads(malformed.read_text(encoding="utf-8"))
    assert saved_theme == {"theme": "light"}

    # ------------------------------------------------------------------
    # _save_theme(): outer write exception.
    # ------------------------------------------------------------------
    class BadPath:
        def exists(self):
            return False

        def write_text(self, *args, **kwargs):
            raise RuntimeError("write failure")

    bad_path = BadPath()

    monkeypatch.setattr(
        dashboard,
        "data_path",
        lambda name: bad_path,
    )

    real_window._save_theme()

