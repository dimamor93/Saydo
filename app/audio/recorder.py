from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd


class AudioRecorder:
    """Records microphone audio into memory."""

    def __init__(self, sample_rate: int = 16_000) -> None:
        self.sample_rate = sample_rate
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status,
    ) -> None:
        if status:
            print(f"[Saydo] Audio status: {status}")

        with self._lock:
            self._chunks.append(indata[:, 0].copy())

    def start(self) -> None:
        if self.is_recording:
            return

        with self._lock:
            self._chunks.clear()

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()

        except Exception:
            self._stream = None
            raise

    def stop(self) -> np.ndarray:
        if self._stream is None:
            raise RuntimeError("Recording has not started.")

        stream = self._stream
        self._stream = None

        try:
            stream.stop()
            stream.close()
        finally:
            with self._lock:
                if not self._chunks:
                    return np.array([], dtype=np.float32)

                audio = np.concatenate(self._chunks).astype(
                    np.float32,
                    copy=False,
                )
                self._chunks.clear()

        return audio

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    @property
    def duration(self) -> float:
        with self._lock:
            samples = sum(len(chunk) for chunk in self._chunks)

        return samples / self.sample_rate