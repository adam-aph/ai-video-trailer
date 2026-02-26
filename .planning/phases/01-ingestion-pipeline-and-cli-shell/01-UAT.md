---
status: complete
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
  root_cause: "Script is correctly installed at ~/.local/bin/cinecut but ~/.local/bin is not on PATH in the user's interactive shell. ~/.local/bin is added by .profile (login shells) and .bashrc (interactive shells) but the current shell session does not have it."
  artifacts:
    - path: "/home/adamh/.local/bin/cinecut"
      issue: "Script exists but PATH doesn't include ~/.local/bin in the active shell"
    - path: "/home/adamh/ai-video-trailer/pyproject.toml"
      issue: "Entry point declaration is correct — not a code issue"
  missing:
    - "Add ~/.local/bin to PATH in current shell session or shell config"
  debug_session: ""

- truth: "Running cinecut with an unsupported file extension shows an error panel explaining the type is not supported"
  status: failed
  reason: "Error panel shown but for 'file does not exist' not 'wrong extension' — Typer file-existence check fires before extension validator; extension validation unconfirmed"
  severity: minor
  test: 2
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
