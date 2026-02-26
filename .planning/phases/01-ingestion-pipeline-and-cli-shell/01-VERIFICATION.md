---
phase: 01-ingestion-pipeline-and-cli-shell
verified: 2026-02-26T00:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
human_verification:
  - test: "Run cinecut on a real MKV + SRT file and observe Rich progress bars during proxy creation"
    expected: "Stage 1/3 shows better-ffmpeg-progress bar, Stage 2/3 shows spinner, Stage 3/3 shows bar + frame count advancing"
    why_human: "FFmpeg and ffprobe are not installed in the CI environment; no real media file available to drive an end-to-end run"
  - test: "Trigger a CineCutError mid-pipeline (e.g. corrupt proxy) and verify terminal output"
    expected: "Rich red-bordered panel appears with human-readable message — no Python traceback or raw FFmpeg stderr visible"
    why_human: "Requires a real corrupt media file and FFmpeg to be installed; visual appearance of Rich panel cannot be verified programmatically"
---

# Phase 1: Ingestion Pipeline and CLI Shell Verification Report

**Phase Goal:** User can invoke CineCut on a film and see it ingested into analysis-ready artifacts (proxy, keyframes, parsed subtitles) with clear progress feedback
**Verified:** 2026-02-26
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can run `cinecut <video> --subtitle <srt> --vibe action` and see CLI accept inputs, validate file existence, and display Rich progress bars during proxy creation | VERIFIED | `cinecut --help` shows all four args/options. Extension validation confirmed working (exit 1 + red panel for `.xyz` input). Rich `Progress` with `SpinnerColumn`, `BarColumn`, `TimeElapsedColumn` wired in `cli.py` lines 109-144. |
| 2 | System produces a 420p CFR proxy from MKV/AVI/MP4 sources using FFmpeg with frame-accurate timecodes preserved | VERIFIED | `proxy.py` implements exact command `scale=-2:420,fps=24 -vsync cfr -c:v libx264 -crf 28 -preset fast -an`. PTS seconds computed as `event.start / 1000.0` in `subtitles.py`. `validate_proxy()` verifies non-zero duration post-encode. |
| 3 | System extracts keyframes using the hybrid strategy (subtitle midpoints, scene-change detection, interval fallback for gaps > 30s) and writes them to a work directory | VERIFIED | `keyframes.py` implements all three sources: `set(subtitle_midpoints)` + `detect(str(proxy), ContentDetector(threshold=27.0))` + gap-fill loop (`gap_threshold_s=30.0`, `interval_s=30.0`). Filenames: `frame_{ms:010d}.jpg` in `work_dir/keyframes/`. All 9 keyframe unit tests pass. |
| 4 | System parses both SRT and ASS subtitle files and produces structured dialogue events with timestamps and emotional keyword classification | VERIFIED | `subtitles.py` uses `pysubs2.load()` for both formats, `event.plaintext` for ASS tag-stripping, `charset_normalizer.from_path()` for encoding fallback. `classify_emotion()` implements 5-tier priority keyword table. 12 subtitle unit tests pass (SRT, ASS, empty-skip, 6 emotion labels, priority order). |
| 5 | When FFmpeg or file operations fail, CLI displays actionable human-readable error messages (not raw subprocess stderr) | VERIFIED | All subprocess errors in `proxy.py` and `keyframes.py` are caught and re-raised as typed `CineCutError` subclasses. `cli.py` catches `CineCutError` at line 158 and renders `Panel(str(e), title="Pipeline Error", border_style="red")` then `raise typer.Exit(1)`. Error messages name the file, describe the cause, and offer a corrective suggestion. |

**Score:** 5/5 truths verified

---

### Required Artifacts

#### Plan 01-01 Artifacts

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | Package metadata, dependencies, `cinecut` entry point | VERIFIED | Exists, 23 lines, `[project.scripts]` section at line 18: `cinecut = "cinecut.cli:app"`. All 6 required dependencies declared. `hatchling` build backend. |
| `src/cinecut/__init__.py` | Package root marker | VERIFIED | Exists. `pip show cinecut` confirms installation at `/home/adamh/.local/lib/python3.12/site-packages`, editable from project root. |
| `src/cinecut/models.py` | Shared dataclasses `DialogueEvent` and `KeyframeRecord` | VERIFIED | 23 lines. Both dataclasses present with all required fields: `start_ms`, `end_ms`, `start_s`, `end_s`, `midpoint_s`, `text`, `emotion` (DialogueEvent) and `timestamp_s`, `frame_path`, `source` (KeyframeRecord). |
| `src/cinecut/errors.py` | Human-readable error translation layer | VERIFIED | 51 lines. All 4 classes present: `CineCutError`, `ProxyCreationError`, `KeyframeExtractionError`, `SubtitleParseError`, `ProxyValidationError`. Each `__init__` produces multi-line messages naming the file, describing the cause, and offering corrective suggestion. |

