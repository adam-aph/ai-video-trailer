# Milestones

## v1.0 MVP (Shipped: 2026-02-27)

**Phases completed:** 5 phases, 17 plans, 0 tasks

**Key accomplishments:**
1. Full ingestion pipeline: 420p FFmpeg proxy, hybrid keyframe extraction (subtitle midpoints + scene-change + interval fallback), SRT/ASS subtitle parsing with emotion classification, and Rich CLI shell with ordered extension/existence validation
2. 18 vibe profiles with Pydantic manifest schema, programmatic LUT generation (.cube files for all vibes), FFmpeg conform pipeline with per-vibe LUFS loudnorm and lut3d filter application, and --review workflow
3. LLaVA inference engine via llama-server HTTP mode with VRAM-aware sequential processing, GPU_LOCK for strict sequentiality, and binary mmproj patch resolving llama.cpp 8156 projector_type incompatibility
4. 8-signal money shot scoring model, 7-type narrative beat classifier, and AI-driven TRAILER_MANIFEST.json generation from real inference output with full per-clip reasoning and audio/transition treatment
5. 3-act trailer assembly with vibe-driven pacing curves, atomic POSIX-safe checkpoint/resume (tempfile + os.replace), and 119 unit tests covering the full pipeline

**Delivered:** A complete local CLI tool (`cinecut`) that transforms any feature film + subtitle file into a narratively coherent, vibe-styled ~2-minute trailer using LLaVA AI analysis — fully automated with human-override via --review.

**Stats:** 78 commits | 95 files | 4,822 Python LOC | 2 days (2026-02-26 → 2026-02-27)

---


## v2.0 Structural & Sensory Overhaul (Shipped: 2026-02-28)

**Phases completed:** 5 phases, 11 plans

**Key accomplishments:**
1. **Inference persistence** (Phase 6) — msgpack SceneDescription cache eliminates 30-60 min LLaVA re-inference on pipeline resume; invalidates on source file mtime/size change
2. **Structural analysis** (Phase 7) — Mistral 7B identifies BEGIN_T/ESCALATION_T/CLIMAX_T narrative anchors from subtitle corpus via chunk-based inference; heuristic fallback (5%/45%/80% runtime) when GGUF absent; configurable models dir via `CINECUT_MODELS_DIR`
3. **Non-linear scene ordering** (Phase 8) — CPU sentence-transformers (all-MiniLM-L6-v2) cosine similarity assigns clips to BEGINNING/ESCALATION/CLIMAX zones; zone-first assembly replaces film-chronology ordering as the core narrative claim of v2.0
4. **BPM grid + music bed** (Phase 9) — librosa BPM detection with octave correction, beat-snapped clip start points; Jamendo API v3 CC-licensed music with permanent per-vibe cache; deliberate 3-5s silence segment injected at Act 2→3 boundary
5. **Synthesized SFX** (Phase 10) — FFmpeg aevalsrc linear-chirp synthesis (no external SFX files); hard-cut (0.4s) and act-boundary (1.2s) tiers overlaid via adelay timeline
6. **Four-stem audio mix** (Phase 10) — protagonist VO extraction from film audio; sidechaincompress music ducking; amix normalize=0; stem-level loudnorm at −16 LUFS; 48kHz stereo resampling throughout

**Delivered:** Full structural and sensory overhaul — trailers now have a real dramatic arc (BEGINNING→ESCALATION→CLIMAX), BPM-synced edit rhythm, CC-licensed music bed with dynamic ducking, synthesized transition SFX, and protagonist voice-over extracted from film audio.

**Stats:** 60 commits | 69 files | 5,644 Python LOC (822 added) | 207 tests | 1 day (2026-02-28)

---

