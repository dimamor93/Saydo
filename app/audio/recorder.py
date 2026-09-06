from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd


class AudioRecorder:
    """Microphone recorder with thread-safe live audio snapshots."""

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self.channels = 1

        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._is_recording = False

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def duration(self) -> float:
        with self._lock:
            samples = sum(len(chunk) for chunk in self._chunks)
        return samples / self.sample_rate

    def start(self) -> None:
        if self._is_recording:
            return

        with self._lock:
            self._chunks.clear()

        stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
        )

        try:
            stream.start()
        except Exception:
            try:
                stream.close()
            except Exception:
                pass
            raise

        self._stream = stream
        self._is_recording = True

    def stop(self) -> np.ndarray:
        if not self._is_recording:
            return np.array([], dtype=np.float32)

        self._is_recording = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)

            audio = np.concatenate(self._chunks).astype(np.float32)
            self._chunks.clear()

        return audio

    def trim_silence(
        self,
        audio: np.ndarray,
        threshold_db: float = -42.0,
        frame_ms: int = 20,
        padding_ms: int = 120,
    ) -> np.ndarray:
        """Trim quiet audio only from the beginning and end."""
        if audio.size == 0:
            return audio

        samples = np.asarray(audio, dtype=np.float32).reshape(-1)

        if samples.size < 2:
            return samples.copy()

        frame_size = max(1, int(self.sample_rate * frame_ms / 1000))
        padding = max(0, int(self.sample_rate * padding_ms / 1000))

        # Calculate RMS energy for short frames.
        frame_count = int(np.ceil(samples.size / frame_size))
        rms_values = np.empty(frame_count, dtype=np.float32)

        for index in range(frame_count):
            start = index * frame_size
            end = min(start + frame_size, samples.size)
            frame = samples[start:end]
            rms_values[index] = np.sqrt(np.mean(frame * frame))

        # Use the loudest frame as a reference so the threshold adapts
        # to different microphones and recording levels.
        peak_rms = float(np.max(rms_values))

        if peak_rms <= 0.0:
            return samples.copy()

        threshold = peak_rms * (10.0 ** (threshold_db / 20.0))
        active = rms_values >= threshold

        if not np.any(active):
            return samples.copy()

        first_frame = int(np.argmax(active))
        last_frame = int(len(active) - 1 - np.argmax(active[::-1]))

        start = max(0, first_frame * frame_size - padding)
        end = min(samples.size, (last_frame + 1) * frame_size + padding)

        return samples[start:end].copy()

    def snapshot(self) -> np.ndarray:
        """
        Return a copy of all audio recorded so far.

        Safe to call from a background realtime transcription thread.
        """
        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)

            return np.concatenate(self._chunks).astype(np.float32)

    def _callback(self, indata, frames, time, status) -> None:
        if status:
            print(f"[Saydo] Audio status: {status}")

        if not self._is_recording:
            return

        chunk = indata[:, 0].copy()

        with self._lock:
            self._chunks.append(chunk)