from __future__ import annotations
import queue
from unittest.mock import Mock, patch
from app.ui.overlay import _overlay_process

from app.ui.overlay import (
    SaydoOverlay,
    _calculate_height,
    _get_logo_path,
    _limit_text,
)


def test_get_logo_path_source() -> None:
    path = _get_logo_path()

    assert path.name == "saydo-logo.png"
    assert path.parent.name == "assets"


def test_get_logo_path_frozen() -> None:
    with patch("app.ui.overlay.sys.frozen", True, create=True), \
         patch("app.ui.overlay.sys._MEIPASS", r"C:\bundle", create=True):
        path = _get_logo_path()

    assert path == (
        __import__("pathlib").Path(r"C:\bundle")
        / "assets"
        / "saydo-logo.png"
    )


def test_limit_text_empty() -> None:
    assert _limit_text("") == ""


def test_limit_text_short() -> None:
    text = "hello world"

    assert _limit_text(text) == text


def test_limit_text_exact_limit() -> None:
    text = "a" * 216

    assert _limit_text(text) == text


def test_limit_text_long() -> None:
    text = "a" * 300

    result = _limit_text(text)

    assert len(result) == 216
    assert result.startswith("…")
    assert result.endswith("a" * 215)


def test_calculate_height_empty() -> None:
    assert _calculate_height("") == 82


def test_calculate_height_short() -> None:
    assert _calculate_height("hello") == 82


def test_calculate_height_two_lines() -> None:
    text = "a" * 73

    assert _calculate_height(text) == 82


def test_calculate_height_three_lines() -> None:
    text = "a" * 145

    assert _calculate_height(text) == 88


def test_calculate_height_newlines() -> None:
    text = "one\ntwo\nthree"

    assert _calculate_height(text) == 88


def test_calculate_height_capped_at_three_lines() -> None:
    text = "a" * 1000

    assert _calculate_height(text) == 88


def test_overlay_initial_state() -> None:
    overlay = SaydoOverlay()

    assert overlay._root is None
    assert overlay._window is None
    assert overlay._process is None
    assert overlay._commands is None


def test_start_creates_process() -> None:
    overlay = SaydoOverlay()

    fake_queue = Mock()
    fake_process = Mock()
    fake_process.is_alive.return_value = False

    with patch(
        "app.ui.overlay.mp.Queue",
        return_value=fake_queue,
    ) as queue_class, patch(
        "app.ui.overlay.mp.Process",
        return_value=fake_process,
    ) as process_class:
        overlay.start()

    queue_class.assert_called_once()

    process_class.assert_called_once_with(
        target=__import__("app.ui.overlay", fromlist=["_overlay_process"])._overlay_process,
        args=(fake_queue,),
        name="SaydoOverlayProcess",
        daemon=True,
    )

    fake_process.start.assert_called_once()

    assert overlay._commands is fake_queue
    assert overlay._process is fake_process
    assert overlay._root is True
    assert overlay._window is True


def test_start_does_nothing_when_process_is_alive() -> None:
    overlay = SaydoOverlay()

    fake_process = Mock()
    fake_process.is_alive.return_value = True

    overlay._process = fake_process

    with patch("app.ui.overlay.mp.Queue") as queue_class, \
         patch("app.ui.overlay.mp.Process") as process_class:
        overlay.start()

    fake_process.is_alive.assert_called_once()
    queue_class.assert_not_called()
    process_class.assert_not_called()


def test_show_calls_show_recording() -> None:
    overlay = SaydoOverlay()

    with patch.object(overlay, "show_recording") as show_recording:
        overlay.show()

    show_recording.assert_called_once()


def test_set_state_recording() -> None:
    overlay = SaydoOverlay()

    with patch.object(overlay, "show_recording") as show_recording, \
         patch.object(overlay, "hide") as hide:
        overlay.set_state("recording")

    show_recording.assert_called_once()
    hide.assert_not_called()


def test_set_state_idle() -> None:
    overlay = SaydoOverlay()

    with patch.object(overlay, "show_recording") as show_recording, \
         patch.object(overlay, "hide") as hide:
        overlay.set_state("idle")

    hide.assert_called_once()
    show_recording.assert_not_called()


