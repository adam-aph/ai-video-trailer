# Requirements: CineCut AI

**Defined:** 2026-02-26
**Updated:** 2026-02-28 — v2.0 requirements added
**Core Value:** Given a feature film and its subtitle file, produce a narratively coherent, vibe-styled trailer that a human editor would be proud to show — technically clean output with a real beginning, escalation, and climax arc.

## v1 Requirements (Complete — v1.0)

### Pipeline

- [x] **PIPE-01**: User can provide MKV/AVI/MP4 source video + SRT/ASS subtitle file as inputs to the CLI
- [x] **PIPE-02**: System creates a 420p analysis proxy from the source video using FFmpeg before inference
- [x] **PIPE-03**: System extracts keyframes using a hybrid strategy: subtitle event midpoints (primary), FFmpeg scene-change detection (supplementary), interval fallback for subtitle gaps > 30s
- [x] **PIPE-04**: Pipeline persists stage-based checkpoint state files so a run can resume after failure without restarting from scratch
- [x] **PIPE-05**: All GPU operations run strictly sequentially — llama-server inference and FFmpeg GPU operations never run concurrently

### Inference

- [x] **INFR-01**: System integrates with llama-server HTTP mode for persistent LLaVA inference (avoiding model reload per frame)
- [x] **INFR-02**: System applies mmproj binary patch for llama.cpp 8156 / LLaVA projector_type compatibility
- [x] **INFR-03**: System enforces GPU_LOCK across all GPU-using stages (llama-server + FFmpeg never concurrent)

### Narrative

- [x] **NARR-01**: System classifies extracted frames into 7 beat types (Inciting Incident, Climax, Money Shot, Character Introduction, Relationship Beat, Escalation Beat, Breath)
- [x] **NARR-02**: System scores keyframes using 8-signal money shot scorer
- [x] **NARR-03**: System generates TRAILER_MANIFEST.json with all clip decisions, reasoning, and per-clip treatment

### Edit

- [x] **EDIT-01**: System assembles clips into a 3-act structure with vibe-driven pacing curves
- [x] **EDIT-02**: System applies LUT grading per vibe via FFmpeg lut3d filter
- [x] **EDIT-03**: System normalises audio to vibe-specific LUFS target (two-pass loudnorm; single-pass for clips < 3s)

### CLI

- [x] **CLI-01**: User can run `cinecut <video> --subtitle <srt> --vibe <name> [--review] [--manifest <path>]`
- [x] **CLI-02**: `--review` flag pauses pipeline after manifest generation for human inspection before conform

---

## v2 Requirements

Requirements for v2.0 Structural & Sensory Overhaul. Each maps to a roadmap phase.

### Inference Infrastructure

- [x] **IINF-01**: Pipeline resume skips LLaVA inference when a valid SceneDescription cache exists for the source file
- [x] **IINF-02**: SceneDescription cache is automatically invalidated when source file mtime or size changes
- [ ] **IINF-03**: System resolves all model files (LLaVA GGUF, mmproj, text GGUF) from `~/models` by default; directory overridable via `CINECUT_MODELS_DIR` environment variable
- [ ] **IINF-04**: Pipeline uses heuristic zone fallback (5% / 45% / 80% of runtime) when the text model GGUF file is not present in the models directory

### Structural Analysis

- [ ] **STRC-01**: Text LLM identifies three narrative anchor timestamps (BEGIN_T, ESCALATION_T, CLIMAX_T) from subtitle corpus, processing in chunks of 50-100 events
- [ ] **STRC-02**: System assigns each extracted clip to a narrative zone: BEGINNING, ESCALATION, or CLIMAX
- [ ] **STRC-03**: Zone assignments are stored in TRAILER_MANIFEST.json v2.0 schema alongside existing clip fields

### Edit Ordering

- [ ] **EORD-01**: Clips are assembled in zone-first order (BEGINNING → ESCALATION → CLIMAX), not film chronology
- [ ] **EORD-02**: Within each zone, clips are ranked by emotional signal score (not source timestamp)
- [ ] **EORD-03**: Act 1 clips average 4-8 beats/clip; Act 3 clips average 1-2 beats/clip (montage density)
- [ ] **EORD-04**: A deliberate silence segment (3-5s black video + muted audio) is inserted at the Act 2→3 boundary

### BPM Grid

