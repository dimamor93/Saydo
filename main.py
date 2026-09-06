from __future__ import annotations

import threading

from app.audio.recorder import AudioRecorder
from app.core.logging import get_logger
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

logger = get_logger("main")


def main() -> None:
    logger.info("Starting...")

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
        logger.info("Mode changed: %s", current_mode.value)

    def on_model_change(model: str) -> None:
        llm.model = model
        logger.info("LLM model changed: %s", model)

    desktop_ui = SaydoDesktopUI(
        hotkey=HOTKEY,
        mode=current_mode.value,
        on_mode_change=on_mode_change,
        on_model_change=on_model_change,
    )

    overlay = SaydoOverlay()

    live_stop_event = threading.Event()
    live_thread: threading.Thread | None = None
    recording_stopping = False
    shutdown_started = False

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
                        except Exception:
                            logger.exception("Overlay live error")
                        try:
                            desktop_ui.set_live_text(text)
                        except Exception:
                            logger.exception("UI live error")
                        last_text = text

                        if hands_free:
                            schedule_hands_free_timeout()

            except Exception:
                logger.exception("Realtime STT error")
            live_stop_event.wait(0.5)

    # Hands-free state.
    hands_free = False
    hands_free_stop_timer: threading.Timer | None = None

    def stop_hands_free() -> None:
        nonlocal hands_free_stop_timer

        if hands_free_stop_timer is not None:
            hands_free_stop_timer.cancel()
            hands_free_stop_timer = None

        if hands_free and recorder.is_recording:
            logger.info("Hands-free timeout.")
            stop_recording()

    def schedule_hands_free_timeout() -> None:
        nonlocal hands_free_stop_timer

        if hands_free_stop_timer is not None:
            hands_free_stop_timer.cancel()

        hands_free_stop_timer = threading.Timer(
            2.0,
            stop_hands_free,
        )
        hands_free_stop_timer.daemon = True
        hands_free_stop_timer.start()

    def enable_hands_free() -> None:
        nonlocal hands_free

        if hands_free:
            logger.info("Hands-free already active.")
            stop_hands_free()
            hands_free = False
            return

        hands_free = True

        logger.info("Hands-free enabled.")

        if not recorder.is_recording:
            start_recording()

        schedule_hands_free_timeout()

    def disable_hands_free() -> None:
        nonlocal hands_free

        if not hands_free:
            return

        hands_free = False

        if hands_free_stop_timer is not None:
            hands_free_stop_timer.cancel()

        logger.info("Hands-free disabled.")

    def shutdown() -> None:
        nonlocal shutdown_started

        if shutdown_started:
            return

        shutdown_started = True

        disable_hands_free()
        logger.info("Shutting down...")

        try:
            hotkey.stop()
        except Exception:
            logger.exception("Hotkey shutdown error")

        if recorder.is_recording:
            try:
                stop_recording()
            except Exception:
                logger.exception("Recording shutdown error")

        try:
            overlay.close()
        except Exception:
            logger.exception("Overlay shutdown error")

        try:
            desktop_ui.stop()
        except Exception:
            logger.exception("UI shutdown error")

    def start_recording() -> None:
        if recorder.is_recording:
            return

        try:
            recorder.start()
            live_stop_event.clear()

            logger.info("Recording...")

            nonlocal live_thread
            live_thread = threading.Thread(
                target=realtime_worker,
                name="SaydoRealtimeSTT",
                daemon=True,
            )
            live_thread.start()

            try:
                overlay.show_recording()
            except Exception:
                logger.exception("Overlay show error")

            try:
                desktop_ui.set_runtime_state("recording")
            except Exception:
                pass

        except Exception:
            logger.exception("Recording error")

    def stop_recording() -> None:
        nonlocal hands_free, recording_stopping

        if recording_stopping:
            return

        if not recorder.is_recording:
            return

        recording_stopping = True

        if hands_free:
            hands_free = False
            if hands_free_stop_timer is not None:
                hands_free_stop_timer.cancel()

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
                logger.warning("No audio captured.")
                return

            duration = len(audio) / recorder.sample_rate

            print(
                f"[Saydo] Recorded "
                f"{duration:.2f} seconds."
            )

            logger.info("Transcribing...")

            raw_text = stt.transcribe(audio)

            if not raw_text:
                logger.info("Nothing recognized.")
                return

            logger.info("STT: %s", raw_text)

            try:
                text = pipeline.process(raw_text)
            except Exception:
                logger.exception("Processing error")
                return

            if not text:
                logger.info("Nothing to insert.")
                return

            logger.info("Final: %s", text)

            # ---------------------------------------------------------
            # CRITICAL ORDER:
            #
            # First deliver the final text to the active application.
            # UI/history/dictionary logic must never be able to prevent
            # the actual dictation from being inserted.
            # ---------------------------------------------------------

            try:
                injector.inject(text)
                logger.info("Text injected.")
            except Exception:
                logger.exception("Injection error")

            # Update UI/history only after the main operation succeeded.
            try:
                desktop_ui.set_live_text(text)
            except Exception:
                logger.exception("UI live text error")

            try:
                desktop_ui.add_transcription(
                    text,
                    duration,
                    current_mode.value,
                    raw_text=raw_text,
                )
            except Exception:
                logger.exception("History error")

        except Exception:
            logger.exception("Error")

        finally:
            recording_stopping = False

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
        on_double_tap=enable_hands_free,
    )

    logger.info("Ready")
    logger.info("Mode: %s", current_mode.value)
    logger.info("LLM model: %s", llm.model)
    logger.info("Hold '%s', speak, then release.", HOTKEY)
    logger.info("Press Esc to exit.")

    try:
        # Qt must run on the main thread.
        desktop_ui.start()

    except KeyboardInterrupt:
        logger.info("Interrupted.")

    except Exception:
        logger.exception("Desktop UI error")

    finally:
        shutdown()

        try:
            tray.stop()
        except Exception:
            pass

    logger.info("Exiting...")


if __name__ == "__main__":
    main()



