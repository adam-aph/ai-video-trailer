"""SFX synthesis and timeline overlay for CineCut trailer generation.

Implements two public functions:
- synthesize_sfx_files(): Generate two sweep WAV tiers via FFmpeg aevalsrc (no external files)
- apply_sfx_to_timeline(): Overlay synthesized SFX at scene-cut positions using adelay

All synthesis is at 48000Hz stereo PCM — AMIX-03 compliant.
"""

import shutil
import subprocess
from pathlib import Path

from cinecut.manifest.schema import TrailerManifest
from cinecut.errors import ConformError

# Hard-cut transition: short high-to-low chirp sweep (0.4s)
SFX_HARD_DURATION_S: float = 0.4

# Act-boundary transition: longer low-to-high chirp sweep with Gaussian envelope (1.2s)
SFX_BOUNDARY_DURATION_S: float = 1.2


def synthesize_sfx_files(work_dir: Path) -> tuple[Path, Path]:
    """Generate two SFX sweep WAV files via FFmpeg aevalsrc — no external files required.

    Creates work_dir/sfx/ if it does not exist. If both WAV files already exist
    the function returns immediately (idempotent — avoids ~2-3s FFmpeg call on resume).

    SFX tiers:
    - sfx_hard.wav   : 0.4s high-to-low linear chirp (3000Hz -> 300Hz), exponential decay
    - sfx_boundary.wav : 1.2s low-to-high linear chirp (200Hz -> 2000Hz), Gaussian envelope

    Chirp formula uses slope = (f1 - f0) / (2 * d) for instantaneous frequency at time t:
        f(t) = f0 + slope * t
        phase = 2*PI * f(t) * t  (NOT the integral — keeps linear freq progression)

    All output at 48000Hz, stereo PCM s16le.

    Args:
        work_dir: Pipeline working directory; sfx/ subdir is created here.

    Returns:
        Tuple of (sfx_hard_path, sfx_boundary_path).

    Raises:
        ConformError: If either FFmpeg synthesis call fails.
    """
    sfx_dir = work_dir / "sfx"
    sfx_dir.mkdir(parents=True, exist_ok=True)

    sfx_hard_path = sfx_dir / "sfx_hard.wav"
    sfx_boundary_path = sfx_dir / "sfx_boundary.wav"

    # Idempotent: skip synthesis if both files already exist
    if sfx_hard_path.exists() and sfx_boundary_path.exists():
        return sfx_hard_path, sfx_boundary_path

    # --- sfx_hard.wav ---
    # High-to-low linear chirp: 3000Hz -> 300Hz over 0.4s
    # slope = (300 - 3000) / (2 * 0.4) = -3375 Hz/s
    # envelope: 0.6 * exp(-3 * t)   (exponential decay)
    # expression: 0.6*exp(-3*t)*sin(2*PI*(3000+(-3375)*t)*t)
    hard_expr = "0.6*exp(-3*t)*sin(2*PI*(3000+(-3375)*t)*t)"
    hard_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"aevalsrc={hard_expr}:s=48000:d={SFX_HARD_DURATION_S}:c=stereo",
        "-ar", "48000",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(sfx_hard_path),
    ]
    result = subprocess.run(hard_cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConformError(sfx_hard_path, result.stderr[-500:])

    # --- sfx_boundary.wav ---
    # Low-to-high linear chirp: 200Hz -> 2000Hz over 1.2s
    # slope = (2000 - 200) / (2 * 1.2) = 750 Hz/s
    # Gaussian envelope: 0.5 * (1 - exp(-2*t)) * exp(-0.5 * pow(t-0.6, 2) / 0.15)
    # expression: 0.5*(1-exp(-2*t))*exp(-0.5*pow(t-0.6,2)/0.15)*sin(2*PI*(200+750*t)*t)
    boundary_expr = "0.5*(1-exp(-2*t))*exp(-0.5*pow(t-0.6,2)/0.15)*sin(2*PI*(200+750*t)*t)"
    boundary_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"aevalsrc={boundary_expr}:s=48000:d={SFX_BOUNDARY_DURATION_S}:c=stereo",
        "-ar", "48000",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(sfx_boundary_path),
    ]
    result = subprocess.run(boundary_cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConformError(sfx_boundary_path, result.stderr[-500:])

    return sfx_hard_path, sfx_boundary_path


def apply_sfx_to_timeline(
    manifest: TrailerManifest,
    sfx_hard: Path,
    sfx_boundary: Path,
    work_dir: Path,
    concat_duration_s: float,
) -> Path:
    """Overlay SFX sweep sounds at scene-cut positions in the assembled timeline.

    Each clip's timeline start time is accumulated from preceding clip durations.
    SFX is positioned slightly before each cut so the sweep peaks at the cut:
    - Hard cut (transition == "hard_cut"): sfx_hard (0.4s), lead = SFX_HARD_DURATION_S / 4 = 0.1s
    - Soft/boundary cut (all other transitions, or first clip of act3): sfx_boundary (1.2s),
      lead = SFX_BOUNDARY_DURATION_S / 4 = 0.3s

    Clips with act == "title_card" or "button" are skipped (generated segments, no SFX).
    Clip index 0 is always skipped (no cut before the first clip).

    All adelay offsets are in milliseconds (as required by FFmpeg adelay filter).
    amix uses normalize=0 — mandatory to preserve ducking ratios.

    Args:
        manifest: Assembled TrailerManifest (clips with transition and act fields).
        sfx_hard: Path to the synthesized sfx_hard.wav.
        sfx_boundary: Path to the synthesized sfx_boundary.wav.
        work_dir: Pipeline working directory; output written to work_dir/sfx/sfx_mix.wav.
        concat_duration_s: Total duration of the assembled clip timeline in seconds.

    Returns:
        Path to work_dir/sfx/sfx_mix.wav.

    Raises:
        ConformError: If FFmpeg filtergraph fails.
    """
    sfx_dir = work_dir / "sfx"
    sfx_dir.mkdir(parents=True, exist_ok=True)
    sfx_mix_path = sfx_dir / "sfx_mix.wav"

    # Accumulate timeline positions and build SFX placement list
    # List of (sfx_path, position_s)
    placements: list[tuple[Path, float]] = []

    # Detect which clips are the first clip of act3 (ESCALATION->CLIMAX boundary)
    act3_first_index: int | None = None
    for i, clip in enumerate(manifest.clips):
        if clip.act == "act3" and i > 0:
            act3_first_index = i
            break

    timeline_pos_s = 0.0
    for i, clip in enumerate(manifest.clips):
        clip_duration_s = clip.source_end_s - clip.source_start_s

        if i == 0:
            # No cut before the first clip
            timeline_pos_s += clip_duration_s
            continue

        # Skip generated segments
        if clip.act in ("title_card", "button"):
            timeline_pos_s += clip_duration_s
            continue

        # Classify SFX tier for this cut
        is_boundary_cut = (
            clip.transition in ("crossfade", "fade_to_black", "fade_to_white")
            or i == act3_first_index
        )

        if is_boundary_cut:
            lead_s = SFX_BOUNDARY_DURATION_S / 4  # 0.3s
            sfx_path = sfx_boundary
        else:
            # Default: hard cut
            lead_s = SFX_HARD_DURATION_S / 4  # 0.1s
            sfx_path = sfx_hard

        # Position: sweep peaks at the cut (start of this clip on timeline)
        position_s = max(0.0, timeline_pos_s - lead_s)
        placements.append((sfx_path, position_s))

        timeline_pos_s += clip_duration_s

    # Edge case: no cuts found (single-clip manifest) — copy sfx_hard as placeholder
    if not placements:
        shutil.copy2(sfx_hard, sfx_mix_path)
        return sfx_mix_path

    # Build FFmpeg command with adelay + amix filtergraph
    # Inputs: sfx_hard (index 0) + sfx_boundary (index 1) + ... wait, we need one input
    # per placement event. Build unique input list and map positions.
    #
    # Strategy: use one input per placement (may repeat sfx_hard or sfx_boundary paths).
    # FFmpeg supports duplicate input paths fine.
    cmd: list[str] = ["ffmpeg", "-y"]

    # Add one -i per placement
    for sfx_path, _ in placements:
        cmd += ["-i", str(sfx_path)]

    # Build filtergraph
    filter_parts: list[str] = []
    sfx_labels: list[str] = []

    for idx, (_, position_s) in enumerate(placements):
        offset_ms = int(position_s * 1000)
        delay_filter = f"[{idx}:a]adelay={offset_ms}|{offset_ms}[sfx{idx}]"
        filter_parts.append(delay_filter)
        sfx_labels.append(f"[sfx{idx}]")

    # Mix all delayed SFX streams together (normalize=0 — mandatory)
    n_inputs = len(placements)
    mix_inputs = "".join(sfx_labels)
    filter_parts.append(f"{mix_inputs}amix=inputs={n_inputs}:normalize=0[sfx_mix]")

    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[sfx_mix]",
        "-ar", "48000",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(sfx_mix_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConformError(sfx_mix_path, result.stderr[-500:])

    return sfx_mix_path
