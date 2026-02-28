---
phase: 07-structural-analysis
plan: 02
subsystem: inference
tags: [structural-analysis, mistral, subtitle-chunking, manifest-schema, heuristic-fallback, tdd]
dependency_graph:
  requires: [07-01]
  provides: [structural_anchors, manifest-v2.0, stage5-gate]
  affects: [cli.py, manifest/schema.py, narrative/generator.py, checkpoint.py]
tech_stack:
  added: [statistics.median for anchor aggregation]
  patterns: [chunk-and-aggregate LLM pattern, inline imports to avoid circular deps, constrained JSON generation via json_schema]
key_files:
  created:
    - src/cinecut/inference/structural.py
    - tests/test_structural.py
  modified:
    - src/cinecut/inference/text_engine.py
    - src/cinecut/manifest/schema.py
    - src/cinecut/checkpoint.py
    - src/cinecut/cli.py
    - src/cinecut/narrative/generator.py
decisions:
  - "_clamp_anchors_to_chunk uses +-10s tolerance window — prevents hallucinated LLM timestamps from polluting median aggregation"
  - "Inline import of StructuralAnchors in structural.py (avoid circular import from manifest.schema)"
  - "Mock LLM tests use chunk-local timestamps: test vectors must be within [chunk_start-10, chunk_end+10] for clamp to pass through"
  - "statistics.median aggregation across chunks smooths per-chunk variation; single valid chunk passes through unchanged"
metrics:
  duration: ~10 min
  completed: 2026-02-28
  tasks_completed: 3
  files_changed: 7
---

# Phase 7 Plan 02: Structural Analysis Implementation Summary

Structural analysis pipeline: subtitle chunking + Mistral LLM inference + heuristic fallback + manifest v2.0 schema + Stage 5 in cli.py. Anchors flow from Stage 5 through Stage 6 (run_narrative_stage) into TRAILER_MANIFEST.json.

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Create structural.py and add analyze_chunk to TextEngine | f4cc4d6 | src/cinecut/inference/structural.py, src/cinecut/inference/text_engine.py |
| 2 | StructuralAnchors schema, Stage 5, TOTAL_STAGES=8, generator wiring | 246b0f3 | src/cinecut/manifest/schema.py, src/cinecut/checkpoint.py, src/cinecut/cli.py, src/cinecut/narrative/generator.py |
| 3 | Unit tests for structural.py (20 tests, no live LLM) | d5aa8c2 | tests/test_structural.py |

## What Was Built

### src/cinecut/inference/structural.py (new)

- `CHUNK_SIZE = 75` — processes subtitle corpus in 75-event chunks (~1500 tokens each)
- `STRUCTURAL_ANCHORS_SCHEMA` — JSON schema for constrained Mistral output
- `_format_subtitle_chunk()` — formats events with absolute `start_s` timestamps (never normalized)
- `_chunk_events()` — splits events into CHUNK_SIZE slices
- `_clamp_anchors_to_chunk()` — rejects LLM results with timestamps more than 10s outside chunk boundaries (hallucination guard)
- `compute_heuristic_anchors(duration_s)` — 5%/45%/80% zone fallback, source="heuristic"
- `run_structural_analysis(events, engine)` — chunk loop, median aggregation, heuristic fallback if all chunks fail

### src/cinecut/inference/text_engine.py (modified)

- Added `analyze_chunk(chunk_text, timeout_s=60.0)` method to TextEngine
- Uses `/v1/chat/completions` endpoint (NOT `/chat/completions` — per research pitfall 1)
- `json_schema` constrained generation for deterministic output
- Returns `dict | None` — never raises, pipeline continues on chunk failure

### src/cinecut/manifest/schema.py (modified)

- Added `StructuralAnchors` model before `ClipEntry` with `begin_t`, `escalation_t`, `climax_t`, `source` fields
- `TrailerManifest.schema_version` bumped from `"1.0"` to `"2.0"` — kept as `str` (not Literal) for backward compat
- `TrailerManifest.structural_anchors: Optional[StructuralAnchors] = None` — old v1.0 manifests load without error

### src/cinecut/checkpoint.py (modified)

