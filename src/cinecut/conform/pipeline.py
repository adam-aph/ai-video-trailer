"""FFmpeg conform pipeline for CineCut trailer generation.

Implements three functions:
- extract_and_grade_clip(): Frame-accurate clip extraction with lut3d + loudnorm
- concatenate_clips(): Concat demuxer approach for combining clips
- conform_manifest(): Main orchestrator that processes a TrailerManifest into a final MP4
"""

import json
import re
import subprocess
from pathlib import Path

from cinecut.manifest.schema import TrailerManifest
from cinecut.manifest.vibes import VIBE_PROFILES
from cinecut.conform.luts import ensure_luts
from cinecut.errors import ConformError

# Short clips below this duration skip two-pass loudnorm (Act 3 montage clips 1.2-1.8s)
MIN_LOUDNORM_DURATION_S = 3.0


def extract_and_grade_clip(
    source: Path,
    start_s: float,
    end_s: float,
    lut_path: Path,
    lufs_target: float,
    output_path: Path,
) -> Path:
    """Extract a frame-accurate clip with LUT grading and audio normalization.

    Uses -ss before -i for frame-accurate seek (not nearest keyframe).

    For clips < 3.0s: applies lut3d + volume=0dB in a single FFmpeg pass.
    For clips >= 3.0s: two-pass loudnorm using JSON stats from stderr of pass 1.

    Args:
        source: Input video file path.
        start_s: Clip start time in seconds (frame-accurate).
        end_s: Clip end time in seconds.
        lut_path: Path to the .cube LUT file.
        lufs_target: Integrated loudness target in LUFS (negative float).
        output_path: Destination MP4 path.

    Returns:
        output_path on success.

    Raises:
        ConformError: If FFmpeg fails at any stage.
    """
    duration = end_s - start_s

    if duration < MIN_LOUDNORM_DURATION_S:
        # Single-pass: apply LUT + volume=0dB (no-op gain) for short clips
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_s),
            "-i", str(source),
            "-t", str(duration),
            "-vf", f"lut3d=file={lut_path}",
            "-af", "volume=0dB",
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-ar", "48000",
            "-avoid_negative_ts", "make_zero",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ConformError(output_path, result.stderr[-500:])
    else:
        # Two-pass loudnorm for clips >= 3.0s
        # Pass 1: measure loudness stats
        pass1_cmd = [
            "ffmpeg",
            "-ss", str(start_s),
            "-i", str(source),
            "-t", str(duration),
            "-af", f"loudnorm=I={lufs_target}:LRA=7:tp=-2:print_format=json",
            "-f", "null",
            "-",
        ]
        pass1_result = subprocess.run(
            pass1_cmd, capture_output=True, text=True, check=False
        )

        # Parse JSON stats from stderr
        json_match = re.search(r"\{[^}]+\}", pass1_result.stderr, re.DOTALL)
        if not json_match:
            raise ConformError(
                output_path,
                "loudnorm pass 1 did not produce JSON stats",
            )

        try:
            stats = json.loads(json_match.group())
        except json.JSONDecodeError as exc:
            raise ConformError(
                output_path,
                f"loudnorm pass 1 JSON parse error: {exc}",
            ) from exc

        input_i = stats.get("input_i", "0")
        input_lra = stats.get("input_lra", "0")
        input_tp = stats.get("input_tp", "0")
        input_thresh = stats.get("input_thresh", "0")
        target_offset = stats.get("target_offset", "0")

        # Pass 2: apply LUT + linear normalization using measured stats
        loudnorm_filter = (
            f"loudnorm=I={lufs_target}:LRA=7:tp=-2"
            f":measured_I={input_i}"
            f":measured_LRA={input_lra}"
            f":measured_tp={input_tp}"
            f":measured_thresh={input_thresh}"
            f":offset={target_offset}"
            f":linear=true"
        )
        pass2_cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_s),
            "-i", str(source),
            "-t", str(duration),
            "-vf", f"lut3d=file={lut_path}",
            "-af", loudnorm_filter,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-ar", "48000",
            "-avoid_negative_ts", "make_zero",
            str(output_path),
        ]
        pass2_result = subprocess.run(
            pass2_cmd, capture_output=True, text=True, check=False
        )
        if pass2_result.returncode != 0:
            raise ConformError(output_path, pass2_result.stderr[-500:])

    return output_path


