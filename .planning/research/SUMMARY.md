# Project Research Summary

**Project:** CineCut AI v2.0 — Structural & Sensory Overhaul
**Domain:** AI-driven video trailer generation (local LLM inference, Python CLI)
**Researched:** 2026-02-28
**Confidence:** MEDIUM-HIGH

## Executive Summary

CineCut AI v2.0 transforms the existing v1.0 highlight-reel pipeline into a dramatically structured, sonically layered trailer generator. The v1.0 pipeline (7 stages, LLaVA vision inference on K6000, OpenCV keyframes, FFmpeg conform) is a validated working baseline. v2.0 adds eight features that operate at two levels: structural intelligence (LLM-driven three-act zone assignment, non-linear clip ordering) and sensory texture (BPM-synced edit rhythm, music bed with auto-ducking, synthesized SFX transitions, protagonist VO narration). The recommended approach extends the existing pipeline to 9 stages using sequential server restarts for the two-model LLM pipeline, CPU-only audio libraries (librosa, sentence-transformers), and the established FFmpeg subprocess pattern throughout. No architectural rewrites are needed — v2.0 slots new modules into a proven structure with one manifest schema bump from "1.0" to "2.0".

The single highest-risk constraint is the CUDA 11.4 / Kepler (K6000) hardware environment. The system's pinned llama-server build 8156 must not be upgraded — modern llama.cpp dropped compute capability 3.5 support, and upgrading risks breaking the mmproj binary patch that enables LLaVA inference. All new Python dependencies are CPU-only (librosa, sentence-transformers with an explicit CPU PyTorch wheel, msgpack) or existing system tools (FFmpeg, SoX). The sentence-transformers library requires installing `torch --index-url https://download.pytorch.org/whl/cpu` first to prevent accidental CUDA wheel selection, which would be incompatible with the K6000.

The primary operational risks are: (1) CUDA memory not releasing between sequential llama-server invocations — requires polling `nvidia-smi` before starting the second model server; (2) FFmpeg audio mixing complexity — four simultaneous audio layers (film audio, music bed, SFX, VO) require stem-level normalization and strict `amix normalize=0` discipline to preserve dynamic ducking intent; (3) BPM detection failure modes (0 BPM on silence, octave errors) require fallback logic keyed to vibe-default BPM values; and (4) music API reliability — the Jamendo integration must cache aggressively and degrade gracefully to no-music rather than aborting the pipeline. All of these have well-defined prevention strategies documented in the research.

## Key Findings

### Recommended Stack

The v2.0 stack adds five new Python libraries on top of the validated v1.0 stack (Python 3.10+, Typer, Rich, Pydantic, pysubs2, OpenCV headless, NumPy, requests, FFmpeg subprocess, llama-server HTTP). All new additions are CPU-only or existing system tools, eliminating VRAM contention risk from the new dependency surface.

**Core v2.0 additions:**
- `librosa >= 0.11.0`: BPM detection and beat grid generation — CPU-only, seeded with vibe-default start BPM to avoid half/double tempo errors; handles OGG (unlike aubio)
- `soundfile >= 0.12.1`: Audio I/O backend for librosa — required for WAV loading from FFmpeg-extracted audio tracks
- `msgpack >= 1.0.0`: SceneDescription inference cache persistence — ~30% smaller than JSON, not executable on load (unlike pickle), schema-version-gated for safe invalidation
- `sentence-transformers >= 3.0.0`: Scene-to-zone text embedding via `all-MiniLM-L6-v2` (22MB model, <2ms CPU inference per sentence) — text-to-text zone matching avoids PyTorch CUDA dependency entirely
- `torch (CPU wheel only)`: Pulled in by sentence-transformers; must be installed first with `--index-url https://download.pytorch.org/whl/cpu` to prevent CUDA wheel selection
- **Jamendo API v3** (via existing `requests`): 600K+ CC-licensed tracks, self-service client_id, `audiodownload` field, 18-vibe tag mapping built into the codebase
- **FFmpeg `aevalsrc` + SoX `synth`** (existing system tools): Transition SFX synthesis — deterministic, cacheable, zero new dependencies
- **Mistral 7B Instruct v0.3 Q4_K_M GGUF**: Text-only structural LLM (~4.37 GB VRAM) via existing llama-server build 8156 on port 8090, separate from LLaVA on port 8089

**Critical non-negotiable constraint:** The `llama-server` binary must remain at build 8156. Modern llama.cpp prebuilt wheels target compute capability 6.1+ (Pascal+) and will not run on the K6000 (Kepler, cc 3.5). Do not `apt upgrade` or manually rebuild llama.cpp.

