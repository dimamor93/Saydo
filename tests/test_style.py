from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.core.style as style_module
from app.core.style import BUILTIN_STYLES, StyleStore, app_root, data_path


def make_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StyleStore:
    monkeypatch.setattr(
        style_module,
        "data_path",
        lambda name: tmp_path / name,
    )
    return StyleStore()


def test_app_root_returns_project_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(style_module.sys, "frozen", False, raising=False)

    result = app_root()

    assert result == Path(style_module.__file__).resolve().parents[2]


def test_app_root_uses_executable_directory_when_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(style_module.sys, "frozen", True, raising=False)

    result = app_root()

    assert result == Path(style_module.sys.executable).resolve().parent


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
    assert (tmp_path / "data").is_dir()


def test_store_creates_default_styles_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    assert store.path.exists()

    data = json.loads(store.path.read_text(encoding="utf-8"))

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

    data = json.loads(path.read_text(encoding="utf-8"))

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

    data = json.loads(path.read_text(encoding="utf-8"))

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
        json.dumps({"selected": "normal", "styles": {}}),
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

    selected = store.get_selected()

    assert selected["id"] == "business"


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

    style = store.add(
        "My Style",
        "  My description  ",
        "  My prompt  ",
    )

    assert style == {
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
    assert store.get_selected()["id"] == "normal"


def test_delete_non_selected_custom_style_keeps_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store(tmp_path, monkeypatch)

    first = store.add("First", "", "first")
    second = store.add("Second", "", "second")

    assert store.get_selected_id() == second["id"]

    assert store.select(first["id"]) is True
    assert store.delete(second["id"]) is True

    assert store.get_selected_id() == first["id"]
    assert store.get_selected()["id"] == first["id"]


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
