from __future__ import annotations

import os
import subprocess
import sys
import types
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.stt.local_gigaam import LocalGigaAMProvider


def make_provider() -> LocalGigaAMProvider:
    """Create provider without loading the real GigaAM model."""
    with patch(
        "app.stt.local_gigaam.configure_nvidia_runtime"
    ), patch(
        "app.stt.local_gigaam.gigaam.load_model",
        return_value=MagicMock(),
    ):
        return LocalGigaAMProvider()


def test_init_configures_runtime_and_loads_model():
    fake_model = MagicMock()

    with patch(
        "app.stt.local_gigaam.configure_nvidia_runtime"
    ) as mock_runtime, patch(
        "app.stt.local_gigaam.gigaam.load_model",
        return_value=fake_model,
    ) as mock_load:
        provider = LocalGigaAMProvider()

    mock_runtime.assert_called_once_with()
    mock_load.assert_called_once_with("v3_e2e_ctc")
    assert provider.model is fake_model


def test_prepare_audio_none_returns_empty_list():
    provider = make_provider()

    assert provider._prepare_audio(None) == []


def test_prepare_audio_converts_regular_iterable_to_float_list():
    provider = make_provider()

    assert provider._prepare_audio([1, 2, 0.5, -1]) == [
        1.0,
        2.0,
        0.5,
        -1.0,
    ]


def test_prepare_audio_uses_tolist():
    provider = make_provider()

    audio = MagicMock(spec=["tolist"])
    audio.tolist.return_value = [1, 2, 3]

    result = provider._prepare_audio(audio)

    assert result == [1.0, 2.0, 3.0]
    audio.tolist.assert_called_once_with()


def test_prepare_audio_converts_tensor_like_object():
    provider = make_provider()

    audio = MagicMock()
    detached = MagicMock()
    cpu_audio = MagicMock()
    numpy_audio = MagicMock()

    detached.cpu.return_value = cpu_audio
    cpu_audio.numpy.return_value = numpy_audio
    numpy_audio.tolist.return_value = [0.1, -0.2, 0.3]

    audio.detach.return_value = detached

    result = provider._prepare_audio(audio)

    assert result == [0.1, -0.2, 0.3]

    audio.detach.assert_called_once_with()
    detached.cpu.assert_called_once_with()
    cpu_audio.numpy.assert_called_once_with()


def test_prepare_audio_converts_values_to_float():
    provider = make_provider()

    assert provider._prepare_audio(["1", "2.5", "-0.25"]) == [
        1.0,
        2.5,
        -0.25,
    ]


def test_transcribe_returns_empty_for_empty_audio():
    provider = make_provider()

    with patch.object(
        provider,
        "_prepare_audio",
        return_value=[],
    ), patch.object(
        provider,
        "_write_temp_wav",
    ) as mock_write:
        assert provider.transcribe([]) == ""

    mock_write.assert_not_called()


def test_transcribe_uses_short_pipeline_for_short_audio():
    provider = make_provider()

    audio = [0.1] * 16000

    with patch.object(
        provider,
        "_write_temp_wav",
    ), patch.object(
        provider,
        "_transcribe_short",
        return_value="Короткая расшифровка",
    ) as mock_short, patch.object(
        provider,
        "_transcribe_longform",
    ) as mock_long:
        result = provider.transcribe(audio)

    assert result == "Короткая расшифровка"
    mock_short.assert_called_once()
    mock_long.assert_not_called()


def test_transcribe_uses_longform_pipeline_for_long_audio():
    provider = make_provider()

    audio = [0.1] * int(
        (provider.MAX_SHORT_DURATION + 1) * provider.SAMPLE_RATE
    )

    with patch.object(
        provider,
        "_write_temp_wav",
    ), patch.object(
        provider,
        "_transcribe_short",
    ) as mock_short, patch.object(
        provider,
        "_transcribe_longform",
        return_value="Длинная расшифровка",
    ) as mock_long:
        result = provider.transcribe(audio)

    assert result == "Длинная расшифровка"
    mock_long.assert_called_once()
    mock_short.assert_not_called()


def test_transcribe_deletes_temporary_file():
    provider = make_provider()

    audio = [0.1] * 100

    with patch.object(
        provider,
        "_write_temp_wav",
    ), patch.object(
        provider,
        "_transcribe_short",
        return_value="текст",
    ), patch(
        "app.stt.local_gigaam.Path.unlink",
    ) as mock_unlink:
        result = provider.transcribe(audio)

    assert result == "текст"
    mock_unlink.assert_called_once_with(missing_ok=True)


