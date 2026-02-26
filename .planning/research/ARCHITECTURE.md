# Architecture Patterns

**Domain:** AI-driven video trailer generation pipeline (CLI tool)
**Project:** CineCut AI
**Researched:** 2026-02-26

## Recommended Architecture

### High-Level Pipeline

```
                         CineCut CLI
                             |
              +--------------+--------------+
              |              |              |
         [Tier 1]       [Tier 2]       [Tier 3]
      Ingestion &    Multimodal       High-Bitrate
       Proxy Gen     Inference         Conform
              |              |              |
         420p proxy   TRAILER_       Final MP4
         + keyframes  MANIFEST.json  at source res
```

The system is a **strict sequential pipeline** with three well-defined tiers. Each tier produces artifacts that the next tier consumes. This is not a service architecture -- it is a batch processing pipeline where each stage has clear inputs, outputs, and failure modes.

### Package/Module Structure

```
cinecut/
    __init__.py              # Package version, public API
    __main__.py              # Entry point: python -m cinecut
    cli.py                   # Click/Typer CLI definition, arg parsing
    config.py                # Settings, paths, hardware detection

    pipeline/
        __init__.py
        orchestrator.py      # Pipeline coordinator, stage sequencing, resumability
        state.py             # PipelineState dataclass, checkpoint serialization

    ingest/
        __init__.py
        proxy.py             # FFmpeg proxy generation (420p transcode)
        keyframes.py         # Scene detection + keyframe extraction
        subtitles.py         # SRT/ASS parser, dialogue timeline extraction

    inference/
        __init__.py
        llava.py             # llama-cli subprocess management, prompt construction
        batching.py          # VRAM-aware batch sizing, sequential frame inference
        narrative.py         # Beat extraction (inciting incident, climax, money shots)
        manifest.py          # TRAILER_MANIFEST.json generation and validation

    conform/
        __init__.py
        render.py            # High-bitrate FFmpeg assembly from manifest
        audio.py             # LUFS normalization, audio ducking per vibe
        lut.py               # LUT application (.cube file handling)

    vibes/
        __init__.py
        profiles.py          # Vibe profile dataclass definitions
        registry.py          # Profile loader, all 18 vibes registered
        data/
            action.yaml      # Per-vibe config files
            drama.yaml
            ...              # 18 total

    ffmpeg/
        __init__.py
        runner.py            # FFmpeg subprocess execution, error handling
        builder.py           # Fluent FFmpeg command builder
        probe.py             # ffprobe wrapper for media info extraction

    models/
        __init__.py
        manifest.py          # Pydantic model: TRAILER_MANIFEST.json schema
        scene.py             # Pydantic model: scene analysis results
        timeline.py          # Pydantic model: subtitle timeline, dialogue beats
        vibe.py              # Pydantic model: vibe profile schema

    utils/
        __init__.py
        progress.py          # Rich-based progress bars and status
        tempfiles.py         # Temp directory lifecycle management
        checkpoints.py       # Pipeline checkpoint save/restore
```

**Rationale for this structure:**
- Each pipeline tier maps to a top-level package (`ingest/`, `inference/`, `conform/`).
- Cross-cutting concerns (`ffmpeg/`, `models/`, `utils/`) are separated from pipeline logic.
- Vibe profiles get their own package because they are configuration-heavy and will grow.
- The `models/` package holds all Pydantic schemas in one place -- everything serializable.
- `pipeline/orchestrator.py` is the "main loop" that sequences tier execution with checkpointing.

## Component Boundaries

