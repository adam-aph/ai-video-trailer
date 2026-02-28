# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

---

## Milestone: v1.0 — MVP

**Shipped:** 2026-02-27
**Phases:** 5 | **Plans:** 17 | **Duration:** 2 days

### What Was Built

- **7-stage ingestion-to-output pipeline** — proxy creation, hybrid keyframe extraction (subtitle midpoints + scene-change detection + interval fallback), SRT/ASS parsing, LLaVA inference, beat/manifest generation, 3-act assembly, FFmpeg conform
- **18 vibe profiles** with Pydantic manifest schema, programmatically generated .cube LUT files (NumPy transforms), LUFS audio normalization, and frame-accurate FFmpeg conform
- **LLaVA inference engine** via llama-server HTTP mode with GPU_LOCK sequential enforcement and binary mmproj patch for llama.cpp 8156 compatibility
- **8-signal money shot scorer + 7-type beat classifier** producing a structured TRAILER_MANIFEST.json with full per-clip reasoning
- **3-act assembly with pacing curves**, atomic POSIX-safe checkpoint/resume via tempfile + os.replace(), and 119 unit tests covering the full pipeline

### What Worked

- **Phase ordering**: Defining the manifest schema contract (Phase 2) before the AI that generates it (Phase 4) eliminated interface ambiguity — Phase 4 implementation never needed to guess schema shape
- **Isolation of riskiest work**: Placing LLaVA integration in its own phase (Phase 3) let the rest of the pipeline be validated with hand-crafted manifests before investing in inference
- **Gap phases (01-04, 01-05)**: Treating PATH fix and CLI validation order as explicit planned gaps rather than hotfixes kept the phase structure clean and auditable
- **Binary mmproj patch**: Resolving the projector_type incompatibility with a 42-byte patch rather than re-downloading models saved significant time and confirmed root cause understanding
- **Unit test discipline**: 119 tests across all modules means regressions are caught immediately; test_checkpoint.py and test_assembly.py exercised edge cases (corrupt checkpoints, degenerate pacing curves) not visible in manual testing

### What Was Inefficient

- **SceneDescription not persisted**: Re-running 30–60 min inference on checkpoint resume is a known v1 regression. The decision was correct for scope, but should be v2 priority #1 before any real-film testing
- **Decimal phases (01-04, 01-05) inserted retroactively**: These could have been anticipated during Phase 1 planning; PATH setup and CLI validation order are predictable requirements for any Python CLI tool
- **mmproj investigation time**: The projector_type bug required significant debugging before the binary patch approach was identified; a pre-flight model validation step in the CLI would surface this earlier

### Patterns Established

- **GPU_LOCK pattern**: A threading.Lock() in cinecut.inference controls GPU exclusivity; FFmpeg and llama-server never run concurrently. Extend this pattern to any future GPU-accelerated stage.
- **Two-pass loudnorm with 3s floor**: Clips under 3s use single-pass volume instead of loudnorm — prevents FFmpeg instability on short Act 3 montage clips. Applies to any FFmpeg audio workflow with variable-length inputs.
- **tempfile + os.replace() for atomic writes**: POSIX-atomic checkpoint persistence pattern. Use for any file that must survive power loss mid-write.
- **LlavaEngine.__new__() bypass for unit tests**: Instantiate without __enter__ to skip server startup in mocked tests. General pattern for any context manager wrapping an external process.
- **Typer validation order**: Remove exists=True from Argument/Option; use manual Path.exists() checks inside main() after extension checks. Required for Rich error panels to fire before Typer's parse-time validation.
- **pysubs2 .plaintext (not .text)**: Strips ASS override tags cleanly; same code path for SRT and ASS. Always use .plaintext for display text extraction from pysubs2.

### Key Lessons

