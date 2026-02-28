# Roadmap: CineCut AI

## Milestones

- ✅ **v1.0 MVP** — Phases 1-5 (shipped 2026-02-27)
- 🚧 **v2.0 Structural & Sensory Overhaul** — Phases 6-10 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-5) — SHIPPED 2026-02-27</summary>

- [x] Phase 1: Ingestion Pipeline and CLI Shell (5/5 plans) — completed 2026-02-26
- [x] Phase 2: Manifest Contract, Vibes, and Conform (3/3 plans) — completed 2026-02-26
- [x] Phase 3: LLaVA Inference Engine (3/3 plans) — completed 2026-02-26
- [x] Phase 4: Narrative Beat Extraction and Manifest Generation (2/2 plans) — completed 2026-02-26
- [x] Phase 5: Trailer Assembly and End-to-End Pipeline (4/4 plans) — completed 2026-02-27

See `.planning/milestones/v1.0-ROADMAP.md` for full phase details.

</details>

### 🚧 v2.0 Structural & Sensory Overhaul (In Progress)

**Milestone Goal:** Transform the flat chronological highlight reel into a dramatically structured, sonically layered trailer — non-linear scene ordering driven by narrative zone assignment, BPM-synced edit rhythm, royalty-free music bed with dynamic ducking, synthesized transition SFX, and protagonist VO extracted from film audio.

- [ ] **Phase 6: Inference Persistence** — SceneDescription cache eliminates re-inference on crash resume
- [ ] **Phase 7: Structural Analysis** — Text LLM identifies BEGIN/ESCALATION/CLIMAX anchors; zone assignments stored in manifest v2.0
- [ ] **Phase 8: Zone Matching and Non-Linear Ordering** — Clips assigned to narrative zones and assembled zone-first by emotional signal
- [ ] **Phase 9: BPM Grid and Music Bed** — Beat grid snaps cut timing; royalty-free music selected per vibe and cached locally
- [x] **Phase 10: SFX, VO, and Audio Mix** — Synthesized transition SFX, protagonist VO extraction, and full four-stem audio mix (completed 2026-02-28)

## Phase Details

### Phase 6: Inference Persistence
**Goal**: Pipeline resume skips LLaVA inference entirely when a valid SceneDescription cache exists, eliminating the 30-60 minute re-inference penalty after any crash or interrupt.
**Depends on**: Phase 5 (v1.0 pipeline complete)
**Requirements**: IINF-01, IINF-02
**Success Criteria** (what must be TRUE):
  1. User can resume a failed pipeline run and Stage 4 (LLaVA inference) is skipped — Rich output confirms cache hit
  2. Cache is automatically invalidated and inference re-runs when the source file has changed (different mtime or size)
  3. A completed run produces a `.scenedesc.msgpack` cache file alongside the checkpoint directory
**Plans**: 1 plan

Plans:
- [ ] 06-01-PLAN.md — msgpack SceneDescription cache (inference/cache.py), Stage 4 CLI guard, cascade checkpoint reset, unit tests

### Phase 7: Structural Analysis
**Goal**: A text LLM (Mistral 7B) reads the subtitle corpus and identifies three narrative anchor timestamps (BEGIN_T, ESCALATION_T, CLIMAX_T) that drive all zone-based features downstream. Models directory is configurable. Heuristic fallback covers no-GGUF environments.
**Depends on**: Phase 6
**Requirements**: IINF-03, IINF-04, STRC-01, STRC-03
**Success Criteria** (what must be TRUE):
  1. Running `cinecut` against a film produces BEGIN_T, ESCALATION_T, CLIMAX_T timestamps visible in the generated manifest (v2.0 schema)
  2. Setting `CINECUT_MODELS_DIR=/custom/path` causes the pipeline to load all model files from that directory instead of `~/models`
  3. When the Mistral GGUF is absent, the pipeline continues using the 5%/45%/80% runtime heuristic fallback — no abort, log message explains fallback
  4. Manifest schema version field reads "2.0" and includes `structural_anchors` block
**Plans**: 2 plans

Plans:
- [ ] 07-01-PLAN.md — TextEngine context manager (inference/text_engine.py), wait_for_vram polling, get_models_dir(), cli.py model path migration
- [ ] 07-02-PLAN.md — Structural analysis (inference/structural.py), analyze_chunk on TextEngine, StructuralAnchors schema, Stage 5 in cli.py, unit tests

### Phase 8: Zone Matching and Non-Linear Ordering
**Goal**: Every extracted clip is assigned to BEGINNING, ESCALATION, or CLIMAX using sentence-transformers cosine similarity, then assembled in zone-first order ranked by emotional signal — replacing film-chronology ordering as the core narrative claim of v2.0.
**Depends on**: Phase 7
**Requirements**: STRC-02, EORD-01, EORD-02, EORD-03
**Success Criteria** (what must be TRUE):
  1. Output trailer clips appear in BEGINNING → ESCALATION → CLIMAX order regardless of their source timestamps in the film
  2. Within each zone, clips are ordered by descending emotional signal score (not source timestamp)
  3. Act 1 clips are visibly longer-cut than Act 3 clips — montage density increases through the trailer
  4. Each clip in the manifest carries a `narrative_zone` field (BEGINNING, ESCALATION, or CLIMAX)
