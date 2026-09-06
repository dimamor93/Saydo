from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.audio.recorder import AudioRecorder


def test_initial_state() -> None:
    recorder = AudioRecorder(sample_rate=16000)

    assert recorder.is_recording is False
    assert recorder.duration == 0.0


def test_start_creates_and_starts_stream() -> None:
    recorder = AudioRecorder(sample_rate=16000)
    stream = MagicMock()

    with patch(
        "app.audio.recorder.sd.InputStream",
        return_value=stream,
    ) as input_stream:
        recorder.start()

    input_stream.assert_called_once_with(
        samplerate=16000,
        channels=1,
        dtype="float32",
        callback=recorder._callback,
    )
    stream.start.assert_called_once()
    assert recorder.is_recording is True


def test_start_twice_does_not_create_second_stream() -> None:
    recorder = AudioRecorder()
    stream = MagicMock()

    with patch(
        "app.audio.recorder.sd.InputStream",
        return_value=stream,
    ) as input_stream:
        recorder.start()
        recorder.start()

    input_stream.assert_called_once()
    stream.start.assert_called_once()


def test_start_error_closes_stream() -> None:
    recorder = AudioRecorder()
    stream = MagicMock()
    stream.start.side_effect = RuntimeError("microphone error")

    with patch(
        "app.audio.recorder.sd.InputStream",
        return_value=stream,
    ):
        with pytest.raises(RuntimeError, match="microphone error"):
            recorder.start()

    stream.close.assert_called_once()
    assert recorder.is_recording is False
    assert recorder._stream is None


def test_stop_without_recording_returns_empty_audio() -> None:
    recorder = AudioRecorder()

    audio = recorder.stop()

    assert audio.size == 0
    assert audio.dtype == np.float32


def test_stop_closes_stream_and_returns_audio() -> None:
    recorder = AudioRecorder()
    stream = MagicMock()

    with patch(
        "app.audio.recorder.sd.InputStream",
        return_value=stream,
    ):
        recorder.start()

    recorder._chunks = [
        np.array([0.1, 0.2], dtype=np.float32),
        np.array([0.3, 0.4], dtype=np.float32),
    ]

    audio = recorder.stop()

    np.testing.assert_array_equal(
        audio,
        np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    stream.stop.assert_called_once()
    stream.close.assert_called_once()
    assert recorder.is_recording is False
    assert recorder._stream is None
    assert recorder._chunks == []


def test_stop_with_empty_chunks_releases_stream() -> None:
    recorder = AudioRecorder()
    stream = MagicMock()

    with patch(
        "app.audio.recorder.sd.InputStream",
        return_value=stream,
    ):
        recorder.start()

    audio = recorder.stop()

    assert audio.size == 0
    stream.stop.assert_called_once()
    stream.close.assert_called_once()


def test_duration_uses_recorded_samples() -> None:
    recorder = AudioRecorder(sample_rate=1000)
    recorder._chunks = [
        np.zeros(250, dtype=np.float32),
        np.zeros(750, dtype=np.float32),
    ]

    assert recorder.duration == 1.0


def test_snapshot_returns_recorded_audio() -> None:
    recorder = AudioRecorder()
    recorder._chunks = [
        np.array([1.0, 2.0], dtype=np.float32),
        np.array([3.0], dtype=np.float32),
    ]

    snapshot = recorder.snapshot()

    np.testing.assert_array_equal(
        snapshot,
        np.array([1.0, 2.0, 3.0], dtype=np.float32),
    )


def test_snapshot_returns_copy() -> None:
    recorder = AudioRecorder()
    recorder._chunks = [
        np.array([1.0, 2.0], dtype=np.float32),
    ]

    snapshot = recorder.snapshot()
    snapshot[0] = 99.0

    np.testing.assert_array_equal(
        recorder._chunks[0],
        np.array([1.0, 2.0], dtype=np.float32),
    )


def test_snapshot_without_audio_returns_empty_array() -> None:
    recorder = AudioRecorder()

    snapshot = recorder.snapshot()

    assert snapshot.size == 0
    assert snapshot.dtype == np.float32


def test_callback_stores_first_channel() -> None:
    recorder = AudioRecorder()
    recorder._is_recording = True

    indata = np.array(
        [
            [0.1, 9.0],
            [0.2, 8.0],
            [0.3, 7.0],
        ],
        dtype=np.float32,
    )

    recorder._callback(indata, 3, None, None)

    np.testing.assert_array_equal(
        recorder._chunks[0],
        np.array([0.1, 0.2, 0.3], dtype=np.float32),
    )


def test_callback_ignores_audio_when_not_recording() -> None:
    recorder = AudioRecorder()

    indata = np.ones((3, 2), dtype=np.float32)

    recorder._callback(indata, 3, None, None)

    assert recorder._chunks == []


def test_callback_reports_status(capsys) -> None:
    recorder = AudioRecorder()

    recorder._callback(
        np.ones((1, 1), dtype=np.float32),
        1,
        None,
        "input overflow",
    )

    captured = capsys.readouterr()

    assert "Audio status: input overflow" in captured.out


def test_trim_silence_removes_beginning_and_end() -> None:
    recorder = AudioRecorder(sample_rate=1000)

    audio = np.concatenate(
        [
            np.zeros(500, dtype=np.float32),
            np.ones(500, dtype=np.float32),
            np.zeros(500, dtype=np.float32),
        ]
    )

    trimmed = recorder.trim_silence(
        audio,
        frame_ms=100,
        padding_ms=0,
    )

    assert len(trimmed) == 500
    np.testing.assert_array_equal(
        trimmed,
        np.ones(500, dtype=np.float32),
    )


def test_trim_silence_preserves_internal_pause() -> None:
    recorder = AudioRecorder(sample_rate=1000)

    audio = np.concatenate(
        [
            np.zeros(300, dtype=np.float32),
            np.ones(300, dtype=np.float32),
            np.zeros(200, dtype=np.float32),
            np.ones(300, dtype=np.float32),
            np.zeros(300, dtype=np.float32),
        ]
    )

    trimmed = recorder.trim_silence(
        audio,
        frame_ms=100,
        padding_ms=0,
    )

    assert len(trimmed) == 800
    assert np.any(trimmed[:300] > 0)
    assert np.any(trimmed[-300:] > 0)


def test_trim_silence_empty_audio() -> None:
    recorder = AudioRecorder()

    audio = np.array([], dtype=np.float32)

    trimmed = recorder.trim_silence(audio)

    assert trimmed is audio


def test_trim_silence_single_sample() -> None:
    recorder = AudioRecorder()

    audio = np.array([0.5], dtype=np.float32)

    trimmed = recorder.trim_silence(audio)

    np.testing.assert_array_equal(trimmed, audio)
    assert trimmed is not audio


def test_trim_silence_all_silence_is_preserved() -> None:
    recorder = AudioRecorder(sample_rate=1000)

    audio = np.zeros(500, dtype=np.float32)

    trimmed = recorder.trim_silence(audio)

    np.testing.assert_array_equal(trimmed, audio)


def test_trim_silence_respects_padding() -> None:
    recorder = AudioRecorder(sample_rate=1000)

    audio = np.concatenate(
        [
            np.zeros(300, dtype=np.float32),
            np.ones(300, dtype=np.float32),
            np.zeros(300, dtype=np.float32),
        ]
    )

    trimmed = recorder.trim_silence(
        audio,
        frame_ms=100,
        padding_ms=100,
    )

    assert len(trimmed) == 500
