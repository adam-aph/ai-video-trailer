---
phase: 03-llava-inference-engine
plan: "01"
subsystem: inference
tags: [llava, gguf, llama-server, requests, error-handling, testing]

# Dependency graph
requires:
  - phase: 01-ingestion-pipeline-and-cli-shell
    provides: KeyframeRecord model used in test scaffold context
  - phase: 02-manifest-contract-vibes-and-conform
    provides: established error class conventions followed by InferenceError/VramError
provides:
  - InferenceError and VramError error classes in cinecut.errors
  - requests>=2.31.0 declared as project dependency
  - tests/test_inference.py scaffold with all 6 Phase 3 test cases
  - LLaVA model download instructions for /home/adamh/models/
affects:
  - 03-02 (implements LlavaEngine and vram module that test scaffold imports)
  - 03-03 (unskips describe_frame tests)

# Tech tracking
tech-stack:
  added: [requests>=2.31.0]
  patterns:
    - "CineCutError subclass pattern: __init__ with detail str, actionable message with Cause/Check/Tip"
    - "pytest.importorskip for modules not yet created -- scaffold stays collectable through plan sequence"
    - "integration = pytest.mark.skipif(...exists()) -- marks skip when model files absent from disk"

key-files:
  created: [tests/test_inference.py]
  modified: [pyproject.toml, src/cinecut/errors.py]

key-decisions:
  - "InferenceError and VramError take only detail: str (no Path) -- inference errors are not file-path-specific"
  - "pytest.importorskip used for cinecut.inference.* imports so scaffold is collectible before plan-02 exists"
  - "integration mark uses _models_exist flag checking both GGUF and mmproj file presence"

patterns-established:
  - "New error classes appended after ConformError following CineCutError subclass convention"
  - "Test scaffold created before implementation with all tests skipped via importorskip or pytest.mark.skip"

requirements-completed: [INFR-01, INFR-02, INFR-03, PIPE-05]

# Metrics
duration: 2min
completed: "2026-02-26"
---

# Phase 03 Plan 01: LLaVA Infrastructure Setup Summary

**requests dependency declared, InferenceError/VramError error classes added to cinecut.errors, and 6-test Phase 3 scaffold created with clean skip-all behavior**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T19:53:59Z
- **Completed:** 2026-02-26T19:55:17Z
- **Tasks:** 3 of 3 (checkpoint:human-verify approved by user)
- **Files modified:** 3

## Accomplishments
- requests>=2.31.0 added to pyproject.toml dependencies
- InferenceError and VramError added to src/cinecut/errors.py following established CineCutError pattern
- tests/test_inference.py scaffold with all 6 Phase 3 test cases collected and skip cleanly (6 skipped, 0 errors)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add requests dependency and InferenceError/VramError classes** - `9ac0f82` (feat)
2. **Task 2: Create test scaffold for Phase 3** - `daec717` (feat)
3. **Task 3: Checkpoint human-verify** - approved by user (no code changes)

**Plan metadata:** `77a95c5` (docs: complete Phase 3 plan 01 -- infrastructure setup checkpoint)

## Files Created/Modified
- `/home/adamh/ai-video-trailer/pyproject.toml` - Added requests>=2.31.0 to dependencies
- `/home/adamh/ai-video-trailer/src/cinecut/errors.py` - Added InferenceError and VramError classes
- `/home/adamh/ai-video-trailer/tests/test_inference.py` - Phase 3 test scaffold (6 tests, all skipped)

## Decisions Made
- InferenceError and VramError take only `detail: str` (no Path parameter) -- inference errors are not file-path-specific, unlike ProxyCreationError etc.
- pytest.importorskip used for all cinecut.inference.* imports so the scaffold file stays collectible before plan-02 creates those modules
- integration mark based on `_models_exist` flag checking both GGUF and mmproj file presence

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- pip install -e . blocked by externally-managed-environment (Debian PEP 668). Used `--break-system-packages` flag as project already uses system Python without venv. Import verification passed.

## User Setup Required

**LLaVA model files require manual download.** Run these commands before plan-02 integration tests will run:

```bash
mkdir -p /home/adamh/models
wget -c "https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/main/ggml-model-q4_k.gguf" \
     -O /home/adamh/models/ggml-model-q4_k.gguf
wget -c "https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/main/mmproj-model-f16.gguf" \
     -O /home/adamh/models/mmproj-model-f16.gguf
```

Verify: `ls -lh /home/adamh/models/*.gguf` -- both files should exist (~4+ GB base, ~600 MB mmproj)

## Next Phase Readiness
- Error classes ready for plan-02 LlavaEngine and vram module to import
- Test scaffold ready -- plan-02 will unskip tests as modules are implemented
- Model download approved by user; files at /home/adamh/models/ (prerequisite for integration tests)
- Plan 03-01 fully complete; 03-02 can begin immediately

---
*Phase: 03-llava-inference-engine*
*Completed: 2026-02-26*