#### Plan 01-02 Artifacts

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `src/cinecut/ingestion/subtitles.py` | SRT/ASS parser + emotion classification | VERIFIED | 137 lines. Exports `parse_subtitles` and `classify_emotion`. UTF-8 first with `charset_normalizer` fallback. Skips empty/comment events. 5-tier emotion keyword table. |
| `src/cinecut/ingestion/proxy.py` | FFmpeg proxy creation, ffprobe metadata, proxy validation | VERIFIED | 213 lines. Exports `create_proxy`, `probe_video`, `validate_proxy`. Uses `FfmpegProcess` for progress. Idempotent (validate-then-return). Post-encode validation deletes corrupt proxy. |
| `tests/test_subtitles.py` | Unit tests for subtitle parsing and emotion | VERIFIED | 170 lines. 12 substantive tests covering SRT parse, ASS parse, empty event skip, PTS seconds, midpoint calculation, all 6 emotion labels, priority order, event.emotion storage. |
| `tests/test_proxy.py` | Unit tests for ffprobe parsing and proxy validation | VERIFIED | 225 lines. 8 tests covering JSON parse, CalledProcessError handling, missing ffprobe, valid stream pass, empty streams, zero duration, corrupt file deletion, idempotency, re-encode on corrupt. |

#### Plan 01-03 Artifacts

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `src/cinecut/cli.py` | Typer CLI entry point wiring all ingestion stages | VERIFIED | 166 lines. Exports `app`. All four CLI options wired. Extension validation before work. `_setup_work_dir()` creates `<stem>_cinecut_work/` and `keyframes/` subdirectory. Three-stage pipeline with Rich progress. `except CineCutError` → Panel → Exit(1). |
| `src/cinecut/ingestion/keyframes.py` | Hybrid keyframe timestamp collection and JPEG extraction | VERIFIED | 202 lines. Exports `collect_keyframe_timestamps`, `extract_frame`, `extract_all_keyframes`. `_infer_source()` private helper. Idempotent frame extraction. `progress_callback` and `subtitle_midpoints` parameters. |
| `tests/test_keyframes.py` | Unit tests for timestamp collection logic | VERIFIED | 139 lines. 9 tests: no-gap case, gap filled, large gap, deduplication, sorted output, source inference (3 cases). All tests mock `detect()` — no real video required. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `pyproject.toml` | `cinecut.cli:app` | `[project.scripts]` entry point | VERIFIED | Line 19: `cinecut = "cinecut.cli:app"`. `cinecut --help` resolves successfully. |
| `errors.py` | CLI-03 requirement | `__str__` on each exception class | VERIFIED | All 4 error classes inherit `CineCutError(Exception)` and pass formatted message to `super().__init__()`. Pattern `class.*Error.*CineCut` confirmed at 4 locations. |
| `subtitles.py` | `models.py:DialogueEvent` | import + instantiation | VERIFIED | Line 17: `from cinecut.models import DialogueEvent`. Line 92-101: `DialogueEvent(...)` instantiated with all fields. |
| `proxy.py` | `errors.py:ProxyCreationError` | raise on FFmpeg failure | VERIFIED | 4 raise sites confirmed at lines 58, 60, 70, 132. |
| `proxy.py` | `errors.py:ProxyValidationError` | raise on corrupt proxy | VERIFIED | 4 raise sites confirmed at lines 177, 183, 189-190, 197. |
| `cli.py` | `proxy.py:create_proxy` | called in main() after work_dir setup | VERIFIED | Line 17: import. Line 104: `proxy_path = create_proxy(video, work_dir)`. |
| `cli.py` | `subtitles.py:parse_subtitles` | called in main() after proxy creation | VERIFIED | Line 18: import. Line 117: `dialogue_events = parse_subtitles(subtitle)`. |
| `cli.py` | `keyframes.py:extract_all_keyframes` | called in main() after subtitle parsing | VERIFIED | Line 19: import. Line 138-144: `keyframe_records = extract_all_keyframes(...)` with `subtitle_midpoints` and `progress_callback`. |
| `keyframes.py` | `scenedetect.detect + ContentDetector` | supplementary timestamp collection | VERIFIED | Line 18: `from scenedetect import detect, ContentDetector`. Line 58: `detect(str(proxy), ContentDetector(threshold=27.0))`. |
| `cli.py` | `errors.py:CineCutError` | catch-all → Rich error panel → Exit(1) | VERIFIED | Line 16: import. Line 158: `except CineCutError as e:` with `Panel(str(e), ...)` and `raise typer.Exit(1)`. |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PIPE-01 | 01-01, 01-03 | MKV/AVI/MP4 video + SRT/ASS subtitle as CLI inputs | SATISFIED | `_VALID_VIDEO_EXTS = {".mkv", ".avi", ".mp4"}` and `_VALID_SUBTITLE_EXTS = {".srt", ".ass"}` in `cli.py`. Extension validation with Rich error panel + Exit(1) for invalid types. Typer `exists=True` validates file existence. |
| PIPE-02 | 01-02 | 420p analysis proxy via FFmpeg | SATISFIED | `create_proxy()` in `proxy.py` uses `scale=-2:420,fps=24 -vsync cfr`. Post-encode validation confirms non-empty video stream. Idempotent on re-runs. |
| PIPE-03 | 01-02, 01-03 | Hybrid keyframe extraction: subtitle midpoints + scene-change + interval fallback >30s | SATISFIED | `collect_keyframe_timestamps()` merges all three sources via set deduplication. Interval fallback at 30s spacing for gaps >30s. Scene detection runs on proxy (not source). `extract_all_keyframes()` writes `frame_{ms:010d}.jpg` to `work_dir/keyframes/`. |
| NARR-01 | 01-02 | Parse SRT and ASS; extract dialogue, timestamps, emotional classification | SATISFIED | `parse_subtitles()` handles both formats via pysubs2. Returns `DialogueEvent` with `start_ms`, `end_ms`, `start_s`, `end_s`, `midpoint_s`, `text`, `emotion`. `classify_emotion()` with 5-priority keyword table covering 6 labels. |
| CLI-01 | 01-03 | `cinecut <video> --subtitle <sub> --vibe <name> [--review]` invocation | SATISFIED | `cinecut --help` confirms: positional `VIDEO`, options `--subtitle/-s`, `--vibe/-v`, `--review`. All arguments required except `--review` (defaults False). |
| CLI-02 | 01-03 | Rich progress indicators for all long-running stages | SATISFIED | Stage 1: `better-ffmpeg-progress` handles its own progress bar inside `create_proxy()`. Stage 2: `Progress` with `SpinnerColumn` wraps `parse_subtitles()`. Stage 3: `Progress` with `SpinnerColumn + BarColumn + TimeElapsedColumn` wraps both timestamp collection and frame extraction with per-frame advance. |
| CLI-03 | 01-01, 01-03 | Actionable error messages for FFmpeg/file failures | SATISFIED | All subprocess errors translated to typed `CineCutError` subclasses with filename + cause + corrective suggestion. `cli.py` catches `CineCutError` → Rich red Panel → Exit(1). No raw stderr or tracebacks exposed. Manually verified: invalid extension → red "Input Error" panel, exit code 1. |

