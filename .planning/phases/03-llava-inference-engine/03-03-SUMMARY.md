---
phase: 03-llava-inference-engine
plan: "03"
subsystem: inference
tags: [llava, llama-server, describe_frame, json_schema, mock, cli, rich-progress, pydantic, unit-tests]

# Dependency graph
requires:
  - phase: 03-llava-inference-engine
    plan: "02"
    provides: "LlavaEngine context manager, SceneDescription dataclass, validate_scene_description(), SCENE_DESCRIPTION_SCHEMA"
  - phase: 01-ingestion-pipeline-and-cli-shell
    provides: "KeyframeRecord dataclass, CLI scaffold with Rich progress pattern"
provides:
  - "LlavaEngine.describe_frame(record, timeout_s) -- submits KeyframeRecord to /chat/completions, returns SceneDescription or None"
  - "run_inference_stage(records, model_path, mmproj_path, progress_callback) -- sequential LLaVA inference over all keyframes"
  - "CLI Stage 4/4: inference wired with Rich progress bar, --model/--mmproj options, summary panel"
  - "INFR-02 unit tests: test_describe_frame_structure and test_malformed_response_skipped both PASS"
affects:
  - 04-manifest-generation (inference_results list available for manifest builder)
  - 05-trailer-assembly (GPU_LOCK pattern unchanged, inference completes before conform)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "LlavaEngine.__new__() bypass pattern: unit tests instantiate engine without __enter__ to skip server startup"
    - "describe_frame uses lazy import for SCENE_DESCRIPTION_SCHEMA to avoid circular import"
    - "json_schema field (not response_format) in llama-server payload -- using response_format causes HTTP 400"
    - "describe_frame catches all expected exceptions and returns None -- pipeline never aborts on single frame failure"
    - "progress_callback(current, total) pattern: run_inference_stage calls back after each frame"

key-files:
  created: []
  modified:
    - src/cinecut/inference/engine.py
    - src/cinecut/cli.py
    - tests/test_inference.py

key-decisions:
  - "describe_frame accepts KeyframeRecord (not raw Path) -- consistent with pipeline data model; unit tests construct KeyframeRecord with str frame_path pointing to tmp_path fake JPEG"
  - "LlavaEngine.__new__() used in unit tests to bypass __enter__ (no server startup, no VRAM check, no GPU_LOCK) -- correct for mocked describe_frame tests"
  - "Integration test test_no_model_reload upgraded from pytest.skip to real test body (PID stability check) -- still @integration-marked so skips when models absent"
  - "CLI Stage 4 uses progress_callback closure that captures Rich Progress task ID -- same progress bar pattern as Stage 3 keyframe extraction"
  - "Inference results stored as list[tuple[KeyframeRecord, SceneDescription|None]] -- ready for Phase 4 manifest generation without blocking conform path"

patterns-established:
  - "run_inference_stage returns (record, desc_or_none) tuples: Phase 4 can filter None entries to find skipped frames"
  - "CLI inference stage only runs when --manifest is NOT provided (full pipeline path)"

requirements-completed: [INFR-02]

# Metrics
duration: 5min
completed: "2026-02-26"
---

# Phase 03 Plan 03: describe_frame() + CLI Inference Stage Summary

**LlavaEngine.describe_frame() with json_schema constrained output, run_inference_stage() for sequential pipeline processing, and INFR-02 unit tests passing with mocked requests.post**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-26T20:22:43Z
- **Completed:** 2026-02-26T20:27:45Z
- **Tasks:** 2 of 2 (checkpoint pending human verification)
- **Files modified:** 3

## Accomplishments

- `LlavaEngine.describe_frame(record, timeout_s)` added to engine.py: encodes JPEG as base64, builds llama-server payload with `json_schema` (not `response_format`), returns `SceneDescription` or `None` on any error
- `run_inference_stage(records, model_path, mmproj_path, progress_callback)` module-level function: wraps LlavaEngine context manager and iterates all records sequentially
- `test_describe_frame_structure`: PASSES -- mocked requests.post returns valid JSON, asserts all 4 SceneDescription fields
- `test_malformed_response_skipped`: PASSES -- mocked response returns non-JSON, asserts describe_frame returns None
- `test_no_model_reload` upgraded from `pytest.skip` to real integration test body (PID stability check)
- CLI: `--model` and `--mmproj` options added with defaults; Stage 4/4 inference wired with Rich progress bar and summary panel
- 69 non-integration tests pass, 0 regressions; 2 integration tests fail due to documented mmproj format blocker

