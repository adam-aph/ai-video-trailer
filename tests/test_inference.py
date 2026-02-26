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
    pytest.skip("requires plan-02 implementation")


@pytest.mark.skip(reason="requires plan-02 implementation")
def test_describe_frame_structure():
    """INFR-03: describe_frame returns a SceneDescription with all four required fields."""
    LlavaEngine = pytest.importorskip("cinecut.inference.engine").LlavaEngine
    SceneDescription = pytest.importorskip("cinecut.inference.models").SceneDescription

    fake_content = json.dumps(
        {
            "visual_content": "A close-up of a ruined city at dusk.",
            "mood": "tense",
            "action": "static shot",
            "setting": "urban exterior",
        }
    )
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": fake_content}}]
    }

    with mock.patch("requests.post", return_value=mock_response):
        with LlavaEngine(Path(LLAVA_MODEL_PATH), Path(MMPROJ_PATH)) as engine:
            frame_path = Path("/tmp/fake_frame.jpg")
            result = engine.describe_frame(frame_path)
            assert isinstance(result, SceneDescription)
            assert result.visual_content
            assert result.mood
            assert result.action
            assert result.setting


@pytest.mark.skip(reason="requires plan-02 implementation")
def test_malformed_response_skipped():
    """INFR-03: describe_frame returns None when the model response is not valid JSON."""
    LlavaEngine = pytest.importorskip("cinecut.inference.engine").LlavaEngine

    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "not valid json {{{"}}]
    }

    with mock.patch("requests.post", return_value=mock_response):
        with LlavaEngine(Path(LLAVA_MODEL_PATH), Path(MMPROJ_PATH)) as engine:
            frame_path = Path("/tmp/fake_frame.jpg")
            result = engine.describe_frame(frame_path)
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
