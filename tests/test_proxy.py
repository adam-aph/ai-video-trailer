"""Unit tests for cinecut.ingestion.proxy.

All tests mock subprocess and FfmpegProcess — no real FFmpeg calls are made
and no media files are required.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cinecut.errors import ProxyCreationError, ProxyValidationError
from cinecut.ingestion.proxy import create_proxy, probe_video, validate_proxy


# ---------------------------------------------------------------------------
# Helpers for building fake ffprobe JSON payloads
# ---------------------------------------------------------------------------

def _make_ffprobe_json(
    codec_type: str = "video",
    duration: str = "120.5",
    r_frame_rate: str = "24/1",
) -> str:
    """Return a minimal ffprobe JSON string with the given stream attributes."""
    return json.dumps({
        "streams": [
            {
                "codec_type": codec_type,
                "duration": duration,
                "r_frame_rate": r_frame_rate,
            }
        ]
    })


def _make_empty_streams_json() -> str:
    return json.dumps({"streams": []})


def _make_zero_duration_json() -> str:
    return _make_ffprobe_json(duration="0")


# ---------------------------------------------------------------------------
# probe_video tests
# ---------------------------------------------------------------------------

class TestProbeVideo:
    def test_probe_video_parses_json(self, tmp_path: Path) -> None:
        """probe_video extracts duration_seconds and r_frame_rate from ffprobe JSON."""
        source = tmp_path / "movie.mp4"
        source.touch()

        ffprobe_output = _make_ffprobe_json(duration="120.5", r_frame_rate="24/1")

        mock_result = MagicMock()
        mock_result.stdout = ffprobe_output

        with patch("cinecut.ingestion.proxy.subprocess.run", return_value=mock_result) as mock_run:
            result = probe_video(source)

        mock_run.assert_called_once()
        assert result["duration_seconds"] == pytest.approx(120.5)
        assert result["r_frame_rate"] == "24/1"

    def test_probe_video_raises_on_failure(self, tmp_path: Path) -> None:
        """probe_video wraps CalledProcessError in ProxyCreationError."""
        source = tmp_path / "broken.mp4"
        source.touch()

        with patch(
            "cinecut.ingestion.proxy.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "ffprobe", stderr="Invalid data"),
        ):
            with pytest.raises(ProxyCreationError) as exc_info:
                probe_video(source)

        assert "ffprobe failed" in str(exc_info.value).lower()

    def test_probe_video_raises_on_missing_ffprobe(self, tmp_path: Path) -> None:
        """probe_video raises ProxyCreationError when ffprobe is not in PATH."""
        source = tmp_path / "movie.mp4"
        source.touch()

        with patch(
            "cinecut.ingestion.proxy.subprocess.run",
            side_effect=FileNotFoundError("ffprobe not found"),
        ):
            with pytest.raises(ProxyCreationError) as exc_info:
                probe_video(source)

        assert "ffprobe" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# validate_proxy tests
# ---------------------------------------------------------------------------

class TestValidateProxy:
    def test_validate_proxy_passes_good_output(self, tmp_path: Path) -> None:
        """validate_proxy does not raise when ffprobe returns a valid video stream."""
        proxy = tmp_path / "proxy.mp4"
        proxy.touch()
        source = tmp_path / "movie.mp4"

        mock_result = MagicMock()
        mock_result.stdout = _make_ffprobe_json()

        with patch("cinecut.ingestion.proxy.subprocess.run", return_value=mock_result):
            # Should complete without raising
            validate_proxy(proxy, source)

    def test_validate_proxy_raises_on_empty_streams(self, tmp_path: Path) -> None:
        """validate_proxy raises ProxyValidationError when streams list is empty."""
        proxy = tmp_path / "proxy.mp4"
        proxy.touch()
        source = tmp_path / "movie.mp4"

        mock_result = MagicMock()
        mock_result.stdout = _make_empty_streams_json()

        with patch("cinecut.ingestion.proxy.subprocess.run", return_value=mock_result):
            with pytest.raises(ProxyValidationError) as exc_info:
                validate_proxy(proxy, source)

        assert "No video streams" in str(exc_info.value)

    def test_validate_proxy_raises_on_zero_duration(self, tmp_path: Path) -> None:
        """validate_proxy raises ProxyValidationError when stream duration is zero."""
        proxy = tmp_path / "proxy.mp4"
        proxy.touch()
        source = tmp_path / "movie.mp4"

        mock_result = MagicMock()
        mock_result.stdout = _make_zero_duration_json()

        with patch("cinecut.ingestion.proxy.subprocess.run", return_value=mock_result):
            with pytest.raises(ProxyValidationError) as exc_info:
                validate_proxy(proxy, source)

        assert "duration" in str(exc_info.value).lower() or "corrupt" in str(exc_info.value).lower()

    def test_validate_proxy_deletes_corrupt_file_on_empty_streams(self, tmp_path: Path) -> None:
        """validate_proxy removes the corrupt proxy file when validation fails (empty streams)."""
        proxy = tmp_path / "proxy.mp4"
        proxy.write_bytes(b"fake mp4 content")
        source = tmp_path / "movie.mp4"

        mock_result = MagicMock()
        mock_result.stdout = _make_empty_streams_json()

        with patch("cinecut.ingestion.proxy.subprocess.run", return_value=mock_result):
            with pytest.raises(ProxyValidationError):
                validate_proxy(proxy, source)

        assert not proxy.exists(), "Corrupt proxy should be deleted after failed validation"


# ---------------------------------------------------------------------------
# create_proxy idempotency test
# ---------------------------------------------------------------------------

class TestCreateProxy:
    def test_create_proxy_idempotent(self, tmp_path: Path) -> None:
        """create_proxy returns cached proxy without calling FfmpegProcess when valid proxy exists."""
        source = tmp_path / "movie.mp4"
        source.touch()
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        # Create a fake proxy file at the expected path
        proxy_path = work_dir / "movie_proxy.mp4"
        proxy_path.touch()

        with patch("cinecut.ingestion.proxy.validate_proxy") as mock_validate, \
             patch("cinecut.ingestion.proxy.FfmpegProcess") as mock_ffmpeg:

            # validate_proxy succeeds (no exception)
            mock_validate.return_value = None

            result = create_proxy(source, work_dir)

        assert result == proxy_path
        mock_ffmpeg.assert_not_called()

    def test_create_proxy_re_encodes_invalid_proxy(self, tmp_path: Path) -> None:
        """create_proxy re-encodes if existing proxy fails validation."""
        source = tmp_path / "movie.mp4"
        source.touch()
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        proxy_path = work_dir / "movie_proxy.mp4"
        proxy_path.touch()

        mock_process = MagicMock()
        mock_process.run.return_value = 0

        # First validate (idempotency check) raises, second (post-encode) passes
        validate_calls = [
            ProxyValidationError(proxy_path, "corrupt"),  # idempotency check fails
            None,                                          # post-encode check passes
        ]

        def _side_effect(*args, **kwargs):
            val = validate_calls.pop(0)
            if isinstance(val, Exception):
                raise val
            return val

        with patch("cinecut.ingestion.proxy.validate_proxy", side_effect=_side_effect), \
             patch("cinecut.ingestion.proxy.FfmpegProcess", return_value=mock_process) as mock_ffmpeg:

            result = create_proxy(source, work_dir)

        # FfmpegProcess should have been constructed and run
        mock_ffmpeg.assert_called_once()
        mock_process.run.assert_called_once()
        assert result == proxy_path
