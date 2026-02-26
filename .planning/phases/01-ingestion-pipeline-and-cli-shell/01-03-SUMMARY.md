---
phase: 01-ingestion-pipeline-and-cli-shell
plan: "03"
subsystem: cli
tags: [typer, rich, scenedetect, ffmpeg, keyframes, progress-bars]

# Dependency graph
requires:
  - phase: 01-01
    provides: models.py (DialogueEvent, KeyframeRecord), errors.py (CineCutError hierarchy), project scaffold
  - phase: 01-02
    provides: proxy.py (create_proxy, probe_video, validate_proxy), subtitles.py (parse_subtitles)
provides:
  - cli.py — Typer entry point wiring all ingestion stages with Rich progress bars and error panels
  - ingestion/keyframes.py — Hybrid keyframe timestamp collection and JPEG extraction
  - tests/test_keyframes.py — Unit tests for timestamp collection logic (no real video required)
affects:
  - phase-03-inference
  - phase-04-conform

# Tech tracking
tech-stack:
  added: [typer, rich, scenedetect ContentDetector, subprocess pre-seek FFmpeg]
  patterns:
    - Hybrid timestamp collection: subtitle midpoints + scene-change detection + interval fallback merged via set
    - Pre-seek FFmpeg extraction (-ss before -i) for fast keyframe-aligned JPEG writes
    - Idempotent frame extraction: skip if output_path exists (safe to resume)
    - CLI validates extensions before any work begins; all CineCutError subclasses caught and rendered as Rich error panels

key-files:
  created:
    - src/cinecut/cli.py
    - src/cinecut/ingestion/keyframes.py
    - tests/test_keyframes.py
  modified: []

key-decisions:
  - "progress_callback passed into extract_all_keyframes as optional Callable; CLI advances progress bar per-frame without coupling keyframes module to Rich"
  - "subtitle_midpoints accepted as set[float] parameter in extract_all_keyframes for source inference; _infer_source() labels scene_change for both scene and interval timestamps post-merge (indistinguishable and acceptable)"
  - "interval fallback uses a while-loop re-scanning the same gap after insertion to correctly handle multi-segment fills without off-by-one on the sorted list"
  - "--review flag accepted as no-op in Phase 1; Phase 2 will implement manifest/conform pipeline behavior"
  - "vibe validation deferred to Phase 2 where vibe profiles are defined; Phase 1 accepts any string"

patterns-established:
  - "Idempotency pattern: check-then-skip for both proxy creation and frame extraction ensures safe restarts"
  - "Error translation pattern: all subprocess CalledProcessError caught and re-raised as typed CineCutError; CLI catches CineCutError → Rich panel → Exit(1)"
  - "Separation of concerns: keyframes.py has no Rich imports; CLI owns all progress rendering"

requirements-completed: [PIPE-03, CLI-01, CLI-02, CLI-03]

# Metrics
duration: 2min
completed: 2026-02-26
---

# Phase 1 Plan 03: CLI Shell and Hybrid Keyframe Extractor Summary

**Typer CLI wiring proxy creation, subtitle parsing, and hybrid scene-detect+interval-fallback keyframe extraction behind Rich progress bars with error-panel error handling**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T16:10:41Z
- **Completed:** 2026-02-26T16:12:39Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Hybrid keyframe extractor (`keyframes.py`) combining subtitle midpoints, PySceneDetect ContentDetector scene midpoints, and 30s interval fallback into a sorted deduplicated timestamp list
- JPEG frame extraction via FFmpeg pre-seek with idempotent output (skip if exists), optional progress_callback for CLI integration, and source inference distinguishing subtitle vs scene-change origins
- Typer CLI (`cli.py`) accepting `video`, `--subtitle`, `--vibe`, `--review` with extension validation, work-directory setup, three-stage Rich progress pipeline, and CineCutError → Rich error panel error handling
- 9 unit tests covering gap-fill, large gap multi-segment fill, deduplication, sort order, and source inference — all passing without real video files

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement hybrid keyframe extractor** - `037c82b` (feat)
2. **Task 2: Implement Typer CLI shell with Rich progress** - `2d07be9` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/cinecut/ingestion/keyframes.py` - Hybrid timestamp collector, JPEG extractor, idempotent extract_all_keyframes with progress_callback and subtitle_midpoints parameters
- `src/cinecut/cli.py` - Typer command with extension validation, work-dir setup, three-stage Rich progress pipeline, CineCutError catch-all panel
- `tests/test_keyframes.py` - 9 unit tests for collect_keyframe_timestamps and _infer_source (no real video required)

## Decisions Made

- `progress_callback` passed into `extract_all_keyframes` as optional `Callable[[], None]` so the keyframes module has no Rich dependency — CLI owns all progress rendering
- `subtitle_midpoints` accepted as `set[float]` in `extract_all_keyframes` for source inference; `_infer_source()` labels both scene-change and interval-fallback timestamps as `"scene_change"` since they are indistinguishable post-merge (acceptable per plan spec)
- Interval fallback implemented with a while-loop re-scan to correctly handle multi-segment gaps (e.g., 0s to 120s fills at 30s, 60s, 90s)
- `--review` is a no-op in Phase 1; Phase 2 implements the manifest/conform pipeline
- Vibe validation deferred to Phase 2 where vibe profiles are defined

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 1 is now complete: all three ingestion plans (models/errors, proxy+subtitles, CLI+keyframes) are implemented and tested
- Work directory layout (`<stem>_cinecut_work/keyframes/frame_{ms:010d}.jpg`) is ready for Phase 3 inference consumption
- All 33 unit tests passing (test_proxy, test_subtitles, test_keyframes)
- Phase 3 dependency on Phase 1 confirmed satisfied; Phase 2 (conform pipeline) can proceed in parallel

## Self-Check: PASSED

- FOUND: src/cinecut/ingestion/keyframes.py
- FOUND: src/cinecut/cli.py
- FOUND: tests/test_keyframes.py
- FOUND: .planning/phases/01-ingestion-pipeline-and-cli-shell/01-03-SUMMARY.md
- FOUND commit: 037c82b (Task 1 - hybrid keyframe extractor)
- FOUND commit: 2d07be9 (Task 2 - Typer CLI shell)
- FOUND commit: 90a8a7e (docs - plan metadata)
- All 33 tests passing

---
*Phase: 01-ingestion-pipeline-and-cli-shell*
*Completed: 2026-02-26*
