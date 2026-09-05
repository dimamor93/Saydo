from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request


class OllamaService:
    """Small adapter for discovering and controlling the local Ollama server."""

    def __init__(
        self,
        command: str = "ollama",
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 5.0,
        load_timeout: float = 300.0,
    ) -> None:
        self.command = command
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.load_timeout = load_timeout

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

    def load_model(self, model: str) -> tuple[bool, str]:
        """Load a model into Ollama memory and keep it resident indefinitely."""
        payload = {
            "model": model,
            "prompt": "",
            "stream": False,
            "think": False,
            "keep_alive": -1,
        }

        try:
            data = self._request(
                "/api/generate",
                payload,
                self.load_timeout,
            )

        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            return False, str(exc)

        except Exception as exc:
            return False, str(exc)

        if not isinstance(data, dict):
            return False, "Ollama returned an invalid response."

        return True, ""

    def unload_model(self, model: str) -> bool:
        """
        Immediately unload a model using Ollama's native stop command.

        We intentionally use `ollama stop <model>` instead of keep_alive=0.
        This is the authoritative mechanism used by Saydo when AI Mode
        is disabled.
        """
        print(f"[Saydo] Unloading LLM: {model}")

        try:
            result = subprocess.run(
                [self.command, "stop", model],
                capture_output=True,
                text=True,
                timeout=self.load_timeout,
                check=False,
            )

        except (OSError, subprocess.SubprocessError) as exc:
            print(f"[Saydo] Ollama stop error: {exc}")
            return False

        if result.returncode != 0:
            print(
                f"[Saydo] Ollama stop failed: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
            return False

        print(f"[Saydo] Ollama stop completed: {model}")

        # Confirm that the model disappeared from Ollama's running model list.
        unloaded = self._wait_until_unloaded(model)

        if unloaded:
            print(f"[Saydo] LLM unloaded: {model}")
        else:
            print(f"[Saydo] Could not confirm LLM unload: {model}")

        return unloaded

    def _model_is_loaded(self, model: str) -> bool:
        """
        Check whether a model is currently loaded in Ollama.

        /api/ps is a GET endpoint, so it must not use _request(),
        which is intended for POST requests.
        """
        try:
            request = urllib.request.Request(
                f"{self.base_url}/api/ps",
                headers={
                    "Content-Type": "application/json",
                },
                method="GET",
            )

            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                raw = response.read().decode("utf-8")

            data = json.loads(raw)

            for item in data.get("models", []):
                if (
                    item.get("name") == model
                    or item.get("model") == model
                ):
                    return True

        except Exception as exc:
            print(f"[Saydo] Ollama /api/ps check failed: {exc}")

        return False

    def _wait_until_unloaded(
        self,
        model: str,
        timeout: float = 5.0,
    ) -> bool:
        """Wait until Ollama confirms that the model is no longer loaded."""
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if not self._model_is_loaded(model):
                return True

            time.sleep(0.25)

        return not self._model_is_loaded(model)

    def _request(
        self,
        endpoint: str,
        payload: dict,
        timeout: float,
    ) -> dict:
        """Send a JSON POST request to Ollama."""
        request = urllib.request.Request(
            f"{self.base_url}{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            raw = response.read().decode("utf-8")

        return json.loads(raw)