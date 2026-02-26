---
phase: 01-ingestion-pipeline-and-cli-shell
plan: "04"
subsystem: infra
tags: [bash, PATH, shell-config, cinecut, cli]

requires: []
provides:
  - "~/.bash_profile with unconditional PATH export for ~/.local/bin"
  - "~/.bashrc PATH export moved before non-interactive guard"
  - "cinecut command accessible in all shell contexts including non-interactive subshells"
affects: [uat, ci, test-execution, phase-01-05]

tech-stack:
  added: []
  patterns:
    - "PATH export in ~/.bash_profile for unconditional login-shell coverage"
    - "PATH export before non-interactive guard in ~/.bashrc for script/subshell coverage"

key-files:
  created:
    - "~/.bash_profile: unconditional PATH export for ~/.local/bin, sources ~/.bashrc"
  modified:
    - "~/.bashrc: moved PATH export to line 6 (before non-interactive guard at line 9); removed duplicate at old lines 124-125"
    - ".planning/debug/gap1-cinecut-not-on-path.md: status updated to resolved with fix details"

key-decisions:
  - "Created ~/.bash_profile (not modifying ~/.profile) -- ~/.bash_profile takes precedence over ~/.profile for bash login shells, providing a clean, dedicated location for the PATH export"
  - "Moved PATH line in ~/.bashrc to before the guard instead of removing it -- covers non-login non-interactive subshells that source ~/.bashrc directly without a login shell"
  - "Removed both duplicate PATH entries from end of ~/.bashrc (old lines 124-125) -- both were dead code after the guard; redundant with the new line 6 export"

patterns-established:
  - "Shell config: Always export user-local bin paths before any non-interactive guard in ~/.bashrc"

requirements-completed: [CLI-01]

duration: 2min
completed: 2026-02-26
---

# Phase 1 Plan 04: Fix cinecut PATH for Non-Interactive Shells Summary

**PATH bootstrap split across ~/.bash_profile (login) and ~/.bashrc line 6 (pre-guard) ensures `cinecut --help` works in all shell contexts including `bash -c '...'` subshells**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T18:08:45Z
- **Completed:** 2026-02-26T18:10:38Z
- **Tasks:** 2
- **Files modified:** 3 (2 home-dir shell configs + 1 planning debug file)

## Accomplishments

- Created `~/.bash_profile` with unconditional `export PATH="$HOME/.local/bin:$PATH"` before any sourcing of `~/.bashrc`
- Moved the PATH export in `~/.bashrc` to line 6, before the `case $-` non-interactive early-exit guard
- Removed two duplicate PATH entries that were dead code after the guard (old lines 124-125)
- `bash -c 'source ~/.bash_profile && cinecut --help'` exits 0 and prints usage with --subtitle, --vibe, and --review
- All 33 existing unit tests still pass (no regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1 + Task 2: Fix cinecut PATH in non-interactive shells** - `02d8ab9` (fix)

**Plan metadata:** (see final docs commit)

## Files Created/Modified

- `~/.bash_profile` (created) - Unconditional PATH export for `~/.local/bin`, sources `~/.bashrc`
- `~/.bashrc` (modified) - PATH export moved to line 6 (before non-interactive guard); duplicates at old lines 124-125 removed
- `.planning/debug/gap1-cinecut-not-on-path.md` - Status updated to resolved with fix details and files changed

## Decisions Made

- Used `~/.bash_profile` as primary fix rather than `~/.profile` -- `~/.bash_profile` takes precedence over `~/.profile` for bash login shells; having a dedicated file is cleaner
- Also moved PATH line in `~/.bashrc` to before the guard -- covers non-login non-interactive subshells that source `~/.bashrc` directly (e.g., scripts that do `source ~/.bashrc`)
- Removed both duplicate PATH entries at end of `~/.bashrc` -- both were unreachable (after the guard); the new line 6 export is the sole authoritative entry

## Deviations from Plan

None - plan executed exactly as written. The `~/.bash_profile` did not exist and was created as specified. The `~/.bashrc` duplicates were removed as specified. All verification commands passed on first attempt.

## Issues Encountered

None. The root cause was exactly as diagnosed in `gap1-cinecut-not-on-path.md`: the PATH export for `~/.local/bin` was located after the non-interactive guard in `~/.bashrc`. The fix was straightforward.

## User Setup Required

None - no external service configuration required. The PATH fix takes effect immediately in new shells. Existing open terminal sessions should be refreshed with `source ~/.bash_profile` or by opening a new terminal.

## Next Phase Readiness

- UAT Test 1 (`bash -c 'cinecut --help'`) should now pass
- Phase 01-05 (gap2 fix: extension validation order) can proceed independently
- The `cinecut` command is now accessible in all contexts: interactive, login, non-interactive, and subshells

---
*Phase: 01-ingestion-pipeline-and-cli-shell*
*Completed: 2026-02-26*

## Self-Check: PASSED

- FOUND: ~/.bash_profile (created)
- FOUND: 01-04-SUMMARY.md (this file)
- FOUND: PATH export in ~/.bash_profile
- FOUND: commit 02d8ab9
