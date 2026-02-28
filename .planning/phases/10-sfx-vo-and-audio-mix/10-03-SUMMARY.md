---
phase: 10-sfx-vo-and-audio-mix
plan: "03"
subsystem: conform/audio
tags: [ffmpeg, amix, sidechaincompress, loudnorm, audio-mix, four-stem, ducking, adelay]

# Dependency graph
requires:
  - phase: 10-sfx-vo-and-audio-mix/10-01
    provides: synthesize_sfx_files(), apply_sfx_to_timeline(), SFX_HARD_DURATION_S
  - phase: 10-sfx-vo-and-audio-mix/10-02
    provides: extract_vo_clips(), VoClip dataclass, identify_protagonist()
  - phase: 09-bpm-grid-and-music-bed
    provides: manifest.music_bed.local_path (optional — three-stem fallback if absent)
provides:
  - mix_four_stems() — four-stem FFmpeg audio mix with sidechaincompress music ducking
  - DUCK_THRESHOLD, DUCK_RATIO, DUCK_ATTACK_MS, DUCK_RELEASE_MS constants
  - conform_manifest() extended with Pass 3 (SFX+VO) and Pass 4 (four-stem mix)
  - tests/test_sfx_vo_mix.py — 7 unit tests covering all Phase 10 audio constraints
affects:
  - cli.py Stage 8 (if added) — calls conform_manifest() with subtitle_path

# Tech tracking
tech-stack:
  added: []
  patterns:
    - sidechaincompress: [music][vo_sc] sidechain ducking — music compressed when VO is audible
    - amix normalize=0 is MANDATORY throughout — normalize=1 destroys ducking ratios (STATE.md decision)
    - Two-pass loudnorm per stem at -16 LUFS before mixing (AMIX-02 pattern)
    - aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo per stem in filtergraph
    - Three-stem fallback (film+SFX+VO) when music_bed_path is None or absent (MUSC-03 graceful degradation)
    - TYPE_CHECKING guard for VoClip import in audio_mix.py — avoids circular import
    - Silence placeholder (0.1s aevalsrc=0) for VO stem when no vo_clips — keeps filtergraph inputs consistent

key-files:
  created:
    - src/cinecut/conform/audio_mix.py
    - tests/test_sfx_vo_mix.py
  modified:
    - src/cinecut/conform/pipeline.py

key-decisions:
  - "amix normalize=0 mandatory throughout — normalize=1 destroys sidechain ducking ratios (AMIX-01)"
  - "Stem-level loudnorm at -16 LUFS before mixing, not after — allows correct amix weight ratios to hold"
  - "Three-stem fallback (no sidechaincompress) when music_bed_path is None or file does not exist — MUSC-03 graceful degradation"
  - "VO silence placeholder (0.1s near-silence AAC) when no vo_clips — avoids branching filtergraph complexity"
  - "Pass 2 output renamed to pass2_concat_path; Pass 4 output (trailer_final.mp4) is the new final path"
  - "subtitle_path: Path | None = None added to conform_manifest() — backward-compatible with all existing callers"
  - "Test _loudnorm_side_effect: injects fake JSON loudnorm stats into mock stderr — avoids actual FFmpeg while testing mix path"

patterns-established:
  - "Pattern: sidechaincompress with [vo_sc] sidechain — voice-keyed music compression in FFmpeg"
  - "Pattern: stem normalization before amix — loudnorm each input independently, then combine"
  - "Pattern: silence placeholder stem — touch file or aevalsrc=0 to maintain consistent filtergraph input count"

requirements-completed: [AMIX-01, AMIX-02, AMIX-03]

# Metrics
duration: 11min
completed: 2026-02-28
---

# Phase 10 Plan 03: Audio Mix Summary

**Four-stem FFmpeg audio mix (film+music+SFX+VO) with sidechaincompress music ducking under protagonist VO — amix normalize=0 mandatory, stem-level -16 LUFS loudnorm, Pass 3+4 wired into conform pipeline**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-02-28T17:57:48Z
- **Completed:** 2026-02-28T18:08:59Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 1 created new, 1 modified)

## Accomplishments

- `mix_four_stems()` builds dynamic FFmpeg `-filter_complex` with `sidechaincompress` ducking: music compressed when VO plays, using DUCK_THRESHOLD=0.025, DUCK_RATIO=6, attack=100ms, release=600ms
- Independent per-stem loudnorm at -16 LUFS (two-pass) before mixing — film audio, SFX, music bed, VO each normalized separately (AMIX-02)
- `conform_manifest()` extended with backward-compatible `subtitle_path: Path | None = None`, Pass 3 (SFX synthesis + VO extraction), and Pass 4 (four-stem mix); returns `trailer_final.mp4`
- 7 unit tests verifying: idempotency, chirp slopes, SRT None protagonist, adelay milliseconds, normalize=0 constraint, three-stem fallback — all pass with mocked subprocess.run