See `.planning/research/STACK.md` for complete integration patterns, pyproject.toml additions, and the full CUDA 11.4 compatibility matrix.

### Expected Features

**Must have (v2.0 table stakes — milestone fails without these):**
- SceneDescription persistence — eliminates 30-60 min re-inference on crash resume; no other v2.0 dependencies; build this first
- Two-stage LLM pipeline + three-act zone tagging — all structural features depend on BEGIN_T / ESCALATION_T / CLIMAX_T anchors
- Non-linear scene ordering — the core narrative claim of v2.0; clips sorted zone-first, then by emotional signal, not by source timestamp
- Music bed per vibe — silence is a worse default than imperfect music; Jamendo API with permanent per-vibe local cache

**Should have (differentiators that require table stakes to be stable first):**
- BPM grid / beat map — requires music bed to exist; snaps clip start points to beat grid within ±1 beat tolerance
- Dynamic music ducking — music auto-attenuates during VO/dialogue via FFmpeg `sidechaincompress`
- Silence / breathing room segments — 3–5s deliberate pauses at act 2→3 boundary ("stopdown" technique per Derek Lieu)
- SFX transitions (synthesized) — whoosh/sweep tones at cuts via FFmpeg `aevalsrc` + SoX `synth`; pre-rendered to a single WAV per run

**Ship last (high complexity, requires earlier features to be stable):**
- Hero VO narration — depends on Stage 1 protagonist detection output; EQ tuning is iterative; background score bleeds into extracted audio (inherent limitation; mitigate with lower VO volume and placement during music lulls)

**Explicitly deferred to v2.1+:**
- VO line quality scoring beyond dialogue-line-count heuristic
- Per-scene SFX intensity calibration (start with fixed intensity tiers per beat type)
- Music archive management UI (auto-download on first use is sufficient for v2.0)