## Task Commits

Each task was committed atomically:

1. **Task 1: Add describe_frame() and run_inference_stage() to engine.py** - `b2dfa5f` (feat)
2. **Task 2: Enable INFR-02 unit tests and wire inference into CLI** - `7c72412` (feat)

## Files Created/Modified

- `/home/adamh/ai-video-trailer/src/cinecut/inference/engine.py` - Added describe_frame() method and run_inference_stage() function
- `/home/adamh/ai-video-trailer/src/cinecut/cli.py` - Added --model/--mmproj options, Stage 4/4 inference stage with Rich progress
- `/home/adamh/ai-video-trailer/tests/test_inference.py` - Replaced pytest.skip with real implementations for test_describe_frame_structure and test_malformed_response_skipped; upgraded test_no_model_reload

## Decisions Made

- `describe_frame` accepts `KeyframeRecord` (not raw `Path`) to be consistent with pipeline data model; `KeyframeRecord.frame_path` is the str path read by `Path.read_bytes()`.
- `LlavaEngine.__new__()` pattern used in unit tests to bypass `__enter__` -- avoids VRAM check, GPU_LOCK, and llama-server startup entirely. Engine object initialized with `base_url`, `_process=None`, `debug=False`.
- Integration test `test_no_model_reload` upgraded from `pytest.skip` to real body checking PID stability; still `@integration` marked so it only runs when model files present.
- CLI inference stage only runs when `--manifest` flag is NOT provided. The conform path (`--manifest`) continues to work unchanged.
- `run_inference_stage` returns `list[tuple[KeyframeRecord, SceneDescription | None]]` -- Phase 4 manifest generation will consume this list.

## Deviations from Plan

None - plan executed exactly as written.

## Integration Test Blocker (Known Issue)

`test_server_health` and `test_no_model_reload` both FAIL when model files are present because the downloaded `mmproj-model-f16.gguf` (from `mys/ggml_llava-v1.5-7b` on HuggingFace) lacks the `clip.projector_type` metadata key required by llama.cpp build 8156.

**Error message:** `clip_init: failed to load model '...mmproj-model-f16.gguf': load_hparams: unknown projector type:`

**Root cause:** The older GGUF V2 format from this model repo predates the `clip.projector_type` spec addition. llama.cpp 8156 requires this key to be `"mlp"` for LLaVA 1.5 models.

**Fix options:**
1. Download a newer mmproj from a repo that sets `clip.projector_type = "mlp"` (e.g., `bartowski/llava-v1.5-7b-GGUF`)
2. Patch the GGUF file to add the missing metadata key using a Python GGUF editor
3. Build an older llama.cpp version (pre-projector-type requirement)

This is a model file compatibility issue, not a code bug. All unit tests (describe_frame, vram_check, gpu_lock) pass correctly with mocked infrastructure.

## Self-Check: PASSED

Files verified:
- `src/cinecut/inference/engine.py` -- FOUND (has describe_frame + run_inference_stage)
- `src/cinecut/cli.py` -- FOUND (has run_inference_stage import, Stage 4/4)
- `tests/test_inference.py` -- FOUND (136 lines, >= 80 minimum)

Commits verified:
- `b2dfa5f` -- FOUND (Task 1)
- `7c72412` -- FOUND (Task 2)

## Next Phase Readiness

- `run_inference_stage` returns `(KeyframeRecord, SceneDescription | None)` tuples ready for Phase 4 manifest generation
- Integration tests blocked by mmproj compatibility; fix requires new model file or GGUF patch
- All INFR-02 requirements delivered; INFR-01/INFR-03/PIPE-05 delivered in plan 02

---
*Phase: 03-llava-inference-engine*
*Completed: 2026-02-26*
