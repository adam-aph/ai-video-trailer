# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-26)

**Core value:** Given a feature film and its subtitle file, produce a narratively coherent, vibe-styled trailer that a human editor would be proud to show.
**Current focus:** Phase 1: Ingestion Pipeline and CLI Shell

## Current Position

Phase: 1 of 5 (Ingestion Pipeline and CLI Shell)
Plan: 2 of 3 in current phase
Status: In progress
Last activity: 2026-02-26 -- Completed 01-02: Core ingestion modules (subtitle parser and proxy creator)

Progress: [##........] 13%

## Performance Metrics

**Velocity:**
- Total plans completed: 2
- Average duration: 2 min
- Total execution time: 0.07 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-ingestion-pipeline-and-cli-shell | 2 | 4 min | 2 min |

**Recent Trend:**
- Last 5 plans: 2 min
- Trend: stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: EDIT-01 (manifest generation) assigned to Phase 4 (not Phase 2) because Phase 2 defines the schema and tests conform with hand-crafted manifests; Phase 4 generates real manifests from inference output
- [Roadmap]: Phase 3 depends on Phase 1 only (not Phase 2), enabling parallel development if needed -- inference engine does not require the conform pipeline
- [01-01]: stdlib dataclasses over Pydantic for ingestion-layer models -- validation overhead not needed at ingestion; Pydantic reserved for Phase 2 manifest work
- [01-01]: hatchling over setuptools -- handles src/ layout automatically, no [tool.setuptools] sections needed
- [01-01]: ProxyValidationError included beyond plan minimum -- handles FFmpeg exits 0 but produces corrupt proxy (Pitfall 3 from research)
- [01-02]: pysubs2 .plaintext property used (not .text) to strip ASS override tags cleanly, ensuring same code path for SRT and ASS
- [01-02]: charset-normalizer best() on UnicodeDecodeError; SubtitleParseError raised if best() returns None -- never use errors='ignore'
- [01-02]: FfmpegProcess wraps FFmpeg call; stderr written to log file by library, FfmpegProcessError caught and re-raised as ProxyCreationError
- [01-02]: validate_proxy() deletes corrupt proxy on failure so next create_proxy() re-encodes rather than short-circuiting idempotency check on bad file

### Pending Todos

None yet.

### Blockers/Concerns

- [Research]: CUDA 11.4 / Kepler sm_35 compatibility must be validated before Phase 3 begins -- llama-server LLaVA inference on K6000 is untested
- [Research]: LUT sourcing strategy (programmatic .cube generation vs. curated free LUTs) needs investigation during Phase 2 planning
- [Research]: llama-server availability in the system llama.cpp build is unknown -- Phase 3 first-day investigation item

## Session Continuity

Last session: 2026-02-26
Stopped at: Completed 01-02-PLAN.md -- Core ingestion modules (subtitle parser and proxy creator)
Resume file: None
