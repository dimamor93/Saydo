from __future__ import annotations

import json
import subprocess
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from app.llm.ollama import OllamaService


def make_response(payload: object) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    return response


def test_init_uses_defaults():
    service = OllamaService()

    assert service.command == "ollama"
    assert service.base_url == "http://127.0.0.1:11434"
    assert service.timeout == 5.0
    assert service.load_timeout == 300.0


def test_init_strips_trailing_slash():
    service = OllamaService(
        command="custom-ollama",
        base_url="http://localhost:1234///",
        timeout=10.0,
        load_timeout=100.0,
    )

    assert service.command == "custom-ollama"
    assert service.base_url == "http://localhost:1234"
    assert service.timeout == 10.0
    assert service.load_timeout == 100.0


@pytest.mark.parametrize(
    "returncode, expected",
    [
        (0, True),
        (1, False),
    ],
)
def test_is_available_checks_return_code(returncode, expected):
    result = MagicMock(returncode=returncode)

    with patch(
        "app.llm.ollama.subprocess.run",
        return_value=result,
    ) as mock_run:
        assert OllamaService().is_available() is expected

    mock_run.assert_called_once_with(
        ["ollama", "list"],
        capture_output=True,
        text=True,
        timeout=5.0,
        check=False,
    )


@pytest.mark.parametrize(
    "exception",
    [
        OSError("ollama not found"),
        subprocess.SubprocessError("process failed"),
    ],
)
def test_is_available_returns_false_on_subprocess_error(exception):
    with patch(
        "app.llm.ollama.subprocess.run",
        side_effect=exception,
    ):
        assert OllamaService().is_available() is False


def test_status_returns_ready_with_unique_models():
    result = MagicMock(
        returncode=0,
        stdout=(
            "NAME ID SIZE MODIFIED\n"
            "qwen3.8:27b abc 20GB 1 hour ago\n"
            "llama3:8b def 5GB 2 hours ago\n"
            "qwen3.8:27b abc 20GB 1 hour ago\n"
        ),
    )

    with patch(
        "app.llm.ollama.subprocess.run",
        return_value=result,
    ):
        status = OllamaService().status()

    assert status == (
        "ready",
        ["qwen3.8:27b", "llama3:8b"],
    )


def test_status_ignores_empty_lines():
    result = MagicMock(
        returncode=0,
        stdout=(
            "NAME ID SIZE MODIFIED\n"
            "\n"
            "   \n"
            "qwen3.8:27b abc 20GB\n"
            "\n"
        ),
    )

    with patch(
        "app.llm.ollama.subprocess.run",
        return_value=result,
    ):
        assert OllamaService().status() == (
            "ready",
            ["qwen3.8:27b"],
        )


def test_status_returns_no_models_for_header_only():
    result = MagicMock(
        returncode=0,
        stdout="NAME ID SIZE MODIFIED\n",
    )

    with patch(
        "app.llm.ollama.subprocess.run",
        return_value=result,
    ):
        assert OllamaService().status() == ("no_models", [])


def test_status_returns_no_models_for_empty_output():
    result = MagicMock(
        returncode=0,
        stdout="",
    )

    with patch(
        "app.llm.ollama.subprocess.run",
        return_value=result,
    ):
        assert OllamaService().status() == ("no_models", [])


def test_status_returns_unavailable_on_nonzero_exit():
    result = MagicMock(
        returncode=1,
        stdout="error",
    )

    with patch(
        "app.llm.ollama.subprocess.run",
        return_value=result,
    ):
        assert OllamaService().status() == ("unavailable", [])


@pytest.mark.parametrize(
    "exception",
    [
        OSError("ollama not found"),
        subprocess.SubprocessError("process failed"),
    ],
)
def test_status_returns_unavailable_on_subprocess_error(exception):
    with patch(
        "app.llm.ollama.subprocess.run",
        side_effect=exception,
    ):
        assert OllamaService().status() == ("unavailable", [])


def test_list_models_returns_models():
    service = OllamaService()

    with patch.object(
        service,
        "status",
        return_value=("ready", ["qwen3.8:27b", "llama3:8b"]),
    ):
        assert service.list_models() == [
            "qwen3.8:27b",
            "llama3:8b",
        ]


