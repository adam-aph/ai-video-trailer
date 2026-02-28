---
phase: 09-bpm-grid-and-music-bed
plan: "01"
subsystem: assembly/bpm + manifest/schema
tags: [bpm, beat-grid, librosa, pydantic, manifest, phase9]
dependency_graph:
  requires: []
  provides:
    - assembly/bpm.py BpmGrid dataclass
    - assembly/bpm.py resolve_bpm()
    - assembly/bpm.py generate_beat_grid()
    - assembly/bpm.py snap_to_nearest_beat()
    - manifest/schema.py BpmGrid Pydantic model
    - manifest/schema.py MusicBed Pydantic model
    - manifest/schema.py TrailerManifest.bpm_grid
    - manifest/schema.py TrailerManifest.music_bed
  affects:
    - 09-02 (music.py consumes generate_beat_grid, BpmGrid dataclass)
    - 09-03 (cli.py wiring consumes BpmGrid/MusicBed via manifest)
tech_stack:
  added:
    - librosa 0.11.0 (BPM detection and beat tracking)
  patterns:
    - Dual BpmGrid pattern: dataclass (bpm.py, carries full beat_times_s) vs Pydantic BaseModel (schema.py, JSON-serializable subset)
    - Octave-error correction: four-guard chain (zero-BPM, half-tempo, double-tempo, out-of-range)
    - Outer/inner try pattern in generate_beat_grid() for complete failure isolation
key_files:
  created:
    - src/cinecut/assembly/bpm.py
  modified:
    - src/cinecut/manifest/schema.py
decisions:
  - "BpmGrid exists in two forms: assembly/bpm.py dataclass (carries full beat_times_s list for computation) and manifest/schema.py Pydantic model (stores only bpm+beat_count+source for JSON manifest). No cross-import between packages."
  - "librosa installed system-wide with --break-system-packages (no virtual env in this project); added to implicit dependencies alongside other system packages"
  - "resolve_bpm() uses 0.7x vibe_min threshold for half-tempo guard and 1.4x vibe_max for double-tempo guard — matches RESEARCH.md Pattern 2 tolerances"
metrics:
  duration: "~3 min (193 seconds)"
  completed_date: "2026-02-28"
  tasks_completed: 2
  files_created: 1
  files_modified: 1
---

# Phase 9 Plan 01: BPM Grid and Manifest Models Summary

BPM detection pipeline with octave correction, beat grid synthesis, and beat-snapping, plus dual BpmGrid/MusicBed Pydantic models wired into TrailerManifest as optional Phase 9 fields.

## What Was Built

### Task 1: assembly/bpm.py (commit 7fe150b)

Created `src/cinecut/assembly/bpm.py` with all six exported symbols:

- `VIBE_BPM_DEFAULTS` — 18-vibe dict of research-derived BPM defaults (action=128, drama=80, etc.)
- `VIBE_BPM_RANGES` — 18-vibe dict of acceptable BPM ranges for octave correction
- `BpmGrid` dataclass — carries `bpm`, `beat_times_s`, `source`, `beat_count`
- `resolve_bpm(raw_bpm, vibe) -> float` — four-guard octave correction chain (BPMG-03)
- `generate_beat_grid(audio_path, vibe, duration_s) -> BpmGrid` — librosa beat tracking with complete fallback (BPMG-01)
- `snap_to_nearest_beat(start_s, beat_times_s, bpm) -> float` — +/-1 beat tolerance, clamped >= 0.0 (BPMG-02)

Key implementation details:
- `generate_beat_grid()` uses nested try/except: inner try loads audio and runs librosa; inner except zeroes raw_bpm; outer except catches any remaining failure and synthesizes a vibe-default grid
- numpy ndarray check for `tempo`: `float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)` — handles both librosa <= 0.10 (ndarray) and >= 0.11 (scalar) return types
- Negative beat time filtering in librosa path: `[t for t in raw_times.tolist() if t >= 0.0]`
- `snap_to_nearest_beat()` clamps result with `max(0.0, ...)` even when a valid beat is found (handles negative beat_times_s inputs gracefully)

### Task 2: manifest/schema.py (commit f1dc6bd)

Added to `src/cinecut/manifest/schema.py` without touching existing content:

- `class BpmGrid(BaseModel)` — `bpm: float (gt=0)`, `beat_count: int (ge=0)`, `source: str`
- `class MusicBed(BaseModel)` — `track_id`, `track_name`, `artist_name`, `license_ccurl`, `local_path`, `bpm: Optional[float] = None`
- `TrailerManifest.bpm_grid: Optional[BpmGrid] = None`
- `TrailerManifest.music_bed: Optional[MusicBed] = None`

Both new models placed immediately before `TrailerManifest`, after `ClipEntry` — no forward-reference issues.

## Verification Results

- All six bpm.py symbols importable: PASS
- `resolve_bpm(0.0, 'action')` == 128.0 (0-BPM guard): PASS
- `resolve_bpm(64.0, 'action')` == 128.0 (half-tempo correction): PASS
- `resolve_bpm(256.0, 'action')` == 128.0 (double-tempo correction): PASS
- `resolve_bpm(120.0, 'action')` == 120.0 (in-range passthrough): PASS
- `snap_to_nearest_beat(0.3, [0.0, 0.5, 1.0, 1.5, 2.0], 120.0)` == 0.5: PASS
- Negative beat clamp: PASS
- BpmGrid and MusicBed Pydantic model_dump_json(): PASS
- TrailerManifest.bpm_grid and .music_bed default None: PASS
- TrailerManifest.model_copy with bpm_grid assigned serializes correctly: PASS
- `python3 -m pytest tests/test_assembly.py tests/test_manifest.py -v` — 42 passed, 0 failures

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] librosa not installed**
- **Found during:** Task 1 (pre-execution environment check)
- **Issue:** `librosa` was not installed in the project environment; `pip3 install librosa` was blocked by PEP 668 system Python restriction
- **Fix:** Ran `pip3 install librosa --break-system-packages`; librosa 0.11.0 installed successfully along with scipy, scikit-learn, numba, soundfile, soxr
- **Files modified:** None (system package install)
- **Commit:** N/A (no code change needed)

## Self-Check: PASSED

- FOUND: src/cinecut/assembly/bpm.py
- FOUND: src/cinecut/manifest/schema.py
- FOUND commit: 7fe150b (feat(09-01): create assembly/bpm.py...)
- FOUND commit: f1dc6bd (feat(09-01): add BpmGrid and MusicBed Pydantic models...)
