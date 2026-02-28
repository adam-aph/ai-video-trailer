# Architecture Patterns

**Domain:** AI-driven video trailer generation pipeline (CLI tool)
**Project:** CineCut AI — v2.0 Structural & Sensory Overhaul
**Researched:** 2026-02-28
**Scope:** Integration of v2.0 features into the existing 7-stage pipeline

---

## Existing Architecture Baseline (v1.0)

Before mapping v2.0 integration points, the v1.0 architecture is documented here as the stable baseline.

### Current 7-Stage Pipeline

```
Stage 1: proxy_creation        — FFmpeg 420p transcode, checkpoint "proxy"
Stage 2: subtitle_parsing      — pysubs2 SRT/ASS parse, checkpoint "subtitles"
Stage 3: keyframe_extraction   — OpenCV scene detect + JPEG extraction, checkpoint "keyframes"
Stage 4: llava_inference       — llama-server HTTP, LLaVA multimodal, NO checkpoint (v1.0 gap)
Stage 5: narrative_generation  — Score + classify, write TRAILER_MANIFEST.json, checkpoint "narrative"
Stage 6: assembly              — Sort by act, enforce pacing, generate title_card.mp4 + button.mp4, checkpoint "assembly"
Stage 7: conform               — FFmpeg extract+grade each clip (lut3d + loudnorm), concat demuxer
```

### Current Module Map

```
src/cinecut/
    cli.py                      — Pipeline orchestrator and CLI entry point (Typer)
    checkpoint.py               — PipelineCheckpoint dataclass, atomic save/load
    models.py                   — DialogueEvent, KeyframeRecord dataclasses
    errors.py                   — CineCutError hierarchy
    ingestion/
        proxy.py                — FFmpeg proxy creation
        subtitles.py            — pysubs2 subtitle parser
        keyframes.py            — OpenCV scene detection + extraction
    inference/
        engine.py               — LlavaEngine context manager (llama-server lifecycle + GPU_LOCK)
        models.py               — SceneDescription dataclass + Pydantic TypeAdapter
        vram.py                 — VRAM availability check
        __init__.py             — GPU_LOCK threading.Lock definition
    narrative/
        generator.py            — run_narrative_stage() — manifest assembly pipeline
        scorer.py               — assign_act(), classify_beat(), compute_money_shot_score()
        signals.py              — RawSignals extraction, normalize_all_signals()
    manifest/
        schema.py               — ClipEntry, TrailerManifest Pydantic models (schema_version "1.0")
        loader.py               — load_manifest() with validation
        vibes.py                — VibeProfile frozen dataclass + 18 VIBE_PROFILES dict
    assembly/
        __init__.py             — assemble_manifest() orchestrator
        ordering.py             — sort_clips_by_act(), enforce_pacing_curve()
        title_card.py           — generate_title_card() via FFmpeg lavfi
    conform/
        pipeline.py             — extract_and_grade_clip(), concatenate_clips(), conform_manifest()
        luts.py                 — ensure_luts() LUT file generation
```

### Key v1.0 Constraints Relevant to v2.0

- `GPU_LOCK` (threading.Lock in `inference/__init__.py`) prevents concurrent llama-server and FFmpeg
- `LlavaEngine` starts llama-server on `__enter__`, holds GPU_LOCK for full inference duration
- `PipelineCheckpoint` uses named stage strings ("proxy", "subtitles", "keyframes", "narrative", "assembly")
- `TrailerManifest.schema_version = "1.0"` — must bump on schema change
- `VibeProfile` is a frozen dataclass — adding fields requires unfreezing or creating v2 VibeProfile
- Conform stage: `extract_and_grade_clip()` handles video + audio; no audio mixing beyond loudnorm

---

## v2.0 Feature Integration Architecture

### 1. Pipeline Stage Ordering — Where New Features Fit

The v2.0 additions require **two new stages** and **modifications to three existing stages**. The new 9-stage pipeline:

```
Stage 1: proxy_creation          [UNCHANGED]
Stage 2: subtitle_parsing        [UNCHANGED]
Stage 3: structural_analysis     [NEW] — text-only LLM via llama-server → anchors
Stage 4: keyframe_extraction     [UNCHANGED — renumbered from Stage 3]
Stage 5: llava_inference         [MODIFIED — now saves SceneDescription results]
Stage 6: scene_zone_matching     [NEW] — assign clips to BEGIN/ESCALATION/CLIMAX zones
Stage 7: narrative_generation    [MODIFIED — consumes zone assignments, non-linear ordering]
Stage 8: assembly                [MODIFIED — BPM grid, music, SFX, VO integration]
Stage 9: conform                 [MODIFIED — complex audio filtergraph]
```

**Why this ordering:**