**Plans**: 2 plans

Plans:
- [ ] 08-01-PLAN.md — NarrativeZone enum + ClipEntry.narrative_zone in schema.py; narrative/zone_matching.py with CPU sentence-transformers cosine similarity; unit tests
- [ ] 08-02-PLAN.md — sort_clips_by_zone + enforce_zone_pacing_curve in ordering.py; run_zone_matching wired into generator.py; zone-first manifest assembly

### Phase 9: BPM Grid and Music Bed
**Goal**: A CC-licensed music track is auto-selected per vibe from Jamendo and cached permanently; librosa detects BPM from the track and generates a beat grid that snaps clip start points to the nearest beat. Pipeline continues without music on any API or detection failure.
**Depends on**: Phase 8
**Requirements**: BPMG-01, BPMG-02, BPMG-03, EORD-04, MUSC-01, MUSC-02, MUSC-03
**Success Criteria** (what must be TRUE):
  1. Output trailer has a continuous music bed audible throughout all three acts
  2. A second run with the same vibe does not call the Jamendo API — Rich output confirms cache hit from `~/.cinecut/music/`
  3. Running with `--vibe action` on a machine with no network produces a trailer without music and without aborting — log warns about missing music
  4. A deliberate 3-5s black silence segment is present at the Act 2-to-Act 3 boundary in the output
  5. Clip start points align to within one beat of the detected BPM grid; vibe-default BPM is used when detection returns 0 or an octave error
**Plans**: 3 plans

Plans:
- [ ] 09-01-PLAN.md — BPM detection and beat grid (assembly/bpm.py) + BpmGrid/MusicBed Pydantic manifest models (manifest/schema.py)
- [ ] 09-02-PLAN.md — Music bed (assembly/music.py) — Jamendo API v3 fetch, permanent per-vibe cache, graceful degradation; pyproject.toml deps
- [ ] 09-03-PLAN.md — Silence segment insertion (ordering.py), assemble_manifest wiring (__init__.py), Stage 7 in cli.py, unit tests

### Phase 10: SFX, VO, and Audio Mix
**Goal**: Synthesized swoosh/sweep SFX mark every scene cut; protagonist VO lines are extracted from film audio and placed in Acts 1 and 2; all four audio stems (film audio, music, SFX, VO) are independently normalized and mixed with dynamic ducking — producing the complete sensory-layer trailer.
**Depends on**: Phase 9
**Requirements**: AMIX-01, AMIX-02, AMIX-03, SFXL-01, SFXL-02, SFXL-03, VONR-01, VONR-02, VONR-03
**Success Criteria** (what must be TRUE):
  1. Transition swoosh/sweep SFX is audible at each scene cut; act-boundary transitions have a longer, fuller sweep than hard mid-act cuts
  2. Up to 3 protagonist dialogue clips are audible in the trailer (1 in Act 1, up to 2 in Act 2, none in Act 3) — identifiable as the most frequently-speaking character
  3. Music bed audibly ducks during protagonist VO and high-emotion shots, then recovers
  4. All audio sources play at consistent perceived loudness — no single stem overwhelms or disappears
  5. No SFX file dependencies exist on disk — all synthesis runs via FFmpeg aevalsrc at 48000Hz
**Plans**: 3 plans

Plans:
- [ ] 10-01-PLAN.md — SFX synthesis (conform/sfx.py) — aevalsrc linear chirp, hard-cut (0.4s) and act-boundary (1.2s) tiers, idempotent WAV synthesis, adelay timeline overlay
- [ ] 10-02-PLAN.md — VO extraction (conform/vo_extract.py) — protagonist identification via SSAEvent.name, output-seeking FFmpeg extraction, AAC 48000Hz stereo, 0.8s minimum duration
- [ ] 10-03-PLAN.md — Four-stem audio mix (conform/audio_mix.py) — sidechaincompress ducking, amix normalize=0, stem-level loudnorm, 48000Hz resampling; Pass 3 + Pass 4 wired into conform/pipeline.py; unit tests

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Ingestion Pipeline and CLI Shell | v1.0 | 5/5 | Complete | 2026-02-26 |
| 2. Manifest Contract, Vibes, and Conform | v1.0 | 3/3 | Complete | 2026-02-26 |
| 3. LLaVA Inference Engine | v1.0 | 3/3 | Complete | 2026-02-26 |
| 4. Narrative Beat Extraction and Manifest Generation | v1.0 | 2/2 | Complete | 2026-02-26 |
| 5. Trailer Assembly and End-to-End Pipeline | v1.0 | 4/4 | Complete | 2026-02-27 |
| 6. Inference Persistence | v2.0 | 0/1 | Not started | - |
| 7. Structural Analysis | v2.0 | 0/2 | Not started | - |
| 8. Zone Matching and Non-Linear Ordering | v2.0 | 0/2 | Not started | - |
| 9. BPM Grid and Music Bed | v2.0 | 0/3 | Not started | - |
| 10. SFX, VO, and Audio Mix | 3/3 | Complete   | 2026-02-28 | - |
