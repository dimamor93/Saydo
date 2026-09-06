from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from pathlib import Path

DEFAULT_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3

_LOGGER_NAME = "saydo"
_configured = False


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _settings_path() -> Path:
    return _app_root() / "data" / "settings.json"


def _load_level() -> str:
    try:
        path = _settings_path()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                level = data.get("log_level")
                if isinstance(level, str):
                    return level
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return DEFAULT_LEVEL


def _log_path() -> Path:
    path = _app_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path / "saydo.log"


def _normalize_level(level: str) -> int:
    value = getattr(logging, str(level).upper(), None)
    if isinstance(value, int):
        return value
    return logging.INFO


def configure_logging(
    level: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    global _configured

    logger = logging.getLogger(_LOGGER_NAME)
    effective_level = level or _load_level()

    if _configured:
        logger.setLevel(_normalize_level(effective_level))
        return logger
    logger.setLevel(_normalize_level(effective_level))
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        _log_path(),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    _configured = True
    logger.info("Logging initialized. Level: %s", logging.getLevelName(logger.level))

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    if not _configured:
        configure_logging()

    if not name:
        return logging.getLogger(_LOGGER_NAME)

    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
