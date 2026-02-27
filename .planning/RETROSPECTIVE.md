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

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Days | Tests | LOC |
|-----------|--------|-------|------|-------|-----|
| v1.0 MVP  | 5      | 17    | 2    | 119   | 4,822 |

### Quality Indicators

| Milestone | Req Coverage | Deviations | Known Gaps |
|-----------|-------------|------------|------------|
| v1.0 MVP  | 24/24 (100%) | Minor (auto-fixed) | SceneDescription persistence |

### Recurring Patterns

- Phase ordering by contract-before-consumer is a reliable structure for AI-pipeline projects
- Hardware constraint validation should be a Phase 1 prerequisite (not Phase 3 assumption)
