import json

import pytest

from app.core.dictionary import UserDictionary
from app.core.dictionary_learner import DictionaryLearner
from app.core.modes import ProcessingMode
from app.core.pipeline import ProcessingPipeline
from app.core.snippets import SnippetStore
from app.core.style import StyleStore
from app.text.processor import TextProcessor


def test_processing_mode_values():
    assert ProcessingMode.INSTANT.value == "instant"
    assert ProcessingMode.AI.value == "ai"


def test_dictionary_add_save_load_and_apply(tmp_path):
    path = tmp_path / "dictionary.json"
    dictionary = UserDictionary(path)

    dictionary.add_word("OpenAI")
    dictionary.add_correction("чат жпт", "ChatGPT")

    loaded = UserDictionary(path)

    assert len(loaded.load()) == 2
    assert loaded.words() == ["OpenAI"]
    assert loaded.apply("Я использую чат жпт каждый день.") == (
        "Я использую ChatGPT каждый день."
    )


def test_dictionary_ignores_invalid_corrections(tmp_path):
    dictionary = UserDictionary(tmp_path / "dictionary.json")

    dictionary.add_correction("", "test")
    dictionary.add_correction("test", "")
    dictionary.add_correction("same", "same")

    assert dictionary.corrections() == []


def test_dictionary_apply_uses_exact_stored_case(tmp_path):
    dictionary = UserDictionary(tmp_path / "dictionary.json")
    dictionary.add_correction("saydo", "Saydo")

    assert dictionary.apply("saydo works.") == "saydo works."


def test_dictionary_learner_only_accepts_equal_word_replacements():
    learner = DictionaryLearner()

    assert learner.find_corrections("я люблю saydo", "я люблю Saydo") == []
    assert learner.find_corrections("привет мир", "привет большой мир") == []
    assert learner.find_corrections("привет, мир!", "привет мир!") == []
    assert learner.find_corrections("одно", "другое") == [("одно", "другое")]


def test_dictionary_learner_deduplicates_casefolded_pairs():
    learner = DictionaryLearner()

    result = learner.find_corrections("Saydo saydo", "SAYdo SAYDO")

    assert result == []


def test_snippet_store_crud_and_apply(tmp_path):
    store = SnippetStore(tmp_path / "snippets.json")

    with pytest.raises(ValueError):
        store.add("Test", "", "body")

    with pytest.raises(ValueError):
        store.add("Test", "hello", "")

    store.add("Greeting", "hello", "Hello, world!")
    store.add("Short", "hi", "Hi!")

    assert len(store.load()) == 2
    assert store.find("HELLO")["name"] == "Greeting"
    assert store.apply("hello and hi") == "Hello, world! and Hi!"

    store.update(0, "Updated", "hello", "Updated text")
    assert store.find("hello")["name"] == "Updated"

    store.delete(1)
    assert len(store.load()) == 1


def test_snippet_store_invalid_delete_is_ignored(tmp_path):
    store = SnippetStore(tmp_path / "snippets.json")
    store.add("Test", "hello", "body")

    store.delete(10)

    assert len(store.load()) == 1


def test_style_store_custom_styles_and_selection(tmp_path, monkeypatch):
    styles_path = tmp_path / "styles.json"
    monkeypatch.setattr("app.core.style.data_path", lambda name: styles_path)

    store = StyleStore()
    styles = store.load()

    assert styles
    builtin_ids = {style["id"] for style in styles if style.get("builtin")}
    assert builtin_ids
    assert store.get_selected_id() in builtin_ids

    created = store.add("Test Style", "Description", "Use short sentences.")

    assert created["name"] == "Test Style"
    assert created["builtin"] is False
    assert store.select(created["id"]) is True
    assert store.get_selected_id() == created["id"]
    assert store.delete(created["id"]) is True
    assert store.get_selected_id() != created["id"]


def test_style_store_rejects_empty_name(tmp_path, monkeypatch):
    styles_path = tmp_path / "styles.json"
    monkeypatch.setattr("app.core.style.data_path", lambda name: styles_path)

    store = StyleStore()

    with pytest.raises(ValueError):
        store.add("", "description", "prompt")


def test_style_store_allows_empty_description(tmp_path, monkeypatch):
    styles_path = tmp_path / "styles.json"
    monkeypatch.setattr("app.core.style.data_path", lambda name: styles_path)

    store = StyleStore()
    created = store.add("name", "", "prompt")

    assert created["description"] == next(style["description"] for style in store.load() if style["id"] == created["id"])


def test_text_processor_normalizes_whitespace(tmp_path):
    dictionary_path = tmp_path / "dictionary.json"
    dictionary_path.write_text(
        json.dumps({"чат жпт": "ChatGPT"}, ensure_ascii=False),
        encoding="utf-8",
    )

    processor = TextProcessor(dictionary_path)
    result = processor.process("  я   использую   чат жпт \n каждый день  ")

    assert result == "я использую ChatGPT каждый день"


class FakeProcessor:
    def process(self, text):
        return f"processed:{text}"


class FakeDictionary:
    def apply(self, text):
        return f"dict:{text}"


class FakeSnippets:
    def apply(self, text):
        return f"snippet:{text}"


class FakeLLM:
    def process(self, text):
        return f"llm:{text}"


def test_pipeline_instant_order():
    pipeline = ProcessingPipeline(
        FakeProcessor(),
        ProcessingMode.INSTANT,
        FakeLLM(),
        FakeDictionary(),
    )
    pipeline.snippets = FakeSnippets()

    assert pipeline.process("hello") == "snippet:dict:processed:hello"


def test_pipeline_ai_applies_snippets_before_llm():
    pipeline = ProcessingPipeline(
        FakeProcessor(),
        ProcessingMode.AI,
        FakeLLM(),
        FakeDictionary(),
    )
    pipeline.snippets = FakeSnippets()

    assert pipeline.process("hello") == "llm:snippet:processed:hello"


def test_pipeline_requires_llm_for_ai():
    pipeline = ProcessingPipeline(
        FakeProcessor(),
        ProcessingMode.AI,
        None,
        FakeDictionary(),
    )

    with pytest.raises(RuntimeError):
        pipeline.process("hello")


def test_pipeline_rejects_unknown_mode():
    pipeline = ProcessingPipeline(
        FakeProcessor(),
        "unknown",
        FakeLLM(),
        FakeDictionary(),
    )

    with pytest.raises(ValueError):
        pipeline.process("hello")
