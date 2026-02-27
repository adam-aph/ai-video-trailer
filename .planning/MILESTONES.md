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

