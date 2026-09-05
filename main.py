from __future__ import annotations

import threading
import time
from enum import Enum

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


class SaydoState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"


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
    overlay = SaydoOverlay()
    desktop_ui = SaydoDesktopUI(
        hotkey=HOTKEY,
        mode=MODE.value,
    )

    shutdown_event = threading.Event()
    # Qt requires QApplication and its event loop to run in the process main thread.
    # The previous UI implementation started PySide6 in a worker thread, which can
    # cause a hard GUI freeze/deadlock on Windows. The desktop UI is started below
    # on the main thread; the audio/hotkey work remains in background threads.

    overlay_thread = threading.Thread(
        target=overlay.start,
        name="SaydoOverlay",
        daemon=True,
    )
    overlay_thread.start()

    while overlay._root is None:
        time.sleep(0.01)

    state_lock = threading.Lock()
    state = SaydoState.IDLE
    live_stop_event = threading.Event()
    live_thread: threading.Thread | None = None

    def get_state() -> SaydoState:
        with state_lock:
            return state

    def set_state(new_state: SaydoState) -> None:
        nonlocal state
        with state_lock:
            state = new_state
        desktop_ui.set_runtime_state(new_state.value)

    def shutdown() -> None:
        shutdown_event.set()
        live_stop_event.set()

        try:
            if recorder.is_recording:
                recorder.stop()
        except Exception:
            pass

        try:
            overlay.hide()
        except Exception:
            pass

        try:
            hotkey.stop()
        except Exception:
            pass

        try:
            tray.stop()
        except Exception:
            pass

        desktop_ui.stop()

    tray = SaydoTray(on_show=desktop_ui.show, on_exit=shutdown)
    tray.start()

    desktop_ui.set_runtime_state(SaydoState.IDLE.value)

    print()
    print("[Saydo] Ready")
    print(f"[Saydo] Mode: {MODE.value}")
    print(f"[Saydo] Hold '{HOTKEY}', speak, then release.")
    print("[Saydo] Saydo is running in the system tray.")
    print("[Saydo] Press Esc or use the tray menu to exit.")
    print()

    def realtime_worker() -> None:
        last_text = ""
        while not live_stop_event.is_set():
            try:
                if get_state() != SaydoState.RECORDING:
                    break

                audio = recorder.snapshot()

                if len(audio) < int(0.8 * recorder.sample_rate):
                    time.sleep(0.3)
                    continue

                text = stt.transcribe_realtime(audio)

                if text and text != last_text:
                    overlay.update_text(text)
                    desktop_ui.set_live_text(text)
                    last_text = text

            except Exception as exc:
                print(f"\n[Saydo] Realtime error: {exc}")
                break

            time.sleep(0.5)

    def start_recording() -> None:
        nonlocal live_thread

        if get_state() != SaydoState.IDLE:
            return

        try:
            recorder.start()
            set_state(SaydoState.RECORDING)
            live_stop_event.clear()

            overlay.show_recording()
            desktop_ui.set_live_text("Слушаю…")

            live_thread = threading.Thread(
                target=realtime_worker,
                name="SaydoRealtime",
                daemon=True,
            )
            live_thread.start()

            print("[Saydo] Recording...")

        except Exception as exc:
            set_state(SaydoState.IDLE)
            print(f"[Saydo] Recording error: {exc}")

    def stop_recording() -> None:
        if get_state() != SaydoState.RECORDING:
            return

        set_state(SaydoState.PROCESSING)
        live_stop_event.set()

        try:
            audio = recorder.stop()

            if len(audio) == 0:
                print("[Saydo] No audio captured.")
                overlay.hide()
                desktop_ui.set_live_text("")
                set_state(SaydoState.IDLE)
                return

            duration = len(audio) / recorder.sample_rate
            print(f"[Saydo] Recorded {duration:.2f} seconds.")
            print("[Saydo] Final transcription...")

            text = stt.transcribe(audio)

            if not text:
                print("[Saydo] Nothing recognized.")
                overlay.hide()
                desktop_ui.set_live_text("")
                set_state(SaydoState.IDLE)
                return

            print(f"[Saydo] STT: {text}")
            raw_text = text

            try:
                text = pipeline.process(text)
            except Exception as exc:
                print(f"[Saydo] Processing error: {exc}")
                overlay.hide()
                desktop_ui.set_live_text("")
                set_state(SaydoState.IDLE)
                return

            if not text:
                print("[Saydo] Nothing to insert.")
                overlay.hide()
                desktop_ui.set_live_text("")
                set_state(SaydoState.IDLE)
                return

            print(f"[Saydo] Final: {text}")

            desktop_ui.set_live_text(text)
            desktop_ui.add_transcription(text, duration, MODE.value, raw_text=raw_text)
            injector.inject(text)

            time.sleep(0.4)
            overlay.hide()
            desktop_ui.set_live_text("")
            set_state(SaydoState.IDLE)

        except Exception as exc:
            print(f"[Saydo] Error: {exc}")

            try:
                recorder.stop()
            except Exception:
                pass

            overlay.hide()
            desktop_ui.set_live_text("")
            set_state(SaydoState.IDLE)

    hotkey.start(
        on_press=start_recording,
        on_release=stop_recording,
    )

    def wait_for_hotkey_exit() -> None:
        try:
            hotkey.wait_for_exit()
        finally:
            shutdown_event.set()

    exit_thread = threading.Thread(
        target=wait_for_hotkey_exit,
        name="SaydoHotkeyExit",
        daemon=True,
    )
    exit_thread.start()

    # QApplication must own the main thread. This call blocks in Qt's event loop
    # while hotkey/audio workers continue independently.
    try:
        desktop_ui.start()
    finally:
        shutdown_event.set()
        shutdown()


if __name__ == "__main__":
    main()
