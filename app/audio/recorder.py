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