def test_transcribe_ignores_temp_file_cleanup_error():
    provider = make_provider()

    audio = [0.1] * 100

    with patch.object(
        provider,
        "_write_temp_wav",
    ), patch.object(
        provider,
        "_transcribe_short",
        return_value="текст",
    ), patch(
        "app.stt.local_gigaam.Path.unlink",
        side_effect=OSError("cannot delete"),
    ):
        assert provider.transcribe(audio) == "текст"


def test_transcribe_realtime_returns_empty_for_empty_audio():
    provider = make_provider()

    with patch.object(
        provider,
        "_prepare_audio",
        return_value=[],
    ), patch.object(
        provider,
        "_transcribe_short",
    ) as mock_short:
        assert provider.transcribe_realtime([]) == ""

    mock_short.assert_not_called()


def test_transcribe_realtime_keeps_audio_under_limit():
    provider = make_provider()

    audio = [0.1] * 100

    with patch.object(
        provider,
        "_write_temp_wav",
    ), patch.object(
        provider,
        "_transcribe_short",
        return_value="текст",
    ) as mock_short:
        result = provider.transcribe_realtime(audio)

    assert result == "текст"
    mock_short.assert_called_once()


def test_transcribe_realtime_keeps_only_latest_25_seconds():
    provider = make_provider()

    max_samples = int(
        provider.MAX_SHORT_DURATION * provider.SAMPLE_RATE
    )

    audio = list(range(max_samples + 100))

    captured_audio = []

    def fake_write(audio_data, _path):
        captured_audio.extend(audio_data)

    with patch.object(
        provider,
        "_write_temp_wav",
        side_effect=fake_write,
    ), patch.object(
        provider,
        "_transcribe_short",
        return_value="текст",
    ):
        result = provider.transcribe_realtime(audio)

    assert result == "текст"
    assert len(captured_audio) == max_samples
    assert captured_audio == audio[-max_samples:]


def test_transcribe_realtime_deletes_temporary_file():
    provider = make_provider()

    with patch.object(
        provider,
        "_write_temp_wav",
    ), patch.object(
        provider,
        "_transcribe_short",
        return_value="текст",
    ), patch(
        "app.stt.local_gigaam.Path.unlink",
    ) as mock_unlink:
        assert provider.transcribe_realtime([0.1]) == "текст"

    mock_unlink.assert_called_once_with(missing_ok=True)


def test_transcribe_short_strips_result():
    provider = make_provider()

    provider.model.transcribe.return_value = MagicMock(
        text="  Привет, мир!  \n"
    )

    result = provider._transcribe_short(Path("test.wav"))

    assert result == "Привет, мир!"
    provider.model.transcribe.assert_called_once_with("test.wav")


