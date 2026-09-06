from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.core.dictionary as dictionary_module
import app.core.snippets as snippets_module
from app.core.dictionary import UserDictionary
from app.core.snippets import SnippetStore

# =========================
# UserDictionary
# =========================

def test_dictionary_load_returns_empty_for_missing_file(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")

    assert dictionary.load() == []


def test_dictionary_save_and_load(tmp_path: Path) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")
    entries = [
        {"word": "Saydo", "type": "word"},
        {
            "type": "correction",
            "source": "превед",
            "replacement": "привет",
        },
    ]

    dictionary.save(entries)

    assert dictionary.load() == entries


def test_dictionary_load_returns_empty_for_invalid_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "dictionary.json"
    path.write_text("{invalid", encoding="utf-8")

    dictionary = UserDictionary(path)

    assert dictionary.load() == []


def test_dictionary_load_returns_empty_for_non_list_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "dictionary.json"
    path.write_text('{"word": "Saydo"}', encoding="utf-8")

    dictionary = UserDictionary(path)

    assert dictionary.load() == []


def test_dictionary_add_word_strips_and_inserts_at_beginning(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")
    dictionary.save([{"word": "existing", "type": "word"}])

    dictionary.add_word("  Saydo  ")

    assert dictionary.words() == ["Saydo", "existing"]


def test_dictionary_add_word_ignores_empty_word(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")

    dictionary.add_word("   ")

    assert dictionary.load() == []


def test_dictionary_add_word_ignores_case_insensitive_duplicate(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")
    dictionary.add_word("Saydo")

    dictionary.add_word("sayDO")

    assert dictionary.words() == ["Saydo"]


def test_dictionary_same_word_as_correction_is_allowed(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")
    dictionary.save(
        [
            {
                "type": "correction",
                "source": "Saydo",
                "replacement": "Saydo App",
            }
        ]
    )

    dictionary.add_word("saydo")

    assert dictionary.words() == ["saydo"]


def test_dictionary_add_correction_inserts_new_entry(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")

    dictionary.add_correction("  приветик  ", "  привет  ")

    assert dictionary.corrections() == [("приветик", "привет")]


def test_dictionary_add_correction_ignores_empty_values(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")

    dictionary.add_correction("", "replacement")
    dictionary.add_correction("source", "")
    dictionary.add_correction("   ", "   ")

    assert dictionary.load() == []


def test_dictionary_add_correction_ignores_identical_values(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")

    dictionary.add_correction("Saydo", "saydo")

    assert dictionary.load() == []


def test_dictionary_add_correction_updates_existing_source(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")
    dictionary.add_correction("превед", "привет")

    dictionary.add_correction("ПРЕВЕД", "здравствуйте")

    assert dictionary.corrections() == [
        ("превед", "здравствуйте"),
    ]


def test_dictionary_delete_removes_valid_index(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")
    dictionary.save(
        [
            {"word": "first", "type": "word"},
            {"word": "second", "type": "word"},
        ]
    )

    dictionary.delete(0)

    assert dictionary.words() == ["second"]


def test_dictionary_delete_ignores_invalid_index(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")
    dictionary.save([{"word": "only", "type": "word"}])

    dictionary.delete(-1)
    dictionary.delete(1)

    assert dictionary.words() == ["only"]


def test_dictionary_corrections_filters_invalid_entries(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")
    dictionary.save(
        [
            {
                "type": "correction",
                "source": "one",
                "replacement": "two",
            },
            {
                "type": "correction",
                "source": "",
                "replacement": "three",
            },
            {
                "type": "correction",
                "source": "four",
                "replacement": "",
            },
            {"type": "word", "word": "word"},
        ]
    )

    assert dictionary.corrections() == [("one", "two")]


def test_dictionary_words_filters_invalid_entries(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")
    dictionary.save(
        [
            {"type": "word", "word": "Saydo"},
            {"type": "word", "word": ""},
            {"type": "correction", "source": "a", "replacement": "b"},
        ]
    )

    assert dictionary.words() == ["Saydo"]


def test_dictionary_apply_is_case_insensitive_and_preserves_boundaries(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")
    dictionary.add_correction("превед", "привет")

    result = dictionary.apply(
        "ПРЕВЕД, но не слово-преведенный и снова превед."
    )

    assert result == (
        "привет, но не слово-преведенный и снова привет."
    )


def test_dictionary_apply_prefers_longest_correction(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")
    dictionary.save(
        [
            {
                "type": "correction",
                "source": "машина",
                "replacement": "авто",
            },
            {
                "type": "correction",
                "source": "красная машина",
                "replacement": "красный автомобиль",
            },
        ]
    )

    result = dictionary.apply("красная машина")

    assert result == "красный автомобиль"


def test_dictionary_apply_returns_empty_text_unchanged(
    tmp_path: Path,
) -> None:
    dictionary = UserDictionary(tmp_path / "dictionary.json")

    assert dictionary.apply("") == ""


# =========================
# SnippetStore
# =========================

def test_snippets_load_returns_empty_for_missing_file(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")

    assert snippets.load() == []


def test_snippets_save_and_load_normalizes_entries(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")
    snippets.save(
        [
            {
                "name": " Test ",
                "trigger": "  ;sig  ",
                "text": "Hello",
            }
        ]
    )

    assert snippets.load() == [
        {
            "name": "Test",
            "trigger": ";sig",
            "text": "Hello",
        }
    ]


def test_snippets_load_filters_invalid_entries(
    tmp_path: Path,
) -> None:
    path = tmp_path / "snippets.json"
    path.write_text(
        json.dumps(
            [
                {"name": "valid", "trigger": ";v", "text": "value"},
                {"name": "no trigger", "trigger": "", "text": "value"},
                {"name": "no text", "trigger": ";x", "text": ""},
                "not a dict",
            ]
        ),
        encoding="utf-8",
    )

    snippets = SnippetStore(path)

    assert snippets.load() == [
        {
            "name": "valid",
            "trigger": ";v",
            "text": "value",
        }
    ]


def test_snippets_load_handles_invalid_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "snippets.json"
    path.write_text("{invalid", encoding="utf-8")

    snippets = SnippetStore(path)

    assert snippets.load() == []


def test_snippets_load_handles_non_list_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "snippets.json"
    path.write_text('{"trigger": ";x"}', encoding="utf-8")

    snippets = SnippetStore(path)

    assert snippets.load() == []


def test_snippets_add_strips_values_and_uses_trigger_as_default_name(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")

    snippets.add("   ", "  ;mail  ", "  test@example.com  ")

    assert snippets.load() == [
        {
            "name": ";mail",
            "trigger": ";mail",
            "text": "test@example.com",
        }
    ]


def test_snippets_add_requires_trigger_and_text(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")

    with pytest.raises(ValueError, match="trigger and text are required"):
        snippets.add("name", "", "text")

    with pytest.raises(ValueError, match="trigger and text are required"):
        snippets.add("name", ";trigger", "")


def test_snippets_update_replaces_existing_entry(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")
    snippets.add("Old", ";old", "old text")

    snippets.update(0, "New", ";new", "new text")

    assert snippets.load() == [
        {
            "name": "New",
            "trigger": ";new",
            "text": "new text",
        }
    ]


def test_snippets_update_uses_trigger_as_default_name(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")
    snippets.add("Old", ";old", "old text")

    snippets.update(0, "", ";new", "new text")

    assert snippets.find(";new") == {
        "name": ";new",
        "trigger": ";new",
        "text": "new text",
    }


def test_snippets_update_rejects_invalid_index(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")

    with pytest.raises(IndexError, match="out of range"):
        snippets.update(0, "name", ";trigger", "text")


def test_snippets_update_requires_trigger_and_text(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")
    snippets.add("name", ";trigger", "text")

    with pytest.raises(ValueError, match="trigger and text are required"):
        snippets.update(0, "name", "", "text")

    with pytest.raises(ValueError, match="trigger and text are required"):
        snippets.update(0, "name", ";trigger", "")


def test_snippets_delete_removes_valid_index(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")
    snippets.add("first", ";one", "1")
    snippets.add("second", ";two", "2")

    snippets.delete(0)

    assert snippets.load() == [
        {
            "name": "second",
            "trigger": ";two",
            "text": "2",
        }
    ]


def test_snippets_delete_ignores_invalid_index(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")
    snippets.add("only", ";one", "1")

    snippets.delete(-1)
    snippets.delete(1)

    assert len(snippets.load()) == 1


def test_snippets_find_is_case_insensitive(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")
    snippets.add("Mail", ";mail", "test@example.com")

    assert snippets.find("  ;MAIL ") == {
        "name": "Mail",
        "trigger": ";mail",
        "text": "test@example.com",
    }


def test_snippets_find_returns_none_for_missing_or_empty_trigger(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")
    snippets.add("Mail", ";mail", "test@example.com")

    assert snippets.find("") is None
    assert snippets.find("   ") is None
    assert snippets.find(";unknown") is None


def test_snippets_apply_expands_trigger_case_insensitively(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")
    snippets.add("Mail", ";mail", "test@example.com")

    assert snippets.apply("Напиши ;MAIL") == (
        "Напиши test@example.com"
    )


def test_snippets_apply_respects_word_boundaries(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")
    snippets.add("Mail", ";mail", "test@example.com")

    assert snippets.apply(" ;mail ;mailbox ") == (
        " test@example.com ;mailbox "
    )


def test_snippets_apply_prefers_longest_trigger(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")
    snippets.add("Short", ";sig", "short")
    snippets.add("Long", ";signature", "long")

    assert snippets.apply(";signature") == "long"


def test_snippets_apply_leaves_text_without_triggers_unchanged(
    tmp_path: Path,
) -> None:
    snippets = SnippetStore(tmp_path / "snippets.json")

    assert snippets.apply("ordinary text") == "ordinary text"


def test_dictionary_default_path_uses_executable_directory_when_frozen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "Saydo.exe"

    monkeypatch.setattr(
        dictionary_module.sys,
        "frozen",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        dictionary_module.sys,
        "executable",
        str(executable),
    )

    result = UserDictionary._default_path()

    assert result == tmp_path / "data" / "dictionary.json"


def test_snippets_default_path_uses_executable_directory_when_frozen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "Saydo.exe"

    monkeypatch.setattr(
        snippets_module.sys,
        "frozen",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        snippets_module.sys,
        "executable",
        str(executable),
    )

    result = SnippetStore._default_path()

    assert result == tmp_path / "data" / "snippets.json"
