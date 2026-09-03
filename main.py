from __future__ import annotations

import keyboard

from app.audio.recorder import AudioRecorder
from app.injection.text_injector import TextInjector
from app.stt.local_whisper import LocalWhisperProvider


HOTKEY = "right ctrl"


def main() -> None:
    print("[Saydo] Starting...")

    recorder = AudioRecorder()
    stt = LocalWhisperProvider()
    injector = TextInjector()

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

            print("[Saydo] Transcribing...")

            text = stt.transcribe(audio)

            if not text:
                print("[Saydo] Nothing recognized.")
                return

            print(f"[Saydo] Done: {text}")

            injector.inject(text)

        except Exception as exc:
            print(f"[Saydo] Error: {exc}")

    keyboard.on_press_key(
        HOTKEY,
        lambda _: start_recording(),
    )

    keyboard.on_release_key(
        HOTKEY,
        lambda _: stop_recording(),
    )

    keyboard.wait("esc")

    print("[Saydo] Exiting...")


if __name__ == "__main__":
    main()