| Component | Responsibility | Inputs | Outputs | Communicates With |
|-----------|---------------|--------|---------|-------------------|
| `cli` | Argument parsing, validation, user interaction | sys.argv | Validated config | orchestrator |
| `pipeline/orchestrator` | Stage sequencing, checkpoint management, `--review` pause | Config + source files | Final trailer | All pipeline stages |
| `pipeline/state` | Pipeline state serialization/deserialization | Stage results | JSON checkpoint file | orchestrator |
| `ingest/proxy` | 420p proxy transcode | Source video | proxy.mp4 | ffmpeg/runner |
| `ingest/keyframes` | Scene detection, keyframe image extraction | proxy.mp4 | keyframe PNGs + scene list | ffmpeg/runner, PySceneDetect |
| `ingest/subtitles` | SRT/ASS parsing, dialogue timeline | Subtitle file | Structured dialogue data | narrative |
| `inference/llava` | llama-cli process management | Keyframe images + prompts | JSON scene descriptions | batching |
| `inference/batching` | VRAM-aware sequential processing | Scene list | Batched inference schedule | llava |
| `inference/narrative` | Story arc detection from scenes + dialogue | Scene descriptions + dialogue | Narrative beat annotations | manifest |
| `inference/manifest` | Manifest assembly and validation | Beats + vibe profile | TRAILER_MANIFEST.json | models/manifest |
| `conform/render` | High-bitrate assembly from manifest | Manifest + source video | Final MP4 | ffmpeg/runner |
| `conform/audio` | LUFS normalization, audio treatment | Audio streams | Processed audio | ffmpeg/runner |
| `conform/lut` | LUT selection and application | Vibe profile | FFmpeg LUT filter chain | ffmpeg/builder |
| `vibes/registry` | Vibe profile lookup and validation | Vibe name string | VibeProfile object | vibes/data/*.yaml |
| `ffmpeg/runner` | Subprocess execution, error capture | FFmpeg command | Exit code + output | subprocess |
| `ffmpeg/builder` | Fluent command construction | Builder method calls | FFmpeg command list | runner |
| `ffmpeg/probe` | Media metadata extraction | File path | MediaInfo object | subprocess |
| `models/*` | Data validation and serialization | Raw data | Typed Pydantic objects | All components |

## Data Flow

### Complete Pipeline Data Flow

```
Source Video (MKV/AVI/MP4)     Subtitle File (SRT/ASS)
        |                              |
        v                              v
  [ffmpeg/probe]                [ingest/subtitles]
  MediaInfo extraction          Parse dialogue timeline
        |                              |
        v                              |
  [ingest/proxy]                       |
  420p proxy transcode                 |
        |                              |
        +----------+                   |
        |          |                   |
        v          v                   |
  [ingest/       proxy.mp4             |
   keyframes]      |                   |
  Scene detect     |                   |
  + extract        |                   |
        |          |                   |
        v          |                   v
  keyframe_001.png |          DialogueTimeline
  keyframe_002.png |          (list of timed dialogue)
  ...              |                   |
  SceneList        |                   |
        |          |                   |
        v          |                   |
  [inference/      |                   |
   batching]       |                   |
  Schedule frames  |                   |
  for VRAM budget  |                   |
        |          |                   |
        v          |                   |
  [inference/      |                   |
   llava]          |                   |
  llama-cli calls  |                   |
  per keyframe     |                   |
        |          |                   |
        v          |                   |
  SceneDescriptions|                   |
  (JSON per frame) |                   |
        |          |                   |
        +----------+-------------------+
                   |
                   v
          [inference/narrative]
          Beat extraction:
          - Inciting incident
          - Rising action
          - Climax beats
          - Money shots
                   |
                   v
          NarrativeArc (typed beats)
                   |
                   v
          [inference/manifest]
          + VibeProfile from registry
                   |
                   v
          TRAILER_MANIFEST.json
                   |
          [--review pause point]
                   |
                   v
          [conform/render]
          + [conform/audio]
          + [conform/lut]
          + Source video (original res)
                   |
                   v
          Final Trailer (MP4)
```

### Key Data Artifacts

| Artifact | Format | Stage | Persisted? | Size Estimate |
|----------|--------|-------|------------|---------------|
| MediaInfo | In-memory dataclass | probe | No | Tiny |
| Proxy video | MP4 file (420p) | ingest | Yes, temp dir | ~200-500MB |
| Scene list | In-memory list + JSON checkpoint | ingest | Checkpointed | Tiny |
| Keyframe images | PNG files | ingest | Yes, temp dir | ~50-200KB each, 100-500 total |
| Dialogue timeline | In-memory + JSON checkpoint | ingest | Checkpointed | Tiny |
| Scene descriptions | JSON per frame + aggregated | inference | Checkpointed | ~1-5KB each |
| Narrative arc | In-memory + JSON checkpoint | inference | Checkpointed | Tiny |
| Vibe profile | Loaded from YAML | inference | Bundled with package | Tiny |
| TRAILER_MANIFEST.json | JSON file | inference | Yes, output dir | ~5-20KB |
| Final trailer | MP4 file | conform | Yes, output dir | ~50-200MB |

## Patterns to Follow

### Pattern 1: Stage-Based Pipeline with Checkpointing

**What:** Each pipeline stage writes a checkpoint file upon completion. The orchestrator checks for existing checkpoints on startup and resumes from the last completed stage.

**When:** Always. This is the core execution model.

**Why:** A full pipeline run on a Quadro K6000 will take 15-60 minutes. LLaVA inference alone could be 10-30 minutes. Users should not have to restart from scratch on failure.

**Example:**

```python
# pipeline/state.py
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
import json

class PipelineStage(str, Enum):
    INIT = "init"
    PROXY_GENERATED = "proxy_generated"
    SCENES_DETECTED = "scenes_detected"
    KEYFRAMES_EXTRACTED = "keyframes_extracted"
    SUBTITLES_PARSED = "subtitles_parsed"
    INFERENCE_COMPLETE = "inference_complete"
    NARRATIVE_EXTRACTED = "narrative_extracted"
    MANIFEST_GENERATED = "manifest_generated"
    REVIEW_APPROVED = "review_approved"  # only if --review
    CONFORM_COMPLETE = "conform_complete"

@dataclass
class PipelineState:
    stage: PipelineStage = PipelineStage.INIT
    work_dir: Path | None = None
    proxy_path: Path | None = None
    keyframe_dir: Path | None = None
    manifest_path: Path | None = None
    output_path: Path | None = None
    scene_count: int = 0
    errors: list[str] = field(default_factory=list)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.__dict__, default=str, indent=2))

    @classmethod
    def load(cls, path: Path) -> "PipelineState":
        data = json.loads(path.read_text())
        data["stage"] = PipelineStage(data["stage"])
        # ... restore Path objects ...
        return cls(**data)
```

```python
# pipeline/orchestrator.py
class PipelineOrchestrator:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.state = self._load_or_init_state()

    def run(self) -> Path:
        """Execute pipeline from last checkpoint."""
        if self.state.stage < PipelineStage.PROXY_GENERATED:
            self._run_proxy_generation()

        if self.state.stage < PipelineStage.KEYFRAMES_EXTRACTED:
            self._run_keyframe_extraction()

        if self.state.stage < PipelineStage.SUBTITLES_PARSED:
            self._run_subtitle_parsing()

        if self.state.stage < PipelineStage.MANIFEST_GENERATED:
            self._run_inference_pipeline()

        if self.config.review and self.state.stage < PipelineStage.REVIEW_APPROVED:
            self._pause_for_review()

        if self.state.stage < PipelineStage.CONFORM_COMPLETE:
            self._run_conform()

        return self.state.output_path
```

### Pattern 2: Pydantic Models for All Serializable Data

**What:** Use Pydantic v2 `BaseModel` for every data structure that crosses a boundary (file I/O, stage-to-stage communication, config loading). Use Python dataclasses only for purely internal, non-serialized state.

**When:** Any data that gets written to JSON, read from YAML, or passed between pipeline stages.

**Why:** Pydantic v2 gives you validation, serialization, JSON Schema generation (useful for manifest documentation), and type safety. The manifest schema is the critical contract between inference and conform -- it must be rigorously validated.

**Example:**

```python
# models/manifest.py
from pydantic import BaseModel, Field, field_validator
from enum import Enum

class TransitionType(str, Enum):
    CUT = "cut"
    DISSOLVE = "dissolve"
    FADE_BLACK = "fade_black"
    WHIP = "whip"

class ClipEntry(BaseModel):
    clip_id: int = Field(ge=1)
    source_in: float = Field(ge=0.0, description="Start timecode in seconds")
    source_out: float = Field(gt=0.0, description="End timecode in seconds")
    narrative_beat: str = Field(description="e.g., 'inciting_incident', 'climax', 'money_shot'")
    scene_description: str = Field(description="LLaVA-generated description")
    dialogue_line: str | None = Field(default=None, description="Subtitle text if dialogue-driven clip")
    transition_in: TransitionType = TransitionType.CUT
    transition_out: TransitionType = TransitionType.CUT
    audio_level_db: float = Field(default=0.0, description="Relative audio adjustment")

    @field_validator("source_out")
    @classmethod
    def out_after_in(cls, v, info):
        if "source_in" in info.data and v <= info.data["source_in"]:
            raise ValueError("source_out must be after source_in")
        return v

class AudioSettings(BaseModel):
    target_lufs: float = Field(default=-14.0)
    dialogue_boost_db: float = Field(default=0.0)
    music_bed: str | None = Field(default=None, description="Path to music track if applicable")
    fade_in_seconds: float = Field(default=0.5)
    fade_out_seconds: float = Field(default=1.0)

class TrailerManifest(BaseModel):
    version: str = Field(default="1.0")
    vibe: str
    source_file: str
    source_duration_seconds: float
    target_duration_seconds: float = Field(default=120.0)
    lut_file: str | None = Field(default=None)
    clips: list[ClipEntry]
    audio: AudioSettings
    generated_by: str = Field(default="cinecut")
    generation_timestamp: str

    @field_validator("clips")
    @classmethod
    def clips_not_empty(cls, v):
        if not v:
            raise ValueError("Manifest must contain at least one clip")
        return v

    def total_duration(self) -> float:
        return sum(c.source_out - c.source_in for c in self.clips)
```

### Pattern 3: Fluent FFmpeg Builder

**What:** A builder pattern that constructs FFmpeg commands as structured objects, not raw string concatenation. The builder validates arguments and produces a list[str] for subprocess.

**When:** Every FFmpeg invocation. Never construct FFmpeg command strings directly.

**Why:** FFmpeg commands are complex, order-sensitive, and error-prone. String concatenation leads to injection bugs, quoting issues, and unmaintainable code. A builder provides type safety and testability.

**Note on ffmpeg-python:** The `ffmpeg-python` library (kkroening/ffmpeg-python) is an option but has been unmaintained since ~2023 and has known issues with complex filter graphs. For this project, a custom lightweight builder is better because: (a) we need precise control over `-ss` placement (before `-i` for fast seeking), (b) our FFmpeg usage patterns are well-defined, and (c) we avoid a dependency with uncertain maintenance.

**Example:**

```python
# ffmpeg/builder.py
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class FFmpegCommand:
    """Structured FFmpeg command that can be converted to subprocess args."""
    global_opts: list[str] = field(default_factory=list)
    inputs: list[tuple[list[str], str]] = field(default_factory=list)  # (options, path)
    filter_complex: str | None = None
    output_opts: list[str] = field(default_factory=list)
    output_path: str = ""

    def to_args(self) -> list[str]:
        args = ["ffmpeg"] + self.global_opts
        for opts, path in self.inputs:
            args.extend(opts)
            args.extend(["-i", path])
        if self.filter_complex:
            args.extend(["-filter_complex", self.filter_complex])
        args.extend(self.output_opts)
        if self.output_path:
            args.append(self.output_path)
        return args

class FFmpegBuilder:
    def __init__(self):
        self._cmd = FFmpegCommand()
        self._cmd.global_opts = ["-y", "-hide_banner"]

    def input(self, path: str | Path, *, seek: float | None = None,
              duration: float | None = None) -> "FFmpegBuilder":
        opts = []
        if seek is not None:
            opts.extend(["-ss", f"{seek:.3f}"])  # -ss BEFORE -i = fast seek
        if duration is not None:
            opts.extend(["-t", f"{duration:.3f}"])
        self._cmd.inputs.append((opts, str(path)))
        return self

    def video_codec(self, codec: str, **kwargs) -> "FFmpegBuilder":
        self._cmd.output_opts.extend(["-c:v", codec])
        for k, v in kwargs.items():
            self._cmd.output_opts.extend([f"-{k}", str(v)])
        return self

    def audio_codec(self, codec: str, **kwargs) -> "FFmpegBuilder":
        self._cmd.output_opts.extend(["-c:a", codec])
        for k, v in kwargs.items():
            self._cmd.output_opts.extend([f"-{k}", str(v)])
        return self

    def scale(self, width: int, height: int) -> "FFmpegBuilder":
        self._cmd.output_opts.extend(["-vf", f"scale={width}:{height}"])
        return self

    def filter_complex(self, filtergraph: str) -> "FFmpegBuilder":
        self._cmd.filter_complex = filtergraph
        return self

    def output(self, path: str | Path) -> "FFmpegBuilder":
        self._cmd.output_path = str(path)
        return self

    def build(self) -> FFmpegCommand:
        return self._cmd
```

### Pattern 4: VRAM-Aware Sequential Inference

**What:** Process keyframes one at a time through llama-cli, with explicit VRAM budget tracking. Never run concurrent llama-cli processes.

**When:** All LLaVA inference operations.

**Why:** The Quadro K6000 has exactly 12GB VRAM. LLaVA models (even quantized) consume 6-10GB VRAM. There is no room for concurrent inference. Sequential processing with a single llama-cli process per frame is the only safe approach.

**Example:**

```python
# inference/llava.py
import subprocess
import json
from pathlib import Path
from dataclasses import dataclass

@dataclass
class LlavaConfig:
    model_path: str
    mmproj_path: str  # multimodal projector
    n_gpu_layers: int = -1  # offload all to GPU
    ctx_size: int = 2048
    temperature: float = 0.1  # Low temp for consistent analysis

class LlavaRunner:
    def __init__(self, config: LlavaConfig):
        self.config = config

    def analyze_frame(self, image_path: Path, prompt: str) -> str:
        """Run llama-cli for a single keyframe. Blocks until complete."""
        cmd = [
            "llama-cli",
            "-m", self.config.model_path,
            "--mmproj", self.config.mmproj_path,
            "-ngl", str(self.config.n_gpu_layers),
            "-c", str(self.config.ctx_size),
            "--temp", str(self.config.temperature),
            "--image", str(image_path),
            "-p", prompt,
            "--no-display-prompt",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 min timeout per frame
        )
        if result.returncode != 0:
            raise LlavaInferenceError(
                f"llama-cli failed for {image_path}: {result.stderr}"
            )
        return result.stdout.strip()

    def analyze_frames_sequential(
        self, frames: list[Path], prompt_template: str,
        progress_callback=None
    ) -> list[dict]:
        """Process all frames sequentially. One llama-cli call at a time."""
        results = []
        for i, frame in enumerate(frames):
            prompt = prompt_template.format(frame_number=i + 1, total=len(frames))
            raw = self.analyze_frame(frame, prompt)
            # Parse structured output from LLaVA
            results.append(self._parse_response(raw, frame))
            if progress_callback:
                progress_callback(i + 1, len(frames))
        return results
```

### Pattern 5: Rich-Based CLI Progress

**What:** Use the `rich` library for all terminal output: progress bars, status spinners, tables, and error formatting.

**When:** All user-facing output.

**Why:** Rich is the standard for Python CLI tools. It handles terminal width, color support detection, and provides structured output. For a pipeline that takes 15-60 minutes, clear progress reporting is critical for user trust.

**Example:**

```python
# utils/progress.py
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from contextlib import contextmanager

console = Console()

@contextmanager
def pipeline_progress():
    """Context manager for multi-stage pipeline progress."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        yield progress

# Usage in orchestrator:
# with pipeline_progress() as progress:
#     task = progress.add_task("Analyzing keyframes...", total=len(frames))
#     for frame in frames:
#         analyze(frame)
#         progress.advance(task)
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Monolithic Pipeline Function

**What:** A single function or script that runs the entire pipeline with no stage boundaries.

**Why bad:** No resumability, no testability, no `--review` insertion point, impossible to debug. When LLaVA inference fails on frame 247 of 300, you lose all prior work.

**Instead:** Stage-based orchestrator with checkpointing (Pattern 1).

### Anti-Pattern 2: String-Based FFmpeg Commands

**What:** Building FFmpeg commands via f-strings or string concatenation.

```python
# BAD
cmd = f"ffmpeg -ss {seek} -i {input_path} -vf scale={w}:{h} {output}"
os.system(cmd)
```

**Why bad:** Shell injection risk, quoting bugs with paths containing spaces, no validation of argument order, impossible to test command construction separately from execution.

**Instead:** Builder pattern (Pattern 3) + `subprocess.run()` with list args.

### Anti-Pattern 3: Loading All Keyframes into Memory

**What:** Reading all extracted keyframe images into Python memory before starting inference.

**Why bad:** 300 keyframes at 420p ~= 300 * 300KB = 90MB in RAM. Not catastrophic, but pointless. llama-cli reads files from disk. Python never needs the pixel data.

**Instead:** Pass file paths only. Let llama-cli handle its own image loading.

### Anti-Pattern 4: Concurrent llama-cli Processes

**What:** Launching multiple llama-cli processes in parallel for faster inference.

**Why bad:** Each LLaVA model load consumes 6-10GB VRAM. Two concurrent processes will OOM on 12GB. Even if the first exits, VRAM may not be freed immediately.

**Instead:** Strictly sequential, one process at a time (Pattern 4).

### Anti-Pattern 5: Hardcoded Vibe Parameters

**What:** Embedding vibe profile values (cut lengths, transition styles, LUFS targets) directly in Python code.

**Why bad:** 18 vibes with multiple parameters each = unmaintainable code. Adding or tweaking a vibe requires code changes, not config changes.

**Instead:** YAML config files per vibe, loaded at runtime (see Vibe Profile Design below).

### Anti-Pattern 6: Using shell=True with subprocess

**What:** `subprocess.run(cmd_string, shell=True)`.

**Why bad:** Security risk (file paths in user input), platform-dependent behavior, harder to debug. FFmpeg commands are complex enough without adding shell interpretation issues.

**Instead:** Always `subprocess.run(cmd_list, shell=False)`.

## Vibe Profile Design

Use YAML config files loaded into Pydantic models. Not raw dataclasses (no validation), not JSON (worse readability for config), not Python code (not editable by non-developers).

```yaml
# vibes/data/action.yaml
name: action
display_name: "Action"
description: "Fast-paced, high-energy trailer with quick cuts and impact hits"

edit_profile:
  avg_cut_length_seconds: 1.5
  min_cut_length_seconds: 0.5
  max_cut_length_seconds: 4.0
  preferred_transitions:
    - cut          # weight: 0.7
    - whip         # weight: 0.2
    - fade_black   # weight: 0.1
  pacing_curve: "accelerating"  # slow start, faster toward climax

audio_profile:
  target_lufs: -12.0
  dialogue_boost_db: 3.0
  bass_boost: true
  impact_hits: true
  fade_in_seconds: 0.3
  fade_out_seconds: 0.8

visual_profile:
  lut_file: "action.cube"
  contrast_boost: 1.1
  saturation_boost: 1.05

narrative_profile:
  target_duration_seconds: 120
  preferred_beats:
    - money_shot        # weight: 0.3
    - climax            # weight: 0.25
    - action_sequence   # weight: 0.25
    - inciting_incident # weight: 0.1
    - dialogue          # weight: 0.1
  max_dialogue_clips: 4
  title_card_position: "after_first_beat"
```

```python
# models/vibe.py
from pydantic import BaseModel, Field

class EditProfile(BaseModel):
    avg_cut_length_seconds: float = Field(ge=0.3, le=10.0)
    min_cut_length_seconds: float = Field(ge=0.2, le=5.0)
    max_cut_length_seconds: float = Field(ge=1.0, le=30.0)
    preferred_transitions: list[str]
    pacing_curve: str = "linear"  # linear, accelerating, decelerating, wave

class AudioProfile(BaseModel):
    target_lufs: float = Field(ge=-24.0, le=-6.0)
    dialogue_boost_db: float = Field(ge=-6.0, le=12.0)
    bass_boost: bool = False
    impact_hits: bool = False
    fade_in_seconds: float = Field(ge=0.0, le=5.0)
    fade_out_seconds: float = Field(ge=0.0, le=5.0)

class VisualProfile(BaseModel):
    lut_file: str | None = None
    contrast_boost: float = Field(ge=0.5, le=2.0, default=1.0)
    saturation_boost: float = Field(ge=0.5, le=2.0, default=1.0)

class NarrativeProfile(BaseModel):
    target_duration_seconds: float = Field(ge=30.0, le=300.0, default=120.0)
    preferred_beats: list[str]
    max_dialogue_clips: int = Field(ge=0, le=20, default=6)
    title_card_position: str = "after_first_beat"

class VibeProfile(BaseModel):
    name: str
    display_name: str
    description: str
    edit_profile: EditProfile
    audio_profile: AudioProfile
    visual_profile: VisualProfile
    narrative_profile: NarrativeProfile
```

## Keyframe Extraction Strategy

**Recommendation: Hybrid approach -- scene change detection as primary, with minimum interval fallback.**

Use **PySceneDetect** (`scenedetect` package) for scene change detection. It is the most established Python library for this task, actively maintained, and works well with FFmpeg backends.

**Confidence:** MEDIUM -- based on training data knowledge of PySceneDetect. Version and current maintenance status should be verified.

### Strategy

1. **Primary: Content-aware scene detection** via PySceneDetect's `ContentDetector`. This finds actual shot boundaries (cuts, dissolves) based on frame-to-frame difference.

2. **Fallback: Minimum interval sampling.** If a scene runs longer than 30 seconds without a detected change (common in dialogue scenes), force-extract a keyframe at the midpoint. This ensures long scenes are still represented.

3. **Cap: Maximum keyframe count.** For a 2-hour film, unconstrained detection could yield 500-2000 scenes. Cap at 300 keyframes for practical inference time (~300 * 5 seconds = 25 minutes of LLaVA inference).

4. **Extraction: Middle frame of each scene.** Not the first frame (often black/transition). Not the last (same reason). The middle frame is most representative.

```python
# ingest/keyframes.py
from scenedetect import open_video, SceneManager, ContentDetector
from pathlib import Path

class KeyframeExtractor:
    def __init__(self, max_keyframes: int = 300, min_scene_seconds: float = 1.0,
                 max_gap_seconds: float = 30.0):
        self.max_keyframes = max_keyframes
        self.min_scene_seconds = min_scene_seconds
        self.max_gap_seconds = max_gap_seconds

    def detect_scenes(self, proxy_path: Path) -> list[tuple[float, float]]:
        """Detect scene boundaries. Returns list of (start_sec, end_sec)."""
        video = open_video(str(proxy_path))
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=27.0))
        scene_manager.detect_scenes(video)
        scenes = scene_manager.get_scene_list()

        # Convert to seconds tuples
        scene_times = [(s[0].get_seconds(), s[1].get_seconds()) for s in scenes]

        # Filter out micro-scenes
        scene_times = [(s, e) for s, e in scene_times if e - s >= self.min_scene_seconds]

        # Insert forced keyframes for long gaps
        scene_times = self._fill_gaps(scene_times)

        # Cap total count
        if len(scene_times) > self.max_keyframes:
            scene_times = self._downsample(scene_times)

        return scene_times

    def extract_keyframes(self, proxy_path: Path, scenes: list[tuple[float, float]],
                          output_dir: Path) -> list[Path]:
        """Extract middle frame of each scene as PNG."""
        output_dir.mkdir(parents=True, exist_ok=True)
        keyframes = []
        for i, (start, end) in enumerate(scenes):
            midpoint = (start + end) / 2
            output_path = output_dir / f"keyframe_{i:04d}.png"
            # Use FFmpeg for extraction (single frame)
            # ... ffmpeg builder call ...
            keyframes.append(output_path)
        return keyframes
```

## TRAILER_MANIFEST.json Schema

The manifest is the central artifact -- the contract between AI inference and deterministic FFmpeg rendering. It must be complete enough that the conform stage needs no AI reasoning.

```json
{
  "version": "1.0",
  "metadata": {
    "generated_by": "cinecut",
    "generation_timestamp": "2026-02-26T14:30:00Z",
    "source_file": "/path/to/film.mkv",
    "source_duration_seconds": 7200.0,
    "source_resolution": "1920x1080",
    "source_codec": "h264",
    "subtitle_file": "/path/to/film.srt",
    "vibe": "action",
    "model": "llava-v1.6-mistral-7b-Q4_K_M"
  },
  "target": {
    "duration_seconds": 120.0,
    "resolution": "source",
    "codec": "libx264",
    "crf": 18,
    "audio_codec": "aac",
    "audio_bitrate": "192k"
  },
  "audio": {
    "target_lufs": -12.0,
    "dialogue_boost_db": 3.0,
    "fade_in_seconds": 0.3,
    "fade_out_seconds": 0.8
  },
  "visual": {
    "lut_file": "vibes/luts/action.cube",
    "contrast_boost": 1.1,
    "saturation_boost": 1.05
  },
  "clips": [
    {
      "clip_id": 1,
      "source_in": 145.200,
      "source_out": 148.500,
      "duration": 3.3,
      "narrative_beat": "inciting_incident",
      "scene_description": "Dark alley, protagonist discovers the body, rain falling",
      "dialogue": "What happened here?",
      "transition_in": "fade_black",
      "transition_out": "cut",
      "audio_level_db": 0.0
    },
    {
      "clip_id": 2,
      "source_in": 890.100,
      "source_out": 892.600,
      "duration": 2.5,
      "narrative_beat": "money_shot",
      "scene_description": "Car explosion, wide shot, debris flying",
      "dialogue": null,
      "transition_in": "cut",
      "transition_out": "whip",
      "audio_level_db": -3.0
    }
  ],
  "clip_order_rationale": "Opening with inciting incident establishes stakes, escalating through action sequences to climax, ending on emotional resolution"
}
```

## Temp File Lifecycle

### Directory Structure

```
~/.cinecut/                     # App-level config (optional)
    config.yaml                 # Global defaults

<working_dir>/                  # Where user runs cinecut
    cinecut_work/               # Created per run, named deterministically
        <hash>/                 # Hash of source file path + mtime for dedup
            proxy/
                proxy_420p.mp4
            keyframes/
                keyframe_0001.png
                keyframe_0002.png
                ...
            inference/
                scene_0001.json
                scene_0002.json
                ...
                narrative_arc.json
            state.json          # Pipeline checkpoint
            TRAILER_MANIFEST.json
    output/
        <source_name>_<vibe>_trailer.mp4
```

### Lifecycle Rules

1. **Work directory** is created at pipeline start in the current working directory (not /tmp). Reason: /tmp may have limited space; users expect to find intermediates near their source file.

2. **Deterministic naming** via hash of source path + mtime. Running the same file again reuses the work directory (enabling resumability).

3. **Proxy video** is kept until the pipeline completes successfully. It is the largest temp file (~200-500MB) but is needed for re-extraction if inference fails.

4. **Keyframes** are kept until inference completes. After all LLaVA analysis is done, they can be deleted (but are small, so keeping them is fine for debugging).

5. **Inference JSON files** are always kept -- they are the pipeline's audit trail and enable re-running manifest generation with different vibe profiles without re-running LLaVA.

6. **Cleanup** is explicit via a `cinecut clean` subcommand, not automatic. Users may want to inspect intermediates. Default behavior: keep everything. Clean removes the `cinecut_work/` directory.

7. **The manifest** is always preserved in the output directory alongside the final trailer. It is the definitive record of what the AI decided.

## Scalability Considerations

| Concern | Current (K6000) | Future Considerations |
|---------|-----------------|----------------------|
| VRAM | 12GB, sequential inference, ~5s/frame | With more VRAM: larger context windows, batch inference possible |
| Inference time | ~25 min for 300 frames | Faster GPUs: proportionally faster. Smaller models: faster but less accurate |
| Proxy generation | ~2-5 min for 2hr film at 420p | SSD vs HDD matters more than CPU. Could skip proxy if GPU has enough VRAM for full-res decode |
| Conform/render | ~5-10 min for 2-min trailer at source res | Hardware encoding (NVENC) could cut this to <1 min. K6000 supports NVENC. |
| Keyframe count | Capped at 300 | More frames = better narrative coverage but longer inference. Diminishing returns past ~500 |
| Film length | Tested design: up to 3 hours | Longer inputs scale linearly in all stages. No algorithmic bottlenecks. |

## Suggested Build Order

The build order follows data dependencies. You cannot test a downstream component without its upstream producing real artifacts.

```
Phase 1: Foundation
    models/ (Pydantic schemas)
    ffmpeg/builder.py + ffmpeg/runner.py + ffmpeg/probe.py
    vibes/profiles.py + vibes/registry.py + vibes/data/ (YAML files)
    utils/progress.py + utils/tempfiles.py
    cli.py (skeleton with --help)

Phase 2: Tier 1 -- Ingestion
    ingest/proxy.py (FFmpeg proxy generation)
    ingest/subtitles.py (SRT/ASS parsing)
    ingest/keyframes.py (PySceneDetect + extraction)
    pipeline/state.py (checkpoint basics)
    [Testable: cinecut <video> produces proxy + keyframes + parsed subtitles]

Phase 3: Tier 2 -- Inference
    inference/llava.py (llama-cli subprocess wrapper)
    inference/batching.py (sequential frame processing)
    inference/narrative.py (beat extraction logic)
    inference/manifest.py (manifest assembly)
    pipeline/orchestrator.py (full pipeline wiring)
    [Testable: cinecut <video> --vibe action produces TRAILER_MANIFEST.json]

Phase 4: Tier 3 -- Conform
    conform/render.py (FFmpeg assembly from manifest)
    conform/audio.py (LUFS normalization)
    conform/lut.py (LUT application)
    [Testable: full pipeline produces final trailer MP4]

Phase 5: Polish
    --review flag implementation
    Error recovery and partial failure handling
    cinecut clean subcommand
    All 18 vibe profiles tuned
    LUT sourcing/creation
```

**Phase ordering rationale:**
- Models and FFmpeg utilities are the foundation everything else calls. Build and test them first.
- Tier 1 (Ingestion) produces the artifacts that Tier 2 needs. You can validate proxy quality and keyframe extraction independently.
- Tier 2 (Inference) is the riskiest phase -- LLaVA integration, prompt engineering, narrative extraction are all uncertain. Build it third so you have real proxy/keyframe data to test against.
- Tier 3 (Conform) is deterministic FFmpeg work. Once you have a valid manifest (even hand-written), this stage is straightforward to build and test.
- Polish comes last because the core loop must work before edge cases matter.

## Sources

- Project context: `/home/adamh/ai-video-trailer/.planning/PROJECT.md`
- PySceneDetect: training data knowledge (MEDIUM confidence -- library is well-established but version/API should be verified against current docs)
- Pydantic v2: training data knowledge (HIGH confidence -- well-established, widely documented)
- Rich library: training data knowledge (HIGH confidence -- standard Python CLI library)
- FFmpeg seeking behavior (`-ss` before `-i`): training data knowledge (HIGH confidence -- fundamental FFmpeg behavior, well-documented)
- llama-cli multimodal flags: training data knowledge (MEDIUM confidence -- flag names like `--mmproj` and `--image` should be verified against the installed version)
- LUFS audio normalization via FFmpeg `loudnorm` filter: training data knowledge (HIGH confidence -- standard FFmpeg filter)

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Package structure | HIGH | Standard Python packaging patterns, well-understood |
| Pipeline orchestration | HIGH | Stage-based batch processing is a well-established pattern |
| FFmpeg integration | HIGH | subprocess + builder is the standard approach |
| Pydantic for schemas | HIGH | Pydantic v2 is the de facto standard for Python data validation |
| PySceneDetect | MEDIUM | Well-known library but API details and current version should be verified |
| llama-cli integration | MEDIUM | Flag names and multimodal workflow need verification against installed version |
| Vibe profile YAML structure | HIGH | Design decision, not dependent on external factors |
| VRAM management | HIGH | Sequential processing is the only safe approach on 12GB |
| Manifest schema | HIGH | Design decision informed by FFmpeg capabilities |
| Temp file lifecycle | HIGH | Design decision, standard patterns |