def test_set_state_processing_does_nothing() -> None:
    overlay = SaydoOverlay()

    with patch.object(overlay, "show_recording") as show_recording, \
         patch.object(overlay, "hide") as hide:
        overlay.set_state("processing")

    show_recording.assert_not_called()
    hide.assert_not_called()


def test_show_recording_puts_command() -> None:
    overlay = SaydoOverlay()
    commands = Mock()
    overlay._commands = commands

    overlay.show_recording()

    commands.put.assert_called_once_with(("show", ""))


def test_show_recording_without_commands() -> None:
    overlay = SaydoOverlay()

    overlay.show_recording()


def test_set_text_calls_update_text() -> None:
    overlay = SaydoOverlay()

    with patch.object(overlay, "update_text") as update_text:
        overlay.set_text("hello")

    update_text.assert_called_once_with("hello")


def test_update_text_puts_command() -> None:
    overlay = SaydoOverlay()
    commands = Mock()
    overlay._commands = commands

    overlay.update_text("hello")

    commands.put.assert_called_once_with(("text", "hello"))


def test_update_text_ignores_empty_text() -> None:
    overlay = SaydoOverlay()
    commands = Mock()
    overlay._commands = commands

    overlay.update_text("")

    commands.put.assert_not_called()


def test_update_text_without_commands() -> None:
    overlay = SaydoOverlay()

    overlay.update_text("hello")


def test_hide_puts_command() -> None:
    overlay = SaydoOverlay()
    commands = Mock()
    overlay._commands = commands

    overlay.hide()

    commands.put.assert_called_once_with(("hide", ""))


def test_hide_without_commands() -> None:
    overlay = SaydoOverlay()

    overlay.hide()


def test_close_sends_close_command_and_joins_process() -> None:
    overlay = SaydoOverlay()

    commands = Mock()
    process = Mock()
    process.is_alive.return_value = False

    overlay._commands = commands
    overlay._process = process
    overlay._root = True
    overlay._window = True

    overlay.close()

    commands.put.assert_called_once_with(("close", ""))
    process.join.assert_called_once_with(timeout=1.0)
    process.terminate.assert_not_called()

    assert overlay._commands is None
    assert overlay._process is None
    assert overlay._root is None
    assert overlay._window is None


def test_close_terminates_stuck_process() -> None:
    overlay = SaydoOverlay()

    commands = Mock()
    process = Mock()
    process.is_alive.side_effect = [True, False]

    overlay._commands = commands
    overlay._process = process

    overlay.close()

    commands.put.assert_called_once_with(("close", ""))
    process.join.assert_any_call(timeout=1.0)
    process.terminate.assert_called_once()
    assert process.join.call_count == 2


def test_close_handles_queue_error() -> None:
    overlay = SaydoOverlay()

    commands = Mock()
    commands.put.side_effect = RuntimeError("queue closed")

    process = Mock()
    process.is_alive.return_value = False

    overlay._commands = commands
    overlay._process = process

    overlay.close()

    assert overlay._commands is None
    assert overlay._process is None
    process.join.assert_called_once_with(timeout=1.0)
