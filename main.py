from __future__ import annotations

import threading

from app.audio.recorder import AudioRecorder
from app.core.modes import ProcessingMode
from app.core.pipeline import ProcessingPipeline
from app.hotkey.manager import HotkeyManager
from app.injection.text_injector import TextInjector
from app.llm.local import LocalLLMProvider
from app.llm.ollama import OllamaService
from app.llm.settings import LLMSettingsStore
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
    llm_settings = LLMSettingsStore()
    ollama = OllamaService()
    selected_model = llm_settings.get_model()
    installed_models = ollama.list_models()
    if installed_models and selected_model not in installed_models:
        selected_model = installed_models[0]
        llm_settings.save_model(selected_model)

    # AI Mode is enabled by the dashboard switch. It starts disabled on
    # launch so enabling it always goes through the UI confirmation flow.
    current_mode = MODE
    llm = LocalLLMProvider(model=selected_model)

    pipeline = ProcessingPipeline(
        text_processor=processor,
        mode=current_mode,
        llm_provider=llm,
    )

    injector = TextInjector()
    hotkey = HotkeyManager(HOTKEY)

    def on_mode_change(mode: str) -> None:
        nonlocal current_mode
        current_mode = ProcessingMode(mode)
        pipeline.set_mode(current_mode)
        print(f"[Saydo] Mode changed: {current_mode.value}")

    def on_model_change(model: str) -> None:
        llm.model = model
        print(f"[Saydo] LLM model changed: {model}")

    desktop_ui = SaydoDesktopUI(
        hotkey=HOTKEY,
        mode=current_mode.value,
        on_mode_change=on_mode_change,
        on_model_change=on_model_change,
    )

    overlay = SaydoOverlay()

    live_stop_event = threading.Event()
    live_thread: threading.Thread | None = None

    def realtime_worker() -> None:
        last_text = ""
        while not live_stop_event.is_set() and recorder.is_recording:
            try:
                audio_snapshot = recorder.snapshot()
                if len(audio_snapshot) >= int(0.8 * recorder.sample_rate):
                    text = stt.transcribe_realtime(audio_snapshot)
                    if text and text != last_text:
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
        if recorder.is_recording:
            return

        try:
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

    def stop_recording() -> None:
        if not recorder.is_recording:
            return

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
                    current_mode.value,
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

    hotkey.start(
        on_press=start_recording,
        on_release=stop_recording,
    )

    print()
    print("[Saydo] Ready")
    print(f"[Saydo] Mode: {current_mode.value}")
    print(f"[Saydo] LLM model: {llm.model}")
    print(f"[Saydo] Hold '{HOTKEY}', speak, then release.")
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