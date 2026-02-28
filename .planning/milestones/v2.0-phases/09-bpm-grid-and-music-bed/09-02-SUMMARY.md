---
phase: 09-bpm-grid-and-music-bed
plan: "02"
subsystem: assembly/music
tags: [jamendo, music-bed, cache, audio, librosa, soundfile]
dependency_graph:
  requires: []
  provides:
    - assembly/music.py MusicBed dataclass
    - assembly/music.py fetch_music_for_vibe()
    - assembly/music.py VIBE_TO_JAMENDO_TAG (18 vibes)
    - assembly/music.py get_music_cache_dir()
    - librosa>=0.11.0 dependency
    - soundfile>=0.12.1 dependency
  affects:
    - 09-03 (Plan 03 passes MusicBed.local_path to generate_beat_grid())
tech_stack:
  added:
    - librosa>=0.11.0 (BPM detection, audio loading)
    - soundfile>=0.12.1 (MP3 read support via libsndfile 1.1.0+)
  patterns:
    - Atomic file write via .tmp rename prevents partial-file corruption
    - Permanent per-vibe cache at ~/.cinecut/music/ (API called at most once per vibe)
    - Graceful degradation — entire function body in try/except, returns None on any failure
key_files:
  created:
    - src/cinecut/assembly/music.py
  modified:
    - pyproject.toml
decisions:
  - audiodownload_allowed=True filter applied before selecting track (Jamendo April 2022 change — False returns 404)
  - soundfile>=0.12.1 pinned for MP3 support (bundles libsndfile 1.1.0+ on Linux; older versions cannot load .mp3)
  - MusicBed runtime dataclass is intentionally separate from manifest/schema.py MusicBed Pydantic model — Plan 03 converts between them
  - Cache hit returns MusicBed with track_id="cached" to avoid any API call on subsequent runs
metrics:
  duration_minutes: 2
  completed_date: "2026-02-28"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 1
---

# Phase 9 Plan 02: Music Fetch Module Summary

**One-liner:** Jamendo API v3 music fetch with permanent per-vibe MP3 cache at ~/.cinecut/music/ and full graceful-None degradation on any failure.

## What Was Built

`src/cinecut/assembly/music.py` provides the music acquisition layer for Phase 9. It fetches CC-licensed tracks from the Jamendo API v3 and caches them permanently on disk so the API is called at most once per vibe across all trailer runs.

Key exports:

- `VIBE_TO_JAMENDO_TAG` — maps all 18 genre vibes to Jamendo genre tags
- `MusicBed` — runtime dataclass carrying track metadata and `local_path` to the cached MP3
- `get_music_cache_dir()` — returns `~/.cinecut/music/`, creating it on demand
- `fetch_music_for_vibe(vibe)` — returns `MusicBed` on success, `None` on any failure

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create assembly/music.py | b892d95 | src/cinecut/assembly/music.py |
| 2 | Add librosa and soundfile to pyproject.toml | c55322b | pyproject.toml |

## Implementation Details

### fetch_music_for_vibe() flow

1. Compute `~/.cinecut/music/{vibe}.mp3` (cache path)
2. If cache hit: return `MusicBed` immediately — no API call (MUSC-02)
3. If cache miss: require `JAMENDO_CLIENT_ID` env var, call Jamendo API v3 tracks endpoint
4. Filter results for `audiodownload_allowed=True` (Jamendo April 2022 change — False results return 404)
5. Download via streaming request to `{vibe}.mp3.tmp`, then atomic rename to `{vibe}.mp3`
6. On partial download failure: unlink `.tmp` file, re-raise
7. Entire function body in `try/except Exception` — logs warning and returns `None` (MUSC-03)

### Dependency additions (pyproject.toml)

- `librosa>=0.11.0` — audio loading and BPM detection (used by Plan 01's generate_beat_grid)
- `soundfile>=0.12.1` — provides MP3 support through bundled libsndfile 1.1.0+; without this version, librosa.load() on .mp3 raises LibsndfileError (PITFALL 2)

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

- `python3 -m pytest tests/ -x -q` — 176 passed, 0 failed (no regressions)
- `fetch_music_for_vibe('action')` returns `None` when `JAMENDO_CLIENT_ID` is absent (MUSC-03)
- All 18 vibes present in `VIBE_TO_JAMENDO_TAG`
- `MusicBed` dataclass constructible with `bpm=None` default
- `librosa 0.11.0` and `soundfile 0.13.1` importable in project virtualenv
- Full import chain verified: `from cinecut.assembly.music import fetch_music_for_vibe, MusicBed, VIBE_TO_JAMENDO_TAG; from cinecut.assembly.bpm import generate_beat_grid` succeeds

## Self-Check: PASSED

- [x] `src/cinecut/assembly/music.py` exists and imports correctly
- [x] `pyproject.toml` contains `librosa>=0.11.0` and `soundfile>=0.12.1`
- [x] Commit b892d95 exists (music.py creation)
- [x] Commit c55322b exists (pyproject.toml update)
- [x] 176 tests pass — no regressions