def test_overlay_process_creates_tk_window_and_processes_commands() -> None:
    commands = Mock()

    root = Mock()
    window = Mock()
    container = Mock()
    logo_frame = Mock()
    text_frame = Mock()
    text_label = Mock()
    image = Mock()
    converted_image = Mock()
    photo_image = Mock()

    root.withdraw = Mock()
    root.update_idletasks = Mock()
    root.mainloop = Mock()

    commands.get_nowait.side_effect = [
        ("show", ""),
        ("text", "hello"),
        ("hide", ""),
        ("close", ""),
    ]

    with patch("app.ui.overlay.tk.Tk", return_value=root), \
         patch("app.ui.overlay.tk.Toplevel", return_value=window), \
         patch(
             "app.ui.overlay.tk.Frame",
             side_effect=[container, logo_frame, text_frame],
         ), \
         patch("app.ui.overlay.tk.Label", return_value=text_label), \
         patch("app.ui.overlay.Image.open", return_value=image), \
         patch(
             "app.ui.overlay.ImageTk.PhotoImage",
             return_value=photo_image,
         ), \
         patch("app.ui.overlay._position"), \
         patch("app.ui.overlay.print"):

        image.convert.return_value = converted_image

        root.after.side_effect = lambda delay, callback: callback()

        window.winfo_viewable.return_value = False

        _overlay_process(commands)

    root.withdraw.assert_called_once()
    root.mainloop.assert_called_once()

    window.overrideredirect.assert_called_once_with(True)
    window.attributes.assert_any_call("-topmost", True)
    window.attributes.assert_any_call("-alpha", 0.95)
    window.configure.assert_called_once_with(bg="#111111")

    container.pack.assert_called_once_with(
        fill="both",
        expand=True,
    )

    logo_frame.pack.assert_called_once_with(
        side="left",
        fill="y",
        padx=(0, 18),
    )
    logo_frame.pack_propagate.assert_called_once_with(False)

    image.convert.assert_called_once_with("RGBA")
    converted_image.thumbnail.assert_called_once()

    text_label.pack.assert_called_once_with(
        fill="both",
        expand=True,
    )

    text_label.config.assert_any_call(text="")
    text_label.config.assert_any_call(text="hello")

    window.deiconify.assert_called()
    window.lift.assert_called()

    window.destroy.assert_called_once()
    root.quit.assert_called_once()


def test_overlay_process_handles_logo_error() -> None:
    commands = Mock()
    commands.get_nowait.side_effect = queue.Empty

    root = Mock()
    window = Mock()

    with patch("app.ui.overlay.tk.Tk", return_value=root), \
         patch("app.ui.overlay.tk.Toplevel", return_value=window), \
         patch(
             "app.ui.overlay.tk.Frame",
             side_effect=[Mock(), Mock(), Mock()],
         ), \
         patch("app.ui.overlay.tk.Label", return_value=Mock()), \
         patch(
             "app.ui.overlay.Image.open",
             side_effect=RuntimeError("bad image"),
         ), \
         patch("app.ui.overlay._position"), \
         patch("app.ui.overlay.print") as print_mock:

        root.after.side_effect = lambda delay, callback: root.mainloop()

        _overlay_process(commands)

    print_mock.assert_any_call(
        "[Saydo] Overlay logo error: bad image",
        flush=True,
    )


def test_overlay_process_handles_command_error() -> None:
    commands = Mock()
    commands.get_nowait.side_effect = RuntimeError("queue failure")

    root = Mock()
    window = Mock()
    callbacks = []

    with patch("app.ui.overlay.tk.Tk", return_value=root), \
         patch("app.ui.overlay.tk.Toplevel", return_value=window), \
         patch(
             "app.ui.overlay.tk.Frame",
             side_effect=[Mock(), Mock(), Mock()],
         ), \
         patch("app.ui.overlay.tk.Label", return_value=Mock()), \
         patch(
             "app.ui.overlay.Image.open",
             side_effect=RuntimeError("no logo"),
         ), \
         patch("app.ui.overlay._position"), \
         patch("app.ui.overlay.print") as print_mock:

        root.after.side_effect = (
            lambda delay, callback: callbacks.append(callback)
        )

        _overlay_process(commands)

        assert callbacks
        callbacks[0]()

    print_mock.assert_any_call(
        "[Saydo] Overlay command error: queue failure",
        flush=True,
    )



def test_position_non_windows() -> None:
    from unittest.mock import Mock

    from app.ui.overlay import _position

    window = Mock()
    window.winfo_screenwidth.return_value = 1920
    window.winfo_screenheight.return_value = 1080

    with patch("app.ui.overlay.sys.platform", "linux"), \
         patch("app.ui.overlay._calculate_height", return_value=100):
        _position(window, "hello")

    window.geometry.assert_any_call("720x100")
    window.winfo_screenwidth.assert_called_once()
    window.winfo_screenheight.assert_called_once()


