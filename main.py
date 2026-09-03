from __future__ import annotations

from app.audio.recorder import AudioRecorder
from app.hotkey.manager import HotkeyManager
from app.injection.text_injector import TextInjector
from app.stt.local_whisper import LocalWhisperProvider
from app.text.processor import TextProcessor


HOTKEY = "right ctrl"


def main() -> None:
    print("[Saydo] Starting...")

    recorder = AudioRecorder()
    stt = LocalWhisperProvider()
    processor = TextProcessor()
    injector = TextInjector()
    hotkey = HotkeyManager(HOTKEY)

    print()
    print("[Saydo] Ready")
    print(f"[Saydo] Hold '{HOTKEY}', speak, then release.")
    print("[Saydo] Press Esc to exit.")
    print()

    def start_recording() -> None:
        if recorder.is_recording:
            return

        try:
            recorder.start()
            print("[Saydo] Recording...")
        except Exception as exc:
            print(f"[Saydo] Recording error: {exc}")

    def stop_recording() -> None:
        if not recorder.is_recording:
            return

        try:
            audio = recorder.stop()

            if len(audio) == 0:
                print("[Saydo] No audio captured.")
                return

            print(
                f"[Saydo] Recorded "
                f"{len(audio) / recorder.sample_rate:.2f} seconds."
            )

            print("[Saydo] Transcribing...")

            text = stt.transcribe(audio)

            if not text:
                print("[Saydo] Nothing recognized.")
                return

            print(f"[Saydo] STT: {text}")

            text = processor.process(text)

            if not text:
                print("[Saydo] Nothing to insert.")
                return

            print(f"[Saydo] Final: {text}")

            injector.inject(text)

        except Exception as exc:
            print(f"[Saydo] Error: {exc}")

    hotkey.start(
        on_press=start_recording,
        on_release=stop_recording,
    )

    try:
        hotkey.wait_for_exit()
    finally:
        hotkey.stop()

    print("[Saydo] Exiting...")


if __name__ == "__main__":
    main()