- [ ] **BPMG-01**: System detects music track BPM using librosa and generates a beat timestamp grid
- [ ] **BPMG-02**: Clip start points snap to the nearest beat grid position (within ±1 beat tolerance)
- [ ] **BPMG-03**: System falls back to vibe-default BPM when detection returns 0, half, or double tempo

### Music Bed

- [ ] **MUSC-01**: System selects a CC-licensed music track per vibe from the Jamendo API v3
- [ ] **MUSC-02**: Downloaded tracks are permanently cached per vibe at `~/.cinecut/music/`; Jamendo API is never called if a cached track exists
- [ ] **MUSC-03**: Pipeline continues without music (no abort) when Jamendo API is unavailable or returns an error

### Audio Mix

- [ ] **AMIX-01**: Music bed automatically ducks during protagonist VO and high-emotion shots via FFmpeg sidechaincompress
- [ ] **AMIX-02**: All audio stems (film audio, music, SFX, VO) are normalised independently before mixing; `amix normalize=0` is used throughout
- [ ] **AMIX-03**: All audio sources are resampled to 48000Hz stereo before mixing

### SFX

- [ ] **SFXL-01**: A synthesized swoosh/sweep SFX is added at each scene cut transition
- [ ] **SFXL-02**: SFX intensity varies by cut type: hard cuts get a short sharp sweep (0.4s); act-boundary transitions get a slower full-spectrum sweep (1.0-1.5s)
- [ ] **SFXL-03**: All SFX are synthesized via FFmpeg `aevalsrc` (no external SFX files required); explicitly at 48000Hz

### VO Narration

- [ ] **VONR-01**: System identifies the protagonist as the most frequently-speaking character in the subtitle corpus (via Stage 1 LLM output or dialogue-line-count fallback)
- [ ] **VONR-02**: Up to 3 protagonist dialogue lines are extracted as audio clips from the source film (1 in Act 1, up to 2 in Act 2, 0 in Act 3)
- [ ] **VONR-03**: All VO clips are extracted using output-seeking FFmpeg, re-encoded to AAC 48000Hz stereo, minimum 0.8s duration

---

## v3 Requirements (Deferred)

- **VONR-04**: VO line quality scoring beyond dialogue-line-count heuristic
- **SFXL-04**: Per-scene SFX intensity calibration (currently fixed tiers per beat type)
- **MUSC-04**: Music archive management UI or CLI for reviewing/replacing cached tracks

## Out of Scope

| Feature | Reason |
|---------|--------|
| External SFX file library | License burden; synthesize all SFX instead |
| Cloud TTS / hired VO narrator | Violates local-only constraint; use protagonist's actual film audio |
| Speaker diarization (pyannote.audio) | Requires PyTorch CUDA 12, incompatible with CUDA 11.4 stack |
| Per-frame BPM snap | Over-engineering; snap clip START points only |
| Music time-stretching to fit trailer | Rubato artifacts; cut/loop music to fit instead |
| Subtitle-less input mode | User always provides subtitle file (system constraint) |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| IINF-01 | Phase 6 | Complete |
| IINF-02 | Phase 6 | Complete |
| IINF-03 | Phase 7 | Pending |
| IINF-04 | Phase 7 | Pending |
| STRC-01 | Phase 7 | Pending |
| STRC-02 | Phase 8 | Pending |
| STRC-03 | Phase 7 | Pending |
| EORD-01 | Phase 8 | Pending |
| EORD-02 | Phase 8 | Pending |
| EORD-03 | Phase 8 | Pending |
| EORD-04 | Phase 9 | Pending |
| BPMG-01 | Phase 9 | Pending |
| BPMG-02 | Phase 9 | Pending |
| BPMG-03 | Phase 9 | Pending |
| MUSC-01 | Phase 9 | Pending |
| MUSC-02 | Phase 9 | Pending |
| MUSC-03 | Phase 9 | Pending |
| AMIX-01 | Phase 10 | Pending |
| AMIX-02 | Phase 10 | Pending |
| AMIX-03 | Phase 10 | Pending |
| SFXL-01 | Phase 10 | Pending |
| SFXL-02 | Phase 10 | Pending |
| SFXL-03 | Phase 10 | Pending |
| VONR-01 | Phase 10 | Pending |
| VONR-02 | Phase 10 | Pending |
| VONR-03 | Phase 10 | Pending |

**Coverage:**
- v2 requirements: 26 total
- Mapped to phases: 26
- Unmapped: 0 ✓

---
*Requirements defined: 2026-02-26*
*Last updated: 2026-02-28 after v2.0 milestone start*
