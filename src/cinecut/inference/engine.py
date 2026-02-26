"""LlavaEngine context manager: manages llama-server lifecycle with GPU_LOCK serialization."""
import base64
import json
import subprocess
import time
from pathlib import Path
from typing import Callable

import requests
from pydantic import ValidationError

from cinecut.errors import InferenceError
from cinecut.inference.vram import assert_vram_available
from cinecut.models import KeyframeRecord


class LlavaEngine:
    """Context manager that starts llama-server on enter and terminates it on exit.

    Holds GPU_LOCK for its entire lifetime, preventing concurrent FFmpeg GPU operations.
    VRAM is checked before server startup and raises VramError if free memory is below 6 GB.

    Usage::

        with LlavaEngine(model_path, mmproj_path) as engine:
            r = requests.get(f"{engine.base_url}/health")

    """

    def __init__(
        self,
        model_path: Path,
        mmproj_path: Path,
        port: int = 8089,
        debug: bool = False,
    ) -> None:
        self.model_path = model_path
        self.mmproj_path = mmproj_path
        self.port = port
        self.debug = debug
        self.base_url = f"http://127.0.0.1:{port}"
        self._process: subprocess.Popen | None = None
        self._log_file = None

    def __enter__(self) -> "LlavaEngine":
        # Lazy import to avoid circular import at module level.
        from cinecut.inference import GPU_LOCK

        # Check VRAM before acquiring lock — raises VramError early if insufficient.
        assert_vram_available()

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
            "--mmproj", str(self.mmproj_path),
            "--port", str(self.port),
            "--host", "127.0.0.1",
            "-ngl", "99",
            "-c", "2048",
            "-np", "1",
            "--log-disable",
        ]

        if self.debug:
            # In debug mode write stdout/stderr to a log file beside the model.
            log_path = Path(self.model_path).parent / "llama-server.log"
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

    def describe_frame(
        self,
        record: KeyframeRecord,
        timeout_s: float = 60.0,
    ) -> "SceneDescription | None":
        """Submit one frame to LLaVA. Returns None on timeout/error (skip with warning).

        Never raises — the pipeline continues even if individual frames fail.
        Uses json_schema constrained generation (NOT response_format).
        """
        from cinecut.inference.models import SCENE_DESCRIPTION_SCHEMA, validate_scene_description

        img_bytes = Path(record.frame_path).read_bytes()
        b64 = base64.b64encode(img_bytes).decode("ascii")
        data_uri = f"data:image/jpeg;base64,{b64}"

        payload = {
            "temperature": 0.1,
            "max_tokens": 256,
            "json_schema": SCENE_DESCRIPTION_SCHEMA,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        "Describe this film scene. "
                        "Respond with a JSON object with keys: "
                        "visual_content, mood, action, setting."
                    )},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }],
        }
        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=timeout_s,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            return validate_scene_description(json.loads(content.strip()))
        except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError, ValidationError):
            # Frame is skipped — pipeline continues without raising globally.
            return None


def run_inference_stage(
    records: list,  # list[KeyframeRecord]
    model_path: Path,
    mmproj_path: Path,
    progress_callback: "Callable[[int, int], None] | None" = None,
) -> list:  # list[tuple[KeyframeRecord, SceneDescription | None]]
    """Run LLaVA inference on all keyframe records sequentially.

    Returns list of (record, scene_description_or_none) tuples.
    progress_callback(current: int, total: int) called after each frame.
    """
    results = []
    total = len(records)
    with LlavaEngine(model_path, mmproj_path) as engine:
        for i, record in enumerate(records):
            desc = engine.describe_frame(record)
            results.append((record, desc))
            if progress_callback:
                progress_callback(i + 1, total)
    return results
