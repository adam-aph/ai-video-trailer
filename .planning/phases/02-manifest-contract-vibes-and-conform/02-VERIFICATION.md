---
phase: 02-manifest-contract-vibes-and-conform
verified: 2026-02-26T19:45:00Z
status: human_needed
score: 12/12 automated must-haves verified
re_verification: false
human_verification:
  - test: "End-to-end conform run with a real video file"
    expected: "CLI produces a playable MP4 named <source>_trailer_action.mp4 with the action LUT visibly applied (cool tones, boosted saturation/contrast) and clean audio"
    why_human: "FFmpeg conform pipeline requires a real video source file; CI environment has no test video. Visual and audio quality of output can only be confirmed by a human playing the file."
  - test: "--review flag user prompt flow"
    expected: "CLI prints manifest path, prints inspection hint, then prompts 'Proceed with FFmpeg conform? [y/N]'. Typing 'n' aborts without any FFmpeg calls. Typing 'y' runs conform."
    why_human: "typer.confirm() interactive prompt cannot be driven by automated tests without process spawning with stdin injection."
---

# Phase 02: Manifest Contract, Vibes, and Conform Verification Report

**Phase Goal:** Build the manifest contract (Pydantic schema + vibe profiles + LUT generation) and the FFmpeg conform pipeline, verified by automated tests and a human-approved end-to-end run.
**Verified:** 2026-02-26T19:45:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A valid TRAILER_MANIFEST.json is accepted and parsed into a TrailerManifest object | VERIFIED | `load_manifest()` in loader.py uses `model_validate_json()` + 5 passing tests in TestValidManifest |
| 2 | A malformed manifest is rejected with ManifestError describing the field path and problem | VERIFIED | `ValidationError` caught and re-raised as `ManifestError` with `' -> '.join(str(x) for x in err['loc'])` field path; `test_invalid_json_raises_manifest_error` passes |
| 3 | All 18 VibeProfile instances are importable from cinecut.manifest.vibes with complete parameters | VERIFIED | `VIBE_PROFILES` has exactly 18 entries; `set(VIBE_PROFILES.keys()) == VALID_VIBES`; parametrized LUFS and color spot-checks all pass |
| 4 | Calling ensure_luts(vibe_name, lut_dir) produces a .cube file that FFmpeg lut3d can consume | VERIFIED | File produces header `TITLE/LUT_3D_SIZE 33/DOMAIN_MIN/DOMAIN_MAX` + 35937 triplets; format matches .cube spec; `test_ensure_luts_idempotent` and `test_ensure_luts_creates_dir` pass |
| 5 | An identity LUT (saturation=1.0, contrast=1.0, temp_shift=0.0, brightness=0.0) produces no color change on a reference image | VERIFIED | `test_identity_r_fastest` confirms: index 0 = "0.000000 0.000000 0.000000", index 1 = "1.000000 0.000000 0.000000", index 2 = "0.000000 1.000000 0.000000", index 4 = "0.000000 0.000000 1.000000"; R-fastest B-slowest ordering is correct per .cube spec |
| 6 | conform_manifest() extracts all clips, applies the vibe LUT and LUFS normalization, and concatenates into a single MP4 | VERIFIED (structure) | All three functions exist with correct signatures; VIBE_PROFILES lookup wired; ensure_luts wired; manifest.clips iterated; concatenate_clips called. End-to-end run requires human with real video |
| 7 | Each extracted clip uses frame-accurate -ss before -i seeking | VERIFIED | All three ffmpeg command lists (short-clip, pass1, pass2) have "-ss" at position N and "-i" at position N+1 in the list. shell=True never used. |
| 8 | Output file is named source_trailer_vibe.mp4 | VERIFIED | `make_output_path()` produces `{source.stem}_trailer_{vibe_slug}.mp4`; sci-fi -> sci_fi slug conversion verified |
| 9 | --review flag pauses CLI with typer.confirm(abort=True) before conform | VERIFIED (code) | `typer.confirm("Proceed with FFmpeg conform?", abort=True)` at line 232 of cli.py; human verification required to confirm interactive prompt behavior |
| 10 | --manifest flag and no --review runs conform immediately | VERIFIED (structure) | CLI flow: if manifest is not None -> load_manifest() -> if not review: skip confirm -> conform_manifest() |
| 11 | Short clips < 3.0s use volume=0dB single-pass instead of two-pass loudnorm | VERIFIED | `duration < MIN_LOUDNORM_DURATION_S` (3.0) branch uses single cmd with `-af volume=0dB`; long clips use pass1_cmd + pass2_cmd |
| 12 | All 27 automated unit tests pass | VERIFIED | `python3 -m pytest tests/test_manifest.py tests/test_conform_unit.py -v` exits 0; 27 passed in 0.40s |

