---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Structural & Sensory Overhaul
status: unknown
last_updated: "2026-02-28T17:28:52.490Z"
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 11
  completed_plans: 7
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-28)

**Core value:** Given a feature film and its subtitle file, produce a narratively coherent, vibe-styled trailer that a human editor would be proud to show.
**Current focus:** v2.0 Phase 9 — Music Selection (Jamendo API integration)

## Current Position

Phase: 9 of 10 (BPM Grid and Music Bed) — IN PROGRESS
Plan: 2 of 3 in current phase — COMPLETE
Status: Phase 9 Plan 02 complete — assembly/music.py with Jamendo fetch and permanent per-vibe cache
Last activity: 2026-02-28 — Phase 9 Plan 02 executed — MusicBed dataclass, fetch_music_for_vibe, 18-vibe mapping; librosa+soundfile added to pyproject.toml; 176 tests pass

Progress: [████░░░░░░] 55% (v2.0 milestone — 6/11 plans complete)

## Performance Metrics

**Velocity (v1.0 baseline):**
- Total plans completed: 17
- Average duration: ~2 min
- Total execution time: ~0.57 hours

**By Phase (v1.0):**

| Phase | Plans | Avg/Plan |
|-------|-------|----------|
| 01 Ingestion | 5 | 2 min |
| 02 Manifest/Vibes | 3 | 2 min |
| 03 LLaVA Inference | 3 | 2 min |
| 04 Beat Extraction | 2 | 2 min |
| 05 Assembly | 4 | 2 min |

**v2.0 metrics:**

| Phase | Plans | Avg/Plan |
|-------|-------|----------|
| 06 Inference Persistence | 1 | 3 min |
| 07 Structural Analysis | 2/3 | 7.5 min |
| 08 Zone Matching | 2/2 | 15 min |
| 09 Music Bed | 1/3 | 2 min |
| Phase 09 P01 | 193 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting v2.0 work:

- [Roadmap v2.0]: Phase 6 built first — zero external deps, highest ROI (eliminates 30-60min re-inference on crash)
- [Roadmap v2.0]: STRC-02 (zone assignment) split across Phase 7 (schema/anchors) and Phase 8 (matching logic) — anchors must exist before matching can run
- [Roadmap v2.0]: sentence-transformers must install CPU PyTorch wheel first (`--index-url https://download.pytorch.org/whl/cpu`) to prevent CUDA wheel selection incompatible with K6000
- [Roadmap v2.0]: TextEngine (Phase 7) uses port 8090; LlavaEngine uses port 8089 — never run concurrently; nvidia-smi VRAM polling required between model swaps
- [Roadmap v2.0]: amix normalize=0 is mandatory throughout audio mix — normalize=1 destroys ducking ratios; stem-level loudnorm before mixing
- [Phase 6-01]: Cache stored in work_dir/<stem>.scenedesc.msgpack — lifecycle tied to work dir; deleting work dir clears cache
- [Phase 6-01]: Invalidation on mtime OR size change — either difference triggers cache miss and inference re-run
- [Phase 6-01]: Cascade reset (remove narrative+assembly from stages_complete) only on cache miss — prevents Stage 5 stale keyframe issue
- [Phase 6-01]: msgpack.unpackb(raw=False, strict_map_key=False) required — avoids KeyError on bytes keys
- [Phase 7-01]: TextEngine uses port 8090 and -c 8192 (8k context for structural analysis chunks), never --mmproj
- [Phase 7-01]: wait_for_vram() called before GPU_LOCK.acquire() in TextEngine.__enter__ — handles async VRAM reclaim between model swaps
- [Phase 7-01]: cli.py --model/--mmproj default=None resolved at runtime inside main() via get_models_dir() — avoids hardcoded path at import time
- [Phase 07-02]: _clamp_anchors_to_chunk uses +-10s tolerance window to prevent hallucinated LLM timestamps from polluting median aggregation
- [Phase 07-02]: Inline import of StructuralAnchors in structural.py avoids circular import between inference and manifest packages
- [Phase 07-02]: statistics.median aggregation across subtitle chunks — single valid chunk passes through, multiple chunks produce true median for robustness
- [Phase 08-01]: util exposed as module-level None attribute in zone_matching.py — set by _load_model() — so tests can patch without sentence-transformers installed
- [Phase 08-01]: NarrativeZone(str, Enum) ensures Pydantic v2 serializes as plain string; ClipEntry.narrative_zone defaults None for backward compat with v1.0 manifests
- [Phase 08-02]: test_no_clip_overlap rewritten to per-clip validity check — zone-first ordering breaks chronological adjacency assumption; resolve_overlaps still guarantees non-overlapping pre-sort windows
- [Phase 08-02]: TestManifestGeneration tests patch cinecut.narrative.generator.run_zone_matching with position-based mock — sentence-transformers not installed in dev environment; mock returns correct-length zones list
- [Phase 09-02]: audiodownload_allowed=True filter required before selecting Jamendo track (April 2022 API change — False results return 404)
- [Phase 09-02]: soundfile>=0.12.1 pinned for MP3 support via bundled libsndfile 1.1.0+; without it librosa.load() on .mp3 raises LibsndfileError
- [Phase 09-02]: MusicBed runtime dataclass intentionally separate from manifest/schema.py MusicBed Pydantic model; Plan 03 converts between them
- [Phase 09-01]: BpmGrid exists in two forms: assembly/bpm.py dataclass (carries full beat_times_s list for computation) and manifest/schema.py Pydantic model (stores only bpm+beat_count+source for JSON manifest). No cross-import between packages.
- [Phase 09-01]: resolve_bpm() uses 0.7x vibe_min threshold for half-tempo guard and 1.4x vibe_max for double-tempo guard — matches RESEARCH.md Pattern 2 tolerances

### Pending Todos

None.

### Blockers/Concerns

- [Phase 7]: Mistral 7B v0.3 Q4_K_M GGUF (~4.37 GB) must be downloaded to ~/models before Phase 7 integration tests can run end-to-end
- [Phase 9]: Jamendo API client_id registration required (free developer account at developer.jamendo.com) before Phase 9 integration testing
- [Phase 10]: SoX availability — verify `sox --version` before Phase 10; FFmpeg-only fallback documented in research if absent
- [Phase 10]: FFmpeg audio filtergraph parameter tuning (duck_ratio, sidechaincompress attack/release, VO-to-music volume) requires empirical validation against real film audio — treat as implementation-time iteration

## Session Continuity

Last session: 2026-02-28
Stopped at: Phase 9 Plan 02 complete — assembly/music.py with Jamendo API fetch, permanent per-vibe cache, graceful None; librosa and soundfile added to pyproject.toml; 176 tests pass
Resume file: None
