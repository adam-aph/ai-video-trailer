# Project Research Summary

**Project:** CineCut AI — AI-driven video trailer generator
**Domain:** Local LLM inference pipeline + FFmpeg video processing (Python CLI)
**Researched:** 2026-02-26
**Confidence:** MEDIUM (training data only; WebSearch and Context7 unavailable)

## Executive Summary

CineCut AI is a Python CLI tool that generates professional-quality 2-minute trailers from feature films by combining LLaVA vision model inference with FFmpeg video processing. The project operates under a hard hardware constraint: an Nvidia Quadro K6000 (12GB VRAM, CUDA 11.4, Kepler architecture). Research confirms this constraint drives the entire stack — the key design principle is to keep all GPU operations inside pre-built system binaries (FFmpeg and llama-cli) and avoid any Python library that would need to compile against CUDA 11.4 directly. The recommended Python stack is minimal and conservative: Typer CLI, raw subprocess for FFmpeg/llama-cli, Pydantic v2 for the central manifest schema, and pysubs2 for subtitle parsing.

The pipeline is a strict three-tier sequential batch process: (1) Ingestion & proxy creation — FFmpeg transcodes a 420p proxy and extracts keyframes, pysubs2 parses subtitles; (2) Multimodal inference — llama-cli runs LLaVA sequentially per keyframe to generate scene descriptions, then a narrative analysis layer extracts 7 beat types and assembles `TRAILER_MANIFEST.json`; (3) High-bitrate conform — FFmpeg seeks into the original-resolution source, applies a genre-specific LUT, normalizes audio to LUFS targets, and concatenates segments. The JSON manifest is the critical decoupling artifact between inference and conform, enabling human review and re-renders without re-running inference.

The riskiest phase is LLM integration. Each llama-cli invocation reloads the model into VRAM (~4.5GB for LLaVA 7B Q4_K_M), making batch frame processing slow. Investigating `llama-server` (HTTP mode) for session reuse is a first-priority item in Phase 3. VRAM contention between llama-cli and FFmpeg hardware decoding is a critical pitfall that must be addressed at the architecture level from the start: FFmpeg must always run in CPU decode mode during analysis; GPU is reserved exclusively for inference. Timecode drift between the analysis proxy and original source is the second critical pitfall — VFR source files must be normalized to CFR at ingest and timecodes stored as PTS seconds, not frame indices.

## Key Findings

### Recommended Stack

The stack is deliberately narrow to avoid CUDA 11.4 compatibility failures. Every library that would build against CUDA (PyTorch, OpenCV-GPU, llama-cpp-python) is explicitly excluded. The pipeline relies instead on the system-installed FFmpeg and llama-cli which are already configured for the K6000.

**Core technologies:**
- **Python 3.10+** — runtime; required for `match/case`, `X | Y` type unions used throughout
- **Typer (~0.12) + Rich (~13.0)** — CLI interface with auto-generated `--help`, progress bars, and rich terminal output; Typer wraps Click with less boilerplate
- **subprocess (stdlib)** — FFmpeg and llama-cli invocation; raw subprocess chosen over `ffmpeg-python` (unmaintained) and MoviePy (loads frames into Python memory, catastrophic for 2hr films)
- **Pydantic v2 (~2.6)** — `TRAILER_MANIFEST.json` schema, validation, and serialization; v2 Rust core gives fast validation with clear error messages; v1 is not acceptable
- **pysubs2 (~1.7)** — SRT + ASS subtitle parsing; chosen over pysrt (SRT-only) and regex (edge cases in ASS styling)
- **FFmpeg (6.x, system)** — proxy creation, scene detection, frame extraction, audio analysis, normalization, LUT application, final concatenation; ~8 well-defined command patterns
- **llama-cli (system, CUDA 11.4 build)** — LLaVA vision inference; subprocess-only, no Python bindings
- **pathlib + tempfile + json + logging (stdlib)** — path handling, temp directory lifecycle, manifest I/O, structured logging
- **Ruff (~0.4) + pytest (~8.0)** — development tooling only

**What NOT to install:** `ffmpeg-python`, `moviepy`, `PyTorch`, `OpenCV`, `llama-cpp-python`, `Ollama`, `pysrt`, `PySceneDetect` (OpenCV dependency with CUDA risk).

See `.planning/research/STACK.md` for complete FFmpeg command reference, LLaMA CLI integration pattern, VRAM budget table, and pyproject.toml dependency spec.

### Expected Features