## Task Commits

1. **Task 1: Create conform/audio_mix.py** - `a3089e1` (feat) *(pre-existing from prior session)*
2. **Task 2: Wire Pass 3 + Pass 4 into pipeline.py; add unit tests** - `fc826f5` (feat)

## Files Created/Modified

- `src/cinecut/conform/audio_mix.py` — `mix_four_stems()`, `_loudnorm_stem()`, `_build_vo_mix()`, ducking constants exported; 350 lines
- `src/cinecut/conform/pipeline.py` — imports sfx + audio_mix modules; Pass 3 (SFX+VO) and Pass 4 (audio mix) added after Pass 2 concat; new `subtitle_path` parameter
- `tests/test_sfx_vo_mix.py` — 7 unit tests for sfx.py, vo_extract.py, audio_mix.py; all mocked FFmpeg; 206 total tests pass

## Decisions Made

- `amix normalize=0` used throughout: both the four-stem and three-stem filtergraphs explicitly set `normalize=0`. This is the critical STATE.md decision — `normalize=1` would cause FFmpeg to scale down all inputs when mixing, destroying the sidechain ducking effect.
- Two-pass loudnorm before mixing: each stem (film audio, SFX, music, VO) is independently normalized to -16 LUFS before entering the final filtergraph. This allows the `amix weights` (1.0/0.7/0.8/1.0) to accurately reflect perceived loudness ratios.
- Silence placeholder for missing VO: when `vo_clips=[]`, a 0.1s near-silence AAC is created via `aevalsrc=0`. This avoids a conditional filtergraph branch and keeps the FFmpeg command structure consistent.
- `subtitle_path=None` backward-compatible: existing callers of `conform_manifest()` (cli.py, test suites) are unaffected — Pass 3 simply skips VO extraction when `subtitle_path` is None.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test mock needed loudnorm JSON in stderr**
- **Found during:** Task 2 (test execution)
- **Issue:** `_loudnorm_stem()` parses JSON from stderr of pass-1 FFmpeg call. Mocking subprocess.run with empty stderr caused `ConformError` in mix_four_stems tests.
- **Fix:** Added `_loudnorm_side_effect()` helper that returns fake loudnorm JSON in stderr when the cmd contains `print_format=json`. Tests for `test_normalize_zero` and `test_three_stem_fallback` use this side_effect.
- **Files modified:** tests/test_sfx_vo_mix.py
- **Verification:** All 7 tests pass
- **Committed in:** fc826f5 (Task 2 commit)

**2. [Rule 1 - Bug] ClipEntry required beat_type field**
- **Found during:** Task 2 (test execution)
- **Issue:** `ClipEntry` Pydantic model has `beat_type` as a required field (from Phase 7 structural analysis); test was constructing ClipEntry without it, causing ValidationError.
- **Fix:** Added `beat_type="character_introduction"` and `beat_type="escalation_beat"` to test ClipEntry instances.
- **Files modified:** tests/test_sfx_vo_mix.py
- **Verification:** test_adelay_uses_milliseconds passes
- **Committed in:** fc826f5 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - Bug fixes during test execution)
**Impact on plan:** Both fixes required for tests to pass; no scope creep. Production code unchanged.

## Issues Encountered

None in production code. Test mock setup required two iterations (empty stderr fix + beat_type fix) before all 7 tests passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 10 is complete. All three plans executed: SFX synthesis (10-01), VO extraction (10-02), four-stem audio mix + pipeline wiring (10-03).
- `conform_manifest(manifest, source, work_dir, subtitle_path=subtitle_path)` is the single entry point for full trailer production including audio mix.
- Empirical tuning of `DUCK_THRESHOLD`, `DUCK_RATIO`, `DUCK_ATTACK_MS`, `DUCK_RELEASE_MS` in `audio_mix.py` can be done without code changes.
- v2.0 milestone (Structural & Sensory Overhaul) is complete — all 11 plans across Phases 6-10 executed.

## Self-Check: PASSED

- FOUND: src/cinecut/conform/audio_mix.py
- FOUND: src/cinecut/conform/pipeline.py (modified)
- FOUND: tests/test_sfx_vo_mix.py
- FOUND commit a3089e1 (Task 1 — audio_mix.py)
- FOUND commit fc826f5 (Task 2 — pipeline wiring + tests)
- 206 tests pass (no regressions)
- normalize=0 in filtergraph: verified
- three-stem fallback: verified by test_three_stem_fallback_when_no_music
- subtitle_path in conform_manifest signature: verified

---
*Phase: 10-sfx-vo-and-audio-mix*
*Completed: 2026-02-28*
