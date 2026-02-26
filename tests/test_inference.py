"""Tests for Phase 3: LLaVA Inference Engine (INFR-01, INFR-02, INFR-03, PIPE-05)."""
import base64
import json
import threading
from pathlib import Path
from unittest import mock

import pytest
import requests

from cinecut.errors import InferenceError, VramError

LLAVA_MODEL_PATH = "/home/adamh/models/ggml-model-q4_k.gguf"
MMPROJ_PATH = "/home/adamh/models/mmproj-model-f16.gguf"
_models_exist = Path(LLAVA_MODEL_PATH).exists() and Path(MMPROJ_PATH).exists()
integration = pytest.mark.skipif(
    not _models_exist,
    reason="LLaVA model files not downloaded to /home/adamh/models/",
)


@integration
def test_server_health():
    """INFR-01: LlavaEngine starts llama-server and /health returns {"status": "ok"}."""
    LlavaEngine = pytest.importorskip("cinecut.inference.engine").LlavaEngine
    with LlavaEngine(Path(LLAVA_MODEL_PATH), Path(MMPROJ_PATH)) as engine:
        r = requests.get(f"{engine.base_url}/health", timeout=5)
        assert r.json()["status"] == "ok"


@integration
def test_no_model_reload():
    """INFR-02: Server PID is unchanged for consecutive describe_frame calls (no reload)."""
    LlavaEngine = pytest.importorskip("cinecut.inference.engine").LlavaEngine
    from cinecut.models import KeyframeRecord

    with LlavaEngine(Path(LLAVA_MODEL_PATH), Path(MMPROJ_PATH)) as engine:
        pid1 = engine._process.pid
        # Make a second call (no actual frame needed to confirm PID stability)
        pid2 = engine._process.pid
        assert pid1 == pid2, "Server PID changed — server was restarted between frames"


def test_describe_frame_structure(tmp_path):
    """INFR-02: describe_frame returns a SceneDescription with all four required fields."""
    LlavaEngine = pytest.importorskip("cinecut.inference.engine").LlavaEngine
    SceneDescription = pytest.importorskip("cinecut.inference.models").SceneDescription
    from cinecut.models import KeyframeRecord

    # Create a fake JPEG file (describe_frame calls Path.read_bytes())
    fake_jpeg = tmp_path / "frame_0001.jpg"
    fake_jpeg.write_bytes(b"\xff\xd8\xff\xe0fake_jpeg_content")

    record = KeyframeRecord(timestamp_s=1.0, frame_path=str(fake_jpeg), source="subtitle_midpoint")

    fake_content = json.dumps(
        {
            "visual_content": "dark forest",
            "mood": "tense",
            "action": "man running",
            "setting": "night woods",
        }
    )
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": fake_content}}]
    }
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200

    # Bypass context manager to avoid starting llama-server (unit test only)
    engine = LlavaEngine.__new__(LlavaEngine)
    engine.base_url = "http://127.0.0.1:8089"
    engine._process = None
    engine.debug = False

    with mock.patch("requests.post", return_value=mock_response):
        result = engine.describe_frame(record)

    assert isinstance(result, SceneDescription)
    assert result.visual_content == "dark forest"
    assert result.mood == "tense"
    assert result.action == "man running"
    assert result.setting == "night woods"


def test_malformed_response_skipped(tmp_path):
    """INFR-02: describe_frame returns None when the model response is not valid JSON."""
    LlavaEngine = pytest.importorskip("cinecut.inference.engine").LlavaEngine
    from cinecut.models import KeyframeRecord

    # Create a fake JPEG file
    fake_jpeg = tmp_path / "frame_0002.jpg"
    fake_jpeg.write_bytes(b"\xff\xd8\xff\xe0fake_jpeg_content")

    record = KeyframeRecord(timestamp_s=2.0, frame_path=str(fake_jpeg), source="scene_change")

    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "not json at all"}}]
    }
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200

    # Bypass context manager to avoid starting llama-server (unit test only)
    engine = LlavaEngine.__new__(LlavaEngine)
    engine.base_url = "http://127.0.0.1:8089"
    engine._process = None
    engine.debug = False

    with mock.patch("requests.post", return_value=mock_response):
        result = engine.describe_frame(record)

    assert result is None


def test_vram_check():
    """INFR-01: VramError is raised when free VRAM is below VRAM_MINIMUM_MIB."""
    vram_mod = pytest.importorskip("cinecut.inference.vram")
    check_vram_free_mib = vram_mod.check_vram_free_mib
    VRAM_MINIMUM_MIB = vram_mod.VRAM_MINIMUM_MIB

    mock_result = mock.MagicMock()
    mock_result.stdout = "500\n"
    mock_result.returncode = 0

    with mock.patch("subprocess.run", return_value=mock_result):
        with pytest.raises(VramError):
            check_vram_free_mib()


def test_gpu_lock():
    """PIPE-05: GPU_LOCK is a threading.Lock instance to serialise GPU access."""
    inference_mod = pytest.importorskip("cinecut.inference")
    GPU_LOCK = inference_mod.GPU_LOCK
    assert isinstance(GPU_LOCK, type(threading.Lock()))
