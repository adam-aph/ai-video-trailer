# Phase 9: BPM Grid and Music Bed - Research

**Researched:** 2026-02-28
**Domain:** librosa BPM detection, Jamendo API v3, FFmpeg silence generation, permanent per-vibe music cache
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BPMG-01 | System detects music track BPM using librosa and generates a beat timestamp grid | `librosa.beat.beat_track(y, sr)` returns `(tempo_ndarray, beat_frames)`; convert with `librosa.frames_to_time(beat_frames, sr=sr)` for timestamp grid |
| BPMG-02 | Clip start points snap to the nearest beat grid position (within ±1 beat tolerance) | Simple linear scan: for each `source_start_s`, find the beat timestamp minimizing `abs(beat_t - start_s)`, clamp within 1-beat window |
| BPMG-03 | System falls back to vibe-default BPM when detection returns 0, half, or double tempo | 0-BPM guard: `if bpm < 10.0: use vibe_default_bpm`. Octave guard: `if bpm > vibe_max * 1.6: bpm /= 2` and `if bpm < vibe_min * 0.6: bpm *= 2` |
| EORD-04 | A deliberate silence segment (3-5s black video + muted audio) is inserted at the Act 2→3 boundary | FFmpeg lavfi: `ffmpeg -f lavfi -i color=c=black:s=WxH:r=FR:d=DUR -f lavfi -i anullsrc=r=48000 -shortest -c:v libx264 -c:a aac silence.mp4`; inserted as extra_clip between ESCALATION and CLIMAX clips |
| MUSC-01 | System selects a CC-licensed music track per vibe from the Jamendo API v3 | `GET https://api.jamendo.com/v3.0/tracks/?client_id=CID&tags=TAG&format=json&limit=10&order=popularity_total&audioformat=mp32` — client_id from env var `JAMENDO_CLIENT_ID` |
| MUSC-02 | Downloaded tracks are permanently cached per vibe at `~/.cinecut/music/`; Jamendo API never called if cached | Cache check: `cache_dir / f"{vibe}.mp3"` exists → return path without API call |
| MUSC-03 | Pipeline continues without music (no abort) when Jamendo API is unavailable or returns an error | Wrap entire `fetch_music_for_vibe()` in `try/except Exception` → log warning + return None; callers check None and skip music mixing |
</phase_requirements>

---

## Summary

Phase 9 adds two new modules (`assembly/bpm.py` and `assembly/music.py`) and modifies `assembly/ordering.py` to insert the Act 2→3 silence segment. The three plans map cleanly onto independent technical domains: BPM detection from a downloaded audio file (librosa), music fetching from the Jamendo REST API with permanent per-vibe disk cache (`requests` + stdlib path ops), and silence generation via FFmpeg lavfi to fulfill EORD-04.

The librosa `beat_track` function returns a 1-D NumPy ndarray for tempo (not a plain float, since librosa 0.10.2+), and the raw BPM must be guarded for the 0-BPM case (no onset detected) and the octave-error case (half or double tempo). Vibe-specific BPM default values must be defined per `VibeProfile` and used when detection fails. Beat snapping for clip start points is a simple nearest-neighbor search over the generated timestamp array — no third-party library is needed for this computation.

The Jamendo API v3 is a public REST API requiring a free developer account `client_id`. The `audiodownload_allowed` field (mandatory since April 2022 — tracks returning 404 for download when `false`) must be checked before attempting any binary download. Music files are streamed to `~/.cinecut/music/{vibe}.mp3` using `requests` with `stream=True` and 8 KB chunk writes. On any API failure (network timeout, non-200 status, missing client_id, `audiodownload_allowed=False`), the function returns `None` and the pipeline continues without music, satisfying MUSC-03.

**Primary recommendation:** Use `librosa==0.11.0`, `soundfile>=0.12.1` (MP3 support via libsndfile 1.1.0+), and `requests>=2.31.0` (already in pyproject.toml). FFmpeg (already in the stack) generates the silence segment. All new code lives in `assembly/` alongside existing `ordering.py`.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| librosa | 0.11.0 | BPM detection via `beat_track`, frame-to-time conversion | The standard Python audio analysis library; `beat_track` is the documented beat estimation API |
| soundfile | >=0.12.1 | Loading MP3/OGG/FLAC audio files for librosa | Required by librosa as primary I/O backend; 0.12+ bundles libsndfile with MP3 support |
| numpy | >=1.24.0 (already installed) | Beat frame array operations, nearest-neighbor beat snapping | Already in pyproject.toml; librosa returns numpy arrays |
| requests | >=2.31.0 (already installed) | Jamendo API JSON call + MP3 binary download via stream=True | Already in pyproject.toml; standard HTTP client for the project |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| FFmpeg (subprocess) | system (already used) | Generate black+silent MP4 for Act 2→3 boundary segment | Already used in `conform/pipeline.py`; lavfi color+anullsrc approach proven in project |
| pathlib.Path | stdlib | Cache dir management (`~/.cinecut/music/`) | Already used throughout project |
| os.environ | stdlib | Read `JAMENDO_CLIENT_ID` env var | Standard; avoids hardcoding credentials |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| librosa beat_track | essentia, madmom | Both much heavier to install (C++ build deps); librosa is already the standard Python choice |
| librosa + soundfile for MP3 | FFmpeg probe (ffprobe -i audio.mp3 -show_entries format=bit_rate) | FFprobe can measure duration/BPM via stream metadata but not actual beat detection; librosa is the only Python-native solution |
| Jamendo API | Epidemic Sound, Musicbed | Paid licensing; Jamendo is the only major CC-licensed free API with programmatic access |
| requests stream download | urllib.request | requests already in pyproject.toml; urllib.request would work but inconsistent with project pattern |
| FFmpeg lavfi silence | synthesize via numpy + soundfile | FFmpeg already in stack; lavfi is simpler and produces the exact codec format needed for concat demuxer |

