"""FFmpeg proxy creation, metadata extraction, and proxy validation.

Produces a 420p CFR MP4 at 24fps suitable for all downstream visual
analysis.  All subprocess errors and FFmpeg failures are translated into
typed ``CineCutError`` subclasses — raw stderr never escapes to callers.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from better_ffmpeg_progress import FfmpegProcess
from better_ffmpeg_progress.exceptions import FfmpegProcessError

from cinecut.errors import ProxyCreationError, ProxyValidationError


def probe_video(source: Path) -> dict:
    """Return basic metadata for the first video stream in *source*.

    Parameters
    ----------
    source:
        Path to the source video file.

    Returns
    -------
    dict
        ``{"duration_seconds": float, "r_frame_rate": str}`` where
        ``r_frame_rate`` is the raw fractional string from ffprobe
        (e.g. ``"24000/1001"``).

    Raises
    ------
    ProxyCreationError
        If ffprobe is not installed, the file is unreadable, or its output
        cannot be parsed.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        str(source),
    ]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ProxyCreationError(source, f"ffprobe failed: {exc.stderr.strip()}") from exc
    except FileNotFoundError as exc:
        raise ProxyCreationError(source, "ffprobe not found — is FFmpeg installed and in PATH?") from exc

    try:
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        return {
            "duration_seconds": float(stream.get("duration", 0)),
            "r_frame_rate": stream["r_frame_rate"],
        }
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise ProxyCreationError(source, f"Could not parse ffprobe output: {exc}") from exc


def create_proxy(
    source: Path,
    work_dir: Path,
    progress_callback: Callable | None = None,
) -> Path:
    """Create a 420p CFR MP4 proxy in *work_dir* from *source*.

    The operation is idempotent: if a valid proxy already exists at the
    expected path, it is returned immediately without re-encoding.

    Parameters
    ----------
    source:
        Path to the original video file.
    work_dir:
        Directory where the proxy will be written.
    progress_callback:
        Optional callable; reserved for future use — not passed to
        ``FfmpegProcess`` in the current implementation.

    Returns
    -------
    Path
        Absolute path to the proxy MP4.

    Raises
    ------
    ProxyCreationError
        If FFmpeg fails to produce output.
    ProxyValidationError
        If FFmpeg exits 0 but the proxy is corrupt or empty.
    """
    proxy_path = work_dir / f"{source.stem}_proxy.mp4"

    # Idempotency check — skip encode if a valid proxy already exists
    if proxy_path.exists():
        try:
            validate_proxy(proxy_path, source)
            return proxy_path
        except ProxyValidationError:
            # Existing file is corrupt; fall through to re-encode
            pass

    cmd = [
        "ffmpeg", "-y",
        "-i", str(source),
        "-vf", "scale=-2:420,fps=24",
        "-vsync", "cfr",
        "-c:v", "libx264",
        "-crf", "28",
        "-preset", "fast",
        "-an",
        str(proxy_path),
    ]

    try:
        process = FfmpegProcess(cmd)
        process.run()
    except FfmpegProcessError as exc:
        raise ProxyCreationError(source, str(exc)) from exc

    # Validate after encode — catches FFmpeg-exits-0-but-corrupt (Pitfall 3)
    validate_proxy(proxy_path, source)

    return proxy_path


def validate_proxy(proxy_path: Path, source: Path) -> None:
    """Verify *proxy_path* contains a non-empty video stream.

    If validation fails, the corrupt proxy file is deleted so the next
    call to :func:`create_proxy` triggers a fresh encode.

    Parameters
    ----------
    proxy_path:
        Path to the proxy MP4 to validate.
    source:
        Original source file (used for error context only).

    Raises
    ------
    ProxyValidationError
        If the proxy has no video stream, an unexpected codec type, or
        zero duration.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        str(proxy_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        _remove_corrupt(proxy_path)
        raise ProxyValidationError(proxy_path, f"Could not probe proxy: {exc}") from exc

    streams = data.get("streams", [])

    if not streams:
        _remove_corrupt(proxy_path)
        raise ProxyValidationError(proxy_path, "No video streams found in proxy output.")

    stream = streams[0]

    if stream.get("codec_type") != "video":
        _remove_corrupt(proxy_path)
        raise ProxyValidationError(
            proxy_path,
            f"Expected video stream but found codec_type='{stream.get('codec_type')}'.",
        )

    duration = float(stream.get("duration", 0))
    if duration <= 0:
        _remove_corrupt(proxy_path)
        raise ProxyValidationError(
            proxy_path,
            "Proxy duration is zero — the file may be corrupt or truncated.",
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _remove_corrupt(path: Path) -> None:
    """Delete *path* if it exists, silently ignoring any OS errors."""
    try:
        path.unlink()
    except OSError:
        pass
