---
phase: 05-trailer-assembly-and-end-to-end-pipeline
plan: "01"
subsystem: pipeline
tags: [checkpoint, resumability, atomic-write, dataclass, json, posix]

# Dependency graph
requires: []
provides:
  - PipelineCheckpoint dataclass with source_file, vibe, stages_complete, and per-stage output fields
  - load_checkpoint() returning None for missing or corrupt checkpoint files
  - save_checkpoint() using tempfile.mkstemp(dir=work_dir) + os.replace() for POSIX-atomic writes
affects:
  - 05-02-PLAN.md
  - 05-03-PLAN.md
  - 05-04-PLAN.md

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "atomic-write: tempfile.mkstemp(dir=same_dir) + os.fsync() + os.replace() for power-loss-safe JSON updates"
    - "corrupt-tolerance: except (json.JSONDecodeError, TypeError): return None — never crash pipeline on bad checkpoint"

key-files:
  created:
    - src/cinecut/checkpoint.py
  modified: []

key-decisions:
  - "save_checkpoint uses tempfile.mkstemp(dir=work_dir) not Path.write_text() — os.replace() atomicity requires same-mount temp file"
  - "load_checkpoint returns None on corrupt JSON (not exception) — corrupt checkpoint triggers clean restart, not crash"
  - "PipelineCheckpoint.mark_stage_complete is idempotent — safe to call multiple times without duplicating stage names"

patterns-established:
  - "Checkpoint pattern: write to temp in same dir, fsync, os.replace() — never truncate-in-place"
  - "Fault tolerance: any checkpoint read failure returns None, caller decides whether to restart cleanly"

requirements-completed: [PIPE-04]

# Metrics
duration: 1min
completed: 2026-02-26
---

# Phase 5 Plan 01: Checkpoint Summary

**POSIX-atomic pipeline checkpoint (PipelineCheckpoint + load/save) using tempfile.mkstemp + os.replace() for power-loss-safe stage resumability**

## Performance

- **Duration:** 1 min
- **Started:** 2026-02-26T23:27:13Z
- **Completed:** 2026-02-26T23:28:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Implemented `PipelineCheckpoint` dataclass with all 8 fields (source_file, vibe, stages_complete, plus per-stage output slots)
- `load_checkpoint()` returns `None` for missing files and silently absorbs corrupt JSON — pipeline always gets a clean restart signal
- `save_checkpoint()` uses `tempfile.mkstemp(dir=work_dir)` + `os.fsync()` + `os.replace()` — checkpoint is never partially written even on power loss

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement checkpoint.py — PipelineCheckpoint dataclass and atomic read/write** - `3b9911f` (feat)

**Plan metadata:** TBD (docs: complete plan)

## Files Created/Modified

- `src/cinecut/checkpoint.py` - PipelineCheckpoint dataclass, load_checkpoint(), save_checkpoint() — atomic JSON checkpoint for PIPE-04 stage resumability

## Decisions Made

- `save_checkpoint` must use `tempfile.mkstemp(dir=work_dir)` (same filesystem directory) rather than any cross-directory temp — os.replace atomicity is only guaranteed when src and dst are on the same mount point
- `load_checkpoint` catches `(json.JSONDecodeError, TypeError)` and returns `None` — TypeError covers unexpected schema changes where field names no longer match the dataclass constructor
- `mark_stage_complete` guards against duplicates with `if stage not in self.stages_complete` — idempotent, safe for retry loops

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `checkpoint.py` is ready for 05-02 and later plans to import and use
- Pipeline stages (proxy, subtitles, keyframes, inference, narrative, assembly) can now persist completion state between runs
- Stale checkpoints (different source_file) need to be handled by the caller by comparing `loaded.source_file` against the current run's source

---
*Phase: 05-trailer-assembly-and-end-to-end-pipeline*
*Completed: 2026-02-26*