**Installation:**
```bash
pip install librosa soundfile
```

`requests` and `numpy` are already installed. `soundfile>=0.12.1` bundles libsndfile 1.1.0 on Linux (MP3 support included). No additional system libraries needed.

**pyproject.toml additions:**
```toml
"librosa>=0.11.0",
"soundfile>=0.12.1",
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/cinecut/
├── assembly/
│   ├── bpm.py           # NEW (09-01): BpmGrid, detect_bpm(), generate_beat_grid(), snap_clip_starts()
│   ├── music.py         # NEW (09-02): MusicBed, fetch_music_for_vibe(), BPM_DEFAULTS, cache management
│   ├── ordering.py      # MODIFY (09-03): insert_act2_act3_silence() adds silence segment at ESCALATION→CLIMAX boundary
│   └── __init__.py      # Already exists
├── manifest/
│   └── schema.py        # MODIFY (09-02): BpmGrid and MusicBed models added; TrailerManifest fields added
└── cli.py               # MODIFY (09-03): Stage numbering may adjust; silence insertion wired into assemble step
```

### Pattern 1: librosa BPM Detection with Return Type Guard

**What:** `librosa.beat.beat_track()` returns `tempo` as a 1-D NumPy ndarray (since 0.10.2+), not a scalar float. Must convert explicitly with `float(tempo[0])` or `float(tempo.item())`.

**When to use:** In `assembly/bpm.py`, `detect_bpm()` function.

```python
# Source: librosa 0.11.0 docs https://librosa.org/doc/main/generated/librosa.beat.beat_track.html
# Source: librosa GitHub issue #1867 (resolved: ndarray behavior is codified)
import librosa
import numpy as np

def detect_bpm(audio_path: str) -> float:
    """Detect BPM from audio file. Returns float BPM or 0.0 on failure.

    Uses librosa.beat.beat_track with sr=22050 (librosa default).
    Returns 0.0 if no onset is detected (documented edge case).
    """
    try:
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        # tempo is ALWAYS a 1-D ndarray since librosa 0.10.2 (issue #1867)
        bpm = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
        return bpm
    except Exception:
        return 0.0  # Failed to load or detect — caller applies vibe-default fallback
```

**Critical:** `tempo[0]` not `tempo` — accessing element 0 handles the 1-D array case and raises a clear IndexError if the array is unexpectedly empty (better than silent NaN).

### Pattern 2: Octave Error Correction via Vibe BPM Range Clamp

**What:** librosa's beat tracker has a well-documented octave error problem where it returns half or double the true BPM. The BPMG-03 requirement calls this "half or double tempo". The fix is range-clamping against vibe-expected BPM ranges.

**When to use:** In `assembly/bpm.py`, `apply_bpm_fallback()` or inline in `detect_bpm_for_vibe()`.

```python
# Source: REQUIREMENTS.md BPMG-03 spec + librosa community known issue
# Octave correction: if detected BPM is outside [vibe_min, vibe_max], try halving or doubling

VIBE_BPM_DEFAULTS: dict[str, float] = {
    "action":       128.0,
    "adventure":    110.0,
    "animation":    100.0,
    "comedy":        95.0,
    "crime":        105.0,
    "documentary":   75.0,
    "drama":         80.0,
    "family":        95.0,
    "fantasy":      105.0,
    "history":       80.0,
    "horror":        90.0,
    "music":        120.0,
    "mystery":       88.0,
    "romance":       80.0,
    "sci-fi":       115.0,
    "thriller":     120.0,
    "war":          118.0,
    "western":       90.0,
}

# Acceptable BPM range per vibe (outside this → octave error suspected)
VIBE_BPM_RANGES: dict[str, tuple[float, float]] = {
    "action":       (100.0, 160.0),
    "adventure":    ( 90.0, 140.0),
    "animation":    ( 80.0, 130.0),
    "comedy":       ( 75.0, 130.0),
    "crime":        ( 80.0, 140.0),
    "documentary":  ( 55.0, 110.0),
    "drama":        ( 60.0, 110.0),
    "family":       ( 75.0, 130.0),
    "fantasy":      ( 80.0, 140.0),
    "history":      ( 55.0, 110.0),
    "horror":       ( 60.0, 130.0),
    "music":        ( 90.0, 160.0),
    "mystery":      ( 65.0, 120.0),
    "romance":      ( 60.0, 110.0),
    "sci-fi":       ( 90.0, 150.0),
    "thriller":     ( 90.0, 150.0),
    "war":          ( 90.0, 150.0),
    "western":      ( 65.0, 125.0),
}


def resolve_bpm(raw_bpm: float, vibe: str) -> float:
    """Apply BPMG-03: 0-BPM guard, then octave-error correction, then vibe-default fallback.

    1. If raw_bpm == 0: return vibe default (no onset detected)
    2. If raw_bpm*2 fits vibe range but raw_bpm doesn't: double it (half-tempo octave error)
    3. If raw_bpm/2 fits vibe range but raw_bpm doesn't: halve it (double-tempo octave error)
    4. If still outside range: return vibe default (detection unreliable)
    """
    vibe_min, vibe_max = VIBE_BPM_RANGES.get(vibe, (60.0, 160.0))
    vibe_default = VIBE_BPM_DEFAULTS.get(vibe, 100.0)

    # Guard 1: 0-BPM (no onset detected)
    if raw_bpm < 10.0:
        return vibe_default

    # Guard 2: Octave correction — half-tempo (double it)
    if raw_bpm < vibe_min * 0.7 and vibe_min <= raw_bpm * 2.0 <= vibe_max:
        return raw_bpm * 2.0

    # Guard 3: Octave correction — double-tempo (halve it)
    if raw_bpm > vibe_max * 1.4 and vibe_min <= raw_bpm / 2.0 <= vibe_max:
        return raw_bpm / 2.0

    # Guard 4: Still out of vibe range after correction → use default
    if not (vibe_min <= raw_bpm <= vibe_max):
        return vibe_default

    return raw_bpm
```

