---
status: resolved
trigger: "cinecut not on PATH after install"
created: 2026-02-26T00:00:00Z
updated: 2026-02-26T18:09:00Z
---

## Current Focus

hypothesis: ~/.local/bin IS in PATH via ~/.bashrc but only in interactive shells; non-login non-interactive shells (e.g. scripts, CI, exec'd subshells) skip ~/.bashrc entirely
test: examined ~/.bashrc lines 1-10 (early-exit guard) and lines 118-125 (PATH exports)
expecting: confirmed
next_action: DIAGNOSED - no further action needed

## Symptoms

expected: `cinecut --help` works in all shell contexts after `pip install -e .`
actual: `cinecut: command not found` in some shell contexts (non-login shells)
errors: "cinecut: command not found"
reproduction: open a non-login non-interactive shell (e.g. `bash -c 'cinecut --help'`), or run cinecut from a script without sourcing ~/.bashrc
started: always — ~/.local/bin not universally on PATH

## Eliminated

- hypothesis: ~/.local/bin is simply missing from all config files
  evidence: ~/.bashrc lines 124-125 export PATH="$HOME/.local/bin:$PATH" (duplicated but present); ~/.profile lines 25-26 also add ~/.local/bin conditionally
  timestamp: 2026-02-26T00:00:00Z

## Evidence

- timestamp: 2026-02-26T00:00:00Z
  checked: ~/.bashrc lines 1-10
  found: early-exit guard `case $- in *i*) ;; *) return;; esac` — the entire file is skipped for non-interactive shells
  implication: PATH="$HOME/.local/bin:$PATH" at lines 124-125 is never reached when bash is non-interactive

- timestamp: 2026-02-26T00:00:00Z
  checked: ~/.bashrc lines 118-125
  found: `export PATH="$HOME/.local/bin:$PATH"` appears TWICE (lines 124 and 125) — a harmless duplicate, but both live after the non-interactive guard
  implication: duplicate is cosmetic noise; the guard is the structural problem

- timestamp: 2026-02-26T00:00:00Z
  checked: ~/.profile lines 12-27
  found: ~/.profile sources ~/.bashrc when bash is the shell, then ALSO adds ~/.local/bin unconditionally (lines 25-26); but ~/.profile is only read by LOGIN shells
  implication: login shells are fine; non-login non-interactive shells (most script execution contexts) get neither

- timestamp: 2026-02-26T00:00:00Z
  checked: /etc/environment (conceptual — not read)
  found: not examined; would be system-wide fix
  implication: adding ~/.local/bin to /etc/environment is not appropriate (user-specific path in system file)

## Resolution

root_cause: ~/.bashrc has a non-interactive shell early-exit guard at line 6 (`case $- in *i*) ;; *) return;; esac`). The PATH export for ~/.local/bin sits at lines 124-125, AFTER that guard. In any non-interactive shell context (scripts, `bash -c '...'`, most CI runners, exec'd subprocesses) ~/.bashrc returns immediately at line 8 without ever setting PATH. ~/.profile does add ~/.local/bin but is only sourced by login shells, leaving non-login non-interactive shells with no coverage.

fix: Move the `export PATH="$HOME/.local/bin:$PATH"` line to BEFORE the non-interactive guard in ~/.bashrc, OR add it to ~/.bash_profile (which is read by login shells and not subject to the guard). The minimal, lowest-risk change is:

  File: ~/.bashrc
  Before line 6 (the `case $-` guard), insert:
    export PATH="$HOME/.local/bin:$PATH"

  Alternatively — and more robustly — create or edit ~/.bash_profile:
    File: ~/.bash_profile
    Add line: export PATH="$HOME/.local/bin:$PATH"
  This file is read by bash login shells before ~/.bashrc and has no interactive guard.

  The duplicate at line 125 should also be removed (cosmetic cleanup).

verification: applied — `bash -c 'source ~/.bash_profile && cinecut --help'` exits 0 and prints usage with --subtitle, --vibe, --review
files_changed:
  - ~/.bash_profile (created): added `export PATH="$HOME/.local/bin:$PATH"` before sourcing ~/.bashrc
  - ~/.bashrc (modified): moved `export PATH="$HOME/.local/bin:$PATH"` to line 6 (before non-interactive guard); removed duplicate at old lines 124-125