- Stage 3 (structural analysis) runs before keyframe extraction because the anchor timestamps (BEGIN_T, ESCALATION_T, CLIMAX_T) can bias keyframe sampling toward structurally significant moments. Even if Stage 4 does not use them for extraction itself, they must exist before Stage 6.
- Stage 5 (LLaVA inference) now persists SceneDescriptions so Stage 6 can read them on resume without re-running inference.
- Stage 6 (scene-to-zone matching) depends on both LLaVA results and structural anchors — it must follow both Stage 3 and Stage 5.
- Stage 8 (assembly) now requires a music track to be resolved before BPM detection runs. Music resolution happens inside Stage 8 as a sub-step before BPM detection.
- Stage 9 (conform) receives beat timestamps and SFX timing from Stage 8 via manifest fields; the filtergraph is built there.

**Checkpoint names for new stages:**

```python
"structural_analysis"   # new Stage 3 checkpoint key
"inference"             # Stage 5 (was previously unguarded — now checkpointed)
"zone_matching"         # new Stage 6 checkpoint key
```

---

### 2. Manifest Schema Changes

`TrailerManifest` and `ClipEntry` need new fields. `schema_version` must bump to `"2.0"`.

#### New top-level fields on `TrailerManifest`

```python
class TrailerManifest(BaseModel):
    schema_version: str = "2.0"          # CHANGED from "1.0"
    source_file: str
    vibe: str
    clips: list[ClipEntry] = Field(min_length=1)

    # v2.0 additions
    structural_anchors: Optional[StructuralAnchors] = None
    music_bed: Optional[MusicBed] = None
    bpm_grid: Optional[BpmGrid] = None
    sfx_config: Optional[SfxConfig] = None
    vo_clips: list[VoClip] = Field(default_factory=list)
```

#### New sub-models

```python
class StructuralAnchors(BaseModel):
    """Timestamps marking narrative act boundaries, produced by Stage 3."""
    begin_t: float      # seconds — start of film proper (after title cards)
    escalation_t: float # seconds — first major escalation / second-act turn
    climax_t: float     # seconds — climax peak

class NarrativeZone(str, Enum):
    BEGINNING  = "beginning"
    ESCALATION = "escalation"
    CLIMAX     = "climax"

class MusicBed(BaseModel):
    track_path: str          # absolute path to audio file (WAV/MP3/FLAC)
    vibe: str                # vibe this track was selected for (audit trail)
    duration_s: float        # total track duration
    duck_threshold: float = -20.0   # dB level below which film audio triggers ducking
    duck_ratio: float = 0.25        # music volume multiplier during ducking (0.25 = -12dB)
    fade_in_s: float = 1.0
    fade_out_s: float = 2.0

class BpmGrid(BaseModel):
    bpm: float                      # detected tempo
    beat_times: list[float]         # seconds of each beat in the final trailer timeline
    downbeat_times: list[float]     # subset: first beat of each measure

class SfxConfig(BaseModel):
    swoosh_at_cuts: bool = True     # synthesize swoosh at every hard_cut boundary
    cut_times_s: list[float] = Field(default_factory=list)  # populated in Stage 8
    swoosh_duration_ms: int = 80    # length of synthesized swoosh
    swoosh_freq_start: int = 800    # Hz, sweep start
    swoosh_freq_end: int = 200      # Hz, sweep end

class VoClip(BaseModel):
    """An extracted protagonist dialogue audio clip."""
    source_start_s: float
    source_end_s: float
    dialogue_text: str
    audio_path: str             # path to extracted WAV in work_dir/vo/
    insert_at_clip_index: int   # which ClipEntry this VO plays over
```

#### Modified `ClipEntry` fields

```python
class ClipEntry(BaseModel):
    # ... all existing v1.0 fields unchanged ...

    # v2.0 additions
    narrative_zone: Optional[NarrativeZone] = None
    # "beginning" | "escalation" | "climax" — set by Stage 6 (scene-to-zone matching)
    # Used by Stage 7 ordering: sort by zone first, then by narrative signal within zone

    beat_aligned_start: Optional[float] = None
    # If non-None, conform stage should align clip start to this beat timestamp
    # (snapping source_start_s to nearest beat in the trailer output timeline)
```

#### Schema version gating

`manifest/loader.py` must be updated to accept both `"1.0"` and `"2.0"` manifests. Manifests without `narrative_zone` on clips default to `None` (backward-compatible). The `--manifest` flag path must handle this gracefully.

---

### 3. SceneDescription Persistence — Save/Load Interface

**Problem:** Stage 5 (LLaVA inference) runs 30-60 minutes and produces `list[tuple[KeyframeRecord, SceneDescription | None]]` that is currently discarded after Stage 5 completes. Resume after failure re-runs the entire inference stage.

**Solution:** Persist results to `work_dir/inference_cache.json` atomically after all frames process, keyed by `frame_path`.

#### Interface

