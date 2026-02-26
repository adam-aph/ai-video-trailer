---
phase: 01-ingestion-pipeline-and-cli-shell
plan: 02
subsystem: ingestion
tags: [python, pysubs2, ffmpeg, subtitle-parsing, proxy-creation, emotion-classification, charset-normalizer, better-ffmpeg-progress]

# Dependency graph
requires:
  - phase: 01-ingestion-pipeline-and-cli-shell
    plan: 01
    provides: DialogueEvent dataclass, ProxyCreationError, ProxyValidationError, SubtitleParseError exception classes
provides:
  - parse_subtitles() SRT/ASS parser with UTF-8 + charset-normalizer encoding fallback
  - classify_emotion() keyword-based emotion label classifier (6 labels, priority order)
  - probe_video() ffprobe JSON metadata extractor
  - create_proxy() idempotent 420p CFR 24fps H.264 proxy creator via better-ffmpeg-progress
  - validate_proxy() post-encode proxy integrity check (deletes corrupt file on failure)
affects:
  - 01-ingestion-pipeline-and-cli-shell/plan-03 (keyframe extractor consumes DialogueEvent.midpoint_s)
  - 02-conform-pipeline (uses proxy produced by create_proxy)
  - 03-inference-engine (uses DialogueEvent list from parse_subtitles)

# Tech tracking
tech-stack:
  added:
    - pysubs2==1.8.0 (SRT/ASS subtitle parsing, plaintext tag stripping via .plaintext property)
    - charset-normalizer>=3.0.0 (encoding detection fallback for non-UTF-8 subtitle files)
    - better-ffmpeg-progress==4.0.1 (FFmpeg subprocess wrapper with Rich progress; stderr written to log file, never surfaced to caller)
  patterns:
    - Encoding-safe file loading: attempt UTF-8 first, detect with charset-normalizer on UnicodeDecodeError, raise typed error if detection fails
    - Idempotent proxy creation: validate_proxy() called before encode; if valid, return early without calling FfmpegProcess
    - Post-encode validation: validate_proxy() called after FfmpegProcess.run() to catch FFmpeg-exits-0-but-corrupt (Pitfall 3)
    - Corrupt file cleanup: validate_proxy() deletes the bad file on failure so next run triggers re-encode
    - All subprocess boundaries wrapped: subprocess.CalledProcessError and FfmpegProcessError both caught and re-raised as typed CineCutError subclasses

key-files:
  created:
    - src/cinecut/ingestion/subtitles.py
    - src/cinecut/ingestion/proxy.py
    - tests/test_subtitles.py
    - tests/test_proxy.py
  modified: []

key-decisions:
  - "pysubs2 .plaintext property used (not .text) to strip ASS override tags cleanly, producing the same structured output for both SRT and ASS inputs"
  - "charset-normalizer best() used for encoding detection: if best() returns None, raise SubtitleParseError rather than silently dropping events (never use errors='ignore')"
  - "FfmpegProcess from better-ffmpeg-progress wraps the FFmpeg call: stderr written to log file, FfmpegProcessError caught and re-raised as ProxyCreationError"
  - "validate_proxy() deletes corrupt proxy on failure: ensures next create_proxy() call re-encodes rather than short-circuiting on a bad file"

patterns-established:
  - "Ingestion boundary pattern: subprocess errors always caught at module boundary and re-raised as domain-typed CineCutError subclasses"
  - "Encoding fallback pattern: UTF-8 first, then charset-normalizer best(), then explicit typed error — never silent drops"
  - "Idempotency pattern: check-then-act with validation; if cached artifact passes validation, return it without re-running expensive operation"

requirements-completed: [PIPE-02, NARR-01]

# Metrics
duration: 2min
completed: 2026-02-26
---

# Phase 1 Plan 02: Core Ingestion Modules Summary

**SRT/ASS subtitle parser with 6-label emotion classification and idempotent FFmpeg 420p proxy creator — both with typed error boundaries and no raw subprocess output escaping to callers**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T16:06:01Z
- **Completed:** 2026-02-26T16:08:16Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Subtitle parser handles SRT and ASS formats identically via pysubs2, with charset-normalizer fallback for non-UTF-8 files; produces DialogueEvent objects with PTS seconds, midpoint timestamps, and emotion labels
- Emotion classifier uses priority-ordered keyword dictionary (intense > romantic > comedic > negative > positive > neutral) with O(1) set intersection per label
- FFmpeg proxy creator is idempotent (cached proxy returned without re-encoding if validate_proxy passes), uses better-ffmpeg-progress to keep FFmpeg stderr in a log file rather than surfacing it to the caller
- Post-encode validation via validate_proxy() catches the FFmpeg-exits-0-but-corrupt pitfall; corrupt files are deleted so the next run re-encodes cleanly

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement subtitle parser with emotion classification** - `3255851` (feat)
2. **Task 2: Implement FFmpeg proxy creation with validation** - `b7ea932` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `src/cinecut/ingestion/subtitles.py` - parse_subtitles() and classify_emotion(); UTF-8 with charset-normalizer fallback
- `src/cinecut/ingestion/proxy.py` - probe_video(), create_proxy(), validate_proxy(); all subprocess errors wrapped
- `tests/test_subtitles.py` - 15 unit tests: SRT parse, ASS parse, empty skip, emotion labels, midpoint, PTS
- `tests/test_proxy.py` - 9 unit tests: ffprobe parse, error wrapping, validation cases, idempotency

## Decisions Made
- Used pysubs2 `.plaintext` property (not `.text`) to strip ASS override tags cleanly, ensuring the same code path handles both SRT and ASS without format-specific branches.
- charset-normalizer `best()` used for encoding detection; if `best()` returns `None`, `SubtitleParseError` is raised rather than retrying with `errors='ignore'` — silent drops are worse than explicit failures.
- `FfmpegProcess` from `better-ffmpeg-progress` wraps the FFmpeg call; stderr is written to a log file by the library, so `FfmpegProcessError` is all that escapes — then caught and re-raised as `ProxyCreationError`.
- `validate_proxy()` deletes the corrupt proxy file when validation fails: ensures the next `create_proxy()` call re-encodes instead of short-circuiting the idempotency check on a bad file.

## Deviations from Plan

None — plan executed exactly as written. pytest was already installed in the environment from a prior session.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `parse_subtitles()` is ready for plan 03 (keyframe extractor) to consume `DialogueEvent.midpoint_s` as primary timestamp candidates
- `create_proxy()` is ready for plan 03 to use as the video source for all frame extraction
- `probe_video()` provides duration and frame rate metadata for interval-fallback keyframe selection
- No blockers for Phase 1 plan 03 continuation

---
*Phase: 01-ingestion-pipeline-and-cli-shell*
*Completed: 2026-02-26*
