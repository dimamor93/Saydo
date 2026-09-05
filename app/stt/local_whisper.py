from __future__ import annotations

from pathlib import Path

from app.runtime import configure_nvidia_runtime

configure_nvidia_runtime()

from faster_whisper import WhisperModel  # noqa: E402


class LocalWhisperProvider:
    """Local STT provider with automatic hardware selection."""

    def __init__(
        self,
        model_path: str | Path = "models/large-v3-turbo",
    ) -> None:
        model_path = Path(model_path)

        if not model_path.exists():
            raise FileNotFoundError(
                f"Whisper model not found: {model_path}"
            )

        print("[Saydo] Loading Whisper model...")

        self.model = self._load_model(model_path)

        print("[Saydo] Whisper model loaded.")

    @staticmethod
    def _load_model(model_path: Path) -> WhisperModel:
        """Try GPU first, then fall back to CPU."""

        try:
            print("[Saydo] Trying CUDA...")
            return WhisperModel(
                str(model_path),
                device="cuda",
                compute_type="float16",
            )
        except Exception as cuda_error:
            print(f"[Saydo] CUDA unavailable: {cuda_error}")
            print("[Saydo] Falling back to CPU...")

            return WhisperModel(
                str(model_path),
                device="cpu",
                compute_type="int8",
            )

    def transcribe(
        self,
        audio,
        language: str | None = None,
    ) -> str:
        segments, _ = self.model.transcribe(
            audio,
            language=language,
            vad_filter=True,
            beam_size=5,
        )

        text = " ".join(
            segment.text.strip()
            for segment in segments
        )

        return text.strip()