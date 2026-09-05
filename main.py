from __future__ import annotations

import threading
import time

from app.audio.recorder import AudioRecorder
from app.core.modes import ProcessingMode
from app.core.pipeline import ProcessingPipeline
from app.hotkey.manager import HotkeyManager
from app.injection.text_injector import TextInjector
from app.llm.local import LocalLLMProvider
from app.stt.local_gigaam import LocalGigaAMProvider
from app.text.processor import TextProcessor
from app.ui.dashboard import SaydoDesktopUI
from app.ui.overlay import SaydoOverlay
from app.ui.tray import SaydoTray


HOTKEY = "right ctrl"
MODE = ProcessingMode.INSTANT


def main() -> None:
    print("[Saydo] Starting...")

    recorder = AudioRecorder()
    stt = LocalGigaAMProvider()
    processor = TextProcessor()
    llm = LocalLLMProvider()

    pipeline = ProcessingPipeline(
        text_processor=processor,
        mode=MODE,
        llm_provider=llm,
    )

    injector = TextInjector()
    hotkey = HotkeyManager(HOTKEY)

    desktop_ui = SaydoDesktopUI(
        hotkey=HOTKEY,
        mode=MODE.value,
    )

    overlay = SaydoOverlay()

    live_stop_event = threading.Event()
    live_thread: threading.Thread | None = None
    hands_free = False

    # Hands-free ends based on realtime STT activity, not microphone RMS.
    stt_activity_lock = threading.Lock()
    last_stt_text = ""
    last_stt_change = 0.0
    hands_free_lock = threading.Lock()
    silence_thread: threading.Thread | None = None
    SILENCE_TIMEOUT = 2.0
    SILENCE_RMS_THRESHOLD = 0.008

    def realtime_worker() -> None:
        nonlocal last_stt_text, last_stt_change

        last_text = ""

        while not live_stop_event.is_set() and recorder.is_recording:
            try:
                audio_snapshot = recorder.snapshot()

                if len(audio_snapshot) >= int(0.8 * recorder.sample_rate):
                    text = stt.transcribe_realtime(audio_snapshot)

                    if text:
                        with stt_activity_lock:
                            # A changed realtime transcript means the STT
                            # engine has something new to transcribe.
                            if text != last_stt_text:
                                last_stt_text = text
                                last_stt_change = time.monotonic()

                        if text != last_text:
                            print(f"[Saydo] LIVE STT: {text}")

                            try:
                                overlay.update_text(text)
                            except Exception as exc:
                                print(f"[Saydo] Overlay live error: {exc}")

                            try:
                                desktop_ui.set_live_text(text)
                            except Exception as exc:
                                print(f"[Saydo] UI live error: {exc}")

                            last_text = text

            except Exception as exc:
                print(f"[Saydo] Realtime STT error: {exc}")

            live_stop_event.wait(0.5)

    def hands_free_worker() -> None:
        nonlocal hands_free

        """Stop hands-free after 2 seconds without new realtime STT text."""

        # Give realtime STT time to produce the first transcription.
        while recorder.is_recording:
            with hands_free_lock:
                if not hands_free:
                    return

            with stt_activity_lock:
                has_transcription = bool(last_stt_text)
                last_change = last_stt_change

            if has_transcription and last_change > 0:
                if time.monotonic() - last_change >= SILENCE_TIMEOUT:
                    print(
                        "[Saydo] Hands-free: no new transcription for 2s, stopping."
                    )

                    with hands_free_lock:
                        if not hands_free:
                            return
                        hands_free = False

                    stop_recording()
                    return

            time.sleep(0.10)

    def shutdown() -> None:
        print("[Saydo] Shutting down...")

        try:
            hotkey.stop()
        except Exception:
            pass

        try:
            overlay.close()
        except Exception:
            pass

        try:
            desktop_ui.stop()
        except Exception:
            pass

    def start_recording() -> None:
        nonlocal hands_free, last_stt_text, last_stt_change

        if recorder.is_recording:
            return

        try:
            with hands_free_lock:
                hands_free = False

            with stt_activity_lock:
                last_stt_text = ""
                last_stt_change = 0.0

            recorder.start()
            live_stop_event.clear()

            print("[Saydo] Recording...")

            nonlocal live_thread
            live_thread = threading.Thread(
                target=realtime_worker,
                name="SaydoRealtimeSTT",
                daemon=True,
            )
            live_thread.start()

            try:
                overlay.show_recording()
            except Exception as exc:
                print(f"[Saydo] Overlay show error: {exc}")

            try:
                desktop_ui.set_runtime_state("recording")
            except Exception:
                pass

        except Exception as exc:
            print(f"[Saydo] Recording error: {exc}")

    def enable_hands_free() -> None:
        nonlocal hands_free, silence_thread

        if not recorder.is_recording:
            start_recording()

        with hands_free_lock:
            hands_free = True

        print("[Saydo] Hands-free mode enabled.")
        silence_thread = threading.Thread(
            target=hands_free_worker,
            name="SaydoHandsFree",
            daemon=True,
        )
        silence_thread.start()

    def force_stop_recording() -> None:
        """Force-stop the current hands-free recording via Right Ctrl."""
        nonlocal hands_free
        with hands_free_lock:
            was_hands_free = hands_free
            hands_free = False

        if was_hands_free and recorder.is_recording:
            print("[Saydo] Hands-free: manual stop.")
            stop_recording()

    def stop_recording() -> None:
        nonlocal hands_free

        if not recorder.is_recording:
            return

        with hands_free_lock:
            if hands_free:
                return
            hands_free = False

        try:
            live_stop_event.set()
            if live_thread is not None and live_thread is not threading.current_thread():
                live_thread.join(timeout=0.2)

            audio = recorder.stop()

            try:
                overlay.update_text("")
            except Exception:
                pass

            try:
                desktop_ui.set_runtime_state("processing")
            except Exception:
                pass

            if len(audio) == 0:
                print("[Saydo] No audio captured.")
                return

            duration = len(audio) / recorder.sample_rate

            print(
                f"[Saydo] Recorded "
                f"{duration:.2f} seconds."
            )

            print("[Saydo] Transcribing...")

            raw_text = stt.transcribe(audio)

            if not raw_text:
                print("[Saydo] Nothing recognized.")
                return

            print(f"[Saydo] STT: {raw_text}")

            try:
                text = pipeline.process(raw_text)
            except Exception as exc:
                print(f"[Saydo] Processing error: {exc}")
                return

            if not text:
                print("[Saydo] Nothing to insert.")
                return

            print(f"[Saydo] Final: {text}")

            # ---------------------------------------------------------
            # CRITICAL ORDER:
            #
            # First deliver the final text to the active application.
            # UI/history/dictionary logic must never be able to prevent
            # the actual dictation from being inserted.
            # ---------------------------------------------------------

            try:
                injector.inject(text)
                print("[Saydo] Text injected.")
            except Exception as exc:
                print(f"[Saydo] Injection error: {exc}")

            # Update UI/history only after the main operation succeeded.
            try:
                desktop_ui.set_live_text(text)
            except Exception as exc:
                print(f"[Saydo] UI live text error: {exc}")

            try:
                desktop_ui.add_transcription(
                    text,
                    duration,
                    MODE.value,
                    raw_text=raw_text,
                )
            except Exception as exc:
                print(f"[Saydo] History error: {exc}")

        except Exception as exc:
            print(f"[Saydo] Error: {exc}")

        finally:
            try:
                overlay.hide()
            except Exception:
                pass

            try:
                desktop_ui.set_runtime_state("idle")
            except Exception:
                pass

    # Overlay runs independently from the Qt dashboard.
    overlay_thread = threading.Thread(
        target=overlay.start,
        name="SaydoOverlay",
        daemon=True,
    )
    overlay_thread.start()

    tray = SaydoTray(
        on_show=desktop_ui.show,
        on_exit=shutdown,
    )
    tray.start()

    def handle_press() -> None:
        with hands_free_lock:
            active = hands_free
        if active:
            force_stop_recording()
        else:
            start_recording()

    hotkey.start(
        on_press=handle_press,
        on_release=stop_recording,
        on_double_tap=enable_hands_free,
    )

    print()
    print("[Saydo] Ready")
    print(f"[Saydo] Mode: {MODE.value}")
    print(f"[Saydo] Hold '{HOTKEY}' to dictate, or tap it twice for hands-free mode. Press it once in hands-free to stop.")
    print("[Saydo] Press Esc to exit.")
    print()

    try:
        # Qt must run on the main thread.
        desktop_ui.start()

    except KeyboardInterrupt:
        print("[Saydo] Interrupted.")

    except Exception as exc:
        print(f"[Saydo] Desktop UI error: {exc}")

    finally:
        shutdown()

        try:
            tray.stop()
        except Exception:
            pass

    print("[Saydo] Exiting...")


if __name__ == "__main__":
    main()