**Must have (table stakes):**
- Three-act trailer structure (Setup / Escalation / Climax+Title) — without it, output is a random clip reel
- Subtitle-driven narrative extraction (SRT + ASS) — dialogue is the densest narrative signal
- Keyframe visual analysis via LLaVA — catches action sequences and visual reveals not in dialogue
- 18 genre-specific vibe edit profiles — per-vibe pacing, transitions, LUFS targets, LUT color grading
- `TRAILER_MANIFEST.json` output — the machine-readable edit decision list; enables human review and re-render
- Frame-accurate seeking via FFmpeg `-ss` before `-i` — off-by-one-second cuts look amateur
- LUFS audio normalization per vibe — clips from different scenes have wildly different levels
- 420p proxy analysis + original-resolution conform — analyze cheap, render full quality
- Transition types: hard cut, crossfade, fade-to-black, dip-to-black — core set for 18 vibes
- Rich progress indication — pipeline runs 15-60 minutes; silent CLI = users kill the process
- Actionable error messages for FFmpeg/llama-cli failures

**Should have (differentiators):**
- 7-category narrative beat framework (World Establishment, Character Introduction, Inciting Incident, Escalation Beats, Relationship Beats, Climax Peaks, Money Shots) — expands the 3-beat skeleton to fill Act 2
- Money shot quality scoring (8-signal system: motion, contrast, saturation, uniqueness, face presence, subtitle emotional weight, subtitle silence, temporal position)
- `--review` manifest editing workflow — human-in-the-loop without re-running inference
- Pacing curve (accelerating cut lengths from Act 1 to Act 3 montage) per vibe profile
- Beat reasoning field per clip in manifest — enables meaningful human review
- Hybrid keyframe extraction (subtitle-midpoint + scene-change + interval fallback)
- Audio ducking for dialogue clips vs. visual-only clips

**Defer to v2+:**
- Music generation/selection (legal minefield, separate domain)
- Voiceover/narration TTS (quality risk, separate model)
- Real-time preview / timeline UI (contradicts CLI-first design, K6000 cannot infer + render concurrently)
- Automatic subtitle generation/STT (user always provides subtitles)
- Multi-language subtitle support (multiplies NLP complexity)
- Social media format variants / aspect ratio reframing (requires subject detection)
- Custom transition effects beyond the 4 core types (tacky if done poorly)
- Web/GUI interface (out of scope per constraints)

See `.planning/research/FEATURES.md` for the complete 3-act timing template, all 18 vibe edit profiles, money shot scoring weights, and emotional keyword dictionaries.

### Architecture Approach

CineCut uses a stage-based batch pipeline with checkpointing as its core execution model. The three-tier structure maps directly to data dependencies: proxy/subtitle artifacts must exist before inference can start, and a validated manifest must exist before conform can run. Each stage writes a checkpoint on completion; the orchestrator resumes from the last completed stage on restart, making a 45-minute pipeline survivable. The `TRAILER_MANIFEST.json` is the explicit decoupling contract between the AI inference tier and the deterministic FFmpeg conform tier.

**Major components:**
1. **`pipeline/orchestrator.py`** — stage sequencing, checkpoint management, `--review` pause point; the single "main loop"
2. **`ingest/`** — proxy transcode, keyframe extraction, subtitle parsing; produces the analysis corpus
3. **`inference/`** — llama-cli subprocess management, sequential VRAM-aware frame processing, narrative beat extraction, manifest assembly
4. **`conform/`** — high-bitrate segment extraction from original source, audio normalization, LUT application, final concatenation
5. **`ffmpeg/`** — fluent builder pattern for command construction + subprocess runner; every FFmpeg call goes through this layer
6. **`models/`** — all Pydantic schemas (manifest, scene, timeline, vibe profile); the typed contracts between components
7. **`vibes/`** — 18 YAML config files loaded into Pydantic VibeProfile models; editable without code changes

**Key patterns to follow:**
- Fluent FFmpeg builder (never string concatenation — injection/quoting bugs guaranteed)
- Pydantic v2 for all serializable data crossing stage or file I/O boundaries
- VRAM-aware sequential inference (one llama-cli process at a time, never concurrent)
- Deterministic work directory naming (hash of source path + mtime) for resumability
- Atomic manifest writes (`os.replace()` from temp file) to prevent partial corruption
- Rich progress bars threaded through pipeline from Phase 1 (not bolted on later)

See `.planning/research/ARCHITECTURE.md` for complete module tree, data flow diagram, full manifest JSON schema example, YAML vibe profile format, and temp file lifecycle rules.