**Anti-features — do not build:**
- External SFX file library (license burden; synthesize all SFX instead)
- Cloud TTS / hired VO narrator (violates local-only constraint; use protagonist's actual film audio)
- Speaker diarization via pyannote.audio (requires PyTorch CUDA 12, incompatible with CUDA 11.4 stack)
- Per-frame BPM snap (over-engineering; snap clip START points only, within ±1 beat)
- Variable-tempo BPM time-stretching (rubato artifacts; cut/loop music to fit instead)

See `.planning/research/FEATURES.md` for full feature dependency graph and MVP priority ranking.

### Architecture Approach

The v2.0 architecture extends the existing 7-stage pipeline to 9 stages by inserting two new stages (Stage 3: structural analysis, Stage 6: scene-to-zone matching) and modifying four existing stages (Stage 5 adds inference caching, Stage 7 adds zone-first ordering, Stage 8 adds BPM/music/VO, Stage 9 adds a three-pass audio mix). The manifest schema bumps from "1.0" to "2.0" with new sub-models (StructuralAnchors, MusicBed, BpmGrid, SfxConfig, VoClip) and one new field on ClipEntry (`narrative_zone`). All new components follow established v1.0 patterns: atomic file writes via tempfile + os.replace, GPU_LOCK context managers, Pydantic validation with schema version gating, and FFmpeg subprocess invocations.

**New modules to create:**
1. `inference/text_engine.py` — TextEngine context manager (mirrors LlavaEngine pattern), serves Mistral 7B on port 8090, holds GPU_LOCK for its entire lifetime
2. `inference/cache.py` — SceneDescription save/load/build_results_from_cache with content hash invalidation (mtime + size)
3. `narrative/zone_matching.py` — assigns clips to narrative zones using sentence-transformers cosine similarity; forced `device="cpu"`
4. `assembly/bpm.py` + `assembly/music.py` — BPM detection (librosa) and Jamendo music resolution with permanent per-vibe cache
5. `conform/audio_mix.py` + `conform/sfx.py` + `conform/vo_extract.py` — three-layer audio mixing pass added as Pass 3 + Pass 4 after existing clip extraction and concatenation

**Key patterns to follow:**
- Sequential server restarts (TextEngine then LlavaEngine) with nvidia-smi VRAM polling between swaps — never use router mode (post-build-8156 feature, untested with K6000)
- Two-pass then audio-mix conform sequence: extract clips → concat → audio mix (not a single mega-filtergraph; mega-filtergraphs are fragile and hard to debug)
- Pre-render SFX to a single WAV before mixing (avoids per-beat filtergraph node explosion at 25-35 nodes for action trailers)
- Zone ordering runs first; BPM beat snapping runs second (narrative structure takes precedence over rhythm)

See `.planning/research/ARCHITECTURE.md` for the complete 9-stage data flow diagram, all new module interfaces, manifest schema additions, and 5-phase build order with testable deliverables per phase.

### Critical Pitfalls

1. **CUDA memory lingers between model swaps (V2-1)** — After stopping the first llama-server, poll `nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits` until reported VRAM drops below 500MB or 15s timeout. Add a minimum 3s hard floor even if polling is skipped. If the second server starts in under 3s, emit a warning — the model likely loaded to CPU (50-200x slower inference, no error message).

2. **FFmpeg `amix normalize=1` destroys ducking ratios (V2-2)** — Always use `amix normalize=0`. Normalize each stem independently before mixing (never the final output — loudnorm treats ducking as content to normalize away). Resample all audio to 48000Hz before any mixing filtergraph. Mix audio only after final video concatenation, not per-clip.

3. **Non-linear reordering causes audio bleed and dialogue non-sequiturs (V2-3)** — Apply PTS reset (`setpts=PTS-STARTPTS`, `asetpts=PTS-STARTPTS`) plus 0.1s audio fade-in/out on every extracted clip. Deprioritize pronoun-leading dialogue ("I told you", "He said") for BEGIN zone — it reads as incoherent without prior context.

4. **BPM detection returns 0, half, or double tempo (V2-4)** — Guard against 0 BPM with a vibe-default fallback. Clamp to vibe-expected range (e.g., Action: 120-160 BPM, Drama: 60-90 BPM); halve or double the detected value if outside bounds. If beat array has fewer than 8 beats in the first 30s, classify as non-beat-tracked and fall back to fixed-interval cuts.

5. **Music API downtime or OAuth expiry aborts pipeline (V2-5)** — Cache every downloaded track permanently per vibe in `~/.cinecut/music/`. Treat music as best-effort: any download failure (network error, 401, 404, 429) logs a warning and continues without a music bed. Never abort the pipeline for a missing music track.

## Implications for Roadmap

The ARCHITECTURE.md research derives a clean 5-phase build order from data dependencies. Each phase is testable in isolation and unblocked by the previous phase. The ordering is strongly recommended.

### Phase 1: Inference Persistence (SceneDescription Cache)

**Rationale:** Zero external dependencies; fixes the most painful v1.0 gap immediately (crash recovery without 30-60 min re-inference); foundation that all other v2.0 phases depend on for resume reliability. Can be built and tested in complete isolation from the structural LLM work.
**Delivers:** `inference/cache.py` with save/load/build_results_from_cache; Stage 5 checkpoint guard in cli.py; schema-version-gated cache keyed to source file mtime + size (not just path)
**Addresses:** Table stakes feature "SceneDescription persistence"; V2-7 (stale cache prevention); eliminates the most common v1.0 pain point
**Avoids:** Temptation to use pickle (executable on load, class-path sensitive) or SQLite (schema migration overhead with no query benefit for a flat inference cache)

### Phase 2: Structural Analysis (Text LLM, Stage 3)

**Rationale:** Provides BEGIN_T / ESCALATION_T / CLIMAX_T anchors that all downstream structural features depend on. TextEngine context manager mirrors the existing LlavaEngine — a proven, low-risk pattern. Must exist before zone matching. Provides a `--text-model` fallback heuristic (5%/45%/80% of runtime) so later phases are testable without a downloaded GGUF.
**Delivers:** `inference/text_engine.py` (TextEngine), `inference/structural.py` (analyze_structure + StructuralAnchors), manifest schema 2.0 bump, `--text-model` CLI flag with heuristic fallback, subtitle chunking at 50-100 events per LLM call
**Uses:** Mistral 7B Instruct v0.3 Q4_K_M, llama-server build 8156 on port 8090
**Avoids:** V2-1 (nvidia-smi VRAM polling between server swaps, built here); V2-9 (context window overflow via chunking strategy)

### Phase 3: Zone Matching + Non-Linear Ordering (Stage 6 + Stage 7)

**Rationale:** Depends on StructuralAnchors from Phase 2 (or heuristic fallback). Changes the core clip ordering semantics — the primary narrative claim of v2.0. Must be stable before audio features are layered on top, as audio decisions (where to duck, where to place VO) depend on zone assignments.
**Delivers:** `narrative/zone_matching.py` (sentence-transformers cosine similarity, CPU-only); NarrativeZone enum; `narrative_zone` on ClipEntry; zone-first + emotional-signal ordering in narrative/generator.py; Stage 6 checkpoint
**Implements:** CPU-only sentence-transformers (all-MiniLM-L6-v2, 22MB) with forced `device="cpu"` — install CPU PyTorch wheel first
**Avoids:** V2-3 (PTS reset + 0.1s audio fades on every extracted clip; pronoun-leading dialogue filtering)

### Phase 4: BPM Grid + Music Bed (Stage 8 sub-features)

**Rationale:** Pure addition to Stage 8 with no inference or narrative stage changes. Requires librosa as the only genuinely new dependency. Music bed must exist before ducking and SFX features can be built in Phase 5.
**Delivers:** `assembly/bpm.py` (detect_bpm, beat grid, snap_clips_to_beats); `assembly/music.py` (Jamendo API fetch with permanent per-vibe cache at `~/.cinecut/music/`); BpmGrid and MusicBed manifest models; `music_track_filename` on all 18 VibeProfiles
**Avoids:** V2-4 (0 BPM guard, octave correction, vibe-range clamping — all built here); V2-5 (cache-first, graceful degradation on any API failure); V2-12 (crossfade loop for short tracks under 90s)

### Phase 5: SFX + VO + Audio Mix (Stage 9 conform changes)

**Rationale:** Depends on BpmGrid (cut times, from Phase 4) and music track path. The most complex phase — the FFmpeg filtergraph must be validated end-to-end. Correct stem-level normalization and `amix normalize=0` discipline are day-one architecture decisions within this phase.
**Delivers:** `conform/sfx.py` (pre-rendered SFX WAV at cut positions, explicit -ar 48000 on every synthesis); `conform/vo_extract.py` (output-seeking extraction, always re-encode to AAC 48000Hz stereo, minimum 0.8s duration); `conform/audio_mix.py` (film audio + music + SFX + VO, `amix normalize=0`, stem-level loudnorm); updated conform/pipeline.py with Pass 3 + Pass 4
**Avoids:** V2-2 (amix normalize=0, stem-level loudnorm, 48000Hz resampling throughout); V2-6 (VO background bleed accepted, mitigated with conservative volume and music-lull placement; minimum 0.8s extraction; output seeking for frame accuracy); V2-8 (explicit -ar 48000 in every synthesis command; write SFX to temp file, never pipe FFmpeg to SoX); V2-10 (silence segment frame-boundary rounding to prevent A/V drift accumulation); V2-13 (path escaping extended to all audio filter graph arguments)

### Phase Ordering Rationale

- **Persistence first:** Phase 1 has zero external dependencies and high ROI for immediate pain relief; all other phases benefit from crash-safe resume
- **Structure before audio:** Zone assignments (Phases 2-3) determine which clips appear and where; audio features (Phases 4-5) dress those decisions rather than override them
- **Music before mixing:** SFX and VO (Phase 5) need a music bed to duck against and a BPM grid to time transitions — Phase 4 must deliver both first
- **CUDA isolation maintained throughout:** TextEngine (Phase 2) and LlavaEngine (Phase 3) never run concurrently; GPU_LOCK covers the inter-stage gap; nvidia-smi polling built in Phase 2 before any model swap occurs in production
- **Testable deliverable per phase:** Phase 1 = improved v1.0 output with resume; Phase 3 = zone-ordered output; Phase 4 = music-backed output; Phase 5 = full sensory-layer output

### Research Flags

Phases needing deeper research during planning:
- **Phase 5 (Audio Mix):** FFmpeg filtergraph parameter tuning — duck_ratio, sidechaincompress attack/release, and VO-to-music volume ratios are specified as ranges but require empirical validation against real film audio. Flag these as implementation-time tuning items.
- **Phase 2 (Structural LLM):** Mistral 7B v0.3 prompt engineering for reliable JSON zone-boundary output needs validation against real subtitle corpora of varying film lengths and pacing before the chunking strategy (50-100 events/call) can be considered confirmed.

Phases with standard patterns (safe to skip research-phase):
- **Phase 1 (Persistence):** Atomic file I/O with schema versioning is an established pattern; checkpoint.py is a direct reference implementation
- **Phase 3 (Zone Matching):** sentence-transformers all-MiniLM-L6-v2 is well-documented; cosine similarity zone assignment is a standard embedding application
- **Phase 4 (BPM Grid):** librosa beat_track API is stable; the edge case handling (0 BPM guard, octave correction) is fully specified in PITFALLS.md with no implementation ambiguity

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All libraries verified against PyPI and official docs; CUDA 11.4 compatibility matrix fully documented; CPU PyTorch install order constraint verified against PyTorch forum discussion |
| Features | MEDIUM-HIGH | Table stakes and ordering confirmed by TRAILDREAMS 2025 peer-reviewed research and professional trailer editor sources (Derek Lieu); audio treatment parameters from multiple production sources |
| Architecture | HIGH | Stage ordering derived directly from codebase reading; manifest schema additions are straightforward Pydantic; TextEngine pattern mirrors proven LlavaEngine |
| Pitfalls | MEDIUM-HIGH | FFmpeg and LLM pitfalls verified via official docs and WebSearch; CUDA memory deallocation timing is training-data confidence only (not independently verifiable without hardware access) |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **FFmpeg audio filtergraph parameter tuning:** duck_ratio, sidechaincompress attack/release ms, and VO-to-music volume ratios are specified as ranges from production sources but will require empirical iteration against real film audio. Not a planning blocker — handle as implementation-time validation.
- **Mistral 7B v0.3 zone-tagging prompt reliability:** The structural analysis prompt is designed in STACK.md but untested against real subtitle corpora on the actual hardware. Validate the chunking strategy (50-100 events/call) and JSON output reliability before building Phase 3 downstream features on top of it.
- **Jamendo API client_id registration:** Requires a free developer account at developer.jamendo.com before Phase 4 integration testing can run end-to-end. Not a code blocker but must be completed before Phase 4 test execution.
- **SoX system availability:** Verify with `sox --version` before Phase 5 begins. If SoX is absent, FFmpeg-only synthesis fallback is fully documented in STACK.md for all SFX types.
- **VO background score bleed:** Accepted as an inherent limitation of single-channel audio extraction. Perceptual acceptability of the mitigation (lower VO volume, placement during music lulls) will only be known after end-to-end testing with real film audio.

## Sources

### Primary (HIGH confidence)
- `/home/adamh/ai-video-trailer/src/cinecut/` — existing codebase, read directly for architecture baseline
- [librosa 0.11.0 official docs](https://librosa.org/doc/main/generated/librosa.beat.beat_track.html) — beat_track API, edge cases, trim=False behavior
- [Jamendo API v3](https://developer.jamendo.com/v3.0) — track search, audiodownload field, CC licensing, zip_allowed filter
- [sentence-transformers sbert.net](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) — CPU fallback behavior, all-MiniLM-L6-v2 model card
- [Hugging Face bartowski/Mistral-7B-Instruct-v0.3-GGUF](https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF) — VRAM size confirmation (~4.37 GB Q4_K_M)
- [FFmpeg Filters Documentation](https://ffmpeg.org/ffmpeg-filters.html) — sidechaincompress, amix, adelay, aevalsrc, afade, loudnorm
- [PyTorch CUDA 11.4 compatibility](https://discuss.pytorch.org/t/which-pytorch-version-2-0-1-support-cuda-11-4/190446) — confirms CUDA 11.4 / Kepler dropped from PyTorch 2.x prebuilt wheels

### Secondary (MEDIUM confidence)
- TRAILDREAMS (2025) peer-reviewed research — LLM-driven trailer generation confirming two-stage zone classification approach
- Derek Lieu professional trailer editor blog — three-act structure, stopdown silence technique, sound design parameters
- [llama.cpp Issue #13027](https://github.com/ggml-org/llama.cpp/issues/13027) — router mode compatibility with CUDA 11.4 unverified, justifying sequential server restarts
- Adobe Audition, iZotope production audio sources — ducking parameter ranges (-12 to -18dB, 100ms attack, 300ms release)
- [SoX synth cheat sheet](https://gist.github.com/ideoforms/d64143e2bad16b18de6e97b91de494fd) + sox man page — frequency sweep synthesis syntax
- [Freesound API documentation](https://freesound.org/docs/api/overview.html) — rate limits and OAuth2 expiry (referenced in PITFALLS.md; Jamendo chosen over Freesound)

### Tertiary (LOW confidence — training data only, not independently verified)
- CUDA 11.4 / Kepler slow VRAM deallocation timing after process exit — governs the nvidia-smi polling requirement between model swaps
- AC3/DTS to stereo downmix FFmpeg filter syntax for multi-channel VO source extraction
- llama.cpp context window sizes for text-only 7B models in Q4_K_M quantization

---
*Research completed: 2026-02-28*
*Ready for roadmap: yes*
