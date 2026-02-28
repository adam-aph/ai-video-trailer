---
phase: 10-sfx-vo-and-audio-mix
plan: "01"
subsystem: conform/sfx
tags: [sfx, audio-synthesis, ffmpeg, aevalsrc, adelay, amix]
dependency_graph:
  requires:
    - cinecut.manifest.schema.TrailerManifest
    - cinecut.errors.ConformError
    - FFmpeg (system binary)
  provides:
    - synthesize_sfx_files()
    - apply_sfx_to_timeline()
    - SFX_HARD_DURATION_S
    - SFX_BOUNDARY_DURATION_S
  affects:
    - 10-03 (audio mix pipeline wiring — consumes both functions)
tech_stack:
  added: []
  patterns:
    - FFmpeg aevalsrc for programmatic audio synthesis (no external file deps)
    - adelay filter for millisecond-precision SFX placement on timeline
    - amix normalize=0 for ducking-ratio-safe mixing
    - Idempotency guard via file existence check before FFmpeg synthesis
key_files:
  created:
    - src/cinecut/conform/sfx.py
  modified: []
decisions:
  - "Linear chirp slope uses (f1-f0)/(2*d) not (f1-f0)/d — keeps instantaneous frequency formula consistent with aevalsrc sin(2*PI*f(t)*t) convention"
  - "c=stereo used in aevalsrc (not cl=stereo) — FFmpeg channel layout param for aevalsrc filter"
  - "adelay offsets are integer milliseconds: int(position_s * 1000)"
  - "Idempotency: both WAV files checked before any FFmpeg call — skips ~2-3s synthesis on pipeline resume"
  - "act3_first_index scan is O(n) over clips before position accumulation — ensures ESCALATION->CLIMAX boundary always gets sfx_boundary tier regardless of transition field value"
metrics:
  duration_s: 118
  completed_date: "2026-02-28"
  tasks_completed: 1
  files_created: 1
---

# Phase 10 Plan 01: SFX Synthesis and Timeline Overlay Summary

SFX synthesis module generating two sweep-tone WAV tiers via FFmpeg `aevalsrc` at 48000Hz stereo — zero external file dependencies, idempotent re-use, `adelay`-based positioning at beat-snapped cut boundaries.

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Create conform/sfx.py — SFX synthesis and timeline overlay | 8017a69 | src/cinecut/conform/sfx.py (created, 230 lines) |

## What Was Built

`src/cinecut/conform/sfx.py` exports four symbols:

- `SFX_HARD_DURATION_S = 0.4` — hard-cut chirp duration constant
- `SFX_BOUNDARY_DURATION_S = 1.2` — act-boundary chirp duration constant
- `synthesize_sfx_files(work_dir)` — creates `work_dir/sfx/sfx_hard.wav` and `work_dir/sfx/sfx_boundary.wav`
- `apply_sfx_to_timeline(manifest, sfx_hard, sfx_boundary, work_dir, concat_duration_s)` — overlays SFX at cut positions, returns `work_dir/sfx/sfx_mix.wav`

### synthesize_sfx_files()

Two FFmpeg `aevalsrc` calls using linear chirp formula `f(t) = f0 + slope*t` with `slope = (f1-f0)/(2*d)`:

| File | Freq Range | Duration | Slope | Envelope |
|------|-----------|----------|-------|---------|
| sfx_hard.wav | 3000Hz -> 300Hz | 0.4s | -3375 Hz/s | 0.6*exp(-3*t) |
| sfx_boundary.wav | 200Hz -> 2000Hz | 1.2s | 750 Hz/s | 0.5*(1-exp(-2*t))*exp(-0.5*pow(t-0.6,2)/0.15) |

Idempotent: if both files already exist, returns immediately without calling FFmpeg.

### apply_sfx_to_timeline()

- Accumulates clip timeline positions from `source_end_s - source_start_s` durations
- Classifies each cut: `hard_cut` transition -> sfx_hard (0.1s lead); all other transitions or first `act3` clip -> sfx_boundary (0.3s lead)
- Skips `title_card` and `button` acts; skips clip index 0 (no cut before first clip)
- Positions clamped to `max(0.0, timeline_pos_s - lead_s)`
- Builds FFmpeg filtergraph: `adelay=OFFSET_MS|OFFSET_MS` per SFX input, then `amix=inputs=N:normalize=0`
- Single-clip edge case: copies sfx_hard to sfx_mix.wav directly

## Verification

```
from cinecut.conform.sfx import synthesize_sfx_files, apply_sfx_to_timeline, SFX_HARD_DURATION_S, SFX_BOUNDARY_DURATION_S
# import ok 0.4 1.2
```

199 existing tests pass (no regressions).

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `src/cinecut/conform/sfx.py` exists: confirmed (created, 230 lines)
- Commit 8017a69 exists: confirmed
- `SFX_HARD_DURATION_S = 0.4`: verified
- `SFX_BOUNDARY_DURATION_S = 1.2`: verified
- `c=stereo` used (not `cl=stereo`): verified
- `amix normalize=0`: verified
- `adelay` offsets in milliseconds: verified
- chirp slope formula `(f1-f0)/(2*d)`: verified (slope comments in source)
- 199 tests pass: verified