def test_write_temp_wav_creates_mono_16bit_16khz_file(tmp_path):
    provider = make_provider()

    path = tmp_path / "test.wav"

    provider._write_temp_wav(
        [-1.0, -0.5, 0.0, 0.5, 1.0],
        path,
    )

    with wave.open(str(path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 16000
        assert wav_file.getnframes() == 5


def test_write_temp_wav_clamps_samples(tmp_path):
    provider = make_provider()

    path = tmp_path / "test.wav"

    provider._write_temp_wav(
        [-2.0, 2.0],
        path,
    )

    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.readframes(2)

    assert len(frames) == 4


def test_hidden_console_processes_does_nothing_on_non_windows():
    provider = make_provider()

    with patch(
        "app.stt.local_gigaam.os.name",
        "posix",
    ):
        with provider._hidden_console_processes():
            pass


def test_hidden_console_processes_restores_popen_on_windows():
    provider = make_provider()

    original_popen = subprocess.Popen

    with patch(
        "app.stt.local_gigaam.os.name",
        "nt",
    ), patch.object(
        subprocess,
        "Popen",
        MagicMock(),
    ):
        current_popen = subprocess.Popen

        with provider._hidden_console_processes():
            assert subprocess.Popen is not current_popen

        assert subprocess.Popen is current_popen


def test_hidden_console_processes_sets_create_no_window():
    provider = make_provider()

    original_popen = subprocess.Popen
    fake_popen = MagicMock()
    calls = []

    def capture_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return fake_popen

    with patch(
        "app.stt.local_gigaam.os.name",
        "nt",
    ), patch.object(
        subprocess,
        "Popen",
        side_effect=capture_popen,
    ):
        with provider._hidden_console_processes():
            subprocess.Popen(["ffmpeg"])

    assert calls[0][1]["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert subprocess.Popen is original_popen


def test_hidden_console_processes_preserves_existing_creationflags():
    provider = make_provider()

    calls = []

    def capture_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return MagicMock()

    with patch(
        "app.stt.local_gigaam.os.name",
        "nt",
    ), patch.object(
        subprocess,
        "Popen",
        side_effect=capture_popen,
    ):
        with provider._hidden_console_processes():
            subprocess.Popen(
                ["ffmpeg"],
                creationflags=123,
            )

    assert calls[0][1]["creationflags"] == 123


def test_hidden_console_processes_restores_popen_after_exception():
    provider = make_provider()

    original_popen = subprocess.Popen

    with patch(
        "app.stt.local_gigaam.os.name",
        "nt",
    ):
        with pytest.raises(RuntimeError):
            with provider._hidden_console_processes():
                assert subprocess.Popen is not original_popen
                raise RuntimeError("test")

    assert subprocess.Popen is original_popen


def make_longform_provider():
    provider = make_provider()
    provider.model._device = "cpu"
    return provider


def make_segment(start, end):
    segment = MagicMock()
    segment.start = start
    segment.end = end
    return segment


def make_vad_result(segments):
    timeline = MagicMock()
    timeline.support.return_value = segments

    result = MagicMock()
    result.get_timeline.return_value = timeline

    return result


def make_longform_modules(
    load_audio,
    get_pipeline,
    audio_dataset,
):
    inference_module = types.ModuleType("gigaam.inference")
    inference_module.AudioDataset = audio_dataset
    inference_module.get_pipeline = get_pipeline

    preprocess_module = types.ModuleType("gigaam.preprocess")
    preprocess_module.load_audio = load_audio

    return {
        "gigaam.inference": inference_module,
        "gigaam.preprocess": preprocess_module,
    }


def run_longform_test(
    provider,
    audio,
    vad,
    dataset,
    loader,
    *,
    decode_result=None,
    model_output="model-output",
):
    provider.model.return_value = model_output

    if decode_result is not None:
        provider.model._decode.return_value = decode_result

    inference_module = types.ModuleType("gigaam.inference")
    inference_module.AudioDataset = dataset
    inference_module.get_pipeline = MagicMock(return_value=vad)

    preprocess_module = types.ModuleType("gigaam.preprocess")
    preprocess_module.load_audio = MagicMock(return_value=audio)

    fake_data = types.ModuleType("torch.utils.data")
    fake_data.DataLoader = MagicMock(return_value=loader)

    with patch.dict(
        sys.modules,
        {
            "gigaam.inference": inference_module,
            "gigaam.preprocess": preprocess_module,
            "torch.utils.data": fake_data,
        },
    ):
        return provider._transcribe_longform(Path("test.wav"))



def make_longform_modules(vad, dataset, loader, audio):
    inference_module = types.ModuleType("gigaam.inference")

    pipeline = MagicMock(return_value=vad)

    inference_module.get_pipeline = MagicMock(
        return_value=pipeline
    )
    inference_module.AudioDataset = dataset

    preprocess_module = types.ModuleType("gigaam.preprocess")
    preprocess_module.load_audio = MagicMock(return_value=audio)

    data_module = types.ModuleType("torch.utils.data")
    data_module.DataLoader = MagicMock(return_value=loader)

    return inference_module, preprocess_module, data_module


def run_longform_test(
    provider,
    audio,
    vad,
    dataset,
    loader,
    *,
    decode_result=None,
):
    if decode_result is not None:
        provider.model._decode.return_value = decode_result

    provider.model.return_value = "model-output"

    inference_module, preprocess_module, data_module = (
        make_longform_modules(
            vad,
            dataset,
            loader,
            audio,
        )
    )

    import gigaam

    old_inference = getattr(gigaam, "inference", None)
    old_preprocess = getattr(gigaam, "preprocess", None)

    try:
        gigaam.inference = inference_module
        gigaam.preprocess = preprocess_module

        with patch.dict(
            sys.modules,
            {
                "gigaam.inference": inference_module,
                "gigaam.preprocess": preprocess_module,
                "torch.utils.data": data_module,
            },
        ):
            return provider._transcribe_longform(
                Path("test.wav")
            )
    finally:
        if old_inference is None:
            try:
                del gigaam.inference
            except AttributeError:
                pass
        else:
            gigaam.inference = old_inference

        if old_preprocess is None:
            try:
                del gigaam.preprocess
            except AttributeError:
                pass
        else:
            gigaam.preprocess = old_preprocess


def test_transcribe_longform_returns_empty_when_vad_has_no_segments():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 1

    dataset = MagicMock()

    result = run_longform_test(
        provider,
        audio,
        make_vad_result([]),
        dataset,
        [],
    )

    assert result == ""
    dataset.assert_not_called()


def test_transcribe_longform_squeezes_multichannel_audio():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 2

    squeezed = MagicMock()
    squeezed.unsqueeze.return_value = MagicMock()
    audio.squeeze.return_value = squeezed

    dataset = MagicMock()

    result = run_longform_test(
        provider,
        audio,
        make_vad_result([
            make_segment(0.0, 16.0),
        ]),
        dataset,
        [],
    )

    assert result == ""
    audio.squeeze.assert_called_once_with()
    squeezed.unsqueeze.assert_called_once_with(0)


def test_transcribe_longform_ignores_invalid_segments():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 1

    dataset = MagicMock()

    run_longform_test(
        provider,
        audio,
        make_vad_result([
            make_segment(5.0, 5.0),
            make_segment(10.0, 8.0),
            make_segment(0.0, 16.0),
        ]),
        dataset,
        [],
    )

    chunks = dataset.call_args.args[1]

    assert chunks == [(0.0, 16.0)]


def test_transcribe_longform_merges_close_segments_under_duration_limit():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 1

    dataset = MagicMock()

    run_longform_test(
        provider,
        audio,
        make_vad_result([
            make_segment(0.0, 8.0),
            make_segment(8.1, 16.0),
        ]),
        dataset,
        [],
    )

    chunks = dataset.call_args.args[1]

    assert chunks == [(0.0, 16.0)]


def test_transcribe_longform_splits_when_gap_is_too_large():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 1

    dataset = MagicMock()

    run_longform_test(
        provider,
        audio,
        make_vad_result([
            make_segment(0.0, 16.0),
            make_segment(17.0, 32.0),
        ]),
        dataset,
        [],
    )

    chunks = dataset.call_args.args[1]

    assert chunks == [
        (0.0, 16.0),
        (17.0, 32.0),
    ]


def test_transcribe_longform_splits_when_combined_duration_exceeds_22_seconds():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 1

    dataset = MagicMock()

    run_longform_test(
        provider,
        audio,
        make_vad_result([
            make_segment(0.0, 16.0),
            make_segment(16.1, 24.0),
        ]),
        dataset,
        [],
    )

    chunks = dataset.call_args.args[1]

    assert chunks == [
        (0.0, 16.0),
        (16.1, 24.0),
    ]


def test_transcribe_longform_merges_short_chunk_with_next_segment():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 1

    dataset = MagicMock()

    run_longform_test(
        provider,
        audio,
        make_vad_result([
            make_segment(0.0, 5.0),
            make_segment(5.1, 16.0),
        ]),
        dataset,
        [],
    )

    chunks = dataset.call_args.args[1]

    assert chunks == [(0.0, 16.0)]


def test_transcribe_longform_creates_dataset_with_official_parameters():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 1

    dataset = MagicMock()

    run_longform_test(
        provider,
        audio,
        make_vad_result([
            make_segment(0.0, 16.0),
        ]),
        dataset,
        [],
    )

    dataset.assert_called_once_with(
        audio,
        [(0.0, 16.0)],
        sample_rate=16000,
        max_duration=22.0,
        min_duration=15.0,
        strict_limit_duration=30.0,
    )


def test_transcribe_longform_decodes_string_result():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 1

    batch = MagicMock()
    batch.to.return_value = batch

    dataset = MagicMock()

    result = run_longform_test(
        provider,
        audio,
        make_vad_result([
            make_segment(0.0, 16.0),
        ]),
        dataset,
        [batch],
        decode_result="  Привет мир  ",
    )

    assert result == "Привет мир"
    batch.to.assert_called_once_with("cpu")
    provider.model.assert_called_once_with(batch)
    provider.model._decode.assert_called_once_with(
        "model-output"
    )


def test_transcribe_longform_decodes_iterable_result():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 1

    batch = MagicMock()
    inputs = MagicMock()
    inputs.to.return_value = inputs
    batch.__getitem__.return_value = inputs

    dataset = MagicMock()

    result = run_longform_test(
        provider,
        audio,
        make_vad_result([
            make_segment(0.0, 16.0),
        ]),
        dataset,
        [batch],
        decode_result=[
            " Первый ",
            "",
            "Второй",
            "   ",
        ],
    )

    assert result == "Первый Второй"


def test_transcribe_longform_handles_batch_without_tuple():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 1

    inputs = MagicMock()
    inputs.to.return_value = inputs

    dataset = MagicMock()

    result = run_longform_test(
        provider,
        audio,
        make_vad_result([
            make_segment(0.0, 16.0),
        ]),
        dataset,
        [inputs],
        decode_result=["тест"],
    )

    assert result == "тест"
    inputs.to.assert_called_once_with("cpu")

def test_hidden_console_processes_windows_patches_and_restores_popen():
    provider = make_longform_provider()

    fake_popen = MagicMock()

    with patch(
        "app.stt.local_gigaam.os.name",
        "nt",
    ), patch(
        "app.stt.local_gigaam.subprocess.Popen",
        fake_popen,
    ):
        import app.stt.local_gigaam as gigaam_module

        original_popen = gigaam_module.subprocess.Popen

        with provider._hidden_console_processes():
            assert gigaam_module.subprocess.Popen is not original_popen

            gigaam_module.subprocess.Popen(
                "test-command",
            )

        assert gigaam_module.subprocess.Popen is original_popen

    fake_popen.assert_called_once()
    kwargs = fake_popen.call_args.kwargs
    assert kwargs["creationflags"] == gigaam_module.subprocess.CREATE_NO_WINDOW


def test_hidden_console_processes_restores_popen_after_exception():
    provider = make_longform_provider()

    fake_popen = MagicMock()

    with patch(
        "app.stt.local_gigaam.os.name",
        "nt",
    ), patch(
        "app.stt.local_gigaam.subprocess.Popen",
        fake_popen,
    ):
        import app.stt.local_gigaam as gigaam_module

        original_popen = gigaam_module.subprocess.Popen

        try:
            with provider._hidden_console_processes():
                raise RuntimeError("test error")
        except RuntimeError:
            pass

        assert gigaam_module.subprocess.Popen is original_popen


def test_transcribe_ignores_error_when_deleting_temp_wav():
    provider = make_longform_provider()

    audio = [0.1, 0.2, 0.3]

    with patch.object(
        provider,
        "_transcribe_short",
        return_value="тест",
    ), patch(
        "app.stt.local_gigaam.Path.unlink",
        side_effect=OSError("cannot delete"),
    ):
        result = provider.transcribe(audio)

    assert result == "тест"

def test_transcribe_realtime_ignores_error_when_deleting_temp_wav():
    provider = make_longform_provider()

    audio = [0.1, 0.2, 0.3]

    with patch.object(
        provider,
        "_transcribe_short",
        return_value="тест",
    ), patch(
        "app.stt.local_gigaam.Path.unlink",
        side_effect=OSError("cannot delete"),
    ):
        result = provider.transcribe_realtime(audio)

    assert result == "тест"


def test_transcribe_longform_merges_close_segments_explicitly():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 1

    dataset = MagicMock()

    run_longform_test(
        provider,
        audio,
        make_vad_result([
            make_segment(0.0, 16.0),
            make_segment(16.05, 16.15),
        ]),
        dataset,
        [],
    )

    chunks = dataset.call_args.args[1]

    assert chunks == [
        (0.0, 16.15),
    ]


def test_transcribe_longform_handles_tuple_batch():
    provider = make_longform_provider()

    audio = MagicMock()
    audio.ndim = 1

    inputs = MagicMock()
    inputs.to.return_value = inputs

    batch = (
        inputs,
        MagicMock(),
    )

    dataset = MagicMock()

    result = run_longform_test(
        provider,
        audio,
        make_vad_result([
            make_segment(0.0, 16.0),
        ]),
        dataset,
        [batch],
        decode_result=["тест"],
    )

    assert result == "тест"
    inputs.to.assert_called_once_with("cpu")
    provider.model.assert_called_once_with(inputs)