### Pattern 3: Beat Grid Generation and Beat Snapping

**What:** Convert detected beat frames to timestamps, then snap each clip's `source_start_s` to the nearest beat within ±1 beat tolerance.

**When to use:** In `assembly/bpm.py`, `generate_beat_grid()` and `snap_clip_starts()`.

```python
# Source: librosa 0.11.0 docs https://librosa.org/doc/main/generated/librosa.frames_to_time.html
import librosa
import numpy as np
from dataclasses import dataclass

@dataclass
class BpmGrid:
    """BPM grid produced by Phase 9 beat detection."""
    bpm: float                     # Resolved BPM (after octave correction / fallback)
    beat_times_s: list[float]      # Beat timestamps in seconds
    source: str                    # "librosa" | "vibe_default" (how bpm was determined)


def generate_beat_grid(
    audio_path: str,
    vibe: str,
    duration_s: float,
) -> BpmGrid:
    """Load audio, detect BPM, generate beat timestamps.

    Returns BpmGrid with beat_times_s ready for use in snap_clip_starts().
    Always returns a valid grid even on any failure (uses vibe-default BPM).
    """
    try:
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        raw_bpm = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
    except Exception:
        raw_bpm = 0.0

    resolved_bpm = resolve_bpm(raw_bpm, vibe)
    source = "librosa" if resolved_bpm == raw_bpm else "vibe_default"

    if len(beat_frames) > 0 and source == "librosa":
        # Use detected beat frames for precise grid
        beat_times = librosa.frames_to_time(beat_frames, sr=22050).tolist()
    else:
        # Synthesize regular grid from BPM (vibe default case)
        beat_interval_s = 60.0 / resolved_bpm
        beat_times = list(np.arange(0.0, duration_s, beat_interval_s))

    return BpmGrid(bpm=resolved_bpm, beat_times_s=beat_times, source=source)


def snap_to_nearest_beat(start_s: float, beat_times_s: list[float], bpm: float) -> float:
    """Snap a clip start time to the nearest beat within ±1 beat tolerance.

    If no beat is within 1 beat (60/BPM seconds), return start_s unchanged.
    """
    if not beat_times_s:
        return start_s
    beat_interval_s = 60.0 / max(bpm, 10.0)  # guard against 0-BPM (shouldn't reach here)
    tolerance_s = beat_interval_s  # ±1 beat
    beat_arr = np.array(beat_times_s)
    distances = np.abs(beat_arr - start_s)
    nearest_idx = int(np.argmin(distances))
    if distances[nearest_idx] <= tolerance_s:
        return float(beat_arr[nearest_idx])
    return start_s  # No beat within tolerance — keep original
```

**Why `±1 beat` tolerance:** BPMG-02 specifies "within one beat of the detected BPM grid". A 120 BPM track has 0.5s between beats — snapping within ±0.5s means the clip never shifts more than half a bar.

### Pattern 4: Jamendo API Fetch with Per-Vibe Cache

**What:** Check `~/.cinecut/music/{vibe}.mp3` before calling the Jamendo API. If absent, call the tracks endpoint, select the first result with `audiodownload_allowed=True`, download binary to the cache path.

**When to use:** In `assembly/music.py`, `fetch_music_for_vibe()`.

