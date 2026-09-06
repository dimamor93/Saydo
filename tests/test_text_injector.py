from unittest.mock import patch

from app.injection.text_injector import TextInjector


def test_inject_copies_text_and_pastes() -> None:
    injector = TextInjector()

    with (
        patch("app.injection.text_injector.pyperclip.copy") as copy,
        patch("app.injection.text_injector.pyperclip.paste", return_value="old"),
        patch("app.injection.text_injector.keyboard.press_and_release") as paste,
        patch("app.injection.text_injector.time.sleep"),
    ):
        injector.inject("Привет")

    copy.assert_any_call("Привет")
    paste.assert_called_once_with("ctrl+v")


def test_empty_text_is_not_injected() -> None:
    injector = TextInjector()

    with (
        patch("app.injection.text_injector.pyperclip.copy") as copy,
        patch("app.injection.text_injector.keyboard.press_and_release") as paste,
    ):
        injector.inject("")

    copy.assert_not_called()
    paste.assert_not_called()


def test_clipboard_is_restored_after_injection() -> None:
    injector = TextInjector()

    with (
        patch(
            "app.injection.text_injector.pyperclip.paste",
            return_value="старый текст",
        ),
        patch("app.injection.text_injector.pyperclip.copy") as copy,
        patch("app.injection.text_injector.keyboard.press_and_release"),
        patch("app.injection.text_injector.time.sleep"),
    ):
        injector.inject("текст Saydo")

    assert copy.call_args_list[-1].args == ("старый текст",)


def test_clipboard_is_restored_when_paste_fails() -> None:
    injector = TextInjector()

    with (
        patch(
            "app.injection.text_injector.pyperclip.paste",
            return_value="старый текст",
        ),
        patch("app.injection.text_injector.pyperclip.copy") as copy,
        patch(
            "app.injection.text_injector.keyboard.press_and_release",
            side_effect=RuntimeError("paste failed"),
        ),
        patch("app.injection.text_injector.time.sleep"),
    ):
        injector.inject("текст Saydo")

    assert copy.call_args_list[-1].args == ("старый текст",)
def test_clipboard_restore_failure_does_not_break_injection() -> None:
    injector = TextInjector()

    with (
        patch(
            "app.injection.text_injector.pyperclip.paste",
            return_value="старый текст",
        ),
        patch(
            "app.injection.text_injector.pyperclip.copy",
            side_effect=["Saydo", RuntimeError("clipboard locked")],
        ) as copy,
        patch("app.injection.text_injector.keyboard.press_and_release"),
        patch("app.injection.text_injector.time.sleep"),
    ):
        injector.inject("Saydo")

    assert copy.call_count == 2


def test_empty_text_does_not_read_clipboard() -> None:
    injector = TextInjector()

    with (
        patch("app.injection.text_injector.pyperclip.paste") as paste,
        patch("app.injection.text_injector.pyperclip.copy") as copy,
        patch("app.injection.text_injector.keyboard.press_and_release"),
    ):
        injector.inject("")

    paste.assert_not_called()
    copy.assert_not_called()