**Score:** 12/12 automated must-haves verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/cinecut/manifest/schema.py` | TrailerManifest and ClipEntry Pydantic models; VALID_VIBES frozenset | VERIFIED | 87 lines; exports TrailerManifest, ClipEntry, VALID_VIBES; normalize_vibe validator with _VIBE_ALIASES |
| `src/cinecut/manifest/loader.py` | load_manifest() function | VERIFIED | 23 lines; ValidationError -> ManifestError conversion with field paths; OSError/UnicodeDecodeError handling |
| `src/cinecut/manifest/vibes.py` | VibeProfile dataclass; VIBE_PROFILES dict (18 entries) | VERIFIED | 352 lines; all 18 profiles with complete parameters; frozen=True dataclass |
| `src/cinecut/conform/luts.py` | ensure_luts() and generate_cube_lut() | VERIFIED | 101 lines; NumPy vectorized; R-fastest B-slowest loop; LUT_SIZE=33; idempotent ensure_luts() |
| `src/cinecut/conform/pipeline.py` | conform_manifest(), extract_and_grade_clip(), concatenate_clips() | VERIFIED | 249 lines; all three functions exist with correct signatures; MIN_LOUDNORM_DURATION_S=3.0 |
| `src/cinecut/cli.py` | Extended CLI with --manifest and --review | VERIFIED | --manifest/-m and --review options declared; Stage 4 conform block implemented; Phase 1 stages preserved |
| `src/cinecut/errors.py` | ManifestError and ConformError classes | VERIFIED | Both classes extend CineCutError with correct __init__ signatures; structured error messages with Cause/Check/Tip |
| `src/cinecut/manifest/__init__.py` | Empty package marker | VERIFIED | File exists |
| `src/cinecut/conform/__init__.py` | Empty package marker | VERIFIED | File exists |
| `tests/test_manifest.py` | Unit tests for schema, loader, and vibe profiles | VERIFIED | 21 tests across TestValidManifest, TestInvalidManifest, TestVibeProfiles; all pass |
| `tests/test_conform_unit.py` | Unit tests for LUT generation | VERIFIED | 6 tests covering format, R-fastest ordering, size 33^3, idempotency, unknown vibe ValueError; all pass |
| `tests/fixtures/sample_manifest.json` | Hand-crafted manifest with 3 clips | VERIFIED | Contains clips for cold_open (10.0-14.5s), act1 (45.0-50.0s), act3 (120.0-122.0s) |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `loader.py` | `pydantic.ValidationError` | `model_validate_json()` catch block | WIRED | Line 12: `TrailerManifest.model_validate_json(...)` inside try; line 15: `except ValidationError as e` |
| `conform/luts.py` | `manifest/vibes.py` | VIBE_PROFILES lookup by name | WIRED | Line 4: `from cinecut.manifest.vibes import VIBE_PROFILES`; line 87: `profile = VIBE_PROFILES[vibe_name]` |
| `manifest/schema.py` | `manifest/vibes.py` | VALID_VIBES used in vibe field_validator | WIRED (standalone) | VALID_VIBES defined in schema.py as standalone frozenset; no circular import; validator references it at line 82 |
| `conform/pipeline.py` | `conform/luts.py` | ensure_luts(vibe_name, work_dir/luts) | WIRED | Line 16: `from cinecut.conform.luts import ensure_luts`; line 224: `lut_path = ensure_luts(manifest.vibe, work_dir / "luts")` |
| `conform/pipeline.py` | `manifest/schema.py` | TrailerManifest.clips iteration | WIRED | Line 14: `from cinecut.manifest.schema import TrailerManifest`; line 232: `for i, clip in enumerate(manifest.clips)` |
| `cli.py` | `conform/pipeline.py` | conform_manifest(manifest, source, vibe_profile, work_dir) | WIRED | Line 25: `from cinecut.conform.pipeline import conform_manifest`; line 244: `output_path = conform_manifest(trailer_manifest, video, work_dir)` |
| `cli.py` | `typer.confirm` | --review pause before conform | WIRED | Line 232: `typer.confirm("Proceed with FFmpeg conform?", abort=True)` inside `if review:` block |
| `tests/test_manifest.py` | `manifest/schema.py` | TrailerManifest.model_validate() | WIRED | Line 5: imports; multiple test methods call `TrailerManifest.model_validate()` |
| `tests/test_conform_unit.py` | `conform/luts.py` | generate_cube_lut() with identity params | WIRED | Line 4: `from cinecut.conform.luts import generate_cube_lut`; 3 test methods call it |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| VIBE-01 | 02-01, 02-03 | All 18 vibe profiles with complete parameters | SATISFIED | VIBE_PROFILES has exactly 18 entries; keys match VALID_VIBES; all profiles are VibeProfile instances with full color/audio/pacing parameters; `test_all_18_profiles_present` passes |
| VIBE-02 | 02-01, 02-03 | .cube LUT files for all 18 vibes (programmatically generated) | SATISFIED | `generate_cube_lut()` and `ensure_luts()` generate any of the 18 vibe LUTs on demand; LUT_SIZE=33; correct .cube format verified |
| VIBE-03 | 02-02, 02-03 | Per-vibe LUT applied via FFmpeg lut3d filter during conform | SATISFIED | pipeline.py: `-vf lut3d=file={lut_path}` in both short-clip cmd and pass2_cmd; lut_path comes from ensure_luts() |
| VIBE-04 | 02-02, 02-03 | Per-vibe LUFS via FFmpeg loudnorm two-pass | SATISFIED | pipeline.py: pass1_cmd with `loudnorm=I={lufs_target}:LRA=7:tp=-2:print_format=json`; JSON stats parsed from stderr; pass2_cmd with `linear=true` and measured_ params |
| EDIT-04 | 02-02, 02-03 | --review flag pauses pipeline for user confirmation before conform | SATISFIED (code verified, human behavior needed) | `if review: typer.confirm("Proceed with FFmpeg conform?", abort=True)` at cli.py:232 |
| EDIT-05 | 02-02, 02-03 | Frame-accurate FFmpeg seeking (-ss before -i) | SATISFIED | All three FFmpeg command lists verified: "-ss" precedes "-i" in each list; never shell=True |
| CLI-04 | 02-02, 02-03 | Output written to source_trailer_vibe.mp4 at source resolution | SATISFIED | `make_output_path()` produces `{source.stem}_trailer_{vibe_slug}.mp4` alongside source; sci-fi -> sci_fi slug conversion correct |

All 7 Phase 2 requirement IDs from REQUIREMENTS.md (marked [x] Complete) are fully implemented and verified in code.

**No orphaned requirements.** REQUIREMENTS.md Traceability table maps exactly EDIT-04, EDIT-05, VIBE-01, VIBE-02, VIBE-03, VIBE-04, CLI-04 to Phase 2 — all accounted for.

---

### Anti-Patterns Found

No anti-patterns detected.

Scanned files: `schema.py`, `loader.py`, `vibes.py`, `luts.py`, `pipeline.py`, `cli.py`, `errors.py`

| File | Pattern | Severity | Result |
|------|---------|----------|--------|
| All Phase 2 source files | TODO/FIXME/PLACEHOLDER comments | Checked | None found |
| All Phase 2 source files | `return null`, `return {}`, `return []` stubs | Checked | None found |
| `conform/pipeline.py` | `shell=True` (forbidden) | Checked | Not present; all subprocess.run() calls use list form |
| `conform/pipeline.py` | `-i` before `-ss` (wrong seek order) | Checked | All three extract commands have -ss at index N, -i at N+1 |

---

### Human Verification Required

#### 1. End-to-End Conform Run

**Test:** With a real MKV/MP4 source file, update `tests/fixtures/sample_manifest.json` to set `source_file` to the absolute path of the video and adjust `source_start_s`/`source_end_s` to valid timestamps. Then run:

```
cinecut /path/to/test.mkv --subtitle /path/to/test.srt --vibe action --manifest tests/fixtures/sample_manifest.json
```

**Expected:** CLI prints "Stage 4/4: Running FFmpeg conform...", processes 3 clips, prints the "Trailer Ready" panel with output path. The output file `test_trailer_action.mp4` exists and is playable. Visual quality shows the action LUT effect (cool tones, elevated saturation and contrast). Audio is normalized.

**Why human:** No test video is available in the CI environment. FFmpeg conform requires a real video source. Visual quality and audio normalization correctness can only be confirmed by playing the output.

#### 2. --review Flag Interactive Prompt

**Test:** Run the same command with `--review` added:

```
cinecut /path/to/test.mkv --subtitle /path/to/test.srt --vibe action --manifest tests/fixtures/sample_manifest.json --review
```

**Expected:** CLI prints the manifest path, prints the inspection hint ("Inspect clip decisions..."), then prompts `Proceed with FFmpeg conform? [y/N]`. Entering `n` aborts immediately (typer.Exit via abort=True) without any FFmpeg calls. Entering `y` proceeds to conform and produces the output MP4.

**Why human:** `typer.confirm()` is an interactive TTY prompt that cannot be reliably driven by automated subprocess tests without stdin manipulation. The code path is verified (line 232 of cli.py), but the user experience requires a human to confirm.

---

### Summary

All 12 automated must-haves are verified. The Phase 2 implementation is complete and substantive:

- **Schema contract:** TrailerManifest/ClipEntry Pydantic v2 models with field-level validation, vibe normalization, and ManifestError wrapping are fully implemented and tested.
- **Vibe profiles:** All 18 VibeProfile instances exist with correct color, audio, and pacing parameters matching the research tables. Spot-checked action (temp_shift=-0.05, saturation=1.15, contrast=1.20, act3=1.2s, lufs=-14.0) and horror (brightness=-0.05, contrast=1.35).
- **LUT generation:** NumPy-vectorized .cube generation with correct R-fastest B-slowest loop order verified by identity LUT data line content. Size 33^3=35937 triplets. ensure_luts() is idempotent.
- **FFmpeg conform pipeline:** Frame-accurate extraction (-ss before -i confirmed in all three command lists), lut3d filter wired, two-pass loudnorm with JSON stderr parsing, short-clip guard at 3.0s (volume=0dB single pass), concat demuxer with -safe 0.
- **CLI wiring:** --manifest/-m and --review flags implemented; Stage 4 conform block added; Phase 1 ingestion stages preserved; ManifestError/ConformError caught by existing CineCutError handler.
- **Tests:** 27 tests (21 schema/vibe + 6 LUT), all passing in 0.40s.

Two items need human verification because they require a real video file and/or interactive terminal input. Automated testing cannot substitute for these.

---

*Verified: 2026-02-26T19:45:00Z*
*Verifier: Claude (gsd-verifier)*