def test_position_windows_uses_system_metrics() -> None:
    from unittest.mock import Mock

    from app.ui.overlay import _position

    window = Mock()
    user32 = Mock()
    user32.GetSystemMetrics.side_effect = [2560, 1440]

    fake_ctypes = Mock()
    fake_ctypes.windll.user32 = user32

    with patch("app.ui.overlay.sys.platform", "win32"), \
         patch("app.ui.overlay._calculate_height", return_value=100), \
         patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        _position(window, "hello")

    user32.GetSystemMetrics.assert_any_call(0)
    user32.GetSystemMetrics.assert_any_call(1)
    window.geometry.assert_any_call("720x100+920+1260")


def test_position_windows_falls_back_to_tk_screen_size() -> None:
    from unittest.mock import Mock

    from app.ui.overlay import _position

    window = Mock()
    window.winfo_screenwidth.return_value = 1920
    window.winfo_screenheight.return_value = 1080

    user32 = Mock()
    user32.GetSystemMetrics.side_effect = RuntimeError("metrics unavailable")

    fake_ctypes = Mock()
    fake_ctypes.windll.user32 = user32

    with patch("app.ui.overlay.sys.platform", "win32"), \
         patch("app.ui.overlay._calculate_height", return_value=100), \
         patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        _position(window, "hello")

    window.winfo_screenwidth.assert_called_once()
    window.winfo_screenheight.assert_called_once()
    window.geometry.assert_any_call("720x100+600+900")


def test_overlay_process_updates_visible_window() -> None:
    from app.ui.overlay import _overlay_process

    commands = Mock()
    commands.get_nowait.side_effect = [
        ("text", "hello"),
    ]

    root = Mock()
    window = Mock()

    # Important: the window is already visible.
    window.winfo_viewable.return_value = True

    callbacks = []

    with patch("app.ui.overlay.tk.Tk", return_value=root), \
         patch("app.ui.overlay.tk.Toplevel", return_value=window), \
         patch(
             "app.ui.overlay.tk.Frame",
             side_effect=[Mock(), Mock(), Mock()],
         ), \
         patch("app.ui.overlay.tk.Label", return_value=Mock()), \
         patch("app.ui.overlay.Image.open", side_effect=RuntimeError("no logo")), \
         patch("app.ui.overlay._position"), \
         patch("app.ui.overlay.print"):

        root.after.side_effect = (
            lambda delay, callback: callbacks.append(callback)
        )

        _overlay_process(commands)

        assert callbacks
        callbacks[0]()

    window.winfo_viewable.assert_called_once_with()
    window.deiconify.assert_not_called()
    window.lift.assert_not_called()


def test_overlay_process_schedules_next_command_check() -> None:
    from app.ui.overlay import _overlay_process

    commands = Mock()
    commands.get_nowait.side_effect = [
        ("hide", ""),
        queue.Empty,
    ]

    root = Mock()
    window = Mock()
    callbacks = []

    with patch("app.ui.overlay.tk.Tk", return_value=root), \
         patch("app.ui.overlay.tk.Toplevel", return_value=window), \
         patch(
             "app.ui.overlay.tk.Frame",
             side_effect=[Mock(), Mock(), Mock()],
         ), \
         patch("app.ui.overlay.tk.Label", return_value=Mock()), \
         patch("app.ui.overlay.Image.open", side_effect=RuntimeError("no logo")), \
         patch("app.ui.overlay._position"), \
         patch("app.ui.overlay.print"):

        root.after.side_effect = (
            lambda delay, callback: callbacks.append(callback)
        )

        _overlay_process(commands)

        assert callbacks

        callbacks[0]()

    assert window.withdraw.call_count == 2
    assert len(callbacks) == 2

def test_overlay_process_handles_startup_error() -> None:
    with patch(
        "app.ui.overlay.tk.Tk",
        side_effect=RuntimeError("tk unavailable"),
    ), patch("app.ui.overlay.print") as print_mock:

        _overlay_process(Mock())

    print_mock.assert_called_once_with(
        "[Saydo] Overlay process failed: tk unavailable",
        flush=True,
    )    