```python
# inference/cache.py  (NEW MODULE)

def save_inference_cache(
    results: list[tuple[KeyframeRecord, SceneDescription | None]],
    work_dir: Path,
) -> None:
    """Atomically write inference results to work_dir/inference_cache.json.

    Format: dict[frame_path_str, SceneDescription_dict | null]
    Uses same atomic tempfile + os.replace() pattern as checkpoint.py.
    """

def load_inference_cache(
    work_dir: Path,
) -> dict[str, SceneDescription | None] | None:
    """Load cached inference results. Returns None if cache missing or corrupt.

    Returns dict keyed by frame_path (absolute str) → SceneDescription or None.
    """

def build_results_from_cache(
    records: list[KeyframeRecord],
    cache: dict[str, SceneDescription | None],
) -> list[tuple[KeyframeRecord, SceneDescription | None]]:
    """Reconstruct inference result list from cache + current keyframe records.

    Any record not in cache (e.g., new keyframes after partial run) gets None.
    """
```

#### Where in the pipeline

In `cli.py`, Stage 5 logic becomes:

```python
# Stage 5: LLaVA Inference
cache = load_inference_cache(work_dir)
if cache is not None and not ckpt.is_stage_complete("inference"):
    # Partial run: cache exists but stage not marked complete
    # Treat as complete to avoid re-running
    inference_results = build_results_from_cache(keyframe_records, cache)
    ckpt.inference_complete = True
    ckpt.mark_stage_complete("inference")
    save_checkpoint(ckpt, work_dir)
elif not ckpt.is_stage_complete("inference"):
    # Fresh run: no cache
    inference_results = run_inference_stage(...)
    save_inference_cache(inference_results, work_dir)   # atomic write
    ckpt.mark_stage_complete("inference")
    save_checkpoint(ckpt, work_dir)
else:
    # Already complete: load from cache for downstream stages
    cache = load_inference_cache(work_dir)
    inference_results = build_results_from_cache(keyframe_records, cache)
```

#### JSON format for `inference_cache.json`

```json
{
  "schema_version": "1.0",
  "frame_count": 247,
  "results": {
    "/path/to/work/keyframes/frame_0001.jpg": {
      "visual_content": "...",
      "mood": "...",
      "action": "...",
      "setting": "..."
    },
    "/path/to/work/keyframes/frame_0002.jpg": null
  }
}
```

`SceneDescription` is a stdlib dataclass — serialize via `dataclasses.asdict()`, deserialize via `validate_scene_description()`. No new Pydantic model needed.

---

### 4. Music Mixing in FFmpeg — Conform Stage Filtergraph

The conform stage must change from per-clip extraction + concat demuxer to a **single-pass complex filtergraph** that mixes four audio layers:

1. **Film audio** — extracted from source at clip timestamps (as today)
2. **Music bed** — royalty-free track, ducked under film audio
3. **SFX layer** — synthesized swoosh tones, placed at each hard cut
4. **VO clips** — protagonist dialogue audio at subtitle timestamps

#### Architecture decision: two-pass vs single-pass

**Recommended: two-pass approach** — extract individual clips first (existing behavior), then compose audio mix as a separate FFmpeg call against the pre-extracted clips.

Reason: Building a single mega-filtergraph that seeks into a 2-hour source file at 25 different timestamps simultaneously is fragile and hard to debug. The existing extract-then-concat approach is proven. The audio layering is a post-process step on the already-assembled video.

#### New conform sequence

```
Pass 1 (unchanged): extract_and_grade_clip() for each ClipEntry → work_dir/conform_clips/clip_NNNx.mp4
Pass 2 (unchanged): concatenate_clips() → work_dir/trailer_raw.mp4 (video + film audio)
Pass 3 (NEW):       audio_mix_pass() → final_trailer.mp4 (adds music + SFX + VO over raw trailer)
```

#### Pass 3 filtergraph architecture

```python
# conform/audio_mix.py  (NEW MODULE)

def build_audio_mix_filtergraph(
    trailer_duration_s: float,
    music_bed: MusicBed,
    sfx_config: SfxConfig,
    vo_clips: list[VoClip],
    lufs_target: float,
) -> str:
    """Build the -filter_complex string for the audio mixing pass.

    Inputs to the FFmpeg call:
      [0] trailer_raw.mp4         — video + film audio
      [1] music_bed.track_path    — music track (pre-trimmed to trailer duration)
      [2..N] vo_clip audio files  — one per VoClip in vo_clips

    Output: mixed stereo audio + original video stream.
    """
```

Filtergraph structure (pseudocode for string construction):

