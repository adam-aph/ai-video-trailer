---
phase: 04-narrative-beat-extraction-and-manifest-generation
plan: "01"
subsystem: narrative
tags: [opencv, cv2, signals, scoring, beat-classification, manifest-schema, pydantic]

# Dependency graph
requires:
  - phase: 03-llava-inference-engine
    provides: SceneDescription dataclass from cinecut.inference.models
  - phase: 01-ingestion-pipeline-and-cli-shell
    provides: KeyframeRecord and DialogueEvent dataclasses from cinecut.models
  - phase: 02-manifest-contract-vibes-and-conform
    provides: ClipEntry/TrailerManifest Pydantic schema from cinecut.manifest.schema
provides:
  - ClipEntry extended with 4 Optional analysis metadata fields (reasoning, visual_analysis, subtitle_analysis, money_shot_score)
  - cinecut.narrative.signals: 8-signal extraction (motion, contrast, uniqueness, subtitle emotion, face presence, llava confidence, saturation, chron position)
  - cinecut.narrative.scorer: normalization, weighted money_shot_score, 7-rule beat classification, act assignment
affects: [04-02-manifest-generator, plan 02 of phase 04]

# Tech tracking
tech-stack:
  added: [opencv-python-headless>=4.8.0]
  patterns:
    - Module-level CascadeClassifier singleton (avoid 200ms per-frame reload penalty)
    - Rule-priority beat classification (earlier rule wins, deterministic)
    - Beat-type-first act assignment (beat_type="breath" overrides chronological position)
    - Min-max normalization with degenerate-pool fallback to 0.5
    - O(n^2) pairwise histogram comparison for pool-level scene uniqueness

key-files:
  created:
    - src/cinecut/narrative/__init__.py
    - src/cinecut/narrative/signals.py
    - src/cinecut/narrative/scorer.py
  modified:
    - src/cinecut/manifest/schema.py
    - pyproject.toml

key-decisions:
  - "CascadeClassifier loaded once at module level (not per-frame) to avoid 200ms startup penalty on each face detection call"
  - "RawSignals._histogram stored as non-dataclass field (field with repr=False, compare=False) so it travels with the struct without affecting equality or repr"
  - "assign_act: beat_type wins before positional check -- breath beat always returns breath act regardless of chron_pos"
  - "classify_beat rule order: breath first (low score + neutral), then climax (late + high), then money_shot (very high), then character_introduction, inciting_incident, relationship_beat, escalation_beat (catch-all)"
  - "normalize_signal_pool degenerate case (all equal) returns 0.5 per value rather than 0.0 to avoid false zero scoring"
  - "opencv-python-headless declared in pyproject.toml -- package was already installed (4.13.0.92) but undeclared as project dependency"

patterns-established:
  - "Signal extraction: O(n^2) pool-level uniqueness computed after all frames extracted"
  - "Normalization: always normalize across the full pool, not per-frame, to enable relative comparison"
  - "ClipEntry optional fields: all Phase 4 metadata fields are Optional with None defaults for backward compatibility"

requirements-completed: [NARR-02, NARR-03]

# Metrics
duration: 2min
completed: 2026-02-26
---

# Phase 4 Plan 01: Narrative Signals and Scorer Summary

**8-signal extraction pipeline (motion, contrast, uniqueness, subtitle emotion, face, LLaVA confidence, saturation, chron position) with min-max normalization, weighted money_shot_score, 7-rule beat classifier, and act assignment -- ClipEntry extended with 4 Optional analysis metadata fields**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T21:50:59Z
- **Completed:** 2026-02-26T21:52:47Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Extended ClipEntry with reasoning, visual_analysis, subtitle_analysis, money_shot_score as Optional fields -- backward compatible with all 21 existing manifest fixture tests
- Implemented signals.py with 8-signal extraction: motion magnitude (frame diff), visual contrast (Laplacian variance), scene uniqueness (O(n^2) histogram pairwise), subtitle emotional weight (nearest event in 5s window), face presence (Haar cascade), LLaVA confidence (completeness + richness), saturation (HSV mean), chronological position
- Implemented scorer.py with SIGNAL_WEIGHTS (sum=1.0), min-max pool normalization, weighted money_shot_score computation, 7-rule priority beat classifier, and beat-type-first act assignment
- Added opencv-python-headless>=4.8.0 to pyproject.toml as explicit dependency

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend ClipEntry with 4 Optional analysis fields** - `d77f00a` (feat)
2. **Task 2: Create narrative package -- signals.py and scorer.py** - `8bfbb83` (feat)

**Plan metadata:** _(docs commit follows)_

## Files Created/Modified

- `src/cinecut/manifest/schema.py` - Added Optional import + 4 Optional analysis fields to ClipEntry after dialogue_excerpt
- `src/cinecut/narrative/__init__.py` - Package marker with module docstring
- `src/cinecut/narrative/signals.py` - 8-signal extraction: RawSignals dataclass, EMOTION_WEIGHTS, get_film_duration_s, get_subtitle_emotional_weight, compute_llava_confidence, extract_image_signals, compute_motion_magnitudes, compute_uniqueness_scores, extract_all_signals
- `src/cinecut/narrative/scorer.py` - SIGNAL_WEIGHTS dict, normalize_signal_pool, normalize_all_signals, compute_money_shot_score, classify_beat, assign_act
- `pyproject.toml` - Added opencv-python-headless>=4.8.0 dependency declaration

## Decisions Made

- CascadeClassifier loaded once at module level (not per-frame) to avoid 200ms startup penalty
- RawSignals._histogram stored as non-dataclass field so it travels with the struct without affecting equality or repr
- assign_act: beat_type wins before positional check -- breath beat always returns breath act
- normalize_signal_pool degenerate case returns 0.5 (not 0.0) to avoid false zero scoring for flat signal pools
- classify_beat rule order is priority-first: breath (low+neutral), climax (late+high), money_shot (very high), character_introduction, inciting_incident, relationship_beat, escalation_beat (catch-all)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- signals.py and scorer.py are the algorithmic core ready for Plan 02 (generator.py)
- generator.py (Plan 02) can import: extract_all_signals, normalize_all_signals, compute_money_shot_score, classify_beat, assign_act
- ClipEntry accepts money_shot_score, reasoning, visual_analysis, subtitle_analysis for manifest population

---
*Phase: 04-narrative-beat-extraction-and-manifest-generation*
*Completed: 2026-02-26*