1. **Define output contracts before the AI that produces them.** The manifest schema existing before inference made Phase 4 deterministic — the generator had a fixed target, not a moving one.
2. **Isolate the riskiest unknown (LLM integration) in its own phase.** Phase 3 being self-contained meant CUDA 11.4 / Kepler sm_35 compatibility was validated or failed without blocking anything else.
3. **Checkpoint persistence at inference boundaries pays dividends immediately.** Even in v1.0, the lack of SceneDescription persistence is already the top known regression. Inference checkpointing is the first thing to add in v2.
4. **Binary patching as a resolution strategy.** When the mmproj projector_type metadata was wrong, patching 42 bytes was faster and more surgical than re-downloading a multi-GB model. Understand root cause before defaulting to re-download.
5. **Short-clip audio instability is a real FFmpeg edge case.** Sub-3s loudnorm two-pass analysis produces invalid integrated loudness measurements. Always gate audio analysis passes on minimum clip duration.

### Cost Observations

- Model mix: quality profile (Sonnet 4.6 for planning/execution, Opus 4.6 for verification)
- Sessions: ~8 sessions across 2 days
- Notable: Phase 3 LLaVA debugging (mmproj binary patch) consumed more clock time than implementation; hardware validation is the real cost driver for ML CLI tools

---

## Milestone: v2.0 — Structural & Sensory Overhaul

**Shipped:** 2026-02-28
**Phases:** 5 (06-10) | **Plans:** 11 | **Duration:** 1 day

### What Was Built

- **Inference persistence** — msgpack SceneDescription cache; cascade checkpoint reset on cache miss; mtime/size-based invalidation. Eliminates 30-60 min LLaVA re-inference on resume.
- **Two-stage LLM structural analysis** — Mistral 7B chunk-based subtitle analysis (BEGIN_T/ESCALATION_T/CLIMAX_T); statistics.median aggregation for robustness; 5%/45%/80% heuristic fallback when GGUF absent. TextEngine on port 8090, LlavaEngine on port 8089 — never concurrent.
- **Zone-based non-linear ordering** — CPU sentence-transformers (all-MiniLM-L6-v2) cosine similarity; BEGINNING → ESCALATION → CLIMAX zone-first assembly; enforce_zone_pacing_curve trims Act 3 clips; replaces film-chronology ordering as core narrative claim.
- **BPM grid + music bed** — librosa beat detection with 4-guard octave correction; Jamendo API v3 CC-licensed tracks (audiodownload_allowed=True filter required); permanent per-vibe cache at `~/.cinecut/music/`; deliberate silence segment at Act 2→3 boundary.
- **Synthesized SFX** — FFmpeg aevalsrc linear-chirp (no external files); hard-cut (0.4s) and act-boundary (1.2s) tiers; c=stereo (not cl=stereo); adelay int milliseconds.
- **Four-stem audio mix** — protagonist VO extraction (longest-duration dialogue events; AAC 48kHz; 0.8s minimum); sidechaincompress ducking; amix normalize=0 mandatory; stem-level loudnorm at −16 LUFS; three-stem fallback (film+SFX+VO) when music absent.

### What Worked

- **v1.0 checkpoint pattern paid off immediately**: The tempfile + os.replace() atomic write pattern from v1.0 was directly reusable for msgpack cache writes in Phase 6. Same pattern, new payload.
- **Phase 6 first (inference persistence before features)**: Building the cache before any v2.0 features meant subsequent phases could iterate on real film without paying the 30-60 min re-inference tax. This was the highest-ROI decision of the milestone.
- **CPU sentence-transformers for zone matching**: The GPU-incompatible CUDA 11.4 stack was correctly anticipated; CPU inference is fast enough for clip-count workloads and the test isolation via module-level `util = None` patching is clean.
- **Two dataclass / Pydantic model split (BpmGrid, MusicBed)**: Separating runtime dataclasses (carry full computation data) from manifest Pydantic models (serializable subset) prevented circular imports between assembly and manifest packages.
- **UAT discipline**: 14-test UAT run before milestone completion caught 4 real bugs (aevalsrc pow(), non-24fps assembly, amix duration, no-VO sidechain silencing) that would have been silent regressions.

### What Was Inefficient