```
# Film audio with loudnorm already applied (Pass 1/2 handled it)
[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[film_audio];

# Music bed: trim to trailer length, fade in/out
[1:a]atrim=0:{trailer_duration_s},
     afade=t=in:st=0:d={fade_in_s},
     afade=t=out:st={fade_out_start}:d={fade_out_s},
     aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[music_raw];

# Ducking: sidechain compress music when film audio is loud
[film_audio]asplit=2[film_sc][film_mix];
[music_raw][film_sc]sidechaincompress=
    threshold=0.02:ratio=4:attack=200:release=1000[music_ducked];

# Synthesized SFX: one aevalsrc per cut point, mixed together
[sfx_stream]: generated separately via subprocess, pre-rendered to WAV
    (see SFX synthesis section below)

# VO clips: each VO is an additional input, delayed to correct position
[2:a]adelay={vo_0_delay_ms}|{vo_0_delay_ms}[vo_0];
[3:a]adelay={vo_1_delay_ms}|{vo_1_delay_ms}[vo_1];
...

# Final mix: film audio + ducked music + SFX + VO
[film_mix][music_ducked][sfx_pre_rendered][vo_0][vo_1]...
amix=inputs={N}:duration=first:normalize=0[audio_out]
```

**SFX synthesis approach:** Do not attempt to synthesize swooshes inside the filtergraph using `aevalsrc` expressions with per-beat timing — this produces filtergraphs of unbounded complexity (one node per beat). Instead:

Pre-render a single SFX audio file before the conform pass:

```python
# conform/sfx.py  (NEW MODULE)

def render_sfx_track(
    sfx_config: SfxConfig,
    trailer_duration_s: float,
    output_path: Path,
) -> Path:
    """Render a single SFX audio track (silence + swooshes at cut positions).

    Algorithm:
    1. For each cut_time in sfx_config.cut_times_s:
       - Synthesize a {swoosh_duration_ms}ms frequency sweep
         from {swoosh_freq_start}Hz to {swoosh_freq_end}Hz using:
         ffmpeg -f lavfi -i "aevalsrc=sin(2*PI*t*(800-600*t/{dur_s})):s=48000:d={dur_s}" \
                -af "volume=0.4" swoosh_{i}.wav
    2. Combine all swooshes into one SFX track at the correct offsets:
       ffmpeg -f lavfi -i "anullsrc=r=48000:cl=stereo:d={trailer_duration_s}" \
              [+ each swoosh with adelay] \
              -filter_complex "amix=inputs=N:normalize=0" sfx_track.wav
    Returns path to sfx_track.wav in work_dir/sfx/.
    """
```

This produces a single clean WAV that the audio mix pass treats as a regular input.

#### VO extraction

```python
# conform/vo_extract.py  (NEW MODULE)

def extract_vo_clip(
    source: Path,
    start_s: float,
    end_s: float,
    output_path: Path,
) -> Path:
    """Extract protagonist dialogue audio from film source.

    ffmpeg -ss {start_s} -i {source} -t {duration} -vn -c:a pcm_s16le -ar 48000 {output_path}

    Audio only (no video), 16-bit PCM WAV for clean mixing.
    Runs WITHOUT GPU_LOCK (audio extraction does not use GPU).
    """
```

VO extraction runs during Stage 8 (assembly), before the manifest is finalized. The extracted WAV paths are written into `VoClip.audio_path` fields in the manifest.

---

### 5. Model Loading Sequencing — Structural Analysis + LLaVA

The project constraint is that llama-server is the only inference backend and CUDA 11.4 stability must not be compromised. The v2.0 structural analysis (Stage 3) uses a text-only LLaMA model (not LLaVA). This requires loading a different GGUF.

#### Option A: Sequential server restarts (RECOMMENDED)

Start llama-server with the text model for Stage 3, stop it, then start it with the LLaVA model for Stage 5. The `LlavaEngine` context manager pattern already handles start/stop. A parallel `TextEngine` context manager follows the same pattern.

```python
# inference/text_engine.py  (NEW MODULE)

class TextEngine:
    """Context manager for text-only llama-server inference.

    Same pattern as LlavaEngine but without --mmproj.
    Holds GPU_LOCK for its entire lifetime.
    """
    def __init__(self, model_path: Path, port: int = 8090, ...):
        ...

    def analyze_structure(
        self,
        subtitle_text: str,
        film_duration_s: float,
    ) -> StructuralAnchors:
        """Submit full subtitle corpus to text model, return anchor timestamps.

        Prompt: "Given these subtitles from a film, identify the timestamp in seconds
        of three narrative moments: BEGIN_T (start of main story after opening),
        ESCALATION_T (first major escalation), CLIMAX_T (peak climax). Respond with JSON."

        Uses json_schema constrained generation, same as LlavaEngine.describe_frame().
        Returns StructuralAnchors Pydantic model.
        """
```

The structural analysis prompt submits the full subtitle text (condensed — timestamps + dialogue only, no ASS formatting tags). The model returns `{"begin_t": ..., "escalation_t": ..., "climax_t": ...}` as a JSON object validated via Pydantic.

**Sequencing in cli.py:**