### Critical Pitfalls

1. **VRAM contention between llama-cli and FFmpeg GPU decoding** — llama.cpp pre-allocates 8-10GB at startup; FFmpeg NVDEC/NVENC silently claims additional VRAM. Prevention: force FFmpeg to use CPU decode (`-hwaccel none`) for all analysis operations; pipeline must be strictly sequential with no overlap between FFmpeg operations and llama-cli. Add `nvidia-smi` VRAM check before inference. Phase: must be addressed in Phase 1 architecture.

2. **CUDA 11.4 / Kepler compatibility wall** — pre-built Python CUDA library wheels almost universally target CUDA 12+ / sm_70+. `CUDA error: no kernel image is available` is the failure mode. Prevention: use only system-installed FFmpeg and llama-cli; compile llama.cpp from source with `CMAKE_CUDA_ARCHITECTURES=35` if needed; reject all Python CUDA libraries (PyTorch, OpenCV-GPU, llama-cpp-python). Validate llama-cli runs LLaVA inference before any other work (Phase 0 blocker).

3. **Timecode drift between 420p proxy and original source** — VFR source files shift timing during CFR proxy creation; different GOP structures cause seek imprecision. Prevention: force CFR at proxy creation (`-vsync cfr`), store timecodes as PTS seconds (not frame indices), validate proxy-source alignment with spot-check thumbnails. Phase 1 proxy design decision that propagates to Phase 4 conform accuracy.

4. **llama-cli subprocess silent failures and zombie processes** — hangs on certain inputs, crashes without detection, zombie processes holding VRAM. Prevention: always use `subprocess.run()` with explicit `timeout=120`, validate output structure before proceeding, implement skip-with-warning for failed frames, never use `subprocess.Popen` without explicit cleanup. Phase 2 inference design.

5. **Audio/video sync drift in concat assembly** — AAC frame boundary misalignment accumulates across clips when using the concat demuxer with stream copy. Prevention: re-encode both audio and video (never `-c copy`) in the final conform; use the concat filter (not demuxer); normalize audio sample rate to 48000Hz per clip; verify final output audio/video duration match within 20ms. Phase 4 conform design.

Additional critical pitfalls: FFmpeg command injection via string concatenation (use builder + list args, never `shell=True`); LUT color space mismatch (design LUTs for Rec.709 input, apply at reduced intensity); subtitle encoding and malformed file edge cases (use `chardet` for encoding detection + pysubs2); keyframe disk space exhaustion (streaming extraction + temp cleanup handlers); LLaVA hallucination and inconsistent output format (minimal prompts, fixed output schema, temp=0, post-process with regex, pre-filter dark frames).

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation — FFmpeg Pipeline, CLI Shell, and Environment Validation

**Rationale:** Lowest risk, highest confidence. FFmpeg patterns are well-documented, no GPU dependencies, forms the substrate everything else runs on. CUDA validation must happen before any inference work begins.
**Delivers:** Working proxy creation, keyframe extraction, subtitle parsing, CLI entry point, progress infrastructure, FFmpeg builder/runner layer, VRAM pre-flight check
**Addresses features:** Frame-accurate seeking, progress indication, actionable error messages, SRT+ASS support, proxy tier of three-tier pipeline
**Avoids pitfalls:** Timecode drift (force CFR at proxy creation), FFmpeg injection (builder from day one), FFmpeg version check (startup validation), CLI progress (baked in, not bolted on later)
**Research flag:** Standard patterns. Skip research-phase. FFmpeg subprocess is well-documented; pyproject setup is standard Python.

### Phase 2: Manifest Schema, Vibe System, and Conform

**Rationale:** Define the contract (manifest schema) before building the AI that produces it. The conform step is deterministic FFmpeg work — once the manifest schema is stable and a valid manifest exists (even hand-crafted), this step can be built and tested independently of inference.
**Delivers:** Complete Pydantic manifest schema with validation, all 18 vibe YAML profiles with edit/audio/visual/narrative parameters, LUT file strategy (programmatic `.cube` generation or sourced), segment extraction from original source, LUFS audio normalization per vibe, LUT application, final MP4 concatenation, `--review` pause and re-run workflow
**Addresses features:** JSON manifest output, 18 vibe profiles, LUT color grading, audio normalization, `--review` workflow, transition types, title card timing
**Avoids pitfalls:** A/V sync drift (concat filter + re-encode from the start), LUT color space mismatch (Rec.709-input LUTs, blend opacity), manifest schema integrity (Pydantic validation at every read boundary, atomic writes)
**Research flag:** LUT sourcing needs investigation — programmatic `.cube` generation via NumPy vs. sourcing free cinematic LUTs. The STACK.md provides both approaches; a prototype comparison is needed.

