---
status: diagnosed
phase: 01-ingestion-pipeline-and-cli-shell
source: 01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md
started: 2026-02-26T16:30:00Z
updated: 2026-02-26T16:30:00Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[testing complete]

## Tests

### 1. CLI is installed and shows help
expected: Running `cinecut --help` prints usage with video argument and --subtitle, --vibe, --review options visible. No Python traceback, no "command not found".
result: issue
reported: "cinecut: command not found"
severity: blocker

### 2. Invalid file extension rejected
expected: Running `cinecut document.pdf` (or any non-video extension) shows a readable error panel explaining the file type is not supported — not a raw Python traceback.
result: issue
reported: "Error panel shown but for 'file does not exist' not 'wrong extension' — Typer's file-existence check fires before the extension validator; extension validation unconfirmed"
severity: minor

### 3. Missing file shows clear error
expected: Running `cinecut nonexistent.mp4` shows a readable error panel naming the file and explaining it doesn't exist — not a raw Python traceback.
result: pass

### 4. Unit tests all pass
expected: Running `python -m pytest tests/ -q` shows all 33 tests passing (test_subtitles, test_proxy, test_keyframes) with no failures or errors.
result: pass

### 5. End-to-end: work directory created with keyframes
expected: Running `cinecut <video.mp4> --subtitle <subs.srt>` creates a `<stem>_cinecut_work/keyframes/` directory containing JPEG files named `frame_<timestamp_ms>.jpg`. Progress bars are shown during proxy creation, subtitle parsing, and frame extraction.
result: pass

## Summary

total: 5
passed: 3
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "Running `cinecut --help` prints usage with video argument and --subtitle, --vibe, --review options visible. No Python traceback, no 'command not found'."
  status: failed
  reason: "User reported: cinecut: command not found"
  severity: blocker
  test: 1
  root_cause: "~/.bashrc has a non-interactive shell early-exit guard (line 6-8: case $- in) that skips the entire file including the PATH export at line 124. ~/.profile adds ~/.local/bin only for login shells. No mechanism adds ~/.local/bin for non-login non-interactive shells. Not a code bug — environment setup issue."
  artifacts:
    - path: "~/.bashrc"
      issue: "PATH export at line 124-125 is after the non-interactive guard at line 6 — unreachable in non-interactive shells"
    - path: "~/.profile"
      issue: "Adds ~/.local/bin but only for login shells"
  missing:
    - "Move PATH export to before the non-interactive guard in ~/.bashrc, or add it to ~/.bash_profile"
  debug_session: ".planning/debug/gap1-cinecut-not-on-path.md"

- truth: "Running cinecut with an unsupported file extension shows an error panel explaining the type is not supported"
  status: failed
  reason: "Error panel shown but for 'file does not exist' not 'wrong extension' — Typer file-existence check fires before extension validator; extension validation unconfirmed"
  severity: minor
  test: 2
  root_cause: "VIDEO argument and --subtitle option both declare exists=True (cli.py lines 47, 59), which Click validates during argument parsing before main() is called. Extension check at cli.py line 76-83 is only reached if file exists. When file doesn't exist, Click fires its own error — bypassing the Rich error panel. Extension check IS correct and works when file exists (confirmed by debugger)."
  artifacts:
    - path: "src/cinecut/cli.py"
      issue: "exists=True on VIDEO (line 47) and --subtitle (line 59) causes Click to validate existence before our extension check at line 76"
  missing:
    - "Remove exists=True from VIDEO and --subtitle; add manual existence checks inside main() after extension checks, using Rich error panels"
  debug_session: ".planning/debug/gap2-extension-validation-order.md"