```python
# Source: Jamendo API v3 docs https://developer.jamendo.com/v3.0/tracks
# Source: Python requests streaming download pattern
import os
import requests
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


JAMENDO_TRACKS_URL = "https://api.jamendo.com/v3.0/tracks/"

# Map vibe → Jamendo genre tag (Jamendo featured tags for genre searches)
VIBE_TO_JAMENDO_TAG: dict[str, str] = {
    "action":       "action",
    "adventure":    "adventure",
    "animation":    "pop",
    "comedy":       "pop",
    "crime":        "darkambient",
    "documentary":  "documentary",
    "drama":        "dramatic",
    "family":       "pop",
    "fantasy":      "epic",
    "history":      "classical",
    "horror":       "darkambient",
    "music":        "pop",
    "mystery":      "darkambient",
    "romance":      "romantic",
    "sci-fi":       "electronic",
    "thriller":     "dramatic",
    "war":          "epic",
    "western":      "acoustic",
}


@dataclass
class MusicBed:
    """Music track selected for Phase 9 music bed."""
    track_id: str
    track_name: str
    artist_name: str
    license_ccurl: str
    local_path: str   # path to cached file at ~/.cinecut/music/{vibe}.mp3
    bpm: Optional[float] = None  # filled in after BPM detection in 09-01


def get_music_cache_dir() -> Path:
    """Return ~/.cinecut/music/, creating it if needed."""
    cache_dir = Path.home() / ".cinecut" / "music"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def fetch_music_for_vibe(vibe: str) -> Optional[MusicBed]:
    """Fetch or return cached CC-licensed music track for the given vibe.

    MUSC-02: If ~/.cinecut/music/{vibe}.mp3 exists, return immediately (no API call).
    MUSC-03: Any exception → log warning, return None (pipeline continues without music).

    Requires: JAMENDO_CLIENT_ID env var set to a valid Jamendo API client_id.
    """
    try:
        cache_dir = get_music_cache_dir()
        cached_path = cache_dir / f"{vibe}.mp3"

        # MUSC-02: Cache hit — return without API call
        if cached_path.exists():
            # We don't have metadata from cache — return a minimal MusicBed
            return MusicBed(
                track_id="cached",
                track_name=f"{vibe} (cached)",
                artist_name="unknown",
                license_ccurl="",
                local_path=str(cached_path),
            )

        # MUSC-01: Cache miss — call Jamendo API
        client_id = os.environ.get("JAMENDO_CLIENT_ID", "")
        if not client_id:
            raise ValueError("JAMENDO_CLIENT_ID env var not set")

        tag = VIBE_TO_JAMENDO_TAG.get(vibe, "pop")
        params = {
            "client_id": client_id,
            "format": "json",
            "limit": "10",
            "tags": tag,
            "order": "popularity_total",
            "audioformat": "mp32",
            "include": "musicinfo",
        }
        resp = requests.get(JAMENDO_TRACKS_URL, params=params, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        tracks = data.get("results", [])
        if not tracks:
            raise ValueError(f"Jamendo returned 0 tracks for tag '{tag}'")

        # Select first track with audiodownload_allowed=True
        selected = None
        for track in tracks:
            if track.get("audiodownload_allowed", False):
                selected = track
                break

        if selected is None:
            raise ValueError("No downloadable tracks in Jamendo results")

        # Download audio binary to cache path
        download_url = selected["audiodownload"]
        if not download_url:
            raise ValueError("Track has no audiodownload URL")

        with requests.get(download_url, stream=True, timeout=60) as dl:
            dl.raise_for_status()
            with open(cached_path, "wb") as f:
                for chunk in dl.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        return MusicBed(
            track_id=str(selected["id"]),
            track_name=selected.get("name", "unknown"),
            artist_name=selected.get("artist_name", "unknown"),
            license_ccurl=selected.get("license_ccurl", ""),
            local_path=str(cached_path),
        )

    except Exception as exc:
        # MUSC-03: Any failure → warn, return None, pipeline continues
        import logging
        logging.getLogger("cinecut").warning(
            "Music bed unavailable for vibe '%s': %s — trailer will be produced without music",
            vibe, exc,
        )
        return None
```

**Important:** `audiodownload_allowed` must be checked. Since April 2022, the Jamendo `/v3.0/tracks/file` endpoint returns 404 for tracks where this is `False`. We use the `audiodownload` URL from the tracks endpoint response directly — this is the download URL already in the tracks response (no separate `/tracks/file` call needed).

### Pattern 5: FFmpeg Silence Segment for EORD-04

**What:** Generate a 3-5 second black video + silent audio MP4 and insert it between the last ESCALATION zone clip and the first CLIMAX zone clip in the assembly output.

**When to use:** In `assembly/ordering.py`, new `generate_silence_segment()` function + modified `assemble_manifest()`.

```python
# Source: FFmpeg lavfi color + anullsrc pattern — verified against project's conform/pipeline.py patterns
import subprocess
from pathlib import Path
from cinecut.errors import ConformError

SILENCE_DURATION_S = 4.0   # 3-5s deliberate black silence (EORD-04)


def generate_silence_segment(
    work_dir: Path,
    width: int,
    height: int,
    frame_rate: str,
    duration_s: float = SILENCE_DURATION_S,
) -> Path:
    """Generate a black video with silent audio as a temporary MP4 for concat.

    Args:
        work_dir: Directory for intermediate files.
        width: Video width in pixels (should match clip resolution).
        height: Video height in pixels.
        frame_rate: Video frame rate string (e.g., "24", "25", "30").
        duration_s: Duration of silence segment in seconds.

    Returns:
        Path to the generated silence MP4.

    Raises:
        ConformError: If FFmpeg fails to generate the segment.
    """
    output_path = work_dir / "silence_act2_act3.mp4"

    cmd = [
        "ffmpeg", "-y",
        # Video source: black frame
        "-f", "lavfi",
        "-i", f"color=c=black:s={width}x{height}:r={frame_rate}:d={duration_s}",
        # Audio source: silence at 48000Hz stereo
        "-f", "lavfi",
        "-i", f"anullsrc=r=48000:cl=stereo",
        "-shortest",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-ar", "48000",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConformError(output_path, result.stderr[-500:])
    return output_path
```

**Resolution and frame rate:** The silence segment must match the resolution and frame rate of the clip sources so the concat demuxer works without re-encoding. The proxy is 420p; the source resolution must be detected or passed through. For Phase 9, use the proxy resolution (width from proxy creation: 420p = 720x420 typical, but actual proxy dimensions depend on the input AR). Use FFprobe to detect, or simply hardcode a default matching the proxy's typical output. See pitfall section on resolution mismatch.

**Insertion point in ordering.py:** After `sort_clips_by_zone()`, find the split index between ESCALATION and CLIMAX zones. Insert the silence segment path into the `extra_paths` list passed to `conform_manifest()` at the correct position.

### Pattern 6: BpmGrid and MusicBed Manifest Models

**What:** Add `BpmGrid` and `MusicBed` as Pydantic models in `manifest/schema.py`; add them as optional fields on `TrailerManifest` for recording detection metadata.