- **aevalsrc pow() discovery at UAT time**: The pow() function not being supported in aevalsrc should have been caught in Phase 10 unit tests — the SFX test validated file creation but not audio content. Test chirp audio output or validate FFmpeg filtergraph before commit.
- **Non-24fps source frame rate hardcoded**: The `r=24` hardcode in assembly was a latent bug from v1.0 that only surfaced when silence/title segments were inserted (Phase 9). Source frame rate should have been parameterized in Phase 5.
- **amix duration=first missing**: The four-stem amix filter needed `duration=first` to prevent the mix extending beyond the video — discovered only during UAT. Audio filter correctness benefits from end-to-end output validation, not just filtergraph string checking.

### Patterns Established

- **Port segregation for multi-model inference**: LlavaEngine (8089) and TextEngine (8090) on distinct ports with wait_for_vram() polling between swaps. Any future model addition gets its own port; never reuse.
- **audiodownload_allowed=True filter for Jamendo**: Required since April 2022 API change. Always filter third-party media APIs for explicit download permission before selection.
- **Module-level sentinel for optional-dep test isolation**: `util = None` at module level in zone_matching.py; `_load_model()` assigns real object at runtime; tests patch without needing sentence-transformers installed. Generalize for any optional ML dependency.
- **NarrativeZone as (str, Enum) for Pydantic v2**: Enum subclassing str ensures serialization as plain string, not dict. Required pattern for any enum field in Pydantic v2 manifests.
- **Three-stem fallback for graceful music degradation**: When an external API or optional feature is unavailable, maintain pipeline continuity with a reduced-stem mix rather than aborting. The fallback path should be tested explicitly.

### Key Lessons

1. **Inference caching is a prerequisite for any iterative AI pipeline.** Phase 6 should have been in v1.0 scope. Any pipeline with >2 min inference should cache before shipping.
2. **Test audio content, not just file creation.** SFX unit tests checked WAV file existence but not that the chirp was syntactically valid FFmpeg aevalsrc output. Output validation (even just `ffprobe -v error`) would have caught the pow() bug.
3. **End-to-end audio output validation needs a dedicated test path.** The four-stem mix had three separate bugs (duration, ducking, sidechain) that only surfaced in UAT. A single integration test rendering a 5s clip with all stems would have caught all three.
4. **Source frame rate is a pipeline-wide concern, not a per-stage concern.** Hardcoded `r=24` in assembly was invisible until silence injection created segments that needed a different frame rate. Parameterize frame rate from source at Stage 1 and thread through.
5. **Jamendo API has undocumented behavior changes.** The audiodownload_allowed filter was not in the v3 docs but required for reliable downloads. When integrating third-party APIs, validate against real responses, not just documented schemas.

### Cost Observations

- Model mix: Sonnet 4.6 for planning and execution
- Sessions: ~6 sessions across 1 day
- Notable: Phase 8 zone matching was the most complex phase (15 min/plan avg vs 2-3 min for others) — sentence-transformers test isolation required careful module architecture

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Days | Tests | LOC |
|-----------|--------|-------|------|-------|-----|
| v1.0 MVP  | 5      | 17    | 2    | 119   | 4,822 |
| v2.0 Overhaul | 5 | 11  | 1    | 207   | 5,644 |

### Quality Indicators

| Milestone | Req Coverage | Deviations | Known Gaps |
|-----------|-------------|------------|------------|
| v1.0 MVP  | 24/24 (100%) | Minor (auto-fixed) | SceneDescription persistence |
| v2.0 Overhaul | 26/26 (100%) | 4 UAT bugs fixed post-implementation | Audio integration test coverage |

### Recurring Patterns

- Phase ordering by contract-before-consumer is a reliable structure for AI-pipeline projects
- Hardware constraint validation should be a Phase 1 prerequisite (not Phase 3 assumption)
- Inference caching belongs in the first milestone of any AI pipeline — iterative development without it is prohibitively slow
- UAT catches audio mix bugs that unit tests miss — end-to-end rendering validation needed alongside unit coverage
