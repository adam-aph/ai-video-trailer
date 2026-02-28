---
phase: 10-sfx-vo-and-audio-mix
plan: 02
subsystem: audio
tags: [pysubs2, ffmpeg, aac, protagonist, vo, subtitle, counter]

# Dependency graph
requires:
  - phase: 08-zone-matching
    provides: narrative_zone on ClipEntry, NarrativeZone enum
  - phase: 07-structural-analysis
    provides: TrailerManifest with structural_anchors, ClipEntry.act values
provides:
  - identify_protagonist() — most-speaking character from ASS SSAEvent.name
  - extract_vo_clips() — protagonist VO extraction, Act1+Act2 only, up to 3 clips
  - VoClip dataclass — path, timeline_s, act_zone
affects:
  - 10-03-audio-mix (consumes VoClip list from extract_vo_clips)

# Tech tracking
tech-stack:
  added: []  # pysubs2 already in pyproject.toml
  patterns:
    - output-seeking FFmpeg (-ss before -i) for accurate audio extraction
    - Counter(event.name).most_common(1) protagonist identification
    - Graceful degradation returning [] on None protagonist (MUSC-03 pattern)

key-files:
  created:
    - src/cinecut/conform/vo_extract.py
  modified: []

key-decisions:
  - "identify_protagonist() returns None for SRT files (event.name always empty) — no silent crash, graceful [] return"
  - "Candidate selection: longest-duration events first (sort by duration desc) then slice — favours intelligible VO"
  - "0.8s minimum enforced via _MIN_DURATION_S constant BEFORE FFmpeg call — never extract inaudibly short clips"
  - "Case-insensitive protagonist name comparison (event.name.strip().lower() vs protagonist.lower()) — tolerates ASS capitalisation variance"
  - "-ss placed before -i in FFmpeg command (output-seeking) — accurate position for re-encoded audio"
  - "Act 3 (breath/act3) explicitly excluded — only _ACT1_ACTS and _ACT2_ACTS frozensets used for candidate search"
  - "FFmpeg failures logged as warnings and skipped — graceful degradation per MUSC-03 pattern; no raise"

patterns-established:
  - "Pattern 1: frozensets for act membership (_ACT1_ACTS, _ACT2_ACTS) — O(1) lookup, explicit exclusion of Act 3"
  - "Pattern 2: timeline_offsets built by accumulating clip durations — reusable for any time-in-trailer computation"
  - "Pattern 3: subprocess.run with capture_output=True for FFmpeg — returncode checked, stderr tail logged on failure"

requirements-completed: [VONR-01, VONR-02, VONR-03]

# Metrics
duration: 2min
completed: 2026-02-28
---

# Phase 10 Plan 02: VO Extract Summary

**Protagonist VO extraction from ASS subtitles using pysubs2 Counter on event.name, with output-seeking FFmpeg (-ss before -i) re-encoding to AAC 48000Hz stereo, up to 3 clips from Acts 1+2 only**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-28T17:50:14Z
- **Completed:** 2026-02-28T17:52:20Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- `identify_protagonist()` identifies the most-speaking named character via `Counter(event.name)` across all non-comment SSA events; returns `None` for SRT files or speaker-less ASS
- `extract_vo_clips()` selects up to 1 Act 1 and up to 2 Act 2 protagonist events (longest first), enforcing 0.8s minimum before extraction; computes trailer timeline position from accumulated clip durations
- FFmpeg extraction uses output-seeking (`-ss` before `-i`) for accurate audio segmentation, re-encodes to AAC 48000Hz stereo 192k; gracefully skips on FFmpeg failure

## Task Commits

1. **Task 1: Create conform/vo_extract.py** - `2599530` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/cinecut/conform/vo_extract.py` - `identify_protagonist()`, `extract_vo_clips()`, `VoClip` dataclass; full VO pipeline from subtitle scan to AAC extraction

## Decisions Made

- `identify_protagonist()` returns `None` for SRT files (event.name always empty) — caller (extract_vo_clips) handles gracefully by returning `[]`
- Candidate selection uses longest-duration events first (`sort(key=lambda c: c["duration"], reverse=True)`) — favours intelligible, complete utterances over short fragments
- Case-insensitive protagonist comparison (`event.name.strip().lower() != protagonist.lower()`) — tolerates capitalisation variance common in ASS files
- `_MIN_DURATION_S = 0.8` constant enforced BEFORE the FFmpeg subprocess call — avoids spawning processes for clips that would be inaudible
- `-ss` placed before `-i` in the FFmpeg command list for output-seeking (not input-seeking) — required for accurate audio re-encode position per VONR-03
- Act 3 excluded via two explicit frozensets (`_ACT1_ACTS`, `_ACT2_ACTS`) — no Act 3 set needed; absence is the guard

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `identify_protagonist` and `extract_vo_clips` are ready for consumption by Plan 03 (audio_mix.py)
- `VoClip.timeline_s` provides the trailer-timeline position needed for FFmpeg amix filter insertion
- `VoClip.act_zone` ("act1" / "act2") available for zone-specific volume or timing adjustments in the mix stage
- No blockers: pysubs2 is already installed; FFmpeg is a project-wide dependency

## Self-Check: PASSED

- FOUND: src/cinecut/conform/vo_extract.py
- FOUND commit: 2599530

---
*Phase: 10-sfx-vo-and-audio-mix*
*Completed: 2026-02-28*