**When to use:** In `manifest/schema.py` and populated in the new `assembly/bpm.py` and `assembly/music.py` before final manifest write.

```python
# Source: project schema.py existing Pydantic pattern (BaseModel, Optional, Field)
from typing import Optional
from pydantic import BaseModel, Field


class BpmGrid(BaseModel):
    """BPM grid metadata recorded in the manifest (BPMG-01, BPMG-03)."""
    bpm: float = Field(gt=0.0, description="Resolved BPM after octave correction / fallback")
    beat_count: int = Field(ge=0, description="Number of detected beat timestamps")
    source: str = Field(description="'librosa' if detected, 'vibe_default' if fallback was used")


class MusicBed(BaseModel):
    """Music track metadata recorded in the manifest (MUSC-01, MUSC-02)."""
    track_id: str
    track_name: str
    artist_name: str
    license_ccurl: str
    local_path: str   # absolute path to ~/.cinecut/music/{vibe}.mp3
    bpm: Optional[float] = None   # filled after beat detection runs on the music file


# In TrailerManifest:
class TrailerManifest(BaseModel):
    schema_version: str = "2.0"   # already bumped by Phase 7
    source_file: str
    vibe: str
    clips: list[ClipEntry] = Field(min_length=1)
    # Phase 7 additions (already present):
    structural_anchors: Optional["StructuralAnchors"] = None
    # Phase 9 additions:
    bpm_grid: Optional[BpmGrid] = None        # None if BPM detection skipped
    music_bed: Optional[MusicBed] = None      # None if music unavailable (MUSC-03)
```

**Note:** `BpmGrid` reuses the name from the dataclass in `assembly/bpm.py`, but the manifest model is a Pydantic `BaseModel` for JSON serialization. The dataclass in `assembly/bpm.py` carries the full `beat_times_s` list for computation; the manifest model stores only summary metadata (bpm, beat_count, source) to avoid serializing potentially thousands of floats.

### Anti-Patterns to Avoid

- **Call `librosa.beat.beat_track()` and use `tempo` directly as a float:** Since 0.10.2 it is always a 1-D ndarray. Use `float(tempo[0])`.
- **Omit the `audiodownload_allowed` check on Jamendo results:** Since April 2022, tracks with `audiodownload_allowed=False` return HTTP 404 for downloads. Always filter results.
- **Raise an exception on music failure:** MUSC-03 explicitly requires the pipeline to continue without music. The entire `fetch_music_for_vibe()` must be wrapped in try/except.
- **Store beat_times_s (potentially 1000+ floats) directly in TrailerManifest JSON:** Keep manifest storage minimal — just `bpm`, `beat_count`, `source`. Beat timestamps are runtime-only data.
- **Hard-code silence segment dimensions (1920x1080):** The project generates 420p proxy clips. The silence segment must match the conform resolution (not necessarily HD). Use proxy dimensions or probed source dimensions.
- **Install librosa without soundfile 0.12+:** On Linux, `pip install librosa` will get soundfile but the bundled libsndfile may be older than 1.1.0. Explicitly pin `soundfile>=0.12.1` to ensure MP3 support for the downloaded Jamendo files.
- **Put music fetch in a new CLI stage with its own checkpoint:** Music fetching is fast (API + download on first run, instant cache hit on subsequent runs). It does not need a checkpoint stage. Run it as part of the assembly stage (Stage 6, pre-conform).
- **Call Jamendo API without checking env var:** If `JAMENDO_CLIENT_ID` is not set, the API returns HTTP 401. Check env var presence before the request and treat absence as a graceful failure (MUSC-03 covers this).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| BPM detection from audio | FFT-based autocorrelation from scratch | `librosa.beat.beat_track(y, sr)` | librosa's DP beat tracker handles onset detection, autocorrelation, and tightness constraints correctly; edge cases (silence, single beat) are handled |
| Beat timestamp generation | Compute `beat_num * (60 / bpm)` from scratch | `librosa.frames_to_time(beat_frames, sr=sr)` | Frame-aligned timestamps account for hop_length offset precisely; arithmetic from scratch accumulates floating-point error |
| MP3 file decoding | Wave parsing or subprocess ffmpeg decode | `librosa.load(path, sr=22050)` via soundfile | soundfile handles all format negotiation; librosa handles resampling |
| HTTP streaming download | urllib.request with manual chunking | `requests.get(url, stream=True)` with `iter_content(8192)` | requests already in pyproject.toml; handles redirects, encoding, and connection reuse correctly |
| Black video generation | Write raw frames as numpy array | FFmpeg lavfi `color=c=black` filter | FFmpeg is already the conforming engine; lavfi handles pixel format, frame rate, and codec encoding for concat compatibility |
| Silence audio generation | Synthesize zero-array to WAV | FFmpeg lavfi `anullsrc=r=48000` | Single-command output; produces AAC at exactly 48000Hz matching the rest of the pipeline |

**Key insight:** All three technical problems in Phase 9 (BPM detection, music fetching, silence generation) have established library solutions that handle codec negotiation, edge cases, and format compatibility. The implementation effort is in the guards and integration, not in the algorithms.

---

## Common Pitfalls

### Pitfall 1: tempo is a 1-D ndarray, Not a float

**What goes wrong:** `float(tempo)` raises `TypeError: only length-1 arrays can be converted to Python scalars` when `tempo` is a 1-D ndarray with one element.

**Why it happens:** librosa 0.10.2 introduced array broadcasting for multichannel support. `tempo` is now always returned as `ndarray` even for mono input. The closed issue #1867 codified this as intentional.