- Added `proxy_duration_s: Optional[float] = None` — captured in Stage 1 for heuristic fallback
- Added `structural_anchors: Optional[dict] = None` — StructuralAnchors.model_dump() result for resume

### src/cinecut/cli.py (modified)

- `TOTAL_STAGES = 8` (was 7)
- Added imports: `TextEngine`, `run_structural_analysis`, `compute_heuristic_anchors`, `StructuralAnchors`, `get_film_duration_s`
- Stage 1: captures `proxy_duration_s` via `get_film_duration_s(proxy_path)` after proxy creation/resume
- Stage 5 (new): structural analysis gate — heuristic if GGUF absent (yellow warning), LLM inference with TextEngine if GGUF present; saves `ckpt.structural_anchors`
- Old Stage 5 → Stage 6 (narrative); old Stage 6 → Stage 7 (assembly); old Stage 7 → Stage 8 (conform)
- Stage 6: `run_narrative_stage(..., structural_anchors=structural_anchors)` — variable always in scope from Stage 5

### src/cinecut/narrative/generator.py (modified)

- Added `StructuralAnchors` to import line
- `run_narrative_stage` signature extended with `structural_anchors: Optional[StructuralAnchors] = None`
- `TrailerManifest(...)` instantiation passes `structural_anchors=structural_anchors` — when not None, appears in `model_dump_json(exclude_none=True)` output

### tests/test_structural.py (new, 252 lines, 20 tests)

All tests use `MagicMock` for engine — no live llama-server needed.

Key test insight: mock responses must use timestamps within `[chunk_start - 10, chunk_end + 10]` to survive `_clamp_anchors_to_chunk`. Tests revised to use chunk-local timestamps.

## Decisions Made

1. **Inline StructuralAnchors import in structural.py** — avoids circular import since structural.py is imported by text_engine.py analyze_chunk which lives in same package as schema.py

2. **_clamp_anchors_to_chunk tolerance +-10s** — matches plan spec; prevents LLM hallucinations from polluting median while allowing minor timestamp imprecision

3. **Mock test vectors use chunk-local timestamps** — discovered during testing that mock returning out-of-range timestamps (300s, 3000s) would be clamped out by the guard. Corrected tests to use values within chunk span.

4. **statistics.median aggregation** — single valid chunk passes through unchanged (median of one value); two chunks produce true median

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test vectors in run_structural_analysis tests used out-of-range timestamps**
- **Found during:** Task 3 test execution
- **Issue:** Tests `test_run_structural_analysis_single_chunk` and `test_run_structural_analysis_median_aggregation` used mock LLM responses with timestamps (300.0, 3000.0, 5500.0) far outside the chunk's timestamp range (events spanning 0-30s). `_clamp_anchors_to_chunk` correctly rejected these as hallucinations, causing tests to assert `source == 'llm'` on what became a heuristic result.
- **Fix:** Updated mock response timestamps to values within each chunk's span. Single chunk test: events span 0..31s, mock returns begin_t=3.0, escalation_t=12.0, climax_t=24.0. Median aggregation test: chunk1 spans 0..224s (returns 10/100/200), chunk2 spans 225..449s (returns 230/330/430).
- **Files modified:** tests/test_structural.py
- **Commit:** d5aa8c2

## Self-Check

### Files exist
- src/cinecut/inference/structural.py: FOUND
- src/cinecut/inference/text_engine.py: FOUND (analyze_chunk method added)
- src/cinecut/manifest/schema.py: FOUND (StructuralAnchors + schema_version 2.0)
- src/cinecut/checkpoint.py: FOUND (proxy_duration_s + structural_anchors)
- src/cinecut/cli.py: FOUND (Stage 5 + TOTAL_STAGES=8)
- src/cinecut/narrative/generator.py: FOUND (structural_anchors kwarg)
- tests/test_structural.py: FOUND (252 lines, 20 tests)

### Commits exist
- f4cc4d6: FOUND
- 246b0f3: FOUND
- d5aa8c2: FOUND

### Test results
- tests/test_structural.py: 20 passed
- Full suite: 153 passed (0 failures)

## Self-Check: PASSED