### Phase 3: LLM Integration and Narrative Analysis

**Rationale:** The riskiest phase. Deferred until the FFmpeg pipeline produces real proxy + keyframe artifacts to test against. LLaVA integration, prompt engineering, and narrative beat extraction are the most uncertain components.
**Delivers:** llama-cli subprocess wrapper with timeouts and retry logic, VRAM-aware sequential batch processing, LLaVA scene description output with structured parsing, 7-beat narrative arc extraction algorithm, money shot scoring (8-signal system), real manifest generation from actual film inference
**Addresses features:** Keyframe visual analysis, narrative beat detection, money shot quality scoring, subtitle emotional keyword extraction, beat reasoning in manifest
**Avoids pitfalls:** VRAM contention (strictly sequential, CPU FFmpeg during inference), llama-cli zombie processes (timeout + cleanup wrapper from day one), LLaVA hallucination (minimal prompts, fixed output schema, dark frame pre-filtering), CUDA 11.4 wall (validated in Phase 0 before this phase starts)
**Research flag:** NEEDS deeper research. Key questions: (1) Is `llama-server` available in the system build? HTTP session reuse vs. per-frame subprocess is a 5-10x performance difference. (2) Which specific LLaVA GGUF model fits within VRAM budget with headroom? 7B Q4_K_M is the recommendation but needs hardware validation. (3) What prompt structure produces reliable structured output from this specific model? Requires experimentation.

### Phase 4: Narrative Assembly and End-to-End Integration

**Rationale:** Wire all three tiers together through the orchestrator with full checkpointing. The trailer assembly algorithm — selecting and sequencing clips from narrative beats according to vibe profile parameters — is a distinct algorithm that sits above individual component pieces.
**Delivers:** Three-act trailer structure assembly algorithm (timing templates per vibe), complete pipeline orchestrator with checkpoint state machine, `--review` manifest editing + re-conform workflow, end-to-end test on a real 2-hour film, performance benchmarks
**Addresses features:** Three-act structure, pacing curve, genre-aware edit pacing, beat emphasis per vibe, button/stinger timing, resumable pipeline
**Avoids pitfalls:** Monolithic pipeline (stage-based orchestrator enforced from Phase 1), memory leaks (streaming processing, incremental disk writes)
**Research flag:** Trailer assembly algorithm (clip selection from beat taxonomy, pacing curve implementation) has sparse direct documentation. May benefit from a focused research pass on trailer editing theory.

### Phase 5: Polish, Edge Cases, and Production Readiness

**Rationale:** Core loop must work end-to-end before addressing edge cases. This phase hardens the tool for real-world film inputs.
**Delivers:** Comprehensive error handling and user-facing messages, adversarial filename handling, subtitle encoding edge case hardening (`chardet` integration), `cinecut clean` subcommand, scene detection threshold configurability (`--scene-threshold`), FFmpeg version startup check, disk space pre-flight, documentation
**Addresses features:** Actionable error messages, anti-features explicitly gated (no cloud, no STT, etc.)
**Avoids pitfalls:** Subtitle parsing edge cases (encoding, overlapping cues, BOM, malformed files), disk space exhaustion (streaming + pre-flight), scene detection sensitivity (configurable threshold), FFmpeg version incompatibilities (startup validation)
**Research flag:** Standard patterns. Skip research-phase.

### Phase Ordering Rationale

- FFmpeg and manifest contract first because they have zero risk and zero ambiguity — building on uncertain ground (LLM) before the plumbing works is a trap
- Manifest schema before inference because the manifest is the producer/consumer contract; defining it late forces rework of both sides
- Conform built in Phase 2 (not Phase 4) because it is deterministic FFmpeg work that can be tested with hand-crafted manifests; deferring it conflates deterministic work with uncertain AI work
- LLM integration is isolated in Phase 3 because it is the highest-risk phase; isolation means failures here cannot corrupt the pipeline foundation
- Assembly algorithm in Phase 4 (after components exist) because it requires real inference output to validate beat selection logic
- Polish deferred to Phase 5 because edge cases cannot be enumerated without first encountering real-world inputs

### Research Flags