**How to avoid:** Use `float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)`. Or use `float(tempo.item())` which works for any ndarray with a single element.

**Warning signs:** `TypeError: only length-1 arrays can be converted` at BPM detection time; JSON serialization errors when storing BPM.

### Pitfall 2: librosa Cannot Load MP3 Without soundfile >= 0.12.1

**What goes wrong:** `librosa.load("track.mp3")` raises `NoBackendError` or `RuntimeError: Error opening file` on Linux when the installed libsndfile is older than 1.1.0.

**Why it happens:** MP3 support in libsndfile requires version 1.1.0+. On Linux, `pip install soundfile` may bundle an older libsndfile. `soundfile>=0.12.1` bundles libsndfile 1.1.0+ on Linux.

**How to avoid:** Pin `soundfile>=0.12.1` in pyproject.toml. Verify in CI: `python -c "import soundfile; print(soundfile.__version__)"`. The Jamendo download format is `mp32` (MP3 VBR) — librosa must be able to read it.

**Warning signs:** `LibsndfileError: Error opening file` or `RuntimeError` when calling `librosa.load` on `.mp3` files; no error on `.ogg` or `.wav` files.

### Pitfall 3: audiodownload_allowed=False Returns HTTP 404 Since April 2022

**What goes wrong:** Calling the `audiodownload` URL for a track where `audiodownload_allowed` is `False` returns HTTP 404. The `requests.get` download raises `HTTPError: 404`.

**Why it happens:** Jamendo changed policy in April 2022: artists who don't permit downloads now cause the download endpoint to return 404 rather than serving the file.

**How to avoid:** Always filter the tracks list to `track["audiodownload_allowed"] == True` before selecting. Do NOT just pick the first result. If no downloadable track is found among 10 results, raise an exception (which is caught by the outer try/except — MUSC-03 handles it).

**Warning signs:** HTTP 404 on `audiodownload` URL even though the track exists on the Jamendo website; works for some vibes but not others.

### Pitfall 4: Silence Segment Resolution Mismatch Breaks Concat

**What goes wrong:** The concat demuxer in `conform/pipeline.py` (`-c copy`) requires all input streams to have identical codec parameters (resolution, frame rate, sample rate). If the silence segment is generated at 1920x1080 while clips are extracted at 420p, FFmpeg errors: `"Concatenation not possible due to inconsistent stream resolution."` or silently produces corrupt output.

**Why it happens:** The silence generation uses hard-coded dimensions instead of detecting the actual clip resolution.

**How to avoid:** Detect proxy resolution before generating the silence segment. The project uses `create_proxy()` which produces a specific resolution. Either: (a) probe the proxy file with `ffprobe` to get width/height, or (b) use the known proxy height (420p) and compute width from a stored AR. For Phase 9, a reasonable default is to use 640x360 (420p widescreen approximation) or probe the actual proxy. Document this clearly in the plan.

**Warning signs:** FFmpeg concat errors mentioning "resolution" or "codec"; trailer plays fine up to the silence segment then fails.

### Pitfall 5: Jamendo API Rate Limiting or Client ID Registration Required

**What goes wrong:** Calling the Jamendo API without a registered `client_id` returns HTTP 401. Calling it too frequently triggers rate limiting (HTTP 429).

**Why it happens:** The Jamendo API requires free developer account registration at `developer.jamendo.com` to get a `client_id`. Rate limits exist but are not published (generous for reasonable usage).

**How to avoid:** Read `client_id` from `JAMENDO_CLIENT_ID` environment variable. Document in README that this env var must be set before the music bed feature works. MUSC-03's graceful degradation covers the case where it's absent — log a clear warning message including the URL to register.

**Warning signs:** HTTP 401 on API call; no music in output with warning log; users confused why music is skipped.

**STATE.md note:** `[Phase 9]: Jamendo API client_id registration required (free developer account at developer.jamendo.com) before Phase 9 integration testing` — this is already documented as a known blocker.

### Pitfall 6: Beat Snapping Shifts Clips Backward Past Zero

**What goes wrong:** `snap_to_nearest_beat()` snaps a clip starting at 0.3s to a beat at -0.1s (if the beat grid starts slightly before 0). The result is a negative `source_start_s` which fails `ClipEntry` validation (`ge=0.0`).

**Why it happens:** `librosa.beat.beat_track()` sometimes places the first beat before time 0 (due to the trim parameter). Converting beat frames to time can produce negative timestamps for the first beat.

**How to avoid:** Filter beat_times_s to `[t for t in beat_times if t >= 0.0]` after conversion. Also guard in `snap_to_nearest_beat()`: `snapped = max(0.0, snapped_result)`.

**Warning signs:** `ValidationError: source_start_s must be >= 0.0` when constructing snapped ClipEntry objects.

### Pitfall 7: Music Download Overwrites a Partially Written File on Failure

**What goes wrong:** The download starts writing to `~/.cinecut/music/{vibe}.mp3`, fails halfway (network drop, disk full), and leaves a partially written file. On the next run, the cache check sees the file exists and returns the corrupted file without re-downloading.

**Why it happens:** The cache check is simply `cached_path.exists()` — it does not verify file integrity.

**How to avoid:** Write the download to a temp file in the same directory (`{vibe}.mp3.tmp`), then `rename()` (atomic on same filesystem). If download fails, `unlink(missing_ok=True)` the temp file. Only the completed file gets the final name.

**Warning signs:** librosa fails to load the cached MP3 with a libsndfile error; re-running with the same vibe fails despite the file appearing to exist.

---

