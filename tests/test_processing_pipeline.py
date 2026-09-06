from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.modes import ProcessingMode
from app.core.pipeline import ProcessingPipeline
from app.llm.base import LLMProvider
from app.llm.router import LLMRouter, LLMStrategy
from app.text.processor import TextProcessor


class FakeProcessor:
    def __init__(self, result: str) -> None:
        self.result = result
        self.calls: list[str] = []

    def process(self, text: str) -> str:
        self.calls.append(text)
        return self.result


class FakeProvider(LLMProvider):
    def __init__(self, result: str = "LLM result") -> None:
        self.result = result
        self.calls: list[str] = []

    def process(self, text: str) -> str:
        self.calls.append(text)
        return self.result


class FailingProvider(LLMProvider):
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[str] = []

    def process(self, text: str) -> str:
        self.calls.append(text)
        raise self.error


class FakeDictionary:
    def __init__(self, result: str) -> None:
        self.result = result
        self.calls: list[str] = []

    def apply(self, text: str) -> str:
        self.calls.append(text)
        return self.result


class FakeSnippets:
    def __init__(self, result: str) -> None:
        self.result = result
        self.calls: list[str] = []

    def apply(self, text: str) -> str:
        self.calls.append(text)
        return self.result


def test_pipeline_instant_processes_processor_dictionary_and_snippets() -> None:
    processor = FakeProcessor("processed")
    dictionary = FakeDictionary("dictionary result")
    snippets = FakeSnippets("final result")

    pipeline = ProcessingPipeline(
        text_processor=processor,
        mode=ProcessingMode.INSTANT,
        dictionary=dictionary,
        snippets=snippets,
    )

    assert pipeline.process("raw text") == "final result"

    assert processor.calls == ["raw text"]
    assert dictionary.calls == ["processed"]
    assert snippets.calls == ["dictionary result"]


def test_pipeline_ai_processes_processor_snippets_and_llm() -> None:
    processor = FakeProcessor("processed")
    snippets = FakeSnippets("expanded text")
    provider = FakeProvider("AI result")

    pipeline = ProcessingPipeline(
        text_processor=processor,
        mode=ProcessingMode.AI,
        llm_provider=provider,
        snippets=snippets,
    )

    assert pipeline.process("raw text") == "AI result"

    assert processor.calls == ["raw text"]
    assert snippets.calls == ["processed"]
    assert provider.calls == ["expanded text"]


def test_pipeline_ai_requires_llm_provider() -> None:
    pipeline = ProcessingPipeline(
        text_processor=FakeProcessor("processed"),
        mode=ProcessingMode.AI,
    )

    with pytest.raises(
        RuntimeError,
        match="AI mode requires an LLM provider",
    ):
        pipeline.process("text")


def test_pipeline_rejects_unsupported_mode() -> None:
    pipeline = ProcessingPipeline(
        text_processor=FakeProcessor("processed"),
    )

    pipeline.mode = "unsupported"  # type: ignore[assignment]

    with pytest.raises(ValueError, match="Unsupported processing mode"):
        pipeline.process("text")


def test_pipeline_set_mode_changes_processing_mode() -> None:
    pipeline = ProcessingPipeline(
        text_processor=FakeProcessor("processed"),
    )

    pipeline.set_mode(ProcessingMode.AI)

    assert pipeline.mode == ProcessingMode.AI


def test_router_local_strategy_uses_local_provider() -> None:
    local = FakeProvider("local result")
    cloud = FakeProvider("cloud result")

    router = LLMRouter(
        local_provider=local,
        cloud_provider=cloud,
        strategy=LLMStrategy.LOCAL,
    )

    assert router.process("text") == "local result"
    assert local.calls == ["text"]
    assert cloud.calls == []


def test_router_cloud_strategy_uses_cloud_provider() -> None:
    local = FakeProvider("local result")
    cloud = FakeProvider("cloud result")

    router = LLMRouter(
        local_provider=local,
        cloud_provider=cloud,
        strategy=LLMStrategy.CLOUD,
    )

    assert router.process("text") == "cloud result"
    assert local.calls == []
    assert cloud.calls == ["text"]


def test_router_local_strategy_requires_local_provider() -> None:
    router = LLMRouter(strategy=LLMStrategy.LOCAL)

    with pytest.raises(
        RuntimeError,
        match="Local LLM provider is not available",
    ):
        router.process("text")