Phases needing deeper research during planning:
- **Phase 3 (LLM Integration):** llama-server vs. llama-cli subprocess performance on this specific hardware; LLaVA GGUF model selection for 12GB VRAM; prompt engineering for structured output from 7B model
- **Phase 2 (LUT Strategy):** Programmatic `.cube` generation quality vs. curated free LUTs; which vibes need custom vs. adapted LUTs

Phases with standard patterns (skip research-phase):
- **Phase 1 (FFmpeg Pipeline):** Well-documented FFmpeg subprocess patterns; command reference in STACK.md
- **Phase 5 (Polish):** Standard Python CLI hardening; no novel technical problems

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Core library choices (Typer, Pydantic v2, pysubs2, subprocess) are well-established and stable. Version numbers not PyPI-verified. llama.cpp CUDA 11.4 Kepler support needs hardware validation. |
| Features | MEDIUM | Feature landscape derived from film editing conventions and trailer production theory; 18 vibe profiles are opinionated starting points, not validated against actual trailers. Money shot scoring weights are estimates. |
| Architecture | MEDIUM-HIGH | Three-tier pipeline + stage checkpointing are textbook batch processing patterns. Module structure is design-driven. llama-cli integration specifics (flag names, mmproj path, multimodal workflow) need verification against installed version. |
| Pitfalls | MEDIUM | VRAM contention, CUDA compatibility, and A/V sync drift are well-documented failure modes. LLaVA prompt engineering pitfalls drawn from VLM literature. Timecode drift from real-world VFR sources is empirically documented. |

**Overall confidence:** MEDIUM

### Gaps to Address

- **llama-server availability:** Is `llama-server` present in the system's llama.cpp build? This is a Phase 3 first-day investigation. If unavailable, per-frame subprocess is the only option and pipeline timing estimates must account for repeated model loading (~30-60s per cold start).
- **LLaVA model selection:** Which GGUF model (7B vs 13B, Q4_K_M vs Q5_K_M) fits within the 12GB VRAM budget alongside FFmpeg's working memory? Needs empirical measurement on the K6000. STACK.md estimates LLaVA 7B Q4_K_M at ~4.5GB but this is approximate.
- **LUT quality validation:** Programmatic `.cube` generation via NumPy produces correct transforms mathematically but visual quality vs. professionally designed LUTs is unknown. Needs visual comparison before Phase 2 completion.
- **FFmpeg NVENC on K6000:** Does the system FFmpeg include NVENC support for Kepler (sm_35)? GPU encoding for final conform could reduce Phase 4 render time significantly but may not be available or may conflict with VRAM budget.
- **pysubs2/Typer/Pydantic exact versions:** Web search was unavailable. All version pins in STACK.md should be verified against PyPI before first `pip install`.
- **LLaVA context window with image tokens:** LLaVA 7B on a 2048-token context with CLIP-ViT-L image encoding (~576 tokens) leaves ~1472 tokens for prompt + output. Prompts must be validated to fit within this budget. Larger context (`-c 4096`) may be available but increases VRAM pressure.

## Sources

### Primary (HIGH confidence — well-established patterns)
- FFmpeg documentation — `loudnorm` filter, `lut3d` filter, scene detection filter, `-ss` seeking behavior, concat demuxer vs filter, NVDEC/NVENC flags
- Python stdlib — subprocess, pathlib, tempfile, json, logging behavior
- Pydantic v2 documentation — BaseModel, field_validator, model_dump_json API (stable since mid-2023)

### Secondary (MEDIUM confidence — training data, widely documented)
- Typer/Rich library API (well-established CLI libraries, stable API)
- pysubs2 subtitle parsing behavior (library active since 2014, SRT+ASS handling well-documented)
- PySceneDetect scene detection (referenced in ARCHITECTURE.md as optional; STACK.md recommends FFmpeg-native approach instead)
- Film trailer editing conventions (three-act structure, cut timing by genre, trailer production literature)
- llama.cpp CUDA 11.4 / sm_35 Kepler support status
- LLaVA architecture — image token count, context window constraints, VLM hallucination behavior

### Tertiary (LOW confidence — needs validation)
- LLaVA 7B Q4_K_M VRAM consumption estimate (~4.5GB) — approximate, measure on hardware
- Free LUT source URLs (lutify.me, rocketstock.com) — verify links are active before downloading
- Money shot scoring signal weights — opinionated estimates, require empirical calibration against real trailer output
- Per-vibe LUFS targets and cut duration parameters — based on genre conventions, require subjective validation

---
*Research completed: 2026-02-26*
*Ready for roadmap: yes*
