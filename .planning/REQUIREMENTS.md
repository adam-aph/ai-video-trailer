# Requirements: CineCut AI

**Defined:** 2026-02-26
**Core Value:** Given a feature film and its subtitle file, produce a narratively coherent, vibe-styled trailer that a human editor would be proud to show — technically clean output with a real beginning, escalation, and climax arc.

## v1 Requirements

Requirements for initial release. Each maps to a roadmap phase.

### Pipeline

- [ ] **PIPE-01**: User can provide MKV/AVI/MP4 source video + SRT/ASS subtitle file as inputs to the CLI
- [ ] **PIPE-02**: System creates a 420p analysis proxy from the source video using FFmpeg before inference
- [ ] **PIPE-03**: System extracts keyframes using a hybrid strategy: subtitle event midpoints (primary), FFmpeg scene-change detection (supplementary), interval fallback for subtitle gaps > 30s
- [ ] **PIPE-04**: Pipeline persists stage-based checkpoint state files so a run can resume after failure without restarting from scratch
- [ ] **PIPE-05**: All GPU operations run strictly sequentially — llama-server inference and FFmpeg GPU operations never run concurrently

### Inference

- [ ] **INFR-01**: System integrates with llama-server HTTP mode for persistent LLaVA inference (avoiding model reload per frame)
- [ ] **INFR-02**: System submits extracted keyframes to LLaVA and stores structured scene descriptions for each frame
- [ ] **INFR-03**: Inference pipeline stays within 12GB VRAM budget (one frame analyzed at a time, with memory verified before each call)

### Narrative Analysis

- [ ] **NARR-01**: System parses SRT and ASS subtitle files and extracts dialogue, timestamps, and emotional keyword classification per event
- [ ] **NARR-02**: System classifies each candidate scene into one of 7 beat types: inciting incident, character introduction, escalation beat, relationship beat, money shot, climax peak, breath
- [ ] **NARR-03**: System scores "money shot" candidates using a weighted multi-signal model: motion magnitude, visual contrast, scene uniqueness, subtitle emotional weight, face presence, LLaVA confidence, saturation, and chronological position

### Edit & Manifest

- [ ] **EDIT-01**: AI pipeline generates a `TRAILER_MANIFEST.json` containing all clip decisions with source timecodes, beat type, reasoning, visual analysis, subtitle analysis, and per-clip audio/transition treatment
- [ ] **EDIT-02**: System assembles clips according to a 3-act trailer structure: cold open, Act 1 setup, beat drop, Act 2 escalation, breath, Act 3 climax montage, title card, button
- [ ] **EDIT-03**: System implements pacing curves — average cut duration decreases from Act 1 to Act 3 per vibe-defined parameters
- [ ] **EDIT-04**: `--review` flag pauses the pipeline after manifest generation and waits for user to confirm before running the FFmpeg conform step
- [ ] **EDIT-05**: Conform pipeline applies the manifest against the original source file with frame-accurate FFmpeg seeking (`-ss` before `-i`)

### Vibes

- [ ] **VIBE-01**: System implements all 18 vibe profiles (Action, Adventure, Animation, Comedy, Crime, Documentary, Drama, Family, Fantasy, History, Horror, Music, Mystery, Romance, Sci-Fi, Thriller, War, Western) with concrete parameters: avg cut durations per act, clip count target, primary/secondary transitions, LUFS target, dialogue ratio, LUT specification, color temperature/contrast/saturation, pacing curve description
- [ ] **VIBE-02**: System includes or generates `.cube` LUT files for all 18 vibes (sourced from free/open libraries or programmatically generated via NumPy color transforms)
- [ ] **VIBE-03**: System applies per-vibe LUT to all output clips via FFmpeg `lut3d` filter during the conform step
- [ ] **VIBE-04**: System applies per-vibe LUFS audio normalization via FFmpeg `loudnorm` two-pass analysis and application

### CLI

- [ ] **CLI-01**: User invokes tool as `cinecut <video_file> --subtitle <subtitle_file> --vibe <vibe_name> [--review]`
- [ ] **CLI-02**: CLI provides Rich progress indicators for all long-running stages (proxy creation, keyframe extraction, LLaVA inference, manifest generation, conform)
- [ ] **CLI-03**: CLI provides actionable error messages when FFmpeg or llama-server failures occur (translates subprocess errors to human-readable guidance)
- [ ] **CLI-04**: Output is an approximately 2-minute MP4 trailer at source resolution, written to `<source_basename>_trailer_<vibe>.mp4`

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Extended Input

- **INPUT-01**: System accepts video files without subtitle input (graceful degradation to visual-only narrative analysis)
- **INPUT-02**: System supports multi-language subtitle files with automatic encoding detection

### Advanced Editing

- **AEDIT-01**: User can provide a music track file; system syncs hard cuts to beat onsets
- **AEDIT-02**: System supports vertical (9:16) and square (1:1) output formats for social media
- **AEDIT-03**: System supports custom transition effect profiles beyond hard-cut, crossfade, and fade-to-black

### UX

- **UX-01**: System provides interactive vibe selection when `--vibe` is not specified
- **UX-02**: System outputs a human-readable review report alongside the JSON manifest (HTML or markdown summary of AI decisions)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Cloud inference or remote API calls | Hard constraint — local-only; hardware is pre-provisioned |
| Speech-to-text / subtitle generation | User always provides subtitle file; adding STT is a separate project |
| Web or GUI interface | CLI is the product; GUI adds complexity without adding core value |
| Custom transition effects beyond core 4 | Tacky if done poorly; hard cuts are the professional standard for trailers |
| Music/score generation | Source audio is the correct approach for trailers; music gen is a separate project |
| Multi-GPU support | Single Quadro K6000 per constraint; distributing adds architectural complexity with no target hardware |
| Real-time preview during pipeline | K6000 cannot render and infer simultaneously; manifest + fast re-render is the workflow |
| Ollama or Python-native LLM loading | llama-cli/llama-server is the pre-configured inference engine; deviating risks CUDA 11.4 instability |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PIPE-01 | — | Pending |
| PIPE-02 | — | Pending |
| PIPE-03 | — | Pending |
| PIPE-04 | — | Pending |
| PIPE-05 | — | Pending |
| INFR-01 | — | Pending |
| INFR-02 | — | Pending |
| INFR-03 | — | Pending |
| NARR-01 | — | Pending |
| NARR-02 | — | Pending |
| NARR-03 | — | Pending |
| EDIT-01 | — | Pending |
| EDIT-02 | — | Pending |
| EDIT-03 | — | Pending |
| EDIT-04 | — | Pending |
| EDIT-05 | — | Pending |
| VIBE-01 | — | Pending |
| VIBE-02 | — | Pending |
| VIBE-03 | — | Pending |
| VIBE-04 | — | Pending |
| CLI-01 | — | Pending |
| CLI-02 | — | Pending |
| CLI-03 | — | Pending |
| CLI-04 | — | Pending |

**Coverage:**
- v1 requirements: 24 total
- Mapped to phases: 0
- Unmapped: 24 ⚠️ (filled by roadmapper)

---
*Requirements defined: 2026-02-26*
*Last updated: 2026-02-26 after initial definition*
