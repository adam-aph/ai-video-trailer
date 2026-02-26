---
phase: 02-manifest-contract-vibes-and-conform
plan: "02"
subsystem: conform
tags: [ffmpeg, loudnorm, lut3d, concat-demuxer, typer, rich, subprocess]

# Dependency graph
requires:
  - phase: 02-01
    provides: TrailerManifest schema, VibeProfile dataclass with 18 profiles, ensure_luts(), ManifestError/ConformError types
  - phase: 01-ingestion-pipeline-and-cli-shell
    provides: CLI shell (cli.py), CineCutError hierarchy, Phase 1 ingestion stages

provides:
  - conform/pipeline.py with conform_manifest(), extract_and_grade_clip(), concatenate_clips()
  - CLI --manifest flag for direct conform from TRAILER_MANIFEST.json
  - CLI --review flag for human inspection pause before conform
  - Vibe validation in CLI before any stage runs

affects: [03-inference-engine, 04-manifest-generation, 05-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-pass loudnorm: pass-1 JSON stats parsed from stderr via re.search, fed into linear=true pass-2"
    - "Frame-accurate seek: -ss before -i, re-encode with libx264 crf 18 (never stream copy for clip extraction)"
    - "Short-clip guard: clips < 3.0s skip two-pass loudnorm, use volume=0dB single pass"
    - "Concat demuxer: _concat_list.txt with single-quote path escaping and -safe 0"
    - "CLI stage branching: --manifest bypasses Phase 1 ingestion block, both paths converge at Stage 4"

key-files:
  created:
    - src/cinecut/conform/pipeline.py
  modified:
    - src/cinecut/cli.py

key-decisions:
  - "Short clips < 3.0s use volume=0dB (no-op gain) in single-pass instead of two-pass loudnorm -- avoids loudnorm instability on <3s audio (Act 3 montage clips avg 1.2-1.8s per action/horror profiles)"
  - "make_output_path() replaces hyphens with underscores in vibe slug for filename safety (sci-fi -> sci_fi)"
  - "typer.Exit(1) raised directly inside manifest-not-found check (inside try block) -- this is caught before CineCutError handler so raises cleanly; manifest validation errors that raise ManifestError/ConformError fall through to except CineCutError"
  - "vibe validation added to CLI using VIBE_PROFILES dict keys (not VALID_VIBES frozenset) so both are consistent -- VIBE_PROFILES is single source of truth for runtime validation"

patterns-established:
  - "Pattern: subprocess.run() always uses list form, capture_output=True, text=True, check=False -- never shell=True"
  - "Pattern: FFmpeg -ss before -i for frame-accurate seek (input seeking is fast AND accurate with modern FFmpeg)"
  - "Pattern: ConformError wraps stderr[-500:] to limit error message size while preserving most-relevant tail"

requirements-completed: [EDIT-04, EDIT-05, VIBE-03, VIBE-04, CLI-04]

# Metrics
duration: 2min
completed: 2026-02-26
---

# Phase 2 Plan 02: Conform Pipeline and CLI Wiring Summary

**FFmpeg conform pipeline with two-pass loudnorm (short-clip guard at 3.0s), lut3d grading, concat demuxer, and --manifest/--review CLI flags**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T19:03:34Z
- **Completed:** 2026-02-26T19:05:24Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `conform/pipeline.py` implements `extract_and_grade_clip()` with frame-accurate -ss before -i, lut3d video filter, and two-pass loudnorm with JSON stat extraction from stderr
- Short clips (< 3.0s) skip two-pass loudnorm and use volume=0dB single pass, matching Act 3 montage clip durations in action/horror/thriller vibe profiles
- `concatenate_clips()` uses concat demuxer with single-quote escaping and -safe 0 flag; temp `_concat_list.txt` auto-deleted on success or failure
- `conform_manifest()` orchestrates the full pipeline: ensure_luts() -> per-clip extract_and_grade_clip() -> concatenate_clips() with CLI-04 output naming
- CLI extended with --manifest/-m and vibe validation; --review triggers `typer.confirm(abort=True)` before conform; all Phase 1 stages preserved exactly

## Task Commits

Each task was committed atomically:

1. **Task 1: Build FFmpeg conform pipeline** - `6c63e3e` (feat)
2. **Task 2: Wire --manifest and --review into CLI** - `9ec0b61` (feat)

**Plan metadata:** TBD (docs commit)

## Files Created/Modified
- `src/cinecut/conform/pipeline.py` - FFmpeg conform pipeline (extract_and_grade_clip, concatenate_clips, conform_manifest, make_output_path, MIN_LOUDNORM_DURATION_S)
- `src/cinecut/cli.py` - Extended with --manifest/-m, vibe validation, Stage 4 conform block, --review pause

## Decisions Made
- Short clips < 3.0s use volume=0dB (no-op gain) in single-pass instead of two-pass loudnorm: avoids loudnorm instability on sub-3s audio segments (Act 3 montage clips average 1.2-1.8s per action/horror/thriller vibe profiles per research)
- `make_output_path()` replaces hyphens with underscores in vibe slug (sci-fi -> sci_fi) for safe filenames per CLI-04 spec
- Vibe validation in CLI uses `VIBE_PROFILES` dict keys (not `VALID_VIBES` frozenset) as single source of runtime truth
- `typer.Exit(1)` raised directly inside manifest-not-found check (inside try block) to exit before CineCutError handler -- works correctly since typer.Exit is not CineCutError

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- conform/pipeline.py is complete and ready for Phase 3 to test against real inference-generated manifests
- CLI now accepts TRAILER_MANIFEST.json files for direct conform, enabling manual testing end-to-end before Phase 4
- All Phase 1 ingestion stages preserved; Phase 3 inference engine can be developed independently (depends on Phase 1 only per roadmap)
- Remaining concern: CUDA 11.4 / Kepler sm_35 compatibility must be validated before Phase 3 begins

---
*Phase: 02-manifest-contract-vibes-and-conform*
*Completed: 2026-02-26*
