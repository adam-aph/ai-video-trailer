"""Hybrid keyframe timestamp collection and JPEG extraction.

Combines three sources of keyframe timestamps:
  1. Subtitle midpoints  (primary — PIPE-03)
  2. Scene-change detection on the proxy (supplementary — PySceneDetect)
  3. Interval fallback at every 30s for any gap > 30s (coverage guarantee)

Raw FFmpeg errors are translated into ``KeyframeExtractionError`` — callers
never see raw subprocess output.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from scenedetect import detect, ContentDetector

from cinecut.errors import KeyframeExtractionError
from cinecut.models import KeyframeRecord


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_keyframe_timestamps(
    proxy: Path,
    subtitle_midpoints: list[float],
    gap_threshold_s: float = 30.0,
    interval_s: float = 30.0,
) -> list[float]:
    """Collect a deduplicated sorted list of PTS seconds for frame extraction.

    Parameters
    ----------
    proxy:
        Path to the 420p analysis proxy (scene detection runs on this, not
        the source — avoids reading the full-resolution file).
    subtitle_midpoints:
        Primary timestamps from subtitle dialogue events.
    gap_threshold_s:
        Gaps between consecutive timestamps greater than this value will
        receive interval-fallback coverage.  Default 30s.
    interval_s:
        Spacing between interval-fallback timestamps.  Default 30s.

    Returns
    -------
    list[float]
        Sorted, deduplicated PTS seconds covering subtitles, scene changes,
        and intervals with no gap longer than *gap_threshold_s*.
    """
    timestamps: set[float] = set(subtitle_midpoints)

    # Supplementary: scene-change midpoints from PySceneDetect
    scenes = detect(str(proxy), ContentDetector(threshold=27.0))
    for start, end in scenes:
        mid = round((start.get_seconds() + end.get_seconds()) / 2.0, 3)
        timestamps.add(mid)

    sorted_ts = sorted(timestamps)

    # Interval fallback: fill gaps > gap_threshold_s
    filled: list[float] = list(sorted_ts)
    i = 0
    while i < len(filled) - 1:
        prev = filled[i]
        nxt = filled[i + 1]
        if nxt - prev > gap_threshold_s:
            insert_at = prev + interval_s
            while insert_at < nxt:
                filled.append(insert_at)
                insert_at += interval_s
            filled = sorted(set(filled))
            # Do not advance i — re-check the same gap after insertion
            continue
        i += 1

    return sorted(set(filled))


def extract_frame(proxy: Path, timestamp_s: float, output_path: Path) -> None:
    """Extract a single JPEG frame from *proxy* at *timestamp_s*.

    Uses pre-seek (``-ss`` before ``-i``) for fast, keyframe-aligned
    extraction suitable for the 24fps analysis proxy.

    Parameters
    ----------
    proxy:
        Path to the analysis proxy video.
    timestamp_s:
        PTS position in seconds.
    output_path:
        Destination JPEG path (will be created or overwritten).

    Raises
    ------
    KeyframeExtractionError
        If FFmpeg exits non-zero.
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp_s),
        "-i", str(proxy),
        "-frames:v", "1",
        "-q:v", "2",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise KeyframeExtractionError(
            timestamp_s,
            exc.stderr.decode("utf-8", errors="replace"),
        ) from exc


def extract_all_keyframes(
    proxy: Path,
    timestamps: list[float],
    keyframes_dir: Path,
    subtitle_midpoints: set[float] | None = None,
    progress_callback: Callable[[], None] | None = None,
) -> list[KeyframeRecord]:
    """Extract JPEG frames for every timestamp in *timestamps*.

    The operation is idempotent: if a frame file already exists at the
    expected path it is skipped (allowing resume after interruption).

    Parameters
    ----------
    proxy:
        Path to the analysis proxy video.
    timestamps:
        Sorted list of PTS seconds from :func:`collect_keyframe_timestamps`.
    keyframes_dir:
        Directory where JPEG files will be written.  Created if absent.
    subtitle_midpoints:
        Set of timestamps that came from subtitle midpoints; used to infer
        the ``source`` field on each :class:`KeyframeRecord`.  Defaults to
        an empty set (all frames labelled ``"scene_change"``).
    progress_callback:
        Optional callable invoked once per extracted frame (not called for
        skipped/cached frames).  Used by the CLI to advance a progress bar.

    Returns
    -------
    list[KeyframeRecord]
        One record per timestamp, in input order.
    """
    keyframes_dir.mkdir(exist_ok=True)
    _subtitle_midpoints: set[float] = subtitle_midpoints if subtitle_midpoints is not None else set()

    records: list[KeyframeRecord] = []
    for timestamp_s in timestamps:
        filename = f"frame_{int(timestamp_s * 1000):010d}.jpg"
        output_path = keyframes_dir / filename

        if not output_path.exists():
            extract_frame(proxy, timestamp_s, output_path)
            if progress_callback is not None:
                progress_callback()

        records.append(
            KeyframeRecord(
                timestamp_s=timestamp_s,
                frame_path=str(output_path.resolve()),
                source=_infer_source(timestamp_s, _subtitle_midpoints),
            )
        )

    return records


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _infer_source(ts: float, subtitle_midpoints: set[float]) -> str:
    """Return the source label for a keyframe timestamp.

    Parameters
    ----------
    ts:
        The timestamp in PTS seconds.
    subtitle_midpoints:
        Set of timestamps that originated from subtitle dialogue midpoints.

    Returns
    -------
    str
        ``"subtitle_midpoint"`` if *ts* is in *subtitle_midpoints*, else
        ``"scene_change"`` (interval-fallback timestamps are indistinguishable
        from scene-change timestamps post-merge; this is acceptable).
    """
    if ts in subtitle_midpoints:
        return "subtitle_midpoint"
    return "scene_change"
