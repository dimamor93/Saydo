from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.llm.base import LLMProvider
from app.llm.hardware import has_cuda_gpu
from app.llm.settings import LLMSettingsStore
from app.runtime import configure_nvidia_runtime


class TestProvider(LLMProvider):
    def process(self, text: str) -> str:
        return text.upper()


class BareTestProvider(LLMProvider):
    def process(self, text: str) -> str:
        return super().process(text)


def test_llm_provider_interface_can_be_implemented() -> None:
    provider = TestProvider()

    assert provider.process("hello") == "HELLO"


def test_llm_provider_cannot_be_instantiated_directly() -> None:
    try:
        LLMProvider()
    except TypeError:
        pass
    else:
        raise AssertionError("LLMProvider should be abstract")


def test_has_cuda_gpu_returns_true_when_cuda_available() -> None:
    fake_torch = MagicMock()
    fake_torch.cuda.is_available.return_value = True

    with patch.dict("sys.modules", {"torch": fake_torch}):
        assert has_cuda_gpu() is True


def test_has_cuda_gpu_returns_false_when_cuda_unavailable() -> None:
    fake_torch = MagicMock()
    fake_torch.cuda.is_available.return_value = False

    with patch.dict("sys.modules", {"torch": fake_torch}):
        assert has_cuda_gpu() is False


def test_has_cuda_gpu_returns_false_when_torch_fails() -> None:
    fake_torch = MagicMock()
    fake_torch.cuda.is_available.side_effect = RuntimeError("CUDA failed")

    with patch.dict("sys.modules", {"torch": fake_torch}):
        assert has_cuda_gpu() is False


def test_llm_settings_load_empty_when_file_missing(tmp_path: Path) -> None:
    store = LLMSettingsStore(tmp_path / "settings.json")

    assert store.load() == {}


def test_llm_settings_loads_dictionary(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"llm_model": "test-model", "ai_mode": True}),
        encoding="utf-8",
    )

    store = LLMSettingsStore(path)

    assert store.load() == {
        "llm_model": "test-model",
        "ai_mode": True,
    }


def test_llm_settings_load_returns_empty_for_non_object_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text('["invalid"]', encoding="utf-8")

    store = LLMSettingsStore(path)

    assert store.load() == {}


def test_llm_settings_load_returns_empty_for_invalid_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{invalid", encoding="utf-8")

    store = LLMSettingsStore(path)

    assert store.load() == {}


def test_get_model_returns_saved_model(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"llm_model": "qwen-test:7b"}),
        encoding="utf-8",
    )

    store = LLMSettingsStore(path)

    assert store.get_model() == "qwen-test:7b"


def test_get_model_returns_default_for_missing_value(tmp_path: Path) -> None:
    store = LLMSettingsStore(tmp_path / "settings.json")

    assert store.get_model() == "qwen3.8:27b"


def test_get_model_returns_default_for_blank_value(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"llm_model": "   "}), encoding="utf-8")

    store = LLMSettingsStore(path)

    assert store.get_model("fallback") == "fallback"


def test_get_model_returns_default_for_non_string_value(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"llm_model": 123}), encoding="utf-8")

    store = LLMSettingsStore(path)

    assert store.get_model("fallback") == "fallback"


def test_get_ai_mode_returns_saved_value(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"ai_mode": True}), encoding="utf-8")

    store = LLMSettingsStore(path)

    assert store.get_ai_mode() is True


def test_get_ai_mode_returns_default_when_missing(tmp_path: Path) -> None:
    store = LLMSettingsStore(tmp_path / "settings.json")

    assert store.get_ai_mode() is False
    assert store.get_ai_mode(True) is True


def test_get_ai_mode_converts_value_to_bool(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"ai_mode": 1}), encoding="utf-8")

    store = LLMSettingsStore(path)

    assert store.get_ai_mode() is True


def test_save_model_persists_model(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = LLMSettingsStore(path)

    store.save_model("qwen-test:14b")

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "llm_model": "qwen-test:14b",
    }


def test_save_ai_mode_preserves_existing_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"llm_model": "qwen-test:7b"}),
        encoding="utf-8",
    )

    store = LLMSettingsStore(path)
    store.save_ai_mode(True)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "llm_model": "qwen-test:7b",
        "ai_mode": True,
    }


def test_save_model_preserves_existing_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"ai_mode": True}),
        encoding="utf-8",
    )

    store = LLMSettingsStore(path)
    store.save_model("qwen-test:27b")

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "ai_mode": True,
        "llm_model": "qwen-test:27b",
    }


def test_settings_write_ignores_write_errors(tmp_path: Path) -> None:
    store = LLMSettingsStore(tmp_path / "settings.json")

    with patch.object(
        Path,
        "write_text",
        side_effect=OSError("disk full"),
    ):
        store._write({"llm_model": "test"})

    assert not store.path.exists()


def test_runtime_does_nothing_on_non_windows() -> None:
    with patch("app.runtime.sys.platform", "linux"):
        configure_nvidia_runtime()


def test_runtime_does_nothing_without_nvidia_directory(
    tmp_path: Path,
) -> None:
    with patch("app.runtime.sys.platform", "win32"),          patch("app.runtime.sys.prefix", str(tmp_path)),          patch("app.runtime.os.add_dll_directory") as add_dll:
        configure_nvidia_runtime()

    add_dll.assert_not_called()


def test_runtime_adds_existing_cuda_directories(tmp_path: Path) -> None:
    nvidia = tmp_path / "Lib" / "site-packages" / "nvidia"

    directories = [
        nvidia / "cublas" / "bin",
        nvidia / "cuda_nvrtc" / "bin",
        nvidia / "cudnn" / "bin",
    ]

    for directory in directories:
        directory.mkdir(parents=True)

    with patch("app.runtime.sys.platform", "win32"),          patch("app.runtime.sys.prefix", str(tmp_path)),          patch("app.runtime.os.add_dll_directory") as add_dll,          patch.dict("app.runtime.os.environ", {"PATH": ""}, clear=True):
        configure_nvidia_runtime()

        assert add_dll.call_count == 3

        path_entries = os.environ["PATH"].split(os.pathsep)

        for directory in directories:
            assert str(directory) in path_entries


def test_runtime_does_not_duplicate_path_entry(tmp_path: Path) -> None:
    nvidia = tmp_path / "Lib" / "site-packages" / "nvidia"
    cublas = nvidia / "cublas" / "bin"
    cublas.mkdir(parents=True)

    with patch("app.runtime.sys.platform", "win32"),          patch("app.runtime.sys.prefix", str(tmp_path)),          patch("app.runtime.os.add_dll_directory"),          patch.dict(
             "app.runtime.os.environ",
             {"PATH": str(cublas)},
             clear=True,
         ):
        configure_nvidia_runtime()

        assert os.environ["PATH"].split(os.pathsep) == [str(cublas)]


def test_llm_provider_process_base_method_raises_not_implemented() -> None:
    provider = BareTestProvider()

    with pytest.raises(NotImplementedError):
        provider.process("test")
