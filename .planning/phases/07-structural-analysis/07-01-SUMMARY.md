---
phase: 07-structural-analysis
plan: 01
subsystem: inference
tags: [llama-server, mistral, text-engine, vram, gpu-lock, model-paths]

# Dependency graph
requires:
  - phase: 06-inference-persistence
    provides: msgpack inference cache, LlavaEngine pattern
provides:
  - TextEngine context manager for Mistral 7B text inference on port 8090
  - wait_for_vram() VRAM polling between model swaps
  - get_models_dir() / CINECUT_MODELS_DIR env override for all model paths
  - GPU_LOCK serialization between LlavaEngine and TextEngine
affects:
  - phase: 07-structural-analysis (plan 02 uses TextEngine.analyze_chunk)
  - phase: 08-zone-matching-and-non-linear-ordering

# Tech tracking
tech-stack:
  added: []
  patterns:
    - TextEngine mirrors LlavaEngine context-manager pattern (port 8090, -c 8192, no --mmproj)
    - VRAM polling before GPU_LOCK.acquire() instead of assert_vram_available()
    - CINECUT_MODELS_DIR env var for portable model path resolution

key-files:
  created:
    - src/cinecut/inference/text_engine.py
  modified:
    - src/cinecut/inference/vram.py
    - src/cinecut/inference/__init__.py
    - src/cinecut/cli.py

key-decisions:
  - "TextEngine uses port 8090 (never 8089) and -c 8192 — never run concurrently with LlavaEngine"
  - "wait_for_vram() called before GPU_LOCK.acquire() in TextEngine.__enter__ — async VRAM reclaim after llama-server exit"
  - "CINECUT_MODELS_DIR env var drives all three model paths; falls back to ~/models when unset"
  - "cli.py model args default=None resolved at runtime — avoids hardcoded path evaluated at import time"

patterns-established:
  - "GPU engine context managers: call wait_for_vram() before GPU_LOCK.acquire(), release lock in __exit__ finally block"
  - "Model path resolution: get_models_dir() called at runtime inside main(), never as module-level constant"

requirements-completed: [IINF-03]

# Metrics
duration: 5min
completed: 2026-02-28
---

# Phase 07 Plan 01: TextEngine and CINECUT_MODELS_DIR Migration Summary

**TextEngine context manager for Mistral 7B on port 8090 with GPU_LOCK serialization, wait_for_vram() VRAM polling, and CINECUT_MODELS_DIR env-var model path resolution across inference and CLI**

## Performance

- **Duration:** ~5 min (continuation — Tasks 1 and 2 from prior session)
- **Started:** 2026-02-28T13:40:00Z
- **Completed:** 2026-02-28T13:51:41Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Created TextEngine context manager mirroring LlavaEngine exactly (port 8090, -c 8192, no --mmproj), with wait_for_vram() before GPU_LOCK.acquire()
- Added wait_for_vram() and _check_vram_free_mib_raw() to vram.py; exported TextEngine, get_models_dir, MISTRAL_GGUF_NAME, wait_for_vram from inference package __init__
- Migrated cli.py from hard-coded /home/adamh/models paths to CINECUT_MODELS_DIR-aware get_models_dir() resolved at runtime

## Task Commits

Each task was committed atomically:

1. **Task 1: Create inference/text_engine.py with TextEngine and get_models_dir** - `a30f81a` (feat)
2. **Task 2: Add wait_for_vram to vram.py and export TextEngine from inference/__init__.py** - `00089c4` (feat)
3. **Task 3: Migrate cli.py model paths to get_models_dir (IINF-03)** - `76e7632` (feat)

## Files Created/Modified

- `src/cinecut/inference/text_engine.py` - TextEngine context manager, get_models_dir(), MISTRAL_GGUF_NAME constant
- `src/cinecut/inference/vram.py` - Added _check_vram_free_mib_raw() and wait_for_vram() polling function
- `src/cinecut/inference/__init__.py` - Exported TextEngine, get_models_dir, MISTRAL_GGUF_NAME, wait_for_vram
- `src/cinecut/cli.py` - Removed _DEFAULT_MODEL_PATH/_DEFAULT_MMPROJ_PATH; model paths resolved at runtime via get_models_dir()

## Decisions Made

- TextEngine uses port 8090 and -c 8192 (8k context for structural analysis chunks), never --mmproj
- wait_for_vram() polled BEFORE GPU_LOCK.acquire() — not assert_vram_available() — to handle async VRAM reclaim between model swaps
- cli.py --model and --mmproj default to None; resolved inside main() after work_dir setup, not at module import time (avoids hardcoded path evaluation at import)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- TextEngine is ready for Plan 07-02 to add `analyze_chunk()` method and wire structural analysis
- All model paths respect CINECUT_MODELS_DIR — portable across machines
- GPU_LOCK serialization ensures LlavaEngine and TextEngine cannot run concurrently
- Blocker remains: Mistral 7B v0.3 Q4_K_M GGUF (~4.37 GB) must be downloaded to ~/models before integration tests can run end-to-end

---
*Phase: 07-structural-analysis*
*Completed: 2026-02-28*
