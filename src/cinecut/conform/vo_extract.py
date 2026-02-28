"""VO (voice-over) clip extraction from source film subtitle events.

Implements VONR-01, VONR-02, VONR-03:
- Protagonist identification via pysubs2 SSAEvent.name Counter
- Output-seeking FFmpeg extraction (-ss before -i)
- 0.8s minimum clip duration enforcement
- AAC 48000Hz stereo re-encode
- Acts 1 and 2 only (no CLIMAX / Act 3 VO)
- Up to 3 clips: 1 from Act 1 (BEGINNING), up to 2 from Act 2 (ESCALATION)
"""
import logging
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pysubs2

from cinecut.manifest.schema import TrailerManifest

logger = logging.getLogger(__name__)

# Acts that belong to each VO zone
_ACT1_ACTS: frozenset[str] = frozenset({"cold_open", "act1"})
_ACT2_ACTS: frozenset[str] = frozenset({"beat_drop", "act2"})

# Minimum clip duration in seconds (VONR-03)
_MIN_DURATION_S: float = 0.8


@dataclass
class VoClip:
    path: Path        # path to extracted .aac file
    timeline_s: float # position in trailer timeline where this VO should play
    act_zone: str     # "act1" or "act2"


def identify_protagonist(subtitle_path: Path) -> str | None:
    """Return the most-speaking named character from an ASS subtitle file.

    Uses pysubs2 SSAEvent.name to count speaker occurrences.
    Returns None for SRT files or ASS files with no speaker attribution
    (all event.name fields empty).

    Args:
        subtitle_path: Path to .ass or .srt subtitle file.

    Returns:
        Speaker name string if found, None otherwise.
    """
    subs = pysubs2.load(str(subtitle_path), encoding="utf-8")
    names = [
        e.name.strip()
        for e in subs
        if not e.is_comment and e.name.strip()
    ]
    if not names:
        return None
    return Counter(names).most_common(1)[0][0]


def extract_vo_clips(
    manifest: TrailerManifest,
    source: Path,
    subtitle_path: Path,
    work_dir: Path,
) -> list[VoClip]:
    """Extract protagonist VO audio clips from the source film.

    Selects subtitle events spoken by the protagonist that fall within
    Act 1 (BEGINNING) or Act 2 (ESCALATION) clips. Extracts up to 1
    clip from Act 1 and up to 2 from Act 2, favouring longer duration.

    All clips are re-encoded to AAC 48000Hz stereo using output-seeking
    FFmpeg (-ss before -i). Source is always the original film, not proxy.

    Args:
        manifest:      TrailerManifest with clips list and optional anchors.
        source:        Path to the original source film file (not proxy).
        subtitle_path: Path to .ass or .srt subtitle file.
        work_dir:      Working directory; VO files written to work_dir/vo/.

    Returns:
        List of VoClip for successfully extracted clips (may be empty).
    """
    protagonist = identify_protagonist(subtitle_path)
    if protagonist is None:
        # Graceful degradation — SRT or ASS with no speaker names
        logger.warning(
            "vo_extract: no speaker names found in '%s'; skipping VO extraction",
            subtitle_path.name,
        )
        return []

    logger.debug("vo_extract: protagonist identified as '%s'", protagonist)

    # Create output directory
    vo_dir = work_dir / "vo"
    vo_dir.mkdir(parents=True, exist_ok=True)

    # Load subtitle events with timing
    subs = pysubs2.load(str(subtitle_path), encoding="utf-8")

    # Build trailer timeline offsets: timeline_offsets[i] = start time in trailer for clip i
    timeline_offsets: list[float] = []
    accumulated: float = 0.0
    for clip in manifest.clips:
        timeline_offsets.append(accumulated)
        accumulated += clip.source_end_s - clip.source_start_s

    # Partition clips by zone
    act1_indices = [
        i for i, c in enumerate(manifest.clips)
        if c.act in _ACT1_ACTS
    ]
    act2_indices = [
        i for i, c in enumerate(manifest.clips)
        if c.act in _ACT2_ACTS
    ]
    # Act 3 / CLIMAX intentionally excluded — no VO from those clips

    def _find_candidates(clip_indices: list[int]) -> list[dict]:
        """Find protagonist subtitle events overlapping the given clip indices."""
        candidates: list[dict] = []
        for idx in clip_indices:
            clip = manifest.clips[idx]
            for event in subs:
                if event.is_comment:
                    continue
                if event.name.strip().lower() != protagonist.lower():
                    continue
                start_s = event.start / 1000.0
                end_s = event.end / 1000.0
                duration = end_s - start_s
                # Must be fully contained within the source clip window
                if start_s < clip.source_start_s or end_s > clip.source_end_s:
                    continue
                # Enforce minimum duration (VONR-03)
                if duration < _MIN_DURATION_S:
                    continue
                timeline_s = timeline_offsets[idx] + (start_s - clip.source_start_s)
                candidates.append({
                    "start_s": start_s,
                    "end_s": end_s,
                    "duration": duration,
                    "timeline_s": timeline_s,
                })
        # Sort by duration descending so we pick the longest lines first
        candidates.sort(key=lambda c: c["duration"], reverse=True)
        return candidates

    # Select candidates per zone
    act1_candidates = _find_candidates(act1_indices)[:1]   # up to 1 from Act 1
    act2_candidates = _find_candidates(act2_indices)[:2]   # up to 2 from Act 2

    selected = [
        ("act1", c) for c in act1_candidates
    ] + [
        ("act2", c) for c in act2_candidates
    ]

    # Extract each selected clip via FFmpeg
    results: list[VoClip] = []
    for n, (act_zone, cand) in enumerate(selected):
        output_path = vo_dir / f"vo_{n}.aac"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(cand["start_s"]),   # output-seeking: -ss BEFORE -i
            "-i", str(source),
            "-t", str(cand["duration"]),
            "-vn",
            "-c:a", "aac",
            "-ar", "48000",
            "-ac", "2",
            "-b:a", "192k",
            str(output_path),
        ]
        logger.debug("vo_extract: extracting %s: %s", output_path.name, " ".join(cmd))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            logger.warning(
                "vo_extract: FFmpeg failed for '%s' (rc=%d); skipping. stderr: %s",
                output_path.name,
                proc.returncode,
                proc.stderr[-400:],
            )
            continue
        results.append(VoClip(
            path=output_path,
            timeline_s=cand["timeline_s"],
            act_zone=act_zone,
        ))

    logger.info(
        "vo_extract: extracted %d VO clip(s) for protagonist '%s'",
        len(results),
        protagonist,
    )
    return results
