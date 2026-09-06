from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.core.style as style_module
import app.llm.settings as settings_module
from app.core.dictionary_learner import DictionaryLearner
from app.core.style import BUILTIN_STYLES, StyleStore, app_root, data_path
from app.llm.base import LLMProvider
from app.llm.settings import LLMSettingsStore

# =========================
# DictionaryLearner
# =========================

def test_word_tokens_extract_words_and_ignore_punctuation() -> None:
    assert DictionaryLearner._word_tokens(
        "Привет, мир! test-case"
    ) == ["Привет", "мир", "test-case"]


def test_find_corrections_returns_empty_for_empty_original() -> None:
    assert DictionaryLearner.find_corrections("", "привет") == []


def test_find_corrections_returns_empty_for_empty_edited() -> None:
    assert DictionaryLearner.find_corrections("привет", "") == []


def test_find_corrections_ignores_whitespace_and_punctuation_changes() -> None:
    assert DictionaryLearner.find_corrections(
        "Привет, мир",
        "Привет мир!",
    ) == []


def test_find_corrections_detects_one_to_one_replacement() -> None:
    assert DictionaryLearner.find_corrections(
        "Превет мир",
        "Привет мир",
    ) == [("Превет", "Привет")]


def test_find_corrections_is_case_insensitive() -> None:
    assert DictionaryLearner.find_corrections(
        "Привет мир",
        "ПРИВЕТ Мир",
    ) == []


def test_find_corrections_ignores_insertions() -> None:
    assert DictionaryLearner.find_corrections(
        "Превет мир",
        "Привет большой мир",
    ) == []


def test_find_corrections_ignores_deletions() -> None:
    assert DictionaryLearner.find_corrections(
        "Превет большой мир",
        "Привет мир",
    ) == []


def test_find_corrections_detects_multiple_replacements() -> None:
    assert DictionaryLearner.find_corrections(
        "Превет тибе",
        "Привет тебе",
    ) == [
        ("Превет", "Привет"),
        ("тибе", "тебе"),
    ]


def test_find_corrections_deduplicates_same_replacement() -> None:
    assert DictionaryLearner.find_corrections(
        "Превет Превет",
        "Привет Привет",
    ) == [("Превет", "Привет")]


def test_find_corrections_preserves_original_spelling() -> None:
    assert DictionaryLearner.find_corrections(
        "ПРЕВЕТ мир",
        "Привет мир",
    ) == [("ПРЕВЕТ", "Привет")]


# =========================
# LLMSettingsStore
# =========================

def test_llm_settings_default_path_returns_data_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        settings_module.sys,
        "frozen",
        False,
        raising=False,
    )
    monkeypatch.setattr(
        settings_module,
        "__file__",
        str(tmp_path / "app" / "llm" / "settings.py"),
    )

    result = LLMSettingsStore._default_path()

    assert result == tmp_path / "data" / "settings.json"
    assert result.parent.is_dir()


def test_llm_settings_default_path_uses_executable_when_frozen(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        settings_module.sys,
        "frozen",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        settings_module.sys,
        "executable",
        str(tmp_path / "Saydo.exe"),
    )

    result = LLMSettingsStore._default_path()

    assert result == tmp_path / "data" / "settings.json"
    assert result.parent.is_dir()


def test_llm_settings_load_returns_saved_data(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "llm_model": "test-model",
                "ai_mode": True,
            }
        ),
        encoding="utf-8",
    )

    store = LLMSettingsStore(path)

    assert store.load() == {
        "llm_model": "test-model",
        "ai_mode": True,
    }


def test_llm_settings_load_returns_empty_for_invalid_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{invalid", encoding="utf-8")

    store = LLMSettingsStore(path)

    assert store.load() == {}


def test_llm_settings_load_returns_empty_for_non_dict_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text('["invalid"]', encoding="utf-8")

    store = LLMSettingsStore(path)

    assert store.load() == {}


def test_get_model_returns_saved_model(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"llm_model": "qwen-test"}),
        encoding="utf-8",
    )

    store = LLMSettingsStore(path)

    assert store.get_model() == "qwen-test"


