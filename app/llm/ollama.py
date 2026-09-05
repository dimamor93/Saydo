from __future__ import annotations

import subprocess


class OllamaService:
    """Small adapter for discovering locally installed Ollama models."""

    def __init__(self, command: str = "ollama", timeout: float = 5.0) -> None:
        self.command = command
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                [self.command, "list"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def list_models(self) -> list[str]:
        status, models = self.status()
        return models if status != "unavailable" else []

    def status(self) -> tuple[str, list[str]]:
        """Return (status, models): ready, no_models, or unavailable."""
        try:
            result = subprocess.run(
                [self.command, "list"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return "unavailable", []

        if result.returncode != 0:
            return "unavailable", []

        models: list[str] = []
        for line in result.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            name = line.split()[0]
            if name and name not in models:
                models.append(name)

        return ("ready", models) if models else ("no_models", [])
