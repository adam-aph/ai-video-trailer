"""TextEngine context manager: manages llama-server lifecycle for Mistral 7B text inference."""
import json
import os
import subprocess
import time
from pathlib import Path

import requests

from cinecut.errors import InferenceError, VramError
from cinecut.inference.vram import wait_for_vram

# Name of the Mistral 7B Instruct GGUF file expected under get_models_dir().
MISTRAL_GGUF_NAME = "mistral-7b-instruct-v0.3.Q4_K_M.gguf"


def get_models_dir() -> Path:
    """Return the directory where model files are stored.

    Respects the CINECUT_MODELS_DIR environment variable (IINF-03).
    Falls back to ~/models when the variable is not set.
    """
    env_val = os.environ.get("CINECUT_MODELS_DIR")
    if env_val is not None:
        return Path(env_val).expanduser().resolve()
    return Path.home() / "models"


class TextEngine:
    """Context manager that starts llama-server on port 8090 for Mistral 7B text inference.

    Mirrors LlavaEngine exactly with three differences:
    - Port 8090 (LlavaEngine uses 8089) — the two must never run concurrently.
    - No --mmproj flag — text-only model.
    - -c 8192 (8k context instead of 2048) — required for structural analysis chunks.

    Acquires GPU_LOCK for its entire lifetime, preventing concurrent GPU operations.
    Before acquiring the lock, polls VRAM until 6144 MiB is free (or 60s elapses).

    Usage::

        with TextEngine(model_path) as engine:
            r = requests.post(f"{engine.base_url}/v1/chat/completions", json=payload)

    """

    def __init__(
        self,
        model_path: Path,
        port: int = 8090,
        debug: bool = False,
    ) -> None:
        self.model_path = model_path
        self.port = port
        self.debug = debug
        self.base_url = f"http://127.0.0.1:{port}"
        self._process: subprocess.Popen | None = None
        self._log_file = None

    def __enter__(self) -> "TextEngine":
        # Lazy import to avoid circular import at module level.
        from cinecut.inference import GPU_LOCK

        # Poll VRAM before acquiring lock — waits for LlavaEngine to release GPU memory.
        # This is the key difference from LlavaEngine which uses assert_vram_available().
        wait_for_vram()

        GPU_LOCK.acquire()
        try:
            self._start()
        except Exception:
            GPU_LOCK.release()
            raise
        return self

    def __exit__(self, *_: object) -> None:
        from cinecut.inference import GPU_LOCK

        try:
            self._stop()
        finally:
            # Always release GPU_LOCK even if _stop raises.
            GPU_LOCK.release()

    def _start(self) -> None:
        """Launch llama-server and wait for the /health endpoint to become ready."""
        cmd = [
            "llama-server",
            "-m", str(self.model_path),
            "--port", str(self.port),
            "--host", "127.0.0.1",
            "-ngl", "99",
            "-c", "8192",
            "-np", "1",
            "--log-disable",
            # NO --mmproj — text-only model
        ]

        if self.debug:
            # In debug mode write stdout/stderr to a log file beside the model.
            log_path = Path(self.model_path).parent / "llama-server-text.log"
            self._log_file = open(log_path, "wb")  # noqa: WPS515
            self._process = subprocess.Popen(
                cmd,
                stdout=self._log_file,
                stderr=self._log_file,
            )
        else:
            # CRITICAL: never use subprocess.PIPE — pipe buffer fills and deadlocks the server.
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        self._wait_for_health(timeout_s=120)

    def _wait_for_health(self, timeout_s: float) -> None:
        """Poll /health until the server is ready or the timeout is exceeded."""
        deadline = time.monotonic() + timeout_s

        while time.monotonic() < deadline:
            # Detect early exit (bad model path, OOM, etc.).
            if self._process is not None and self._process.poll() is not None:
                raise InferenceError(
                    "llama-server exited during startup — check model path and VRAM"
                )

            try:
                r = requests.get(f"{self.base_url}/health", timeout=2)
                if r.status_code == 200 and r.json().get("status") == "ok":
                    return
            except requests.RequestException:
                pass

            time.sleep(1.0)

        # Timed out — terminate the stuck process then raise.
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        raise InferenceError(
            f"llama-server did not become healthy within {timeout_s}s"
        )

    def _stop(self) -> None:
        """Terminate llama-server gracefully (SIGTERM → SIGKILL on timeout)."""
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

        self._process = None

        if self._log_file is not None:
            self._log_file.close()
            self._log_file = None