```python
# Stage 3: Structural analysis (text LLM)
with TextEngine(text_model_path) as engine:       # acquires GPU_LOCK
    anchors = engine.analyze_structure(...)        # runs inference
# GPU_LOCK released here

# ... Stage 4: keyframe extraction (no GPU needed) ...

# Stage 5: LLaVA inference
with LlavaEngine(model_path, mmproj_path) as engine:  # acquires GPU_LOCK
    inference_results = run_inference_stage(...)
# GPU_LOCK released here
```

**No model swap API needed.** The stop/start approach adds approximately 10-15 seconds (server restart latency), which is negligible compared to the total pipeline runtime. Router mode in llama.cpp is a newer feature (post-build-8156) and its compatibility with CUDA 11.4 and the mmproj binary patch is unverified. Avoid it.

#### Option B: Router mode (NOT recommended for this project)

llama.cpp's router mode (introduced ~late 2025, PR #18228) allows multiple models in one server. However:
- Build 8156 predates this feature
- Router mode's CUDA 11.4 compatibility is unverified
- The 42-byte mmproj binary patch needed for llava-v1.5-7b compatibility may behave differently in multi-model mode
- Upgrading llama.cpp risks re-introducing the mmproj compatibility issue that required the binary patch

**Confidence:** HIGH — sequential server restarts are safe, proven, and within the existing LlavaEngine pattern.

#### New CLI flags needed

```
--text-model PATH    Path to text-only LLaMA GGUF (for structural analysis)
                     Default: None (Stage 3 skipped if not provided)
```

If `--text-model` is not provided, Stage 3 is skipped and `StructuralAnchors` are estimated heuristically (e.g., BEGIN_T = 5% into film, ESCALATION_T = 45%, CLIMAX_T = 80%).

---

### 6. BPM Detection Integration — Dependency Order

BPM detection requires a music track. The dependency chain is:

```
1. Vibe is known at CLI invocation → determines which music track to use
2. Music track is resolved at Stage 8 start (download if not cached)
3. BPM detection runs on the music track (via librosa) → produces BpmGrid
4. Beat timestamps are written into the manifest
5. Stage 9 (conform) aligns clip boundaries and places SFX using beat timestamps
```

**BPM detection does not require GPU.** It runs on CPU with the music file. It can run before or after LLaVA inference — it only needs the music file. The natural place is Stage 8 (assembly).

**Recommended library: librosa**

```python
import librosa

y, sr = librosa.load(music_path, sr=None, mono=True)
tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='time')
# beat_frames is already in seconds when units='time'
beat_times: list[float] = beat_frames.tolist()
bpm: float = float(tempo[0]) if hasattr(tempo, '__len__') else float(tempo)
```

**librosa** is preferred over aubio for this use case: batch processing (not real-time), stable API, well-documented, pure Python + numpy. librosa 0.11.0 is the current version (HIGH confidence).

**Dependency note:** librosa requires soundfile (for audio loading) and numba (optional, for JIT speedup). librosa can load MP3/WAV/FLAC via soundfile + audioread. This is a new dependency for the project.

**BPM-driven clip alignment:** After generating the BpmGrid, the assembly stage snaps each clip's intended trailer start time to the nearest beat. This is a soft snap — if no beat is within 0.3s, use the original timing. The `beat_aligned_start` field on ClipEntry stores the result.

---

### 7. New vs Modified Components

#### New modules to create

| Module | Purpose | Stage |
|--------|---------|-------|
| `inference/text_engine.py` | TextEngine context manager for structural analysis LLM | Stage 3 |
| `inference/structural.py` | analyze_structure() prompt + response parsing, StructuralAnchors model | Stage 3 |
| `inference/cache.py` | save/load inference_cache.json, build_results_from_cache() | Stage 5 |
| `narrative/zone_matching.py` | assign_zone_to_clips() — maps each clip to BEGIN/ESCALATION/CLIMAX | Stage 6 |
| `assembly/bpm.py` | detect_bpm(), build_bpm_grid(), snap_clips_to_beats() | Stage 8 |
| `assembly/music.py` | resolve_music_track() — per-vibe archive lookup + download | Stage 8 |
| `conform/audio_mix.py` | build_audio_mix_filtergraph(), audio_mix_pass() | Stage 9 |
| `conform/sfx.py` | render_sfx_track() — pre-render swoosh WAV at cut positions | Stage 9 |
| `conform/vo_extract.py` | extract_vo_clip() — pull dialogue audio from source at timestamps | Stage 8 |

#### Modified existing modules