## Code Examples

Verified patterns from official sources:

### librosa beat_track full workflow

```python
# Source: librosa 0.11.0 https://librosa.org/doc/main/generated/librosa.beat.beat_track.html
# Source: librosa issue #1867 (tempo is always ndarray since 0.10.2)
import librosa
import numpy as np

y, sr = librosa.load("music.mp3", sr=22050, mono=True)
tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)

# tempo is 1-D ndarray — must extract scalar
bpm = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)

# Convert frame indices to seconds
# Source: https://librosa.org/doc/main/generated/librosa.frames_to_time.html
beat_times_s = librosa.frames_to_time(beat_frames, sr=sr)
# beat_times_s is np.ndarray of shape (n_beats,): [0.07, 0.51, 0.93, ...]
```

### Nearest beat snap

```python
# Source: project design (numpy argmin nearest-neighbor)
import numpy as np

def snap_to_nearest_beat(start_s: float, beat_times_s: np.ndarray, bpm: float) -> float:
    beat_interval_s = 60.0 / max(bpm, 10.0)
    distances = np.abs(beat_times_s - start_s)
    nearest_idx = int(np.argmin(distances))
    if distances[nearest_idx] <= beat_interval_s:
        return max(0.0, float(beat_times_s[nearest_idx]))
    return start_s
```

### Jamendo tracks search with download

```python
# Source: Jamendo API v3 https://developer.jamendo.com/v3.0/tracks
import os, requests
from pathlib import Path

client_id = os.environ["JAMENDO_CLIENT_ID"]
resp = requests.get(
    "https://api.jamendo.com/v3.0/tracks/",
    params={
        "client_id": client_id,
        "format": "json",
        "limit": "10",
        "tags": "action",
        "order": "popularity_total",
        "audioformat": "mp32",
    },
    timeout=15,
)
resp.raise_for_status()
tracks = resp.json()["results"]

# Filter to downloadable tracks
downloadable = [t for t in tracks if t.get("audiodownload_allowed")]
selected = downloadable[0]

# Atomic download to cache
tmp_path = Path.home() / ".cinecut/music/action.mp3.tmp"
final_path = Path.home() / ".cinecut/music/action.mp3"
with requests.get(selected["audiodownload"], stream=True, timeout=60) as dl:
    dl.raise_for_status()
    with open(tmp_path, "wb") as f:
        for chunk in dl.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
tmp_path.rename(final_path)  # atomic rename
```

### FFmpeg black silence segment

```python
# Source: FFmpeg lavfi documentation (color filter + anullsrc)
# Verified pattern used in project's conform/pipeline.py subprocess pattern
import subprocess
cmd = [
    "ffmpeg", "-y",
    "-f", "lavfi", "-i", "color=c=black:s=640x360:r=24:d=4.0",
    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
    "-shortest",
    "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
    "-c:a", "aac", "-ar", "48000",
    "silence.mp4",
]
result = subprocess.run(cmd, capture_output=True, text=True, check=False)
if result.returncode != 0:
    raise RuntimeError(result.stderr[-500:])
```

### Pydantic BpmGrid and MusicBed models