def test_router_cloud_strategy_requires_cloud_provider() -> None:
    router = LLMRouter(strategy=LLMStrategy.CLOUD)

    with pytest.raises(
        RuntimeError,
        match="Cloud LLM provider is not available",
    ):
        router.process("text")


def test_router_auto_prefers_local_provider() -> None:
    local = FakeProvider("local result")
    cloud = FakeProvider("cloud result")

    router = LLMRouter(
        local_provider=local,
        cloud_provider=cloud,
        strategy=LLMStrategy.AUTO,
    )

    assert router.process("text") == "local result"
    assert local.calls == ["text"]
    assert cloud.calls == []


def test_router_auto_falls_back_to_cloud_when_local_fails() -> None:
    local = FailingProvider(RuntimeError("local failed"))
    cloud = FakeProvider("cloud result")

    router = LLMRouter(
        local_provider=local,
        cloud_provider=cloud,
        strategy=LLMStrategy.AUTO,
    )

    assert router.process("text") == "cloud result"
    assert local.calls == ["text"]
    assert cloud.calls == ["text"]


def test_router_auto_requires_at_least_one_provider() -> None:
    router = LLMRouter(strategy=LLMStrategy.AUTO)

    with pytest.raises(
        RuntimeError,
        match="No LLM provider is available",
    ):
        router.process("text")


def test_router_auto_uses_cloud_when_local_is_missing() -> None:
    cloud = FakeProvider("cloud result")

    router = LLMRouter(
        cloud_provider=cloud,
        strategy=LLMStrategy.AUTO,
    )

    assert router.process("text") == "cloud result"
    assert cloud.calls == ["text"]


def test_router_rejects_unsupported_strategy() -> None:
    router = LLMRouter()
    router.strategy = "unsupported"  # type: ignore[assignment]

    with pytest.raises(ValueError, match="Unsupported LLM strategy"):
        router.process("text")


def test_router_set_strategy_changes_strategy() -> None:
    router = LLMRouter()

    router.set_strategy(LLMStrategy.CLOUD)

    assert router.strategy == LLMStrategy.CLOUD


def test_text_processor_strips_and_normalizes_whitespace(
    tmp_path: Path,
) -> None:
    processor = TextProcessor(tmp_path / "dictionary.json")

    assert processor.process("  hello   world  ") == "hello world"


def test_text_processor_returns_empty_for_blank_text(
    tmp_path: Path,
) -> None:
    processor = TextProcessor(tmp_path / "dictionary.json")

    assert processor.process("   ") == ""


def test_text_processor_applies_dictionary_case_insensitively(
    tmp_path: Path,
) -> None:
    dictionary_path = tmp_path / "dictionary.json"
    dictionary_path.write_text(
        json.dumps({"saydo": "Saydo"}),
        encoding="utf-8",
    )

    processor = TextProcessor(dictionary_path)

    assert processor.process("I use SAYDO every day") == (
        "I use Saydo every day"
    )


def test_text_processor_does_not_replace_partial_words(
    tmp_path: Path,
) -> None:
    dictionary_path = tmp_path / "dictionary.json"
    dictionary_path.write_text(
        json.dumps({"cat": "dog"}),
        encoding="utf-8",
    )

    processor = TextProcessor(dictionary_path)

    assert processor.process("cat catalog") == "dog catalog"


def test_text_processor_loads_non_string_dictionary_values(
    tmp_path: Path,
) -> None:
    dictionary_path = tmp_path / "dictionary.json"
    dictionary_path.write_text(
        json.dumps({"123": 456}),
        encoding="utf-8",
    )

    processor = TextProcessor(dictionary_path)

    assert processor.dictionary == {"123": "456"}


def test_text_processor_handles_missing_dictionary(
    tmp_path: Path,
) -> None:
    processor = TextProcessor(tmp_path / "missing.json")

    assert processor.dictionary == {}
    assert processor.process("hello world") == "hello world"


def test_text_processor_handles_invalid_json(
    tmp_path: Path,
) -> None:
    dictionary_path = tmp_path / "dictionary.json"
    dictionary_path.write_text("{invalid", encoding="utf-8")

    processor = TextProcessor(dictionary_path)

    assert processor.dictionary == {}


def test_text_processor_handles_non_dictionary_json(
    tmp_path: Path,
) -> None:
    dictionary_path = tmp_path / "dictionary.json"
    dictionary_path.write_text('["invalid"]', encoding="utf-8")

    processor = TextProcessor(dictionary_path)

    assert processor.dictionary == {}