| Module | What Changes |
|--------|-------------|
| `manifest/schema.py` | Add StructuralAnchors, MusicBed, BpmGrid, SfxConfig, VoClip models; add fields to TrailerManifest and ClipEntry; bump schema_version to "2.0" |
| `manifest/vibes.py` | Add `music_track_filename: str` field to VibeProfile for per-vibe music archive lookup |
| `manifest/loader.py` | Accept both schema_version "1.0" and "2.0"; handle missing v2.0 fields gracefully |
| `checkpoint.py` | Add new stage name fields: `structural_analysis_path`, `zone_matching_complete`, `inference_cache_path` |
| `cli.py` | Add `--text-model` flag; insert Stage 3 (structural) and Stage 6 (zone matching) into pipeline; update TOTAL_STAGES from 7 to 9; add Stage 5 checkpoint guard using inference cache |
| `narrative/generator.py` | Accept zone assignments from Stage 6; change clip ordering from chronological to zone-first + narrative-signal-within-zone |
| `assembly/__init__.py` | Add BPM detection sub-step; resolve music track; generate SFX config; trigger VO extraction; write all into manifest |
| `conform/pipeline.py` | Add Pass 3 audio mixing after concat; keep Passes 1 and 2 unchanged |
| `inference/engine.py` | No structural changes; run_inference_stage() now calls save_inference_cache() before returning |

#### Unchanged modules

- `ingestion/proxy.py` — unchanged
- `ingestion/subtitles.py` — unchanged
- `ingestion/keyframes.py` — unchanged
- `inference/models.py` — SceneDescription unchanged
- `inference/vram.py` — unchanged
- `narrative/scorer.py` — unchanged (zone_matching is a new stage, not a scorer change)
- `narrative/signals.py` — unchanged
- `assembly/ordering.py` — sort_clips_by_act() is supplemented, not replaced, by zone sorting
- `assembly/title_card.py` — unchanged
- `conform/luts.py` — unchanged
- `errors.py` — may add new error types (InferenceModelNotFoundError, MusicTrackError)
- `models.py` — DialogueEvent and KeyframeRecord unchanged

---

### 8. Component Boundaries (v2.0 Complete)

| Component | Responsibility | Inputs | Outputs | Communicates With |
|-----------|---------------|--------|---------|-------------------|
| `inference/text_engine.py` | Text LLM server lifecycle + GPU_LOCK | text model GGUF path | StructuralAnchors JSON | llama-server HTTP |
| `inference/structural.py` | Structural analysis prompt + parse | subtitle text, film duration | StructuralAnchors | text_engine |
| `inference/cache.py` | Persist + restore LLaVA results | inference result list, work_dir | inference_cache.json | inference/engine, manifest |
| `narrative/zone_matching.py` | Map clips to narrative zones | ClipEntry list, StructuralAnchors | ClipEntry list with zones | narrative/generator |
| `assembly/music.py` | Resolve vibe-specific music track | vibe name, archive dir | WAV/MP3 path | filesystem, optional HTTP |
| `assembly/bpm.py` | BPM detection + beat grid | music track path | BpmGrid | librosa |
| `conform/sfx.py` | Synthesize swoosh SFX track | SfxConfig, trailer duration | sfx_track.wav | FFmpeg subprocess |
| `conform/vo_extract.py` | Extract dialogue audio clips | source path, VoClip list | WAV files in work_dir/vo/ | FFmpeg subprocess |
| `conform/audio_mix.py` | Multi-layer audio mixing | trailer_raw.mp4, music, sfx, VO | final_trailer.mp4 | FFmpeg subprocess |

---

### 9. Data Flow — v2.0 Complete Pipeline

```
Source Video + Subtitle File + Vibe
        |
        v
Stage 1: proxy_creation
        → work_dir/proxy.mp4
        |
        v
Stage 2: subtitle_parsing
        → list[DialogueEvent]
        |
        v
Stage 3: structural_analysis (OPTIONAL — requires --text-model)
        → StructuralAnchors {begin_t, escalation_t, climax_t}
        → work_dir/structural_anchors.json
        |
        v
Stage 4: keyframe_extraction
        → list[KeyframeRecord], JPEG files in work_dir/keyframes/
        |
        v
Stage 5: llava_inference
        → list[tuple[KeyframeRecord, SceneDescription|None]]
        → work_dir/inference_cache.json  [NEW — enables resume]
        |
        v
Stage 6: scene_zone_matching
        → each KeyframeRecord annotated with NarrativeZone
        |
        v
Stage 7: narrative_generation
        → TRAILER_MANIFEST.json (schema_version "2.0")
          includes: clips with narrative_zone, StructuralAnchors
        |
Stage 8: assembly
    ├── resolve_music_track() → work_dir/music/<vibe>_track.mp3
    ├── detect_bpm() → BpmGrid, snap_clips_to_beats() → beat_aligned_start per clip
    ├── extract_vo_clips() → work_dir/vo/vo_NNN.wav
    ├── generate_title_card.mp4, button.mp4
    └── write ASSEMBLY_MANIFEST.json (includes MusicBed, BpmGrid, SfxConfig, VoClips)
        |
        v
Stage 9: conform
    ├── Pass 1: extract_and_grade_clip() × N clips → work_dir/conform_clips/clip_NNNN.mp4
    ├── Pass 2: concatenate_clips() → work_dir/trailer_raw.mp4
    ├── Pass 3: render_sfx_track() → work_dir/sfx/sfx_track.wav
    └── Pass 4: audio_mix_pass() → {source_stem}_trailer_{vibe}.mp4
```

