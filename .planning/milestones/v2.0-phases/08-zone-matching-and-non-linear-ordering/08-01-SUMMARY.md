---
phase: 08-zone-matching-and-non-linear-ordering
plan: "01"
subsystem: narrative/zone_matching + manifest/schema
tags: [zone-matching, narrative-structure, sentence-transformers, pydantic, STRC-02]
dependency_graph:
  requires: []
  provides: [NarrativeZone enum, ClipEntry.narrative_zone field, run_zone_matching(), assign_narrative_zone(), ZONE_ANCHORS]
  affects: [src/cinecut/manifest/schema.py, src/cinecut/narrative/zone_matching.py]
tech_stack:
  added: [sentence-transformers>=3.0, torch>=2.0]
  patterns: [lru_cache singleton, str Enum Pydantic serialization, position-based fallback, mock patching module-level attributes]
key_files:
  created:
    - src/cinecut/narrative/zone_matching.py
    - tests/test_zone_matching.py
  modified:
    - src/cinecut/manifest/schema.py
    - tests/test_assembly.py
    - pyproject.toml
decisions:
  - "util exposed as module-level None attribute in zone_matching.py so tests can patch it without sentence-transformers being installed"
  - "NarrativeZone placed before StructuralAnchors in schema.py (both are Phase 8/7 additions respectively)"
  - "TestSortClipsByZone and TestEnforceZonePacingCurve written without skip guards per Wave 0 pattern — expected to fail until 08-02"
metrics:
  duration_minutes: 18
  completed_date: "2026-02-28"
  tasks_completed: 3
  files_changed: 5
---

# Phase 08 Plan 01: Zone Matching Foundation Summary

NarrativeZone str enum + ClipEntry.narrative_zone field + all-MiniLM-L6-v2 CPU zone assignment module with lru_cache singleton and position-based fallback for empty dialogue.

## What Was Built

**src/cinecut/manifest/schema.py** — Extended with:
- `NarrativeZone(str, Enum)` with BEGINNING, ESCALATION, CLIMAX values. `str, Enum` ensures Pydantic v2 serializes as plain string (`"BEGINNING"` not `{"value":"BEGINNING"}`).
- `ClipEntry.narrative_zone: Optional[NarrativeZone] = None` — backward compatible field; old manifests load without ValidationError; absent from JSON when `exclude_none=True`.

**src/cinecut/narrative/zone_matching.py** — New module with:
- `ZONE_ANCHORS: dict[NarrativeZone, str]` — static semantic anchor phrases for each zone
- `_load_model()` — lru_cache singleton loading `all-MiniLM-L6-v2` on `device='cpu'`; sets module-level `util` reference
- `_zone_by_position()` — position-based fallback using StructuralAnchors timestamps or 33%/66% fraction split
- `assign_narrative_zone()` — single-clip assignment; routes to position fallback for empty dialogue
- `run_zone_matching()` — batch assignment; pre-encodes anchor phrases once; position fallback for all-empty input (no model load)

**tests/test_zone_matching.py** — 14 unit tests (179 lines), no live model download required:
- ZONE_ANCHORS completeness, position fallback (no anchors + with StructuralAnchors), empty/whitespace fallback, semantic assignment (mocked util.cos_sim), batch length/type checks

**tests/test_assembly.py** — TestSortClipsByZone (5 tests) and TestEnforceZonePacingCurve (4 tests) appended; fail with ImportError until 08-02 implements `sort_clips_by_zone`/`enforce_zone_pacing_curve`.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | `4b083bf` | feat(08-01): add NarrativeZone enum and ClipEntry.narrative_zone to schema |
| 2 | `fee57a4` | feat(08-01): create narrative/zone_matching.py with CPU sentence-transformers zone assignment |
| 3 | `d1e2da8` | feat(08-01): add zone matching tests and append zone ordering test stubs |

## Test Results

```
tests/test_zone_matching.py: 14 passed
tests/test_manifest.py + test_cache.py + test_checkpoint.py: 40 passed
Full suite (excluding new zone stubs): 153 passed, 0 failures
New zone stubs (test_assembly.py): 9 ImportError — expected until 08-02
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed util.cos_sim mock patching approach**
- **Found during:** Task 3
- **Issue:** `util` was imported inside function body (`from sentence_transformers import util`), making `patch("cinecut.narrative.zone_matching.util")` fail with AttributeError and `patch("sentence_transformers.util.cos_sim")` fail because sentence_transformers is not installed in the dev environment.
- **Fix:** Exposed `util` as a module-level `None` attribute in zone_matching.py (set to the real `sentence_transformers.util` by `_load_model()` on first call). Tests patch `cinecut.narrative.zone_matching.util` directly.
- **Files modified:** `src/cinecut/narrative/zone_matching.py`, `tests/test_zone_matching.py`
- **Commit:** `d1e2da8`

## Self-Check: PASSED

Files verified:
- `src/cinecut/manifest/schema.py` — FOUND (NarrativeZone enum, ClipEntry.narrative_zone)
- `src/cinecut/narrative/zone_matching.py` — FOUND (ZONE_ANCHORS, _load_model, assign_narrative_zone, run_zone_matching)
- `tests/test_zone_matching.py` — FOUND (179 lines, 14 tests)
- `tests/test_assembly.py` — FOUND (TestSortClipsByZone and TestEnforceZonePacingCurve appended)

Commits verified:
- `4b083bf` — FOUND
- `fee57a4` — FOUND
- `d1e2da8` — FOUND