def concatenate_clips(clip_paths: list[Path], output_path: Path) -> Path:
    """Concatenate multiple clips into a single MP4 using the FFmpeg concat demuxer.

    Args:
        clip_paths: Ordered list of clip file paths to concatenate.
        output_path: Destination MP4 path.

    Returns:
        output_path on success.

    Raises:
        ConformError: If FFmpeg concat fails.
    """
    concat_list = output_path.parent / "_concat_list.txt"

    with open(concat_list, "w", encoding="utf-8") as f:
        for p in clip_paths:
            # Escape single quotes in path (for ffmpeg concat list format)
            escaped = str(p).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        concat_list.unlink(missing_ok=True)
        raise ConformError(output_path, result.stderr[-500:])

    concat_list.unlink(missing_ok=True)
    return output_path


def make_output_path(source: Path, vibe: str) -> Path:
    """Build the output trailer path per CLI-04 naming convention.

    Pattern: {source.stem}_trailer_{vibe_slug}.mp4

    Args:
        source: Original video source path.
        vibe: Normalized vibe name (e.g. "sci-fi").

    Returns:
        Output path alongside the source file.
    """
    vibe_slug = vibe.replace("-", "_")
    return source.parent / f"{source.stem}_trailer_{vibe_slug}.mp4"


def conform_manifest(
    manifest: TrailerManifest,
    source: Path,
    work_dir: Path,
    extra_clip_paths: list[Path] | None = None,
    inject_after_clip: int | None = None,
    inject_paths: list[Path] | None = None,
) -> Path:
    """Orchestrate full conform: extract+grade each clip, then concatenate.

    Args:
        manifest: Validated TrailerManifest with clips to extract.
        source: Original video file path (used for extraction and output naming).
        work_dir: Working directory for intermediate files (luts/ and conform_clips/).
        extra_clip_paths: Optional list of pre-encoded clip paths (e.g. title_card.mp4,
            button.mp4) to append AFTER the manifest clips in the final concat list.
            Backward-compatible — defaults to None (no extra clips appended).
        inject_after_clip: If provided, inject_paths are inserted into the concat list
            AFTER the Nth extracted clip (0-indexed count of clips before insertion).
            Used for EORD-04 silence segment at the ESCALATION->CLIMAX boundary.
        inject_paths: Pre-encoded clip paths to inject at inject_after_clip position.
            Ignored if inject_after_clip is None.

    Returns:
        Path to the final trailer MP4.

    Raises:
        ConformError: If any FFmpeg operation fails.
        ValueError: If manifest.vibe is not a known vibe (programming error).
    """
    # Look up vibe profile (vibe already normalized by schema validator)
    profile = VIBE_PROFILES[manifest.vibe]

    # Ensure LUT file exists (generate if needed)
    lut_path = ensure_luts(manifest.vibe, work_dir / "luts")

    # Create conform_clips directory
    clips_dir = work_dir / "conform_clips"
    clips_dir.mkdir(exist_ok=True)

    # Extract and grade each clip
    clip_output_paths: list[Path] = []

    # EORD-04: inject silence before all clips when inject_after_clip == 0
    if inject_after_clip == 0 and inject_paths:
        clip_output_paths.extend(inject_paths)

    for i, clip in enumerate(manifest.clips):
        output = clips_dir / f"clip_{i:04d}.mp4"
        extract_and_grade_clip(
            source=source,
            start_s=clip.source_start_s,
            end_s=clip.source_end_s,
            lut_path=lut_path,
            lufs_target=profile.lufs_target,
            output_path=output,
        )
        clip_output_paths.append(output)
        # EORD-04: inject silence (or other pre-encoded clips) after specified clip index
        if inject_after_clip is not None and inject_after_clip != 0 and inject_paths and i == inject_after_clip - 1:
            clip_output_paths.extend(inject_paths)

    # Append pre-encoded extra clips (title_card, button) after act3 clips
    if extra_clip_paths:
        clip_output_paths.extend(extra_clip_paths)

    # Build final output path and concatenate
    final_output_path = make_output_path(source, manifest.vibe)
    concatenate_clips(clip_output_paths, final_output_path)

    return final_output_path
