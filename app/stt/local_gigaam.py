from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
import warnings
import wave
from pathlib import Path
from typing import Iterator

# Suppress known harmless warnings before importing GigaAM/PyAnnote.
warnings.filterwarnings(
    "ignore",
    message=r"torchcodec is not installed correctly.*",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r"TensorFloat-32.*",
)

import gigaam
import torch

from app.runtime import configure_nvidia_runtime


class LocalGigaAMProvider:
    """Local speech-to-text provider based on GigaAM-v3 e2e-CTC."""

    SAMPLE_RATE = 16000
    MAX_SHORT_DURATION = 25.0

    def __init__(self) -> None:
        configure_nvidia_runtime()

        print("[Saydo] Loading GigaAM-v3 e2e-CTC...")
        self.model = gigaam.load_model("v3_e2e_ctc")

        print("[Saydo] GigaAM-v3 e2e-CTC loaded.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transcribe(self, audio) -> str:
        """
        Final transcription.

        Uses the official GigaAM short-form transcribe() for audio
        up to 25 seconds and the official long-form pipeline for
        longer recordings.
        """

        audio = self._prepare_audio(audio)

        if not audio:
            return ""

        duration = len(audio) / self.SAMPLE_RATE

        with self._hidden_console_processes():
            with tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False,
            ) as temp_file:
                wav_path = Path(temp_file.name)

            try:
                self._write_temp_wav(audio, wav_path)

                if duration <= self.MAX_SHORT_DURATION:
                    return self._transcribe_short(wav_path)

                return self._transcribe_longform(wav_path)

            finally:
                try:
                    wav_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def transcribe_realtime(self, audio) -> str:
        """
        Pseudo-realtime transcription.

        Uses the latest portion of the accumulated recording.
        """

        audio = self._prepare_audio(audio)

        if not audio:
            return ""

        max_samples = int(
            self.MAX_SHORT_DURATION * self.SAMPLE_RATE
        )

        if len(audio) > max_samples:
            audio = audio[-max_samples:]

        with self._hidden_console_processes():
            with tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False,
            ) as temp_file:
                wav_path = Path(temp_file.name)

            try:
                self._write_temp_wav(audio, wav_path)
                return self._transcribe_short(wav_path)

            finally:
                try:
                    wav_path.unlink(missing_ok=True)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # GigaAM inference
    # ------------------------------------------------------------------

    def _transcribe_short(self, wav_path: Path) -> str:
        """Official GigaAM short-form transcription."""

        result = self.model.transcribe(
            str(wav_path)
        )

        return result.text.strip()

    def _transcribe_longform(self, wav_path: Path) -> str:
        """
        Official GigaAM long-form transcription pipeline.

        Uses PyAnnote VAD and the official GigaAM long-form chunking
        logic. Audio is passed to PyAnnote as a preloaded waveform
        to avoid TorchCodec file decoding on Windows.
        """

        from torch.utils.data import DataLoader

        from gigaam.inference import (
            AudioDataset,
            get_pipeline,
        )
        from gigaam.preprocess import load_audio

        # Load audio directly into a tensor.
        audio = load_audio(str(wav_path))

        if audio.ndim > 1:
            audio = audio.squeeze()

        audio_input = {
            "waveform": audio.unsqueeze(0),
            "sample_rate": self.SAMPLE_RATE,
        }

        # Official PyAnnote VAD pipeline.
        pipeline = get_pipeline(self.model._device)

        sad_segments = pipeline(audio_input)

        # --------------------------------------------------------------
        # Official GigaAM long-form parameters
        # --------------------------------------------------------------

        max_duration = 22.0
        min_duration = 15.0
        strict_limit_duration = 30.0
        new_chunk_threshold = 0.2

        # --------------------------------------------------------------
        # Convert VAD output into speech segments
        # --------------------------------------------------------------

        segments = []

        for segment in sad_segments.get_timeline().support():
            start = float(segment.start)
            end = float(segment.end)

            if end <= start:
                continue

            segments.append(
                (
                    start,
                    end,
                )
            )

        if not segments:
            return ""

        # --------------------------------------------------------------
        # Build chunks using official long-form logic
        # --------------------------------------------------------------

        chunks = []

        current_start = segments[0][0]
        current_end = segments[0][1]

        for start, end in segments[1:]:
            current_duration = current_end - current_start
            proposed_duration = end - current_start

            if (
                proposed_duration <= max_duration
                and (
                    end - current_end
                ) <= new_chunk_threshold
            ):
                current_end = end
                continue

            if current_duration < min_duration:
                current_end = end
                continue

            chunks.append(
                (
                    current_start,
                    current_end,
                )
            )

            current_start = start
            current_end = end

        if current_end > current_start:
            chunks.append(
                (
                    current_start,
                    current_end,
                )
            )

        # --------------------------------------------------------------
        # Prepare AudioDataset
        # --------------------------------------------------------------

        dataset = AudioDataset(
            audio,
            chunks,
            sample_rate=self.SAMPLE_RATE,
            max_duration=max_duration,
            min_duration=min_duration,
            strict_limit_duration=strict_limit_duration,
        )

        loader = DataLoader(
            dataset,
            batch_size=16,
            shuffle=False,
            num_workers=0,
        )

        results = []

        # --------------------------------------------------------------
        # Model inference
        # --------------------------------------------------------------

        with torch.inference_mode():
            for batch in loader:
                if isinstance(batch, (tuple, list)):
                    inputs = batch[0]
                else:
                    inputs = batch

                inputs = inputs.to(
                    self.model._device
                )

                outputs = self.model(
                    inputs
                )

                decoded = self.model._decode(
                    outputs
                )

                if isinstance(decoded, str):
                    results.append(decoded)
                else:
                    results.extend(
                        str(item)
                        for item in decoded
                    )

        return " ".join(
            item.strip()
            for item in results
            if item and item.strip()
        ).strip()

    # ------------------------------------------------------------------
    # Windows subprocess handling
    # ------------------------------------------------------------------

    @contextlib.contextmanager
    def _hidden_console_processes(self) -> Iterator[None]:
        """
        Hide Windows console windows created by GigaAM/FFmpeg.

        GigaAM's audio loading may invoke FFmpeg through subprocess.
        On Windows, console subprocesses can briefly create a visible
        terminal window. CREATE_NO_WINDOW prevents that.

        The patch is temporary and restored immediately afterwards.
        """

        if os.name != "nt":
            yield
            return

        original_popen = subprocess.Popen

        def hidden_popen(*args, **kwargs):
            kwargs.setdefault(
                "creationflags",
                subprocess.CREATE_NO_WINDOW,
            )
            return original_popen(
                *args,
                **kwargs,
            )

        subprocess.Popen = hidden_popen

        try:
            yield
        finally:
            subprocess.Popen = original_popen

    # ------------------------------------------------------------------
    # Audio helpers
    # ------------------------------------------------------------------

    def _prepare_audio(self, audio) -> list[float]:
        """Convert incoming audio to a Python float list."""

        if audio is None:
            return []

        if hasattr(audio, "detach"):
            audio = (
                audio.detach()
                .cpu()
                .numpy()
            )

        if hasattr(audio, "tolist"):
            audio = audio.tolist()

        return [
            float(sample)
            for sample in audio
        ]

    def _write_temp_wav(
        self,
        audio: list[float],
        path: Path,
    ) -> None:
        """Write mono 16-bit PCM WAV."""

        import struct

        pcm = bytearray()

        for sample in audio:
            sample = max(
                -1.0,
                min(1.0, sample),
            )

            value = int(
                sample * 32767
            )

            pcm.extend(
                struct.pack(
                    "<h",
                    value,
                )
            )

        with wave.open(
            str(path),
            "wb",
        ) as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(
                self.SAMPLE_RATE
            )
            wav_file.writeframes(
                pcm
            )