"""BPM detection, octave correction, beat grid generation, and beat-snap for Phase 9 (BPMG-01, BPMG-02, BPMG-03)."""

import librosa
import numpy as np
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Vibe BPM defaults and ranges
# ---------------------------------------------------------------------------

VIBE_BPM_DEFAULTS: dict[str, float] = {
    "action": 128.0,
    "adventure": 110.0,
    "animation": 100.0,
    "comedy": 95.0,
    "crime": 105.0,
    "documentary": 75.0,
    "drama": 80.0,
    "family": 95.0,
    "fantasy": 105.0,
    "history": 80.0,
    "horror": 90.0,
    "music": 120.0,
    "mystery": 88.0,
    "romance": 80.0,
    "sci-fi": 115.0,
    "thriller": 120.0,
    "war": 118.0,
    "western": 90.0,
}

VIBE_BPM_RANGES: dict[str, tuple[float, float]] = {
    "action": (100.0, 160.0),
    "adventure": (90.0, 140.0),
    "animation": (80.0, 130.0),
    "comedy": (75.0, 130.0),
    "crime": (80.0, 140.0),
    "documentary": (55.0, 110.0),
    "drama": (60.0, 110.0),
    "family": (75.0, 130.0),
    "fantasy": (80.0, 140.0),
    "history": (55.0, 110.0),
    "horror": (60.0, 130.0),
    "music": (90.0, 160.0),
    "mystery": (65.0, 120.0),
    "romance": (60.0, 110.0),
    "sci-fi": (90.0, 150.0),
    "thriller": (90.0, 150.0),
    "war": (90.0, 150.0),
    "western": (65.0, 125.0),
}

# ---------------------------------------------------------------------------
# BpmGrid dataclass
# ---------------------------------------------------------------------------


@dataclass
class BpmGrid:
    bpm: float                  # Resolved BPM after octave correction or fallback
    beat_times_s: list[float]   # Beat timestamps in seconds, all >= 0.0
    source: str                 # "librosa" or "vibe_default"
    beat_count: int = 0         # len(beat_times_s), set in generate_beat_grid


# ---------------------------------------------------------------------------
# BPM resolution with octave correction (BPMG-03)
# ---------------------------------------------------------------------------


def resolve_bpm(raw_bpm: float, vibe: str) -> float:
    """Apply BPMG-03: 0-BPM guard, octave-error correction, vibe-default fallback."""
    vibe_min, vibe_max = VIBE_BPM_RANGES.get(vibe, (60.0, 160.0))
    vibe_default = VIBE_BPM_DEFAULTS.get(vibe, 100.0)

    # Guard 1: no onset detected — librosa returns 0 or near-zero BPM
    if raw_bpm < 10.0:
        return vibe_default

    # Guard 2: half-tempo octave error — double it
    if raw_bpm < vibe_min * 0.7 and vibe_min <= raw_bpm * 2.0 <= vibe_max:
        return raw_bpm * 2.0

    # Guard 3: double-tempo octave error — halve it
    if raw_bpm > vibe_max * 1.4 and vibe_min <= raw_bpm / 2.0 <= vibe_max:
        return raw_bpm / 2.0

    # Guard 4: still out of range after correction attempts — use vibe default
    if not (vibe_min <= raw_bpm <= vibe_max):
        return vibe_default

    # In range — no correction needed
    return raw_bpm


# ---------------------------------------------------------------------------
# Beat grid generation (BPMG-01, BPMG-03)
# ---------------------------------------------------------------------------


def generate_beat_grid(audio_path: str, vibe: str, duration_s: float) -> BpmGrid:
    """Load audio, detect BPM, generate beat timestamps (BPMG-01, BPMG-03). Always returns valid BpmGrid."""
    vibe_default = VIBE_BPM_DEFAULTS.get(vibe, 100.0)

    try:
        # Inner try: load audio and run beat tracker
        try:
            y, sr = librosa.load(audio_path, sr=22050, mono=True)
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        except Exception:
            tempo = 0.0
            beat_frames = np.array([])

        # PITFALL 1: librosa may return tempo as np.ndarray (newer versions return scalar)
        raw_bpm = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)

        resolved_bpm = resolve_bpm(raw_bpm, vibe)

        # Determine source: "librosa" only when BPM passed through without correction
        source = "librosa" if (resolved_bpm == raw_bpm and raw_bpm >= 10.0) else "vibe_default"

        if source == "librosa" and len(beat_frames) > 0:
            raw_times = librosa.frames_to_time(beat_frames, sr=22050)
            beat_times = [t for t in raw_times.tolist() if t >= 0.0]  # PITFALL 6: filter negatives
        else:
            # Synthesize a regular grid from the resolved BPM
            beat_interval_s = 60.0 / resolved_bpm
            beat_times = list(np.arange(0.0, duration_s, beat_interval_s))

        return BpmGrid(
            bpm=resolved_bpm,
            beat_times_s=beat_times,
            source=source,
            beat_count=len(beat_times),
        )

    except Exception:
        # Outer fallback: synthesize grid from vibe default
        beat_interval_s = 60.0 / vibe_default
        beat_times = list(np.arange(0.0, duration_s, beat_interval_s))
        return BpmGrid(
            bpm=vibe_default,
            beat_times_s=beat_times,
            source="vibe_default",
            beat_count=len(beat_times),
        )


# ---------------------------------------------------------------------------
# Beat snapping (BPMG-02)
# ---------------------------------------------------------------------------


def snap_to_nearest_beat(start_s: float, beat_times_s: list[float], bpm: float) -> float:
    """Snap clip start time to nearest beat within +/-1 beat tolerance (BPMG-02).

    Returns start_s unchanged if no beat within tolerance.
    Result is always clamped to >= 0.0.
    """
    if not beat_times_s:
        return start_s

    beat_interval_s = 60.0 / max(bpm, 10.0)  # +/-1 beat tolerance window
    beat_arr = np.array(beat_times_s)
    distances = np.abs(beat_arr - start_s)
    nearest_idx = int(np.argmin(distances))

    if distances[nearest_idx] <= beat_interval_s:
        return max(0.0, float(beat_arr[nearest_idx]))  # PITFALL 6: clamp >= 0.0

    return start_s  # No beat within tolerance — keep original
