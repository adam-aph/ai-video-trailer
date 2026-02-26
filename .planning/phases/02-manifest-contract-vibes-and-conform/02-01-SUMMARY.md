---
phase: 02-manifest-contract-vibes-and-conform
plan: 01
subsystem: manifest
tags: [pydantic, numpy, lut, vibe-profiles, schema, color-grading]

# Dependency graph
requires:
  - phase: 01-ingestion-pipeline-and-cli-shell
    provides: src layout, pyproject.toml hatchling config, errors.py CineCutError base
provides:
  - TrailerManifest and ClipEntry Pydantic v2 models (schema.py)
  - VALID_VIBES frozenset with 18 canonical vibe names (schema.py)
  - load_manifest() function raising ManifestError on failure (loader.py)
  - VibeProfile frozen dataclass and VIBE_PROFILES dict with 18 entries (vibes.py)
  - ManifestError and ConformError classes (errors.py)
  - generate_cube_lut() and ensure_luts() for .cube LUT file generation (conform/luts.py)
affects: [phase-02-02, phase-02-03, phase-04-manifest-generation, all downstream phases using vibe color grading]

# Tech tracking
tech-stack:
  added: [pydantic>=2.12.0, numpy>=1.24.0]
  patterns:
    - Pydantic v2 model_validate_json() with ValidationError caught and re-raised as ManifestError
    - VALID_VIBES defined in schema.py (not vibes.py) to avoid circular imports
    - NumPy meshgrid indexing='ij' with R-fastest B-slowest loop order for .cube files
    - ensure_luts() idempotent pattern: check file exists before generating

key-files:
  created:
    - src/cinecut/manifest/__init__.py
    - src/cinecut/manifest/schema.py
    - src/cinecut/manifest/loader.py
    - src/cinecut/manifest/vibes.py
    - src/cinecut/conform/__init__.py
    - src/cinecut/conform/luts.py
  modified:
    - pyproject.toml
    - src/cinecut/errors.py

key-decisions:
  - "VALID_VIBES defined as standalone frozenset in schema.py to avoid circular import with vibes.py"
  - "scifi -> sci-fi alias mapping added to normalize_vibe() for user convenience"
  - "LUT_SIZE=33 (professional standard, 33^3=35937 triplets per file)"
  - "ensure_luts() raises ValueError (not ConformError) on unknown vibe -- programming error not runtime"
  - "VibeProfile frozen dataclass (immutable) so profiles cannot be mutated at runtime"

patterns-established:
  - "Circular import prevention: constants needed by multiple modules go in the higher-level module (schema.py)"
  - "NumPy .cube generation: meshgrid indexing='ij', R-fastest loop order, 6 decimal formatting"
  - "Idempotent file generation: check existence before computing, return early"

requirements-completed: [VIBE-01, VIBE-02]

# Metrics
duration: 3min
completed: 2026-02-26
---

# Phase 02 Plan 01: Manifest Contract, Vibe Profiles, and LUT Generation Summary

**Pydantic v2 TrailerManifest schema with 18 vibe profiles, ManifestError/ConformError types, and NumPy-based .cube LUT generator for FFmpeg color grading**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-26T18:58:29Z
- **Completed:** 2026-02-26T19:01:07Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- Pydantic v2 TrailerManifest and ClipEntry models with field-level validation and vibe normalization
- 18 VibeProfile instances covering every genre with complete color, pacing, and audio parameters
- NumPy-vectorized .cube LUT generator with correct R-fastest loop order for FFmpeg lut3d filter
- ManifestError and ConformError classes extending CineCutError with structured error messages

## Task Commits

Each task was committed atomically:

1. **Task 1: Add pydantic/numpy deps and create manifest schema + loader** - `437ff08` (feat)
2. **Task 2: Create VibeProfile dataclass with all 18 profiles** - `1303442` (feat)
3. **Task 3: Create LUT generation module (conform/luts.py)** - `466eafd` (feat)

**Plan metadata:** (docs commit - see below)

## Files Created/Modified
- `pyproject.toml` - Added pydantic>=2.12.0 and numpy>=1.24.0 dependencies
- `src/cinecut/errors.py` - Extended with ManifestError and ConformError classes
- `src/cinecut/manifest/__init__.py` - Empty package marker
- `src/cinecut/manifest/schema.py` - TrailerManifest, ClipEntry Pydantic v2 models; VALID_VIBES frozenset; normalize_vibe() field validator
- `src/cinecut/manifest/loader.py` - load_manifest() function; ValidationError -> ManifestError conversion
- `src/cinecut/manifest/vibes.py` - VibeProfile frozen dataclass; VIBE_PROFILES dict with all 18 profiles
- `src/cinecut/conform/__init__.py` - Empty package marker
- `src/cinecut/conform/luts.py` - generate_cube_lut() and ensure_luts() with NumPy vectorization

## Decisions Made
- VALID_VIBES placed in schema.py (not vibes.py) to avoid circular imports. vibes.py is fully standalone.
- scifi->sci-fi alias mapping added to normalize_vibe() alongside standard lowercasing/hyphenation.
- LUT_SIZE=33 chosen as the professional standard (not 17 or 65) per research recommendation.
- ensure_luts() raises ValueError (not ConformError) on unknown vibe name -- this is a programming error (wrong key) not a recoverable runtime failure.
- VibeProfile uses frozen=True dataclass to prevent accidental mutation of profile constants.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- manifest/ and conform/luts.py modules are importable and tested
- All 18 vibe profiles are ready for use in downstream phases
- TrailerManifest schema is the long-lived contract that Phase 4 must produce valid instances of
- .cube LUT generation verified correct: identity LUT produces (0,0,0) and (1,0,0) as first two triplets (R-fastest)
- pydantic and numpy are installed system-wide

---
*Phase: 02-manifest-contract-vibes-and-conform*
*Completed: 2026-02-26*

## Self-Check: PASSED

All files verified present. All task commits verified in git log:
- FOUND: src/cinecut/manifest/__init__.py
- FOUND: src/cinecut/manifest/schema.py
- FOUND: src/cinecut/manifest/loader.py
- FOUND: src/cinecut/manifest/vibes.py
- FOUND: src/cinecut/conform/__init__.py
- FOUND: src/cinecut/conform/luts.py
- FOUND: 437ff08 feat(02-01): add manifest schema, loader, and error types
- FOUND: 1303442 feat(02-01): add VibeProfile dataclass with all 18 vibe profiles
- FOUND: 466eafd feat(02-01): add LUT generation module (conform/luts.py)