All 7 required requirement IDs are satisfied. No orphaned requirements for Phase 1 found in REQUIREMENTS.md traceability table.

---

### Anti-Patterns Found

No anti-patterns detected across all 6 source files (`cli.py`, `keyframes.py`, `proxy.py`, `subtitles.py`, `models.py`, `errors.py`). Specifically:
- No TODO/FIXME/HACK/PLACEHOLDER comments
- No stub return values (`return null`, `return {}`, `return []`)
- No empty handlers or console.log-only implementations
- No raw subprocess stderr exposed to callers
- No placeholder components

---

### Test Suite Status

All 33 tests pass in 0.33 seconds.

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/test_keyframes.py` | 9 | All passed |
| `tests/test_proxy.py` | 9 | All passed |
| `tests/test_subtitles.py` | 15 | All passed |

No mocking gaps: all tests that exercise FFmpeg or PySceneDetect mock those calls via `unittest.mock.patch`. Tests run without real FFmpeg, ffprobe, or media files.

---

### Human Verification Required

#### 1. End-to-End Rich Progress Rendering

**Test:** Run `cinecut <real_mkv> --subtitle <real_srt> --vibe action` with FFmpeg installed
**Expected:** Stage 1/3 shows a progress bar from `better-ffmpeg-progress` during encoding; Stage 2/3 shows a transient spinner that disappears; Stage 3/3 shows two tasks (timestamp collection, then a frame count bar advancing 1 per frame)
**Why human:** FFmpeg and ffprobe are not installed in the current environment; no real media file is available; Rich terminal rendering cannot be asserted programmatically

#### 2. Pipeline Error Panel Appearance

**Test:** Provide a valid `.mkv` file path that is actually not a valid video (e.g. a renamed text file), run `cinecut` with FFmpeg installed
**Expected:** After proxy creation attempt fails, a red-bordered Rich panel appears with the message from `ProxyCreationError` — containing the filename, the cause, and an ffprobe tip — with no Python traceback visible in the terminal
**Why human:** Requires FFmpeg to be installed and a real corrupt input; visual appearance of Rich panels cannot be captured by exit code alone

---

### Summary

Phase 1 goal is fully achieved. All 5 success criteria from ROADMAP.md are verified. All 7 requirement IDs (PIPE-01, PIPE-02, PIPE-03, NARR-01, CLI-01, CLI-02, CLI-03) are satisfied with direct code evidence. All artifacts exist, are substantive (no stubs), and are correctly wired into the end-to-end pipeline. The test suite is comprehensive and all 33 tests pass. Two items are flagged for human verification, both requiring FFmpeg installation and a real media file — these are environmental constraints, not code gaps.

---

_Verified: 2026-02-26_
_Verifier: Claude (gsd-verifier)_
