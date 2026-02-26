# Roadmap: CineCut AI

## Overview

CineCut AI delivers a local CLI tool that transforms a feature film into a narratively coherent 2-minute trailer styled by genre vibe. The roadmap builds the three-tier pipeline tier by tier: first ingestion (FFmpeg proxy, keyframes, subtitles), then the output contract (manifest schema, vibe system, conform), then LLaVA inference, then narrative analysis algorithms, and finally the assembly and orchestration that wires everything end-to-end. Each phase delivers a testable, standalone capability; the critical manifest contract is defined before the AI that produces it, and the riskiest work (LLM integration) is isolated in its own phase.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Ingestion Pipeline and CLI Shell** - FFmpeg proxy creation, keyframe extraction, subtitle parsing, and the CLI entry point with progress and error handling (completed 2026-02-26)
- [x] **Phase 2: Manifest Contract, Vibes, and Conform** - Pydantic manifest schema, all 18 vibe profiles with LUTs, high-bitrate FFmpeg conform pipeline, and --review workflow (completed 2026-02-26)
- [x] **Phase 3: LLaVA Inference Engine** - llama-server integration for persistent LLaVA inference, structured scene descriptions, and VRAM-aware sequential processing (completed 2026-02-26)
- [x] **Phase 4: Narrative Beat Extraction and Manifest Generation** - Beat classification (7 types), money shot scoring (8-signal model), and AI-driven manifest generation from real inference output (completed 2026-02-26)
- [ ] **Phase 5: Trailer Assembly and End-to-End Pipeline** - 3-act structure assembly with pacing curves, full pipeline orchestrator with checkpointing, and end-to-end integration

## Phase Details

### Phase 1: Ingestion Pipeline and CLI Shell
**Goal**: User can invoke CineCut on a film and see it ingested into analysis-ready artifacts (proxy, keyframes, parsed subtitles) with clear progress feedback
**Depends on**: Nothing (first phase)
**Requirements**: PIPE-01, PIPE-02, PIPE-03, NARR-01, CLI-01, CLI-02, CLI-03
**Success Criteria** (what must be TRUE):
  1. User can run `cinecut <video> --subtitle <srt> --vibe action` and see the CLI accept the inputs, validate file existence, and display Rich progress bars during proxy creation
  2. System produces a 420p CFR proxy from MKV/AVI/MP4 sources using FFmpeg with frame-accurate timecodes preserved (PTS seconds, not frame indices)
  3. System extracts keyframes using the hybrid strategy (subtitle midpoints, scene-change detection, interval fallback for gaps > 30s) and writes them to a work directory
  4. System parses both SRT and ASS subtitle files and produces structured dialogue events with timestamps and emotional keyword classification
  5. When FFmpeg or file operations fail, the CLI displays actionable human-readable error messages (not raw subprocess stderr)
**Plans**: 5 plans

Plans:
- [ ] 01-01-PLAN.md — Package scaffold, shared data models (DialogueEvent, KeyframeRecord), and error translation layer
- [ ] 01-02-PLAN.md — Subtitle parser (SRT/ASS + emotion classification) and FFmpeg proxy creation with validation
- [ ] 01-03-PLAN.md — Hybrid keyframe extractor and Typer CLI shell wiring all ingestion stages with Rich progress
- [ ] 01-04-PLAN.md — [GAP] Fix PATH environment so cinecut is reachable in non-interactive shells
- [ ] 01-05-PLAN.md — [GAP] Fix CLI validation order: extension check before existence check with consistent Rich error panels

### Phase 2: Manifest Contract, Vibes, and Conform
**Goal**: Given a valid TRAILER_MANIFEST.json (hand-crafted or generated), the system can render a final trailer with vibe-specific color grading, audio normalization, and frame-accurate segment extraction
**Depends on**: Phase 1
**Requirements**: EDIT-04, EDIT-05, VIBE-01, VIBE-02, VIBE-03, VIBE-04, CLI-04
**Success Criteria** (what must be TRUE):
  1. A complete Pydantic-validated manifest schema exists and the system can load, validate, and reject malformed manifests with clear error messages
  2. All 18 vibe profiles are defined with concrete parameters (avg cut durations per act, clip count target, transitions, LUFS target, dialogue ratio, LUT spec, color temperature/contrast/saturation, pacing curve)
  3. System applies per-vibe .cube LUT files and LUFS audio normalization to output clips via FFmpeg during conform
  4. User can run with --review flag and the pipeline pauses after manifest generation, allowing inspection and editing before conform proceeds
  5. Given a hand-crafted manifest, the conform pipeline produces an approximately 2-minute MP4 trailer at source resolution written to `<source_basename>_trailer_<vibe>.mp4`
**Plans**: 3 plans

