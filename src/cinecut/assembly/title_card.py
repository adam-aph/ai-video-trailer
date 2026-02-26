"""FFmpeg lavfi-based title card and button segment generation."""
import json
import subprocess
from pathlib import Path

from cinecut.errors import ConformError


def get_video_dimensions(source: Path) -> tuple[int, int]:
    """Return (width, height) of first video stream via ffprobe JSON output.

    Falls back to (1920, 1080) if ffprobe fails (Pitfall 6: ffprobe may not be in PATH
    on some installs; both ffmpeg and ffprobe are confirmed present on this machine).
    """
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        str(source),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return (1920, 1080)
    try:
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if streams:
            return (int(streams[0]["width"]), int(streams[0]["height"]))
    except (json.JSONDecodeError, KeyError, ValueError):
        pass
    return (1920, 1080)


def generate_title_card(
    title_text: str,
    width: int,
    height: int,
    duration_s: float,
    output_path: Path,
    font_size: int = 64,
) -> Path:
    """Generate a pre-encoded black MP4 segment via FFmpeg lavfi color source.

    For Phase 5, title_text="" generates a plain black frame (no text overlay).
    Uses the same codec/framerate as extract_and_grade_clip() to ensure concat
    demuxer compatibility: libx264 crf=18 preset=veryfast, aac 48000Hz.

    Args:
        title_text: Text to overlay on black. Empty string = plain black card.
        width: Video width in pixels (match source resolution).
        height: Video height in pixels.
        duration_s: Duration of the segment in seconds.
        output_path: Destination .mp4 path.
        font_size: drawtext font size (only used when title_text is non-empty).

    Returns:
        output_path on success.

    Raises:
        ConformError: If FFmpeg lavfi generation fails.
    """
    if title_text:
        vf = (
            f"color=c=black:s={width}x{height}:r=24,"
            f"drawtext=text='{title_text}':fontsize={font_size}"
            f":fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2"
        )
    else:
        vf = f"color=c=black:s={width}x{height}:r=24"

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", vf,
        "-t", str(duration_s),
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=48000",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-ar", "48000",
        "-t", str(duration_s),
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConformError(output_path, result.stderr[-500:])
    return output_path
