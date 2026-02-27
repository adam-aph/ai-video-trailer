---
phase: 05-trailer-assembly-and-end-to-end-pipeline
plan: 02
subsystem: assembly
tags: [ffmpeg, lavfi, pydantic, ordering, pacing, title-card]

# Dependency graph
requires:
  - phase: 02-manifest-contract-vibes-and-conform
    provides: ClipEntry/TrailerManifest schema, VibeProfile with act avg cut targets, ConformError
  - phase: 04-narrative-beat-extraction-and-manifest-generation
    provides: TrailerManifest instances from narrative generator for assembly input
provides:
  - cinecut.assembly package with assemble_manifest() entry point
  - sort_clips_by_act() enforcing canonical cold_open→act1→beat_drop→act2→breath→act3 order
  - enforce_pacing_curve() trimming act3 clips to measurable pacing curve
  - generate_title_card() producing pre-encoded MP4 via FFmpeg lavfi (no film frame extraction)
affects: [05-03-conform, 05-04-cli-integration, 05-05-e2e-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FFmpeg lavfi color source for synthetic segments (no ClipEntry with fake timecodes)"
    - "Pydantic v2 model_copy(update=...) for immutable clip trimming"
    - "ffprobe JSON output for dimension detection with 1920x1080 fallback"

key-files:
  created:
    - src/cinecut/assembly/__init__.py
    - src/cinecut/assembly/ordering.py
    - src/cinecut/assembly/title_card.py
  modified: []

key-decisions:
  - "title_card and button are pre-encoded MP4 files (FFmpeg lavfi), NOT ClipEntry objects — avoids extracting first 5s of film as fake segments"
  - "enforce_pacing_curve threshold is act3_avg_cut_s * 1.5 — only trims when clearly over target, avoids unnecessary changes"
  - "MIN_CLIP_DURATION_S = 0.5s floor — prevents trimming act3 clips to below-playable duration"
  - "get_video_dimensions falls back to 1920x1080 on ffprobe failure — ensures title card generation never hard-fails due to probe error"

patterns-established:
  - "Synthetic video segments (black cards, buttons) generated via lavfi color source with matching codec params (libx264 crf=18, aac 48000Hz)"
  - "act_priority dict drives sort_clips_by_act — title_card/button get priority 999 so they never appear in clip list"

requirements-completed: [EDIT-02, EDIT-03]

# Metrics
duration: 2min
completed: 2026-02-26
---

# Phase 05 Plan 02: Assembly Package Summary

**3-act clip ordering and FFmpeg lavfi title card generation implementing EDIT-02 canonical act sort and EDIT-03 measurable pacing curve enforcement**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T22:07:17Z
- **Completed:** 2026-02-26T22:09:17Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- `assembly/ordering.py` implements `sort_clips_by_act()` with canonical ACT_ORDER priority and `enforce_pacing_curve()` trimming act3 clips exceeding 1.5x target
- `assembly/title_card.py` generates pre-encoded black MP4 segments via FFmpeg lavfi — no ClipEntry fake timecodes, no film frame extraction
- `assembly/__init__.py` provides `assemble_manifest()` orchestrating ordering, pacing enforcement, segment generation, and ASSEMBLY_MANIFEST.json output

## Task Commits

Each task was committed atomically:

1. **Task 1: Create assembly/ordering.py and __init__.py** - `835a0fc` (feat)
2. **Task 2: Create assembly/title_card.py** - `b277233` (feat)

## Files Created/Modified
- `src/cinecut/assembly/__init__.py` - Package init exporting assemble_manifest() entry point
- `src/cinecut/assembly/ordering.py` - ACT_ORDER sort, pacing curve enforcement, avg duration helper
- `src/cinecut/assembly/title_card.py` - FFmpeg lavfi MP4 generation, ffprobe dimension detection

## Decisions Made
- `title_card` and `button` segments generated as standalone MP4 files via `ffmpeg -f lavfi`, never as ClipEntry objects with fake source timecodes (Pitfall 1 from research)
- Pacing curve threshold at 1.5x profile target: only trim act3 when clearly over-budget, not on minor variance
- `MIN_CLIP_DURATION_S = 0.5s` floor prevents trimming any clip below playable length
- `get_video_dimensions()` falls back to 1920x1080 on ffprobe failure rather than raising — title card generation remains resilient

## Deviations from Plan

None - plan executed exactly as written.

Note: `title_card.py` was created during Task 1 to unblock the ordering module verification (Python executes `__init__.py` on any submodule import, and `__init__.py` imports `title_card`). Both files were committed in their respective task commits as planned.

## Issues Encountered
- Python's package import mechanism executes `__init__.py` when any submodule is imported (e.g., `from cinecut.assembly.ordering import ...`), causing Task 1 verification to fail with `ModuleNotFoundError: No module named 'cinecut.assembly.title_card'` before Task 2 was complete. Resolution: created `title_card.py` before running Task 1 verification, committed it in Task 2 as planned.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `from cinecut.assembly import assemble_manifest` imports cleanly
- All verification tests pass: ACT_ORDER correct, sort order enforced, pacing curve computable, lavfi MP4 generation produces valid 7830-byte file
- Ready for Phase 05-03: conform pipeline to use assemble_manifest() before FFmpeg concat

## Self-Check: PASSED

- FOUND: src/cinecut/assembly/__init__.py
- FOUND: src/cinecut/assembly/ordering.py
- FOUND: src/cinecut/assembly/title_card.py
- FOUND: commit 835a0fc (Task 1)
- FOUND: commit b277233 (Task 2)

---
*Phase: 05-trailer-assembly-and-end-to-end-pipeline*
*Completed: 2026-02-26*
