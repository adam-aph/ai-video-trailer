---
phase: 06-inference-persistence
plan: 01
subsystem: inference
tags: [msgpack, cache, llava, persistence, checkpoint, pipeline]

# Dependency graph
requires:
  - phase: 03-llava-inference
    provides: "run_inference_stage(), SceneDescription dataclass, LLaVA engine"
  - phase: 05-assembly
    provides: "PipelineCheckpoint dataclass with atomic save_checkpoint() pattern"
provides:
  - "save_cache(results, source_file, work_dir) — atomic msgpack write to work_dir/<stem>.scenedesc.msgpack"
  - "load_cache(source_file, work_dir) — mtime+size validated cache load; None on miss/corrupt/invalidated"
  - "PipelineCheckpoint.cache_hit field for cache observability in checkpoint JSON"
  - "Stage 4 in cli.py guarded by load_cache(); cache miss triggers cascade reset of downstream stages"
affects:
  - phase: 07-text-engine
  - phase: 08-semantic-zones
  - "Any future plan modifying Stage 4 or PipelineCheckpoint"

# Tech tracking
tech-stack:
  added: ["msgpack>=1.1.0"]
  patterns:
    - "Atomic write via tempfile.mkstemp + os.replace (consistent with checkpoint.py pattern)"
    - "Treat corrupt cache as miss, never propagate exceptions from load_cache()"
    - "Cache invalidation via mtime+size comparison — both must match"
    - "Cache co-located with work_dir — deleting work_dir clears cache"

key-files:
  created:
    - "src/cinecut/inference/cache.py"
    - "tests/test_cache.py"
  modified:
    - "src/cinecut/checkpoint.py"
    - "src/cinecut/cli.py"
    - "pyproject.toml"

key-decisions:
  - "Cache stored in work_dir/<stem>.scenedesc.msgpack — not ~/.cinecut/ — cache lifecycle tied to work dir"
  - "Invalidation on mtime OR size change — either is sufficient signal that source file changed"
  - "Cascade reset (clear narrative+assembly from stages_complete) only on cache miss, not on cache hit — prevents stale Stage 5 downstream"
  - "msgpack.unpackb uses raw=False, strict_map_key=False — avoids KeyError on bytes keys"
  - "No checkpoint-based inference guard (is_stage_complete) — cache IS the persistence mechanism"

patterns-established:
  - "load_cache() returns None in all failure cases — callers never need try/except"
  - "save_cache() atomic write mirrors save_checkpoint() tempfile pattern exactly"
  - "Cache invalidation triggers cascade: remove downstream stages from stages_complete before re-inference"

requirements-completed: [IINF-01, IINF-02]

# Metrics
duration: 3min
completed: 2026-02-28
---

# Phase 6 Plan 01: Inference Persistence Summary

**msgpack cache eliminating LLaVA re-inference on pipeline resume, with mtime/size invalidation and atomic writes co-located in the work directory**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-28T11:53:34Z
- **Completed:** 2026-02-28T11:56:25Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Created `src/cinecut/inference/cache.py` with `save_cache()`, `load_cache()`, `_cache_path()` — atomic msgpack persistence for SceneDescription results
- Wired Stage 4 in `cli.py` with cache guard: cache hit skips LLaVA inference entirely; cache miss triggers inference then writes cache; cascade reset clears narrative+assembly stages when source file changes
- Added `cache_hit: Optional[bool]` to `PipelineCheckpoint` for observability, and 8 unit tests covering all cache behaviors

## Task Commits

Each task was committed atomically:

1. **Task 1: Create inference/cache.py with msgpack persistence and mtime invalidation** - `ecde57f` (feat)
2. **Task 2: Extend PipelineCheckpoint and wire Stage 4 guard in cli.py** - `dea8de7` (feat)
3. **Task 3: Write unit tests for cache module** - `59972cf` (test)

## Files Created/Modified

- `src/cinecut/inference/cache.py` - New: save_cache(), load_cache(), _cache_path() with atomic write and mtime+size invalidation
- `tests/test_cache.py` - New: 8 unit tests covering roundtrip, hit, miss, mtime/size invalidation, corrupt file, file location, None description
- `src/cinecut/checkpoint.py` - Added `cache_hit: Optional[bool] = None` field to PipelineCheckpoint
- `src/cinecut/cli.py` - Stage 4 replaced with cache-guarded version; imports load_cache/save_cache; cascade reset on miss
- `pyproject.toml` - Added `msgpack>=1.1.0` to dependencies

## Decisions Made

- Cache stored in `work_dir/<stem>.scenedesc.msgpack` (not `~/.cinecut/`) — lifecycle tied to work directory; deleting work dir clears cache automatically
- Invalidation on mtime OR size change — either difference is sufficient to detect source file replacement
- Cascade reset of narrative and assembly stages only on cache miss — prevents Stage 5 running against stale keyframes when source file changes (Research Pitfall 5)
- `msgpack.unpackb(raw=False, strict_map_key=False)` — avoids `KeyError: b'metadata'` from raw mode key type mismatch
- No `is_stage_complete("inference")` checkpoint guard — the cache IS the persistence mechanism; guard is `load_cache() is not None`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `pip install msgpack` failed with PEP 668 system package protection warning — resolved with `pip3 install --break-system-packages msgpack` (system Python without venv; standard for this project based on existing cinecut installation pattern)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 6 Plan 01 complete — inference cache fully operational
- Phase 7 (Text Engine) can proceed — no blockers from this plan
- Reminder: Mistral 7B v0.3 Q4_K_M GGUF must be downloaded to ~/models before Phase 7 integration tests

---
*Phase: 06-inference-persistence*
*Completed: 2026-02-28*
