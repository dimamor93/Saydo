from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from app.core.style import StyleStore
from app.llm.local import SYSTEM_PROMPT, LocalLLMProvider


def make_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    return response


def test_init_uses_defaults():
    provider = LocalLLMProvider()

    assert provider.model == "qwen3.8:27b"
    assert provider.base_url == "http://127.0.0.1:11434"
    assert provider.timeout == 60.0


def test_init_strips_trailing_slash():
    provider = LocalLLMProvider(
        model="test-model",
        base_url="http://localhost:1234///",
        timeout=15.0,
    )

    assert provider.model == "test-model"
    assert provider.base_url == "http://localhost:1234"
    assert provider.timeout == 15.0


def test_system_prompt_returns_base_prompt_when_style_is_empty():
    provider = LocalLLMProvider()

    with patch.object(
        provider._styles,
        "get_selected",
        return_value={"prompt": ""},
    ):
        assert provider._system_prompt() == SYSTEM_PROMPT


def test_system_prompt_includes_selected_style():
    provider = LocalLLMProvider()

    with patch.object(
        provider._styles,
        "get_selected",
        return_value={"prompt": "Пиши более кратко."},
    ):
        prompt = provider._system_prompt()

    assert prompt.startswith(SYSTEM_PROMPT)
    assert "ДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ ВЫБРАННОГО СТИЛЯ:" in prompt
    assert "Пиши более кратко." in prompt
    assert "Эти инструкции не отменяют базовые правила" in prompt


def test_system_prompt_handles_missing_prompt():
    provider = LocalLLMProvider()

    with patch.object(
        provider._styles,
        "get_selected",
        return_value={},
    ):
        assert provider._system_prompt() == SYSTEM_PROMPT


def test_system_prompt_strips_style_prompt():
    provider = LocalLLMProvider()

    with patch.object(
        provider._styles,
        "get_selected",
        return_value={"prompt": "   Пиши кратко.   "},
    ):
        prompt = provider._system_prompt()

    assert "Пиши кратко." in prompt
    assert "   Пиши кратко.   " not in prompt


def test_process_sends_correct_request_and_returns_response():
    provider = LocalLLMProvider(
        model="test-model",
        base_url="http://localhost:11434",
        timeout=25.0,
    )

    response = make_response({"response": "Готовый текст."})

    with patch(
        "app.llm.local.urllib.request.urlopen",
        return_value=response,
    ) as mock_urlopen:
        result = provider.process("ну короче привет")

    assert result == "Готовый текст."

    mock_urlopen.assert_called_once()

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "http://localhost:11434/api/generate"
    assert request.method == "POST"
    assert request.get_header("Content-type") == "application/json"

    payload = json.loads(request.data.decode("utf-8"))

    assert payload["model"] == "test-model"
    assert payload["prompt"] == "ну короче привет"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["system"] == provider._system_prompt()

    assert mock_urlopen.call_args.kwargs["timeout"] == 25.0


def test_process_strips_response():
    provider = LocalLLMProvider()

    response = make_response({"response": "  Готовый текст.  \n"})

    with patch(
        "app.llm.local.urllib.request.urlopen",
        return_value=response,
    ):
        result = provider.process("тест")

    assert result == "Готовый текст."


def test_process_raises_runtime_error_on_connection_error():
    provider = LocalLLMProvider()

    error = urllib.error.URLError("connection refused")

    with patch(
        "app.llm.local.urllib.request.urlopen",
        side_effect=error,
    ):
        with pytest.raises(RuntimeError, match="Could not connect to Ollama"):
            provider.process("тест")


def test_process_raises_runtime_error_on_empty_response():
    provider = LocalLLMProvider()

    response = make_response({"response": ""})

    with patch(
        "app.llm.local.urllib.request.urlopen",
        return_value=response,
    ):
        with pytest.raises(
            RuntimeError,
            match="Ollama returned an empty response",
        ):
            provider.process("тест")


def test_process_raises_runtime_error_on_missing_response_field():
    provider = LocalLLMProvider()

    response = make_response({"model": "test-model"})

    with patch(
        "app.llm.local.urllib.request.urlopen",
        return_value=response,
    ):
        with pytest.raises(
            RuntimeError,
            match="Ollama returned an empty response",
        ):
            provider.process("тест")


def test_process_sends_utf8_payload():
    provider = LocalLLMProvider(model="тестовая-модель")

    response = make_response({"response": "Ответ"})

    with patch(
        "app.llm.local.urllib.request.urlopen",
        return_value=response,
    ) as mock_urlopen:
        provider.process("Привет, мир!")

    request = mock_urlopen.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))

    assert payload["model"] == "тестовая-модель"
    assert payload["prompt"] == "Привет, мир!"


def test_process_uses_selected_style_in_request():
    provider = LocalLLMProvider()

    response = make_response({"response": "Обработанный текст"})

    with patch.object(
        provider._styles,
        "get_selected",
        return_value={"prompt": "Сделай текст официальным."},
    ), patch(
        "app.llm.local.urllib.request.urlopen",
        return_value=response,
    ) as mock_urlopen:
        result = provider.process("текст")

    assert result == "Обработанный текст"

    request = mock_urlopen.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))

    assert "Сделай текст официальным." in payload["system"]