Plans:
- [ ] 02-01-PLAN.md — Pydantic manifest schema, vibe profiles (18), LUT generation, ManifestError/ConformError
- [ ] 02-02-PLAN.md — FFmpeg conform pipeline (extract + lut3d + loudnorm + concat) and CLI --manifest/--review wiring
- [ ] 02-03-PLAN.md — Unit tests (schema validation, LUT ordering) and human-verify end-to-end conform

### Phase 3: LLaVA Inference Engine
**Goal**: System can analyze extracted keyframes through LLaVA and produce structured scene descriptions while staying within the 12GB VRAM budget
**Depends on**: Phase 1
**Requirements**: INFR-01, INFR-02, INFR-03, PIPE-05
**Success Criteria** (what must be TRUE):
  1. System launches and communicates with llama-server in HTTP mode for persistent LLaVA inference (no model reload per frame)
  2. System submits keyframes to LLaVA one at a time and receives structured scene descriptions (visual content, mood, action, setting) with validated output format
  3. GPU operations are strictly sequential -- llama-server inference and FFmpeg GPU operations never run concurrently, with VRAM verified before each inference call
  4. When llama-server hangs, crashes, or produces malformed output, the system handles it gracefully (timeout, skip with warning, no zombie processes)
**Plans**: 3 plans

Plans:
- [ ] 03-01-PLAN.md — requests dependency, InferenceError/VramError classes, test scaffold, LLaVA model download (human checkpoint)
- [ ] 03-02-PLAN.md — cinecut.inference package: SceneDescription model, VRAM check, LlavaEngine context manager with GPU_LOCK
- [ ] 03-03-PLAN.md — describe_frame() inference loop, run_inference_stage(), CLI wiring, INFR-02 unit tests, human-verify

### Phase 4: Narrative Beat Extraction and Manifest Generation
**Goal**: System can classify analyzed scenes into narrative beats, score money shot candidates, and generate a complete trailer manifest from real film analysis
**Depends on**: Phase 3
**Requirements**: NARR-02, NARR-03, EDIT-01
**Success Criteria** (what must be TRUE):
  1. System classifies each candidate scene into one of 7 beat types (inciting incident, character introduction, escalation beat, relationship beat, money shot, climax peak, breath) using combined subtitle and visual signals
  2. System scores money shot candidates using all 8 weighted signals (motion magnitude, visual contrast, scene uniqueness, subtitle emotional weight, face presence, LLaVA confidence, saturation, chronological position)
  3. System generates a complete TRAILER_MANIFEST.json from real inference output with beat type, reasoning, visual analysis, subtitle analysis, and per-clip audio/transition treatment for every selected clip
**Plans**: 2 plans

Plans:
- [ ] 04-01-PLAN.md — ClipEntry schema extension (4 Optional fields) + narrative package: signals.py (8-signal extraction) and scorer.py (normalization, weighted scoring, beat classification)
- [ ] 04-02-PLAN.md — generator.py (manifest assembly pipeline), CLI Stage 5 wiring, and test_narrative.py unit tests

### Phase 5: Trailer Assembly and End-to-End Pipeline
**Goal**: System produces a complete, narratively coherent trailer from any feature film by assembling clips into a 3-act structure with vibe-driven pacing and surviving failures gracefully
**Depends on**: Phase 2, Phase 4
**Requirements**: EDIT-02, EDIT-03, PIPE-04
**Success Criteria** (what must be TRUE):
  1. System assembles selected clips into a 3-act trailer structure (cold open, Act 1 setup, beat drop, Act 2 escalation, breath, Act 3 climax montage, title card, button) following the vibe profile timing template
  2. Pacing curves are observable in output -- average cut duration decreases from Act 1 to Act 3 per vibe-defined parameters
  3. Pipeline persists stage-based checkpoint state files so a run can resume after failure (power loss, OOM, crash) without restarting the full 30-60 minute pipeline from scratch
  4. A complete end-to-end run from `cinecut <film> --subtitle <srt> --vibe <name>` through proxy, inference, manifest generation, and conform produces a playable trailer MP4
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5
(Note: Phase 3 depends on Phase 1 only, so could theoretically parallel Phase 2, but sequential execution is simpler for a solo workflow.)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Ingestion Pipeline and CLI Shell | 5/5 | Complete   | 2026-02-26 |
| 2. Manifest Contract, Vibes, and Conform | 3/3 | Complete   | 2026-02-26 |
| 3. LLaVA Inference Engine | 3/3 | Complete   | 2026-02-26 |
| 4. Narrative Beat Extraction and Manifest Generation | 2/2 | Complete   | 2026-02-26 |
| 5. Trailer Assembly and End-to-End Pipeline | 0/2 | Not started | - |