---

### 10. Suggested Build Order for Phases

Build order follows data dependencies strictly. Each phase produces a testable deliverable.

#### Phase 1: Inference Persistence (SceneDescription cache)

**Why first:** This is a pure improvement to existing Stage 5 with no external dependencies. It fixes the most painful resume gap from v1.0. Other v2.0 features depend on inference results being available, so this foundation should be solid first.

**Delivers:**
- `inference/cache.py` (save/load/build_results_from_cache)
- `checkpoint.py` updated with `inference_cache_path`
- Stage 5 in `cli.py` wrapped with cache guard
- Tests: cache round-trip, resume simulation (delete checkpoint, keep cache)

#### Phase 2: Structural Analysis (text LLM, Stage 3)

**Why second:** Introduces TextEngine pattern, new CLI flag, new manifest fields. Does not depend on BPM/music/SFX. Stage 3 output feeds Stage 6, so it must exist before zone matching.

**Delivers:**
- `inference/text_engine.py` (TextEngine context manager)
- `inference/structural.py` (analyze_structure, StructuralAnchors)
- `manifest/schema.py` updates (StructuralAnchors, schema_version bump)
- `cli.py` Stage 3 insertion, `--text-model` flag
- Tests: TextEngine lifecycle, structural analysis prompt round-trip, fallback heuristic

#### Phase 3: Zone Matching + Non-Linear Ordering (Stage 6)

**Why third:** Depends on StructuralAnchors from Phase 2 (or heuristic fallback). Changes clip ordering semantics in Stage 7.

**Delivers:**
- `narrative/zone_matching.py` (assign_zone_to_clips)
- `manifest/schema.py` NarrativeZone enum, `narrative_zone` on ClipEntry
- `narrative/generator.py` updated to use zone-first ordering
- `cli.py` Stage 6 insertion, "zone_matching" checkpoint
- Tests: zone assignment with anchors, zone assignment with fallback heuristics, ordering output

#### Phase 4: BPM Grid + Music Bed (Stage 8 sub-features)

**Why fourth:** Pure addition to Stage 8 assembly. No changes to inference or narrative stages. Requires librosa as new dependency.

**Delivers:**
- `assembly/music.py` (resolve_music_track, per-vibe archive)
- `assembly/bpm.py` (detect_bpm, build_bpm_grid, snap_clips_to_beats)
- `manifest/schema.py` MusicBed and BpmGrid models
- `manifest/vibes.py` `music_track_filename` on VibeProfile (all 18 vibes)
- `assembly/__init__.py` updated assemble_manifest()
- Tests: BPM detection on known-tempo file, beat snap logic, music resolution fallback

#### Phase 5: SFX + VO + Audio Mix (Stage 9 conform changes)

**Why last:** Depends on BpmGrid (cut times from Phase 4), VoClip definitions (from manifest), and music track path. This is the most complex phase — the FFmpeg filtergraph must be validated end-to-end.

**Delivers:**
- `conform/sfx.py` (render_sfx_track, FFmpeg aevalsrc synthesis)
- `conform/vo_extract.py` (extract_vo_clip)
- `conform/audio_mix.py` (build_audio_mix_filtergraph, audio_mix_pass)
- `manifest/schema.py` SfxConfig and VoClip models
- `conform/pipeline.py` updated conform_manifest() with Pass 3 + Pass 4
- `cli.py` Stage 8 VO extraction sub-step
- Tests: SFX track generation (verify WAV has sound at cut positions), VO extraction, filtergraph smoke test on short fixture

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Single-Pass Mega-Filtergraph

**What goes wrong:** Building one FFmpeg command that seeks into the 2-hour source at 25 clip positions AND mixes music AND adds SFX simultaneously.

**Why bad:** Filtergraph complexity makes debugging impossible. Seeking into a 2-hour source 25 times in one command stresses FFmpeg's demuxer. Error messages point to the filtergraph, not the clip that failed.

**Instead:** Extract clips first (existing proven behavior), then apply audio mix as a separate pass on the assembled trailer.

### Anti-Pattern 2: Router Mode for Model Swapping

**What goes wrong:** Upgrading llama.cpp to use router mode to avoid server restarts between Stage 3 and Stage 5.

**Why bad:** Build 8156 is the tested stable version for CUDA 11.4 + mmproj binary patch. Router mode was introduced post-8156. Upgrading risks CUDA 11.4 instability and re-introducing the mmproj compatibility failure mode.

**Instead:** Sequential TextEngine → LlavaEngine server restarts. 10-15s overhead is negligible.

