---
phase: 03-llava-inference-engine
plan: "02"
subsystem: inference
tags: [llava, llama-server, vram, gpu-lock, threading, subprocess, pydantic, dataclass]

# Dependency graph
requires:
  - phase: 03-llava-inference-engine
    plan: "01"
    provides: "InferenceError and VramError error classes in cinecut.errors; requests dependency declared"
  - phase: 01-ingestion-pipeline-and-cli-shell
    provides: "established dataclass pattern (KeyframeRecord) followed by SceneDescription"
provides:
  - "cinecut.inference package: GPU_LOCK threading.Lock, LlavaEngine context manager, SceneDescription dataclass"
  - "check_vram_free_mib() raises VramError if free VRAM below 6144 MiB threshold"
  - "LlavaEngine: starts llama-server on __enter__, holds GPU_LOCK for full lifetime, terminates on __exit__"
  - "DEVNULL stderr/stdout in non-debug mode (prevents pipe buffer deadlock per RESEARCH.md Pitfall 1)"
  - "Early-exit detection in _wait_for_health via process.poll() (per RESEARCH.md Pitfall 2)"
affects:
  - 03-03 (implements describe_frame method; unskips test_describe_frame_structure and test_malformed_response_skipped)
  - 05-trailer-assembly (FFmpeg conform pipeline must acquire GPU_LOCK before GPU operations)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy import pattern: GPU_LOCK imported inside __enter__/__exit__ method bodies to avoid circular import (engine.py imports from __init__.py)"
    - "VRAM checked before GPU_LOCK acquired -- fail fast without holding the lock if VRAM insufficient"
    - "GPU_LOCK released in finally block of __exit__ -- always released even if _stop raises"
    - "SIGTERM -> wait(10s) -> SIGKILL fallback on _stop to guarantee no zombie processes"
    - "debug mode uses log file beside model (not PIPE) to preserve DEVNULL-safety invariant"

key-files:
  created:
    - src/cinecut/inference/__init__.py
    - src/cinecut/inference/models.py
    - src/cinecut/inference/vram.py
    - src/cinecut/inference/engine.py
  modified: []

key-decisions:
  - "check_vram_free_mib() raises VramError when below threshold (not just returns int) -- required to match existing test_vram_check scaffold which expects VramError from check_vram_free_mib() directly"
  - "assert_vram_available() wraps check_vram_free_mib() for semantic clarity in engine __enter__"
  - "GPU_LOCK released in try/finally in __exit__ -- guarantees release even on _stop exceptions"
  - "VRAM checked before GPU_LOCK acquired -- fail fast pattern avoids holding lock unnecessarily"

patterns-established:
  - "Lazy import of GPU_LOCK inside method bodies: avoids circular import between engine.py and __init__.py"
  - "Integration tests for llama-server require compatible mmproj format; test_server_health expected to fail until compatible model files are present"

requirements-completed: [INFR-01, INFR-03, PIPE-05]

# Metrics
duration: 4min
completed: "2026-02-26"
---

# Phase 03 Plan 02: LLaVA Inference Engine Summary

**cinecut.inference package with LlavaEngine context manager (GPU_LOCK + llama-server lifecycle), SceneDescription dataclass, and VRAM pre-flight check via nvidia-smi**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-26T20:14:14Z
- **Completed:** 2026-02-26T20:17:50Z
- **Tasks:** 2 of 2
- **Files modified:** 4

## Accomplishments
- `cinecut.inference` package created with GPU_LOCK (threading.Lock), LlavaEngine, SceneDescription, SCENE_DESCRIPTION_SCHEMA, check_vram_free_mib, VRAM_MINIMUM_MIB
- `SceneDescription` dataclass with visual_content, mood, action, setting fields + Pydantic TypeAdapter for runtime validation
- `check_vram_free_mib()` raises VramError when free VRAM below 6144 MiB; `assert_vram_available()` wraps it
- `LlavaEngine` context manager with DEVNULL stderr (no pipe deadlock), GPU_LOCK serialization, health polling, early-exit detection, and SIGTERM/SIGKILL cleanup
- test_gpu_lock and test_vram_check both pass; full test suite has no regressions (67 non-integration tests pass)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create inference package with SceneDescription model and VRAM check** - `bc929a8` (feat)
2. **Task 2: Implement LlavaEngine context manager and complete the package** - `dd958c5` (feat)

## Files Created/Modified
- `/home/adamh/ai-video-trailer/src/cinecut/inference/__init__.py` - GPU_LOCK threading.Lock + re-exports of LlavaEngine, SceneDescription, check_vram_free_mib
- `/home/adamh/ai-video-trailer/src/cinecut/inference/models.py` - SceneDescription dataclass, SCENE_DESCRIPTION_SCHEMA dict, Pydantic TypeAdapter, validate_scene_description()
- `/home/adamh/ai-video-trailer/src/cinecut/inference/vram.py` - check_vram_free_mib() (raises VramError if below 6144 MiB), assert_vram_available()
- `/home/adamh/ai-video-trailer/src/cinecut/inference/engine.py` - LlavaEngine context manager with _start/_stop/_wait_for_health

## Decisions Made
- `check_vram_free_mib()` raises VramError when below threshold in addition to returning the int value. The existing test_vram_check scaffold (written in plan-01) calls `check_vram_free_mib()` and expects VramError when mocked at 500 MiB. The plan spec suggested only `assert_vram_available()` raises, but matching the existing test is authoritative.
- VRAM check happens before GPU_LOCK is acquired: fail fast without holding the lock unnecessarily. If VRAM insufficient, VramError is raised before any lock contention.
- GPU_LOCK released in `finally` block of `__exit__` to guarantee release even if `_stop()` raises an exception.
- Lazy `from cinecut.inference import GPU_LOCK` inside `__enter__`/`__exit__` method bodies avoids circular import between engine.py and `__init__.py`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] check_vram_free_mib() raises VramError on threshold violation**
- **Found during:** Task 1 (reviewing existing test scaffold)
- **Issue:** Plan spec said check_vram_free_mib() returns int and only assert_vram_available() raises VramError. But test_vram_check scaffold (written in plan-01) calls check_vram_free_mib() directly and expects VramError when nvidia-smi reports 500 MiB.
- **Fix:** check_vram_free_mib() checks the threshold and raises VramError if below minimum; assert_vram_available() wraps it for semantic clarity.
- **Files modified:** src/cinecut/inference/vram.py
- **Verification:** test_vram_check passes; assert_vram_available() also works correctly.
- **Committed in:** bc929a8 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - conforming implementation to match pre-written test scaffold)
**Impact on plan:** Auto-fix required for test compatibility. Both check_vram_free_mib() and assert_vram_available() provide correct behavior; the fix combines threshold checking into the lower-level function.

## Issues Encountered
- `test_server_health` integration test runs (models exist at /home/adamh/models/) but fails because the downloaded mmproj file (`mmproj-model-f16.gguf`) uses a projector format unknown to the current llama.cpp build. This is a model/version compatibility issue, not a code bug. The engine correctly detects the early exit and raises InferenceError as designed. This test was previously skipped (models absent); now it runs and reveals model format incompatibility.

## Next Phase Readiness
- `cinecut.inference` package fully importable and exportable
- GPU_LOCK available for Phase 5 FFmpeg conform pipeline
- Plan 03-03 can implement `describe_frame()` method on LlavaEngine and unskip remaining tests
- Integration test `test_server_health` needs compatible mmproj file or newer model format to pass end-to-end

---
*Phase: 03-llava-inference-engine*
*Completed: 2026-02-26*