def test_get_model_returns_default_for_blank_value(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"llm_model": "   "}),
        encoding="utf-8",
    )

    store = LLMSettingsStore(path)

    assert store.get_model("fallback") == "fallback"


def test_get_model_returns_default_for_non_string_value(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"llm_model": 123}),
        encoding="utf-8",
    )

    store = LLMSettingsStore(path)

    assert store.get_model("fallback") == "fallback"


def test_get_ai_mode_returns_saved_boolean(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"ai_mode": True}),
        encoding="utf-8",
    )

    store = LLMSettingsStore(path)

    assert store.get_ai_mode() is True


def test_get_ai_mode_uses_default_when_setting_is_missing(
    tmp_path: Path,
) -> None:
    store = LLMSettingsStore(tmp_path / "settings.json")

    assert store.get_ai_mode(True) is True
    assert store.get_ai_mode(False) is False


def test_get_ai_mode_converts_value_to_bool(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"ai_mode": 0}),
        encoding="utf-8",
    )

    store = LLMSettingsStore(path)

    assert store.get_ai_mode(True) is False


def test_save_model_persists_model(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = LLMSettingsStore(path)

    store.save_model("qwen-test")

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "llm_model": "qwen-test",
    }


def test_save_ai_mode_persists_boolean(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = LLMSettingsStore(path)

    store.save_ai_mode(True)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "ai_mode": True,
    }


def test_save_methods_preserve_existing_settings(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "llm_model": "old-model",
                "ai_mode": False,
                "other": "value",
            }
        ),
        encoding="utf-8",
    )

    store = LLMSettingsStore(path)

    store.save_model("new-model")
    store.save_ai_mode(True)

    assert store.load() == {
        "llm_model": "new-model",
        "ai_mode": True,
        "other": "value",
    }


def test_write_swallows_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.json"
    store = LLMSettingsStore(path)

    original_write_text = Path.write_text

    def fail_write(
        self: Path,
        *args: object,
        **kwargs: object,
    ) -> None:
        if self == path:
            raise OSError("write failed")
        original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_write)

    store._write({"test": "value"})


# =========================
# LLMProvider
# =========================

def test_llm_provider_process_is_abstract() -> None:
    with pytest.raises(TypeError):
        LLMProvider()


# =========================
# StyleStore
# =========================

def make_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> StyleStore:
    monkeypatch.setattr(
        style_module,
        "data_path",
        lambda name: tmp_path / name,
    )
    return StyleStore()


def test_app_root_returns_project_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        style_module.sys,
        "frozen",
        False,
        raising=False,
    )

    assert app_root() == Path(
        style_module.__file__
    ).resolve().parents[2]


def test_app_root_uses_executable_directory_when_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        style_module.sys,
        "frozen",
        True,
        raising=False,
    )

    assert app_root() == Path(
        style_module.sys.executable
    ).resolve().parent


def test_data_path_creates_data_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        style_module,
        "app_root",
        lambda: tmp_path,
    )

    result = data_path("test.json")

    assert result == tmp_path / "data" / "test.json"
    assert result.parent.is_dir()


def test_store_creates_default_styles_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    assert store.path.exists()

    data = json.loads(
        store.path.read_text(encoding="utf-8")
    )

    assert data["selected"] == "normal"
    assert data["styles"] == BUILTIN_STYLES


def test_store_repairs_invalid_styles_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "styles.json"
    path.write_text("{invalid", encoding="utf-8")

    store = make_store(tmp_path, monkeypatch)

    assert store.load() == BUILTIN_STYLES
    assert store.get_selected_id() == "normal"


def test_store_repairs_non_dict_styles_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "styles.json"
    path.write_text(
        json.dumps(["invalid"]),
        encoding="utf-8",
    )

    make_store(tmp_path, monkeypatch)

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert data["selected"] == "normal"
    assert data["styles"] == BUILTIN_STYLES