### Anti-Pattern 3: Synthesizing SFX Inline in Filtergraph

**What goes wrong:** Building one aevalsrc node per cut point inside the audio mix filtergraph (potentially 25-35 nodes for an action trailer).

**Why bad:** FFmpeg filtergraph complexity grows with each node. Filtergraph strings become 2000+ characters, hard to debug, potentially hitting FFmpeg's filter graph limit.

**Instead:** Pre-render a single SFX track WAV (silence + swoosh tones at the right offsets). This is one additional input to the mix filtergraph.

### Anti-Pattern 4: Storing Beat Timestamps Only in Memory

**What goes wrong:** Detecting BPM and producing beat_times list but only keeping it in memory (not persisting to manifest).

**Why bad:** If the conform stage fails and the pipeline resumes, BPM detection must re-run (and may produce slightly different results from librosa's non-deterministic tracker). The assembled clips may have been snapped to different beat positions.

**Instead:** Write BpmGrid to manifest immediately after BPM detection. The manifest is the source of truth for the conform stage.

### Anti-Pattern 5: Zone Matching Based Only on Timestamps

**What goes wrong:** Assigning zone purely by timestamp (e.g., first 33% = BEGINNING regardless of content).

**Why bad:** The whole point of structural analysis is to find where the story actually escalates, not where 33% of runtime falls. A film with a slow burn and late climax will have very different structural boundaries.

**Instead:** Zone assignment is a joint decision: StructuralAnchors provide the primary boundary, but individual clip's `beat_type` and `money_shot_score` can override — high-scoring climax_peak beats get CLIMAX zone regardless of timestamp.

---

## Scalability Considerations

| Concern | v1.0 Approach | v2.0 Change | Notes |
|---------|--------------|-------------|-------|
| GPU sequencing | GPU_LOCK prevents concurrent use | Now two GPU stages (Stage 3 + Stage 5) with different models | Sequential server restarts, ~10-15s overhead per swap |
| Audio processing | loudnorm only, per-clip | Multi-layer mix pass | librosa runs on CPU; FFmpeg audio mix pass adds ~20-30s |
| Music archive | Not present | Per-vibe, auto-downloaded | First run downloads ~10MB per vibe; cached thereafter |
| Manifest size | ~5-20KB | +BpmGrid, +VoClips, +SFX config | Negligible — still under 100KB |
| Stage count | 7 stages | 9 stages | Resume logic now has more granular recovery points |

---

## Sources

- Codebase: `/home/adamh/ai-video-trailer/src/cinecut/` — all modules read directly (HIGH confidence)
- librosa beat_track: [librosa 0.11.0 documentation](https://librosa.org/doc/main/generated/librosa.beat.beat_track.html) (MEDIUM confidence — docs URL confirmed, content from WebSearch)
- FFmpeg sidechaincompress: [FFmpeg Filters Documentation](https://ffmpeg.org/ffmpeg-filters.html) (HIGH confidence — official docs)
- FFmpeg adelay/amix: [FFmpeg Filters Documentation](https://ffmpeg.org/ffmpeg-filters.html) (HIGH confidence)
- FFmpeg aevalsrc: [aevalsrc examples](https://hhsprings.bitbucket.io/docs/programming/examples/ffmpeg/audio_sources/aevalsrc.html) (MEDIUM confidence)
- llama.cpp router mode (why to avoid): [HuggingFace blog: Model Management in llama.cpp](https://huggingface.co/blog/ggml-org/model-management-in-llamacpp), [GitHub Issue #13027](https://github.com/ggml-org/llama.cpp/issues/13027) (MEDIUM confidence — feature exists but build 8156 predates it)
- llama-swap alternative: [mostlygeek/llama-swap](https://github.com/mostlygeek/llama-swap) — rejected as external proxy adds unnecessary complexity

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stage ordering / dependencies | HIGH | Derived directly from reading existing code; logic is deterministic |
| Manifest schema additions | HIGH | Design decisions informed by features; Pydantic patterns well-established |
| SceneDescription cache interface | HIGH | Same atomic file pattern as existing checkpoint.py |
| FFmpeg audio mix filtergraph | MEDIUM | Filtergraph structure correct; specific param tuning (duck_ratio, attack/release) needs empirical testing |
| TextEngine + LlavaEngine sequencing | HIGH | Direct extension of existing LlavaEngine pattern |
| Router mode rejection | MEDIUM | Build 8156 predates router mode; confirmed via web search; exact compatibility untested |
| librosa BPM detection | MEDIUM | API confirmed; accuracy on non-music audio (film scores) may vary; beat snap threshold (0.3s) needs tuning |
| SFX pre-rendering approach | MEDIUM | aevalsrc frequency sweep confirmed in FFmpeg docs; exact swoosh parameter tuning empirical |
| Build order | HIGH | Each phase's dependencies are clearly traceable from the architecture |
