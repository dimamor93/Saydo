from __future__ import annotations

from enum import Enum


class ProcessingMode(str, Enum):
    """Saydo text processing modes."""

    INSTANT = "instant"
    AI = "ai"