def test_store_repairs_dict_without_styles_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "styles.json"
    path.write_text(
        json.dumps({"selected": "normal"}),
        encoding="utf-8",
    )

    make_store(tmp_path, monkeypatch)

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert data["styles"] == BUILTIN_STYLES


def test_load_returns_saved_styles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    custom = {
        "id": "custom",
        "name": "Custom",
        "description": "Description",
        "prompt": "Prompt",
        "builtin": False,
    }

    store.path.write_text(
        json.dumps(
            {
                "selected": "custom",
                "styles": [custom],
            }
        ),
        encoding="utf-8",
    )

    assert store.load() == [custom]


def test_load_falls_back_to_builtin_when_styles_are_not_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    store.path.write_text(
        json.dumps(
            {
                "selected": "normal",
                "styles": {},
            }
        ),
        encoding="utf-8",
    )

    assert store.load() == BUILTIN_STYLES


def test_load_falls_back_to_builtin_on_invalid_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    store.path.write_text("{invalid", encoding="utf-8")

    assert store.load() == BUILTIN_STYLES


def test_get_selected_id_returns_saved_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    store.path.write_text(
        json.dumps(
            {
                "selected": "business",
                "styles": BUILTIN_STYLES,
            }
        ),
        encoding="utf-8",
    )

    assert store.get_selected_id() == "business"


def test_get_selected_id_defaults_to_normal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    store.path.write_text(
        json.dumps({"styles": BUILTIN_STYLES}),
        encoding="utf-8",
    )

    assert store.get_selected_id() == "normal"


def test_get_selected_id_falls_back_on_invalid_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    store.path.write_text("{invalid", encoding="utf-8")

    assert store.get_selected_id() == "normal"


def test_get_selected_returns_selected_style(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    store.select("business")

    assert store.get_selected()["id"] == "business"


def test_get_selected_falls_back_to_normal_for_unknown_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    store.path.write_text(
        json.dumps(
            {
                "selected": "does-not-exist",
                "styles": BUILTIN_STYLES,
            }
        ),
        encoding="utf-8",
    )

    assert store.get_selected() == BUILTIN_STYLES[0]


def test_select_existing_style(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    assert store.select("business") is True
    assert store.get_selected_id() == "business"


def test_select_unknown_style_returns_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    assert store.select("unknown") is False
    assert store.get_selected_id() == "normal"


def test_add_requires_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        store.add("   ", "description", "prompt")


def test_add_requires_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        store.add("Custom", "description", "   ")


def test_add_creates_custom_style_and_selects_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    result = store.add(
        "My Style",
        "  My description  ",
        "  My prompt  ",
    )

    assert result == {
        "id": "my-style",
        "name": "My Style",
        "description": "My description",
        "prompt": "My prompt",
        "builtin": False,
    }
    assert store.get_selected_id() == "my-style"


def test_add_uses_default_description(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    style = store.add("Custom", "   ", "prompt")

    assert style["description"] == "Пользовательский стиль."


def test_add_generates_fallback_id_for_non_alphanumeric_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    style = store.add("!!!", "", "prompt")

    assert style["id"] == "style"


def test_add_resolves_id_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    first = store.add("My Style", "", "first")
    second = store.add("My Style", "", "second")
    third = store.add("My Style", "", "third")

    assert first["id"] == "my-style"
    assert second["id"] == "my-style-2"
    assert third["id"] == "my-style-3"


def test_delete_custom_style(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    custom = store.add("Custom", "", "prompt")

    assert store.delete(custom["id"]) is True
    assert store.get_selected_id() == "normal"


def test_delete_non_selected_custom_style_keeps_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    first = store.add("First", "", "first")
    second = store.add("Second", "", "second")

    store.select(first["id"])

    assert store.delete(second["id"]) is True
    assert store.get_selected_id() == first["id"]


def test_delete_builtin_style_returns_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    assert store.delete("normal") is False
    assert store.get_selected_id() == "normal"


def test_delete_unknown_style_returns_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    assert store.delete("unknown") is False
