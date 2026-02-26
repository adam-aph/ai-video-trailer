---
phase: 01-ingestion-pipeline-and-cli-shell
plan: "05"
subsystem: cli
tags: [typer, rich, click, validation, cli]

# Dependency graph
requires:
  - phase: 01-ingestion-pipeline-and-cli-shell
    provides: CLI entry point (cli.py) with typer + rich error panels from 01-01 through 01-04

provides:
  - "CLI validation order fixed: extension checks fire before existence checks for VIDEO and --subtitle"
  - "Manual video.exists() and subtitle.exists() checks inside main() after extension checks"
  - "tests/test_cli.py with 5 validation tests covering all extension/existence ordering edge cases"

affects:
  - Phase 2 manifest/conform work that exercises the CLI
  - Any future UAT or CLI integration tests

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Remove exists=True from typer.Argument/Option; use manual Path.exists() checks inside main() for ordered validation"
    - "typer.testing.CliRunner (no mix_stderr kwarg; outputs are mixed by default) for CLI unit tests"

key-files:
  created:
    - tests/test_cli.py
  modified:
    - src/cinecut/cli.py

key-decisions:
  - "Removed exists=True from typer.Argument and typer.Option — Typer fires these at parse time before main() is entered, preventing Rich error panels from being shown for wrong-extension nonexistent files"
  - "Manual if not video.exists() and if not subtitle.exists() checks positioned after respective extension checks inside main() — ensures extension always wins in error priority"

patterns-established:
  - "CLI validation ordering: extension check then existence check for each argument"
  - "Always use Rich error panels for all input validation failures — no Typer/Click plain errors visible to users"

requirements-completed: [CLI-02, CLI-03]

# Metrics
duration: 2min
completed: 2026-02-26
---

# Phase 1 Plan 05: Fix CLI Validation Order Summary

**Extension checks now always fire before existence checks in the cinecut CLI, ensuring Rich error panels appear for all invalid-input cases including wrong-extension nonexistent files.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T16:12:40Z
- **Completed:** 2026-02-26T16:14:13Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Removed `exists=True` from `typer.Argument` and `typer.Option` in `cli.py` — these were triggering Click's parse-time existence check before `main()` entered, bypassing Rich error panels
- Added manual `if not video.exists()` and `if not subtitle.exists()` checks inside `main()` after the respective extension checks — establishing the correct priority order
- Created `tests/test_cli.py` with 5 test cases covering all validation-order edge cases (wrong extension + nonexistent, wrong extension + existent, valid extension + nonexistent, for both video and subtitle)

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove exists=True and add manual existence checks in cli.py** - `3443aa0` (fix)
2. **Task 2: Add CLI validation tests covering extension and existence order** - `d99b3a2` (test)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `src/cinecut/cli.py` - Removed `exists=True` from VIDEO and subtitle args; added manual existence checks after extension checks
- `tests/test_cli.py` - 5 new CLI validation tests using `typer.testing.CliRunner`

## Decisions Made

- Removed `exists=True` rather than reordering Typer argument declarations — the issue is architectural: Typer fires `exists=True` at parse time (Click layer), before `main()` body is executed, making it impossible to run extension checks first via Typer's own mechanisms
- Used `typer.testing.CliRunner()` without `mix_stderr` kwarg — Typer's CliRunner does not support this Click-only parameter; output (stdout+stderr) is already mixed by default in the Typer test runner

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unsupported mix_stderr=True kwarg from CliRunner instantiation**
- **Found during:** Task 2 (creating tests/test_cli.py)
- **Issue:** Plan specified `runner = CliRunner(mix_stderr=True)` but `typer.testing.CliRunner.__init__` does not accept `mix_stderr` (it is a Click-only kwarg). This caused a `TypeError` during test collection.
- **Fix:** Changed to `runner = CliRunner()` — Typer's CliRunner already mixes stdout/stderr into `result.output` by default
- **Files modified:** tests/test_cli.py
- **Verification:** All 5 tests pass; `result.output` contains Rich panel text from `err_console` (stderr)
- **Committed in:** d99b3a2 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in plan spec)
**Impact on plan:** Minor fix to accommodate Typer's CliRunner API. Behavior is identical — outputs are still mixed, assertions work as intended.

## Issues Encountered

None beyond the auto-fixed CliRunner kwarg issue above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All Phase 1 CLI requirements (CLI-02, CLI-03) are now fully satisfied
- Phase 1 ingestion pipeline complete: proxy, subtitles, keyframes, CLI shell, PATH fix, validation order
- Ready to proceed to Phase 2 (manifest/conform pipeline)

---
*Phase: 01-ingestion-pipeline-and-cli-shell*
*Completed: 2026-02-26*

## Self-Check: PASSED

- FOUND: src/cinecut/cli.py
- FOUND: tests/test_cli.py
- FOUND: 01-05-SUMMARY.md
- FOUND commit: 3443aa0 (fix: remove exists=True)
- FOUND commit: d99b3a2 (test: add CLI validation tests)
- VERIFIED: no exists=True in cli.py
- VERIFIED: video.exists() check at line 83
- VERIFIED: subtitle.exists() check at line 101