def test_list_models_returns_empty_when_unavailable():
    service = OllamaService()

    with patch.object(
        service,
        "status",
        return_value=("unavailable", []),
    ):
        assert service.list_models() == []


def test_load_model_sends_keep_alive_request():
    service = OllamaService(load_timeout=123.0)

    response = {"response": ""}

    with patch.object(
        service,
        "_request",
        return_value=response,
    ) as mock_request:
        assert service.load_model("qwen3.8:27b") == (True, "")

    mock_request.assert_called_once_with(
        "/api/generate",
        {
            "model": "qwen3.8:27b",
            "prompt": "",
            "stream": False,
            "think": False,
            "keep_alive": -1,
        },
        123.0,
    )


@pytest.mark.parametrize(
    "exception",
    [
        OSError("connection failed"),
        urllib.error.URLError("connection failed"),
        TimeoutError("timed out"),
        RuntimeError("unexpected failure"),
    ],
)
def test_load_model_returns_error_on_request_failure(exception):
    service = OllamaService()

    with patch.object(
        service,
        "_request",
        side_effect=exception,
    ):
        success, error = service.load_model("qwen3.8:27b")

    assert success is False
    assert error == str(exception)


def test_load_model_rejects_non_dict_response():
    service = OllamaService()

    with patch.object(
        service,
        "_request",
        return_value=["invalid"],
    ):
        assert service.load_model("qwen3.8:27b") == (
            False,
            "Ollama returned an invalid response.",
        )


def test_unload_model_returns_false_when_stop_fails():
    service = OllamaService()

    result = MagicMock(
        returncode=1,
        stdout="",
        stderr="model not found",
    )

    with patch(
        "app.llm.ollama.subprocess.run",
        return_value=result,
    ) as mock_run:
        assert service.unload_model("qwen3.8:27b") is False

    mock_run.assert_called_once_with(
        ["ollama", "stop", "qwen3.8:27b"],
        capture_output=True,
        text=True,
        timeout=300.0,
        check=False,
    )


def test_unload_model_returns_false_on_stop_error():
    service = OllamaService()

    with patch(
        "app.llm.ollama.subprocess.run",
        side_effect=OSError("ollama not found"),
    ):
        assert service.unload_model("qwen3.8:27b") is False


def test_unload_model_waits_for_confirmation():
    service = OllamaService()

    result = MagicMock(
        returncode=0,
        stdout="",
        stderr="",
    )

    with patch(
        "app.llm.ollama.subprocess.run",
        return_value=result,
    ), patch.object(
        service,
        "_wait_until_unloaded",
        return_value=True,
    ) as mock_wait:
        assert service.unload_model("qwen3.8:27b") is True

    mock_wait.assert_called_once_with("qwen3.8:27b")


def test_unload_model_returns_false_when_unload_not_confirmed():
    service = OllamaService()

    result = MagicMock(
        returncode=0,
        stdout="",
        stderr="",
    )

    with patch(
        "app.llm.ollama.subprocess.run",
        return_value=result,
    ), patch.object(
        service,
        "_wait_until_unloaded",
        return_value=False,
    ):
        assert service.unload_model("qwen3.8:27b") is False


@pytest.mark.parametrize(
    "field",
    ["name", "model"],
)
def test_model_is_loaded_matches_model(field):
    service = OllamaService()

    response = make_response(
        {
            "models": [
                {field: "qwen3.8:27b"},
            ],
        }
    )

    with patch(
        "app.llm.ollama.urllib.request.urlopen",
        return_value=response,
    ) as mock_urlopen:
        assert service._model_is_loaded("qwen3.8:27b") is True

    request = mock_urlopen.call_args.args[0]

    assert request.full_url == "http://127.0.0.1:11434/api/ps"
    assert request.method == "GET"
    assert request.get_header("Content-type") == "application/json"
    assert mock_urlopen.call_args.kwargs["timeout"] == 5.0


def test_model_is_loaded_returns_false_for_different_model():
    service = OllamaService()

    response = make_response(
        {
            "models": [
                {"name": "llama3:8b"},
            ],
        }
    )

    with patch(
        "app.llm.ollama.urllib.request.urlopen",
        return_value=response,
    ):
        assert service._model_is_loaded("qwen3.8:27b") is False


