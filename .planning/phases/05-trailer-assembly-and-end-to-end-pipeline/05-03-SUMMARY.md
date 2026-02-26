---
phase: 05-trailer-assembly-and-end-to-end-pipeline
plan: 03
subsystem: cli
tags: [checkpoint, pipeline-resume, assembly, pacing, conform, typer, rich]

requires:
  - phase: 05-01
    provides: PipelineCheckpoint dataclass, load_checkpoint, save_checkpoint, CHECKPOINT_FILENAME
  - phase: 05-02
    provides: assemble_manifest(), sort_clips_by_act(), enforce_pacing_curve(), ACT_ORDER, MIN_CLIP_DURATION_S
provides:
  - cli.py with 7-stage pipeline, checkpoint guards on all stages, Stage 6 assembly wiring
  - conform_manifest() backward-compatible extra_clip_paths parameter
  - tests/test_checkpoint.py: 11 unit tests for PipelineCheckpoint, load_checkpoint, save_checkpoint
  - tests/test_assembly.py: 12 unit tests for sort_clips_by_act, enforce_pacing_curve, compute_act_avg_duration
affects:
  - 05-04 (end-to-end human verify — pipeline is now complete)

tech-stack:
  added: []
  patterns:
    - "checkpoint guard pattern: is_stage_complete() check before stage; mark+save after success only"
    - "extra_clip_paths default=None parameter for backward-compatible extend of conform clip list"
    - "TOTAL_STAGES constant for DRY N/7 stage label format"

key-files:
  created:
    - tests/test_checkpoint.py
    - tests/test_assembly.py
  modified:
    - src/cinecut/cli.py
    - src/cinecut/conform/pipeline.py

key-decisions:
  - "Stage 4 (inference) sets ckpt.inference_complete=True but re-runs on resume — persisting SceneDescription objects is deferred to v2 (TODO comment in code)"
  - "Stage 3 (keyframes) on resume: re-runs extraction (idempotent) rather than skipping — simpler and correct"
  - "extra_clip_paths uses list[Path] | None = None signature (not list[Path] = []) — avoids mutable default argument pitfall"
  - "--manifest shortcut path also runs assembly before conform (no checkpoint needed for shortcut)"
  - "conform_manifest() receives reordered_manifest from assemble_manifest(), not raw generator output"

patterns-established:
  - "Checkpoint write pattern: only in success path, never in except handlers (Pitfall 2)"
  - "Stale checkpoint detection: compare ckpt.source_file to str(video) at startup"

requirements-completed: [PIPE-04, EDIT-02, EDIT-03]

duration: 5min
completed: 2026-02-26
---

# Phase 5 Plan 03: CLI Checkpoint Guards + Assembly Wiring Summary

**7-stage checkpoint-guarded CLI with 3-act assembly stage, reordered manifest passed to conform, and 23 new unit tests for checkpoint + assembly modules**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-26T23:30:00Z
- **Completed:** 2026-02-26T23:35:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- cli.py updated to 7-stage pipeline with N/7 labels and TOTAL_STAGES constant
- Checkpoint guards on Stages 1 (proxy), 2 (subtitles), 3 (keyframes), 5 (narrative), 6 (assembly)
- Stage 6 calls assemble_manifest() and injects reordered_manifest + extra_paths into conform
- conform_manifest() extended with backward-compatible extra_clip_paths parameter
- 23 new unit tests passing; full suite 119 tests, 0 failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Update cli.py — checkpoint guards + Stage 6 assembly wiring** - `2461ee7` (feat)
2. **Task 2: Write tests/test_checkpoint.py and tests/test_assembly.py** - `3ff451a` (test)

## Files Created/Modified
- `src/cinecut/cli.py` - 7-stage pipeline with checkpoint guards, Stage 6 assembly, reordered_manifest conform
- `src/cinecut/conform/pipeline.py` - extra_clip_paths param added to conform_manifest()
- `tests/test_checkpoint.py` - TestPipelineCheckpoint, TestLoadCheckpoint, TestSaveCheckpoint (11 tests)
- `tests/test_assembly.py` - TestSortClipsByAct, TestComputeActAvgDuration, TestEnforcePacingCurve (12 tests)

## Decisions Made
- Stage 4 (inference) does not skip on resume — persisting SceneDescription results requires v2 design; TODO comment added
- Stage 3 (keyframes) re-runs on resume since extract_all_keyframes is idempotent
- extra_clip_paths uses `list[Path] | None = None` signature to avoid mutable default argument pitfall
- --manifest shortcut also runs assembly (no checkpoint) to maintain consistent reordered_manifest behavior

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Full 7-stage pipeline with checkpoint resume is complete (PIPE-04)
- 3-act ordering and pacing curve are wired into conform (EDIT-02, EDIT-03)
- Ready for Phase 5 Plan 04: end-to-end human verify with a real film
- No blockers

---
*Phase: 05-trailer-assembly-and-end-to-end-pipeline*
*Completed: 2026-02-26*
