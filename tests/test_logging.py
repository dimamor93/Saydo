import json
import logging

import pytest

import app.core.logging as logging_module


@pytest.fixture(autouse=True)
def reset_logging_state():
    logger = logging.getLogger("saydo")

    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    logging_module._configured = False

    yield

    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    logging_module._configured = False


def test_load_level_returns_default_when_settings_missing(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        logging_module,
        "_settings_path",
        lambda: tmp_path / "missing.json",
    )

    assert logging_module._load_level() == "INFO"


def test_load_level_reads_configured_level(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"log_level": "DEBUG"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        logging_module,
        "_settings_path",
        lambda: path,
    )

    assert logging_module._load_level() == "DEBUG"


def test_load_level_ignores_invalid_json(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{invalid", encoding="utf-8")

    monkeypatch.setattr(
        logging_module,
        "_settings_path",
        lambda: path,
    )

    assert logging_module._load_level() == "INFO"


def test_load_level_ignores_non_string_level(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"log_level": 123}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        logging_module,
        "_settings_path",
        lambda: path,
    )

    assert logging_module._load_level() == "INFO"


def test_normalize_level_is_case_insensitive() -> None:
    assert logging_module._normalize_level("debug") == logging.DEBUG
    assert logging_module._normalize_level("WARNING") == logging.WARNING


def test_normalize_level_falls_back_to_info() -> None:
    assert logging_module._normalize_level("NOT_A_LEVEL") == logging.INFO


def test_log_path_creates_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        logging_module,
        "_app_root",
        lambda: tmp_path,
    )

    path = logging_module._log_path()

    assert path == tmp_path / "logs" / "saydo.log"
    assert path.parent.is_dir()


def test_configure_logging_creates_file_and_console_handlers(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        logging_module,
        "_app_root",
        lambda: tmp_path,
    )

    logger = logging_module.configure_logging(level="DEBUG")

    assert logger.name == "saydo"
    assert logger.level == logging.DEBUG
    assert logger.propagate is False
    assert len(logger.handlers) == 2

    handler_types = {type(handler) for handler in logger.handlers}

    assert logging.handlers.RotatingFileHandler in handler_types
    assert logging.StreamHandler in handler_types


def test_configure_logging_uses_requested_level(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        logging_module,
        "_app_root",
        lambda: tmp_path,
    )

    logger = logging_module.configure_logging(level="WARNING")

    assert logger.level == logging.WARNING


def test_configure_logging_does_not_duplicate_handlers(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        logging_module,
        "_app_root",
        lambda: tmp_path,
    )

    logger = logging_module.configure_logging(level="INFO")

    first_handlers = list(logger.handlers)

    logger_again = logging_module.configure_logging(level="DEBUG")

    assert logger_again is logger
    assert logger.handlers == first_handlers
    assert len(logger.handlers) == 2
    assert logger.level == logging.DEBUG


def test_get_logger_returns_named_child_logger(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        logging_module,
        "_app_root",
        lambda: tmp_path,
    )

    logger = logging_module.get_logger("main")

    assert logger.name == "saydo.main"


def test_get_logger_without_name_returns_root_saydo_logger(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        logging_module,
        "_app_root",
        lambda: tmp_path,
    )

    logger = logging_module.get_logger()

    assert logger.name == "saydo"


def test_logging_writes_utf8_text_to_file(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        logging_module,
        "_app_root",
        lambda: tmp_path,
    )

    logger = logging_module.configure_logging(level="DEBUG")
    logger.info("Привет Saydo")

    for handler in logger.handlers:
        handler.flush()

    log_path = tmp_path / "logs" / "saydo.log"

    assert log_path.exists()
    assert "Привет Saydo" in log_path.read_text(encoding="utf-8")
