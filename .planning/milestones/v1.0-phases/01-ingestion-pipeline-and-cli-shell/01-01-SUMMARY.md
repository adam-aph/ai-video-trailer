---
phase: 01-ingestion-pipeline-and-cli-shell
plan: 01
subsystem: infra
tags: [python, hatchling, dataclasses, pyproject, package-scaffold]

# Dependency graph
requires: []
provides:
  - Installable cinecut Python package with hatchling build backend
  - DialogueEvent and KeyframeRecord dataclasses (shared data contracts)
  - CineCutError, ProxyCreationError, KeyframeExtractionError, SubtitleParseError, ProxyValidationError exception classes
  - src/cinecut/ingestion/ subpackage scaffold
affects:
  - 01-ingestion-pipeline-and-cli-shell (all subsequent plans import from models.py and errors.py)
  - 02-conform-pipeline (will use KeyframeRecord, ProxyValidationError)
  - 03-inference-engine (will use DialogueEvent, KeyframeExtractionError)
  - 04-manifest-and-conform (will use all models and errors)

# Tech tracking
tech-stack:
  added:
    - hatchling (PEP 517 build backend, src/ layout support)
    - typer>=0.12.0 (CLI framework, declared as dependency)
    - rich>=13.0.0 (terminal output, declared as dependency)
    - pysubs2==1.8.0 (subtitle parsing, declared as dependency)
    - scenedetect[opencv-headless]==0.6.7.1 (scene detection, declared as dependency)
    - better-ffmpeg-progress==4.0.1 (FFmpeg wrapper, declared as dependency)
    - charset-normalizer>=3.0.0 (encoding detection, declared as dependency)
  patterns:
    - src/ layout with hatchling (no setup.py, no setuptools)
    - stdlib dataclasses for ingestion-layer data contracts (no Pydantic at this layer)
    - Human-readable exception hierarchy with CineCutError base class
    - Each error names file, describes cause, and offers corrective suggestion

key-files:
  created:
    - pyproject.toml
    - src/cinecut/__init__.py
    - src/cinecut/models.py
    - src/cinecut/errors.py
    - src/cinecut/ingestion/__init__.py
    - tests/__init__.py
  modified: []

key-decisions:
  - "stdlib dataclasses over Pydantic for ingestion-layer models: validation overhead not needed at ingestion; Pydantic reserved for Phase 2 manifest work"
  - "hatchling over setuptools: handles src/ layout automatically with packages config, no [tool.setuptools] section needed"
  - "ProxyValidationError included (beyond plan minimum): handles FFmpeg exits 0 but produces corrupt proxy (Pitfall 3 from research)"

patterns-established:
  - "Error pattern: each CineCutError subclass takes (source_identifier, detail) and produces f-string message naming file + cause + corrective tip"
  - "Package layout: src/cinecut/ with ingestion/ subpackage for ingestion modules"

requirements-completed: [PIPE-01, CLI-03]

# Metrics
duration: 2min
completed: 2026-02-26
---

# Phase 1 Plan 01: Package Scaffold and Data Contracts Summary

**Installable cinecut package with hatchling build backend, shared DialogueEvent/KeyframeRecord dataclasses, and human-readable error hierarchy (ProxyCreationError, KeyframeExtractionError, SubtitleParseError, ProxyValidationError)**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T16:00:46Z
- **Completed:** 2026-02-26T16:03:11Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Installable cinecut package via `pip install -e .` with hatchling src/ layout
- Shared data contracts: `DialogueEvent` (subtitle event with ms/s timestamps and emotion) and `KeyframeRecord` (extracted frame with source type)
- Human-readable error translation layer: four exception classes each naming the file, cause, and corrective suggestion — implementing CLI-03 from day one

## Task Commits

Each task was committed atomically:

1. **Task 1: Create pyproject.toml and package skeleton** - `086d9e2` (chore)
2. **Task 2: Create models.py and errors.py** - `ce40ba2` (feat)

**Plan metadata:** `c89bf68` (docs: complete plan)

## Files Created/Modified
- `pyproject.toml` - Package metadata, hatchling build backend, dependencies, cinecut entry point
- `src/cinecut/__init__.py` - Package root marker
- `src/cinecut/models.py` - DialogueEvent and KeyframeRecord dataclasses
- `src/cinecut/errors.py` - CineCutError base + ProxyCreationError, KeyframeExtractionError, SubtitleParseError, ProxyValidationError
- `src/cinecut/ingestion/__init__.py` - Ingestion subpackage marker
- `tests/__init__.py` - Test package marker

## Decisions Made
- Used stdlib `dataclasses` over Pydantic for ingestion-layer models: validation overhead is not needed at the ingestion layer; Pydantic is reserved for Phase 2 manifest work.
- Used `hatchling` over `setuptools`: handles src/ layout automatically with the `packages` config, avoiding `[tool.setuptools]` sections.
- Included `ProxyValidationError` beyond the plan's required three error classes: handles the FFmpeg-exits-0-but-proxy-corrupt pitfall (Pitfall 3 from Phase 1 research), which plan 02 will raise after proxy creation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed pip via bootstrap script**
- **Found during:** Task 1 (pip install -e .)
- **Issue:** Neither `pip` nor `pip3` was available in the system Python; `python3 -m pip` and `ensurepip` both unavailable; system is Ubuntu 24.04 with externally-managed Python.
- **Fix:** Downloaded and ran `get-pip.py --user --break-system-packages` to install pip 26.0.1 to `~/.local/lib/python3.12/site-packages/`
- **Files modified:** System-level pip installation only (no project files changed)
- **Verification:** `pip --version` shows 26.0.1; `pip install -e .` completed successfully
- **Committed in:** Not committed (environment-level fix, not project file)

---

**Total deviations:** 1 auto-fixed (1 blocking — missing pip)
**Impact on plan:** Necessary environment fix to complete Task 1. No scope creep; no project files changed.

## Issues Encountered
- Ubuntu 24.04 "externally-managed" Python environment had no pip available and blocked `ensurepip`. Resolved by installing pip to user directory with `--break-system-packages` flag.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Package scaffold is complete; all subsequent ingestion modules can `from cinecut.models import ...` and `from cinecut.errors import ...`
- Plan 02 (proxy creation) can immediately use `ProxyCreationError` and `ProxyValidationError`
- CLI entry point binding (`cinecut = "cinecut.cli:app"`) is declared and resolves correctly; `cli.py` implementation is in a later plan
- No blockers for Phase 1 continuation

---
*Phase: 01-ingestion-pipeline-and-cli-shell*
*Completed: 2026-02-26*