def test_model_is_loaded_returns_false_for_empty_models():
    service = OllamaService()

    response = make_response({"models": []})

    with patch(
        "app.llm.ollama.urllib.request.urlopen",
        return_value=response,
    ):
        assert service._model_is_loaded("qwen3.8:27b") is False


def test_model_is_loaded_returns_false_on_request_error():
    service = OllamaService()

    with patch(
        "app.llm.ollama.urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection failed"),
    ):
        assert service._model_is_loaded("qwen3.8:27b") is False


def test_wait_until_unloaded_returns_false_after_timeout():
    service = OllamaService()

    with patch.object(
        service,
        "_model_is_loaded",
        return_value=True,
    ) as mock_loaded, patch(
        "app.llm.ollama.time.monotonic",
        side_effect=[0.0, 6.0, 6.0],
    ), patch(
        "app.llm.ollama.time.sleep",
    ) as mock_sleep:
        assert service._wait_until_unloaded(
            "qwen3.8:27b",
            timeout=5.0,
        ) is False

    assert mock_loaded.call_count == 1
    mock_sleep.assert_not_called()


def test_wait_until_unloaded_waits_until_model_disappears():
    service = OllamaService()

    with patch.object(
        service,
        "_model_is_loaded",
        side_effect=[True, False],
    ) as mock_loaded, patch(
        "app.llm.ollama.time.monotonic",
        side_effect=[0.0, 0.1, 0.2],
    ), patch(
        "app.llm.ollama.time.sleep",
    ) as mock_sleep:
        assert service._wait_until_unloaded(
            "qwen3.8:27b",
            timeout=5.0,
        ) is True

    assert mock_loaded.call_count == 2
    mock_sleep.assert_called_once_with(0.25)


def test_wait_until_unloaded_returns_false_after_timeout():
    service = OllamaService()

    with patch.object(
        service,
        "_model_is_loaded",
        return_value=True,
    ) as mock_loaded, patch(
        "app.llm.ollama.time.monotonic",
        side_effect=[0.0, 6.0, 6.0],
    ), patch(
        "app.llm.ollama.time.sleep",
    ) as mock_sleep:
        assert service._wait_until_unloaded(
            "qwen3.8:27b",
            timeout=5.0,
        ) is False

    assert mock_loaded.call_count == 1
    mock_sleep.assert_not_called()


def test_request_sends_json_post_and_returns_data():
    service = OllamaService(base_url="http://localhost:11434")

    response = make_response(
        {
            "response": "Готовый текст",
        }
    )

    payload = {
        "model": "qwen3.8:27b",
        "prompt": "тест",
        "stream": False,
    }

    with patch(
        "app.llm.ollama.urllib.request.urlopen",
        return_value=response,
    ) as mock_urlopen:
        result = service._request(
            "/api/generate",
            payload,
            42.0,
        )

    assert result == {
        "response": "Готовый текст",
    }

    request = mock_urlopen.call_args.args[0]

    assert request.full_url == "http://localhost:11434/api/generate"
    assert request.method == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert mock_urlopen.call_args.kwargs["timeout"] == 42.0

    assert json.loads(request.data.decode("utf-8")) == payload


def test_request_supports_utf8_payload():
    service = OllamaService()

    response = make_response({"ok": True})

    payload = {
        "model": "тестовая-модель",
        "prompt": "Привет, мир!",
    }

    with patch(
        "app.llm.ollama.urllib.request.urlopen",
        return_value=response,
    ):
        result = service._request(
            "/api/generate",
            payload,
            10.0,
        )

    assert result == {"ok": True}


def test_request_propagates_url_error():
    service = OllamaService()

    error = urllib.error.URLError("connection refused")

    with patch(
        "app.llm.ollama.urllib.request.urlopen",
        side_effect=error,
    ):
        with pytest.raises(urllib.error.URLError):
            service._request(
                "/api/generate",
                {},
                5.0,
            )


def test_model_is_loaded_accepts_both_model_fields():
    service = OllamaService()

    response = make_response(
        {
            "models": [
                {"name": "other-model"},
                {"model": "qwen3.8:27b"},
            ],
        }
    )

    with patch(
        "app.llm.ollama.urllib.request.urlopen",
        return_value=response,
    ):
        assert service._model_is_loaded("qwen3.8:27b") is True