```python
# Source: project manifest/schema.py existing Pydantic v2 BaseModel pattern
from pydantic import BaseModel, Field
from typing import Optional

class BpmGrid(BaseModel):
    bpm: float = Field(gt=0.0)
    beat_count: int = Field(ge=0)
    source: str  # "librosa" | "vibe_default"

class MusicBed(BaseModel):
    track_id: str
    track_name: str
    artist_name: str
    license_ccurl: str
    local_path: str
    bpm: Optional[float] = None

# Usage:
bpm_model = BpmGrid(bpm=128.0, beat_count=342, source="librosa")
assert bpm_model.model_dump_json()  # serializes cleanly
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `tempo` returned as `float` | `tempo` always returned as `np.ndarray` | librosa 0.10.2 (PR #1766) | Must always use `float(tempo[0])` instead of `float(tempo)` |
| audioread fallback for MP3 | soundfile primary (deprecated audioread in 0.10) | librosa 0.10.0 | Must install soundfile >= 0.12.1 for MP3 support |
| Jamendo download always worked | `audiodownload_allowed` check required | April 2022 | Tracks with `False` return HTTP 404 on download; filter before selecting |
| No permanent music cache | Permanent per-vibe cache at `~/.cinecut/music/` | Phase 9 (new) | Second run is instant, no API call |

**Deprecated/outdated:**
- `audioread` backend in librosa: deprecated since 0.10.0, will be removed in 1.0. Do not use it — soundfile handles MP3 via libsndfile 1.1.0+.
- Jamendo `tracks/file` endpoint for discovery: use the `/tracks/` search endpoint instead; `/tracks/file` requires knowing the track ID already.

---

## Open Questions

1. **Proxy resolution for silence segment**
   - What we know: `create_proxy()` creates a 420p proxy. The exact pixel dimensions depend on the input video aspect ratio (e.g., 16:9 → 746x420, 2.39:1 → ~1003x420).
   - What's unclear: Phase 9 needs to generate the silence segment at the same resolution as the extracted clips. The clips come from the original source (not the proxy), so the silence should match the source resolution.
   - Recommendation: Use `ffprobe` to probe the source video dimensions before generating the silence segment. Store width/height in the `PipelineCheckpoint` (Phase 9 adds `source_width` and `source_height` fields) or probe at silence-generation time. A simpler alternative: default to the most common HD resolution (1920x1080) and let FFmpeg's concat filter handle minor resolution mismatches via scale filter — but this requires testing.

2. **Where in the pipeline to run music fetch and BPM detection**
   - What we know: Music fetch is the input to BPM detection (need the file to detect BPM). The beat grid is used for clip start snapping which happens before conform. EORD-04 silence insertion also happens before conform.
   - What's unclear: Phase 9 plans specify an "assembly/bpm.py" and "assembly/music.py" — these should run as part of the assembly stage (Stage 6 of the current pipeline, or Stage 7 after Phase 7 renumbers to 8 stages). The Phase 7 plan sets `TOTAL_STAGES=8` and makes the narrative stage Stage 6.
   - Recommendation: Music fetch and BPM detection become a new Stage 7 (between the current assembly Stage 6 and conform Stage 7→8). Add `music` to `stages_complete` checkpoint. This requires bumping `TOTAL_STAGES` to 9 in `cli.py`.

3. **What Jamendo tag to use per vibe when no exact match**
   - What we know: Jamendo's featured genre tags include: lounge, classical, electronic, jazz, pop, hiphop, relaxation, rock, songwriter, world, metal, soundtrack. There is no "thriller" or "action" tag in the featured list.
   - What's unclear: Whether unfeatured tags (like "action") return results from the full catalog or are filtered.
   - Recommendation: Use `fuzzytags` parameter instead of `tags` for non-featured genre names — this enables OR matching across partial tag names. Test with `fuzzytags=action+epic` for action vibe. If no results, fall back to a curated default tag (e.g., `fuzzytags=rock+energetic` for action). The VIBE_TO_JAMENDO_TAG mapping in `music.py` must be empirically validated during plan execution with a real client_id.

4. **Duration of the silence segment (EORD-04 says "3-5s")**
   - What we know: The requirement specifies "3-5s black video + muted audio". No exact duration specified.
   - What's unclear: Whether the silence duration should vary by vibe (e.g., horror gets 5s for dramatic effect, action gets 3s for pacing).
   - Recommendation: Use a fixed 4.0s for all vibes in Phase 9. This can be made vibe-specific in a future phase if desired. Add `SILENCE_DURATION_S = 4.0` as a module-level constant in `assembly/ordering.py`.

---

## Sources

### Primary (HIGH confidence)

- librosa 0.11.0 official docs: `beat_track` — https://librosa.org/doc/main/generated/librosa.beat.beat_track.html
- librosa 0.11.0 official docs: `frames_to_time` — https://librosa.org/doc/main/generated/librosa.frames_to_time.html
- librosa GitHub issue #1867 (closed): tempo as ndarray is intentional since 0.10.2 — https://github.com/librosa/librosa/issues/1867
- librosa PyPI page: version 0.11.0, released March 2025; Python >=3.8; soundfile primary backend — https://pypi.org/project/librosa/
- Jamendo API v3 tracks endpoint: full parameter list, response structure, audiodownload_allowed field — https://developer.jamendo.com/v3.0/tracks
- Jamendo API v3 tracks/file endpoint: HTTP 404 since April 2022 for audiodownload_allowed=False — https://developer.jamendo.com/v3.0/tracks/file
- Project source: `src/cinecut/conform/pipeline.py` — FFmpeg subprocess pattern, codec params (libx264 crf=18, aac ar=48000)
- Project source: `src/cinecut/manifest/schema.py` — Pydantic v2 BaseModel patterns, existing field structure
- Project source: `src/cinecut/manifest/vibes.py` — All 18 VibeProfile entries (used for VIBE_BPM_DEFAULTS design)
- `.planning/REQUIREMENTS.md` — BPMG-01/02/03, MUSC-01/02/03, EORD-04 verbatim specifications
- `.planning/STATE.md` — Phase 9 blocker: Jamendo client_id registration required before integration testing

### Secondary (MEDIUM confidence)

- soundfile PyPI: version 0.12+ bundles libsndfile 1.1.0 with MP3 support on Linux — https://pypi.org/project/soundfile/
- librosa advanced I/O: audioread deprecated 0.10.0, soundfile is primary — https://librosa.org/doc/main/ioformats.html
- FFmpeg lavfi color+anullsrc pattern: verified against multiple sources (yeupou blog, ffmpeg mailing list archive)
- Jamendo API featured genre tags list: lounge, classical, electronic, jazz, pop, hiphop, relaxation, rock, songwriter, world, metal, soundtrack — from API documentation

### Tertiary (LOW confidence)

- VIBE_BPM_DEFAULTS values (action=128, thriller=120, drama=80, etc.): derived from film scoring conventions and trailer music library BPM metadata; not formally verified against Jamendo catalog
- VIBE_BPM_RANGES (e.g., action 100-160): derived from genre BPM knowledge; not formally verified
- Jamendo rate limits: described as "generous" but specific limits not published in documentation
- Jamendo tag behavior for non-featured tags: whether `tags=action` vs `fuzzytags=action` returns different result counts not verified without a live client_id

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — librosa 0.11.0 API verified against official docs; Jamendo API verified against official docs; requests pattern standard; soundfile MP3 requirement verified
- Architecture: HIGH — patterns derived directly from existing project code (subprocess, Pydantic v2, ClipEntry, pipeline.py); librosa return type behavior verified in issue #1867
- Pitfalls: HIGH — ndarray conversion verified from issue; audiodownload_allowed from Jamendo docs; codec mismatch from FFmpeg concat demuxer behavior; temp file atomic rename is standard
- BPM defaults/ranges: LOW — derived from film scoring conventions, not empirically verified against Jamendo catalog

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (librosa API stable; Jamendo API stable; soundfile MP3 requirement stable)
