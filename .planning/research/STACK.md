# Technology Stack

**Project:** CineCut AI -- AI-driven video trailer generator
**Researched:** 2026-02-26
**Research mode:** Ecosystem (stack dimension)
**Note on sources:** Web search and Context7 were unavailable during this research session. All recommendations are based on training knowledge (cutoff ~May 2025). Confidence levels are adjusted accordingly. Version numbers should be verified against PyPI at install time.

---

## Recommended Stack

### Runtime Environment

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.10+ | Runtime | Match/case support, modern type hints (`X | Y`), required by project spec | HIGH |
| FFmpeg | 6.x+ (system) | Video/audio processing | Industry standard, already on PATH per constraints | HIGH |
| llama-cli | System-installed | LLM inference | Hard constraint -- CUDA 11.4 compatible build already on system | HIGH |

### CLI Framework

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **Typer** | ~0.12+ | CLI interface | Built on Click, adds type-hint-driven argument parsing. Perfectly matches Python 3.10+ style. Auto-generates `--help`. Supports subcommands if needed later. Less boilerplate than Click, far more capable than argparse. | MEDIUM |
| Rich | ~13.0+ | Terminal output | Progress bars for FFmpeg operations, styled tables for manifest preview, error formatting. Typer uses it automatically when installed. | MEDIUM |

**Why Typer over alternatives:**
- **Over Click:** Typer is a thin layer on Click that leverages type annotations. Same ecosystem, less boilerplate. For a CLI like `cinecut <video> --vibe <name> [--review]`, Typer's decorator-based approach is cleaner.
- **Over argparse:** argparse requires manual argument definitions, no auto-completion, no rich help formatting. It's stdlib but the DX is poor for anything beyond trivial CLIs.
- **Over Fire:** Google's Fire auto-generates CLIs from any function, but gives less control over help text, validation, and argument types. Bad fit when CLI UX matters.

### FFmpeg Subprocess Management

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **subprocess (stdlib)** | built-in | FFmpeg process execution | Direct control over FFmpeg commands. No abstraction layer to fight. See rationale below. | HIGH |
| shlex | built-in | Command string safety | Proper quoting of file paths with spaces/special chars | HIGH |

**Why raw subprocess over ffmpeg-python:**

This is the most important stack decision for this project. Use `subprocess.run()` and `subprocess.Popen()` directly. Do NOT use `ffmpeg-python`.

Rationale:
1. **ffmpeg-python is effectively unmaintained.** The `kkroening/ffmpeg-python` repo has had minimal activity. Forks exist but fragment the ecosystem. For a project that needs precise FFmpeg flag control (frame-accurate seeking with `-ss` before `-i`, LUFS normalization, LUT application, complex filter chains), an abstraction layer adds risk without proportional benefit.
2. **CineCut needs precise FFmpeg invocations.** Frame-accurate seeking (`-ss` before `-i`), `loudnorm` filter chains, `lut3d` filter application, proxy creation with specific codec settings -- these are all easier to reason about as direct FFmpeg command strings than through a Python wrapper's API.
3. **Debugging is simpler.** When an FFmpeg command fails, you want to see the exact command that was run. With subprocess, you have the command list directly. With a wrapper, you need to debug through the abstraction.
4. **The project only needs ~5-8 distinct FFmpeg command patterns** (proxy creation, frame extraction, audio analysis, audio normalization, LUT application, segment extraction, final concatenation). A thin helper function wrapping subprocess is sufficient.

**Recommended pattern:**

```python
import subprocess
import shlex
from pathlib import Path

def run_ffmpeg(args: list[str], description: str = "") -> subprocess.CompletedProcess:
    """Run an FFmpeg command with standard error handling."""
    cmd = ["ffmpeg", "-y", "-hide_banner"] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=3600,  # 1 hour max per operation
    )
    if result.returncode != 0:
        raise FFmpegError(f"FFmpeg failed ({description}): {result.stderr[-500:]}")
    return result

def run_ffprobe(args: list[str]) -> str:
    """Run ffprobe and return stdout."""
    cmd = ["ffprobe", "-v", "quiet"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    result.check_returncode()
    return result.stdout
```

For long-running operations (proxy creation, final render), use `subprocess.Popen` with real-time stderr parsing to drive Rich progress bars:

```python
def run_ffmpeg_with_progress(args: list[str], duration_seconds: float) -> None:
    """Run FFmpeg with real-time progress reporting."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-progress", "pipe:1"] + args
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
        for line in proc.stdout:
            if line.startswith("out_time_ms="):
                current_ms = int(line.split("=")[1])
                progress = current_ms / (duration_seconds * 1_000_000)
                # Update Rich progress bar here
```

### Subtitle Parsing

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **pysubs2** | ~1.7+ | SRT/ASS subtitle parsing | Handles both SRT and ASS/SSA in a single library. Clean API for iterating events, accessing timing, text content. More capable than pysrt (which is SRT-only). | MEDIUM |

**Why pysubs2 over alternatives:**
- **Over pysrt:** pysrt only handles SRT format. CineCut explicitly supports ASS format too. pysubs2 handles SRT, ASS, SSA, MicroDVD, and others with a unified API. Using pysrt would require a second library for ASS.
- **Over srt (PyPI):** The `srt` package is minimal and SRT-only. Same problem as pysrt.
- **Over regex parsing:** Subtitle formats have edge cases (styling tags in ASS, multi-line SRT entries, BOM markers). A library handles these correctly.

**Usage pattern for narrative extraction:**

```python
import pysubs2

subs = pysubs2.load("film.srt")  # or .ass -- auto-detected
for event in subs:
    start_seconds = event.start / 1000  # pysubs2 uses milliseconds
    end_seconds = event.end / 1000
    text = event.plaintext  # strips ASS styling tags
    # Feed to narrative analysis
```

### JSON Manifest Validation

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **Pydantic** | ~2.6+ | Manifest schema & validation | Type-safe models, automatic JSON serialization/deserialization, clear error messages. The `TRAILER_MANIFEST.json` is the central pipeline artifact -- it must be rigorously validated. | MEDIUM |

**Why Pydantic over alternatives:**
- **Over jsonschema:** jsonschema validates against JSON Schema specs but doesn't give you Python objects. Pydantic gives you validated Python dataclasses that serialize to/from JSON. For a manifest that both AI generates and Python code consumes, Pydantic is the right abstraction.
- **Over dataclasses + json:** No validation, no type coercion, poor error messages when the LLM generates slightly wrong JSON.
- **Over attrs:** attrs is excellent but Pydantic has first-class JSON support (`model.model_dump_json()`, `Model.model_validate_json()`). Since the manifest IS JSON, Pydantic's JSON ergonomics win.

**Pydantic v2 is the target.** Pydantic v2 (rewritten with Rust core) is significantly faster than v1 and has been stable since mid-2023. Do not use Pydantic v1.

**CUDA note:** Pydantic is pure Python + Rust extension. No CUDA dependency.

**Manifest model sketch:**

```python
from pydantic import BaseModel, Field
from enum import Enum

class VibeProfile(str, Enum):
    ACTION = "action"
    HORROR = "horror"
    # ... 18 vibes

class ClipDecision(BaseModel):
    start_time: float = Field(ge=0, description="Start time in seconds")
    end_time: float = Field(gt=0, description="End time in seconds")
    narrative_role: str = Field(description="e.g. 'inciting_incident', 'climax', 'money_shot'")
    dialogue: str | None = Field(default=None, description="Associated subtitle text")
    confidence: float = Field(ge=0, le=1)

class TrailerManifest(BaseModel):
    source_file: str
    vibe: VibeProfile
    target_duration: float = Field(default=120.0)
    clips: list[ClipDecision]
    audio_treatment: dict
    lut_file: str
```

### Keyframe Extraction / Scene Detection

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **FFmpeg scene filter** | (via FFmpeg) | Scene change detection | `select='gt(scene,0.3)'` filter detects scene boundaries natively. No Python library needed. Avoids loading video frames into Python memory. | HIGH |
| **PySceneDetect** | ~0.6+ | Advanced scene detection (optional) | If FFmpeg's scene filter is insufficient, PySceneDetect offers content-aware and threshold-based detection. Uses OpenCV under the hood. | LOW |

**Recommended approach: FFmpeg-native scene detection.**

The Quadro K6000's 12GB VRAM is shared between LLaVA inference and FFmpeg. Loading frames into Python via OpenCV (which PySceneDetect requires) adds unnecessary memory pressure. FFmpeg can do scene detection directly:

```bash
# Extract frames at scene changes
ffmpeg -i proxy.mp4 -vf "select='gt(scene,0.3)',showinfo" -vsync vfr frame_%04d.jpg

# Get scene change timestamps without extracting frames
ffmpeg -i proxy.mp4 -vf "select='gt(scene,0.3)',showinfo" -f null - 2>&1 | grep showinfo
```

**Strategy for CineCut:** Use a hybrid approach:
1. **Subtitle-driven keyframes (primary):** Extract one frame per subtitle event at the midpoint timestamp. These are the frames that matter for narrative analysis.
2. **Scene-change supplementary:** Use FFmpeg scene filter to detect major visual transitions between subtitle events. These catch "money shot" visual moments that have no dialogue.
3. **Interval fallback:** For subtitle gaps > 30 seconds, extract frames at 10-second intervals to avoid missing long visual sequences.

This avoids PySceneDetect entirely and keeps everything in the FFmpeg + subprocess domain.

### Project Structure & Development

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **pyproject.toml** | PEP 621 | Project metadata & build | Modern Python packaging standard. Single source of truth for dependencies, scripts, and metadata. | HIGH |
| **Ruff** | ~0.4+ | Linting + formatting | Replaces flake8 + black + isort. Extremely fast (Rust-based). The Python linting standard in 2025+. | MEDIUM |
| **pytest** | ~8.0+ | Testing | Standard Python test framework. No justification needed. | HIGH |
| **pathlib (stdlib)** | built-in | Path handling | Modern path manipulation. Every file path in the project should be a `Path` object, not a string. | HIGH |

### Supporting Utilities

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| **tomli** | ~2.0+ | TOML parsing | Only if Python < 3.11 (3.11+ has `tomllib` in stdlib). For reading config files. | MEDIUM |
| **logging (stdlib)** | built-in | Structured logging | All pipeline stages should log to both console (via Rich handler) and file. | HIGH |
| **tempfile (stdlib)** | built-in | Temp directory management | Proxy files, extracted frames, intermediate clips all go in managed temp dirs. | HIGH |
| **json (stdlib)** | built-in | JSON I/O | For reading/writing manifest. Pydantic handles serialization, json handles the file I/O. | HIGH |

---

## FFmpeg Command Reference

These are the specific FFmpeg invocations CineCut will need. Documenting here because the FFmpeg flag ecosystem is vast and getting these wrong causes subtle bugs.

### Proxy Creation (420p)

```bash
ffmpeg -i source.mkv \
  -vf "scale=-2:420" \
  -c:v libx264 -preset fast -crf 28 \
  -c:a aac -b:a 128k \
  -movflags +faststart \
  proxy.mp4
```

**Key flags:**
- `scale=-2:420` -- height 420, width auto-adjusted to maintain aspect ratio (even number)
- `-crf 28` -- low quality is fine for analysis proxy
- `-preset fast` -- don't waste time on proxy encoding
- `-movflags +faststart` -- enables seeking without downloading entire file

### Frame Extraction (at specific timestamps)

```bash
# Fast extraction using -ss BEFORE -i (input seeking, not output seeking)
ffmpeg -ss 00:15:23.500 -i proxy.mp4 \
  -frames:v 1 -q:v 2 \
  frame_0001.jpg
```

**Critical:** `-ss` MUST come before `-i` for fast seeking. Placing it after `-i` causes FFmpeg to decode every frame up to the seek point.

### Audio LUFS Analysis

```bash
ffmpeg -i source.mkv -af "loudnorm=I=-14:TP=-1:LRA=11:print_format=json" -f null - 2>&1
```

This outputs JSON with measured loudness values. Parse the JSON from stderr to get `input_i`, `input_tp`, `input_lra`, `input_thresh`.

### Audio LUFS Normalization (Two-Pass)

**Pass 1 (analysis):**
```bash
ffmpeg -i source.mkv \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json" \
  -f null -
```

**Pass 2 (normalization with measured values):**
```bash
ffmpeg -i source.mkv \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=-18.2:measured_TP=-3.1:measured_LRA=8.5:measured_thresh=-28.5:linear=true" \
  -c:v copy \
  normalized.mkv
```

**LUFS targets by vibe category (recommended):**

| Vibe Category | Target LUFS (I) | True Peak (TP) | Rationale |
|---------------|-----------------|----------------|-----------|
| Action, Thriller, War, Horror | -12 | -1.0 | Loud, punchy, high energy |
| Drama, Romance, History, Mystery | -16 | -1.5 | Dialogue-forward, dynamic range preserved |
| Comedy, Family, Animation | -14 | -1.5 | Balanced, broadcast-standard |
| Documentary, Music | -14 | -1.0 | Broadcast standard |
| Sci-Fi, Fantasy, Adventure, Western, Crime | -14 | -1.0 | Balanced with headroom for effects |

### LUT Application

```bash
ffmpeg -i source.mkv \
  -vf "lut3d=file=vibe_horror.cube" \
  -c:v libx264 -crf 18 \
  -c:a copy \
  graded.mp4
```

**Key:** The `lut3d` filter reads `.cube` files directly. No conversion needed.

### Segment Extraction (Frame-Accurate)

```bash
ffmpeg -ss 00:15:23.500 -i source.mkv \
  -to 00:00:05.000 \
  -c:v libx264 -crf 18 \
  -c:a aac -b:a 192k \
  -avoid_negative_ts make_zero \
  segment_001.mp4
```

**Key flags:**
- `-ss` before `-i` for fast input seeking
- `-to` is duration relative to `-ss`, not absolute timestamp
- `-avoid_negative_ts make_zero` prevents audio sync issues at cut points

### Final Concatenation

```bash
# Using concat demuxer (file-based, most reliable)
ffmpeg -f concat -safe 0 -i segments.txt \
  -c:v libx264 -crf 18 -preset slow \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  trailer.mp4
```

Where `segments.txt` contains:
```
file 'segment_001.mp4'
file 'segment_002.mp4'
...
```

**Note:** Using the concat demuxer (not the concat filter) avoids re-encoding if segments have matching codecs. For CineCut, segments will likely need re-encoding anyway due to LUT application, so the concat demuxer with re-encode is fine.

---

## LLaMA CLI Integration

### Interface Strategy: subprocess with structured prompting

llama-cli is invoked via subprocess. No Python bindings, no IPC, no server mode. Simple command execution.

```python
def run_llama_cli(
    prompt: str,
    image_path: Path | None = None,
    max_tokens: int = 512,
) -> str:
    """Run llama-cli and return generated text."""
    cmd = [
        "llama-cli",
        "--model", str(MODEL_PATH),
        "--prompt", prompt,
        "--n-predict", str(max_tokens),
        "--temp", "0.1",  # Low temp for analytical tasks
        "--ctx-size", "2048",
        "--n-gpu-layers", "35",  # Offload to K6000
    ]
    if image_path:
        cmd.extend(["--image", str(image_path)])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    result.check_returncode()
    return result.stdout
```

**Key considerations:**
1. **VRAM management:** llama-cli loads the model into VRAM on each invocation. For batch processing (many frames), this means repeated model loading. Mitigation: batch multiple frames per invocation where possible, or investigate llama-cli's `--interactive` mode for session reuse.
2. **llama-cli server mode alternative:** `llama-server` (part of llama.cpp) runs an HTTP server. Could invoke once, then hit `http://localhost:8080/completion` for each frame. This avoids repeated model loading. Worth investigating in Phase 1 -- would be a major performance win.
3. **Structured output:** Prompt LLaVA to return JSON. Parse with Pydantic. Include retry logic for malformed JSON responses.
4. **CUDA 11.4 compatibility:** llama.cpp supports CUDA 11.4 via the `LLAMA_CUDA=1` build flag with appropriate CUDA toolkit. The system has a pre-built llama-cli, so this is already handled.

### VRAM Budget

| Process | Estimated VRAM | When |
|---------|---------------|------|
| LLaVA 7B (Q4_K_M quantized) | ~4.5 GB | During inference |
| LLaVA 13B (Q4_K_M quantized) | ~8.5 GB | During inference |
| FFmpeg (proxy creation) | ~200 MB | Before inference |
| FFmpeg (segment extraction) | ~500 MB | After inference |
| FFmpeg (LUT application) | ~300 MB | After inference |

**Recommendation:** Use LLaVA 7B (Q4_K_M) for safety margin. 13B is possible but leaves minimal headroom. The pipeline should never run LLaVA inference concurrently with heavy FFmpeg operations.

---

## LUT File Sourcing

### Free/Open LUT Sources

| Source | URL | License | Notes | Confidence |
|--------|-----|---------|-------|------------|
| **Free LUTs by Lutify.me** | lutify.me/free-luts | Free for personal/commercial | High-quality cinematic LUTs, .cube format | MEDIUM |
| **RocketStock Free LUTs** | rocketstock.com | Free download | 35 free cinematic LUTs, widely used in video community | MEDIUM |
| **Ground Control Color** | groundcontrolcolor.com | Free tier available | Film emulation LUTs (Kodak, Fuji looks) | LOW |
| **SmallHD Movie Look LUTs** | smallhd.com | Free download | Designed for film-style color grading | LOW |
| **Juan Melara Free LUTs** | juanmelara.com | Free for commercial use | ACES-based film look LUTs | LOW |
| **Generate programmatically** | N/A | N/A | Use Colour Science (Python) to generate .cube files from color transform definitions | MEDIUM |

**Recommended approach for 18 vibes:**

1. **Start with 3-4 high-quality free LUTs** that cover broad looks (warm/cool/desaturated/high-contrast)
2. **Programmatically generate variants** using the `colour-science` Python library to create .cube files with specific transforms per vibe
3. **Each vibe's LUT should encode:** contrast curve, saturation shift, color temperature, and tint

**Generating .cube files programmatically:**

```python
# colour-science can generate 3D LUT .cube files
# This avoids sourcing 18 separate third-party LUTs
import numpy as np

def generate_cube_lut(
    size: int = 33,
    contrast: float = 1.0,
    saturation: float = 1.0,
    temperature_shift: float = 0.0,  # -1 cool to +1 warm
    output_path: str = "vibe.cube",
) -> None:
    """Generate a .cube LUT file with specified color transforms."""
    # ... implementation using numpy color transforms
```

The `.cube` format is simple: a header line (`LUT_3D_SIZE 33`) followed by RGB triplets. Generating these is straightforward with NumPy -- no third-party LUT library required.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| CLI framework | Typer | Click | Typer wraps Click with less boilerplate; same ecosystem |
| CLI framework | Typer | argparse | No rich help, no auto-completion, verbose for complex CLIs |
| FFmpeg wrapper | subprocess (raw) | ffmpeg-python | Unmaintained, abstractions fight precise flag control |
| FFmpeg wrapper | subprocess (raw) | moviepy | MoviePy loads frames into Python memory -- unacceptable for full films on 12GB VRAM |
| Subtitle parser | pysubs2 | pysrt | SRT-only; CineCut needs ASS support |
| Subtitle parser | pysubs2 | regex | Edge cases in ASS styling tags, BOM handling, multi-line entries |
| JSON validation | Pydantic v2 | jsonschema | No Python object model; just validates, doesn't deserialize |
| JSON validation | Pydantic v2 | dataclasses | No validation, no JSON serialization, poor error messages |
| Scene detection | FFmpeg scene filter | PySceneDetect | Adds OpenCV dependency, loads frames into Python, extra memory pressure |
| LLM interface | subprocess | llama-cpp-python | Python bindings add complexity, may have CUDA 11.4 build issues, project constraint is llama-cli |
| LLM interface | subprocess | Ollama | Explicitly out of scope per project constraints |

---

## CUDA 11.4 Compatibility Matrix

**Hard constraint:** Quadro K6000, Driver 470.256.02, CUDA 11.4.

| Component | CUDA Relevant? | Compatible? | Notes |
|-----------|---------------|-------------|-------|
| Python 3.10+ | No | Yes | Pure language runtime |
| Typer | No | Yes | Pure Python |
| Pydantic v2 | No | Yes | Rust core, no CUDA |
| pysubs2 | No | Yes | Pure Python |
| Rich | No | Yes | Pure Python |
| Ruff | No | Yes | Rust binary, no CUDA |
| FFmpeg | GPU optional | Yes | FFmpeg NVENC/NVDEC supports Kepler (K6000). But CPU encoding is recommended for quality control. |
| llama-cli | Yes (critical) | Yes | Pre-built on system. llama.cpp supports CUDA 11.4 with `LLAMA_CUDA=1`. Kepler architecture (sm_35) is supported in CUDA 11.4. |
| PySceneDetect | Indirect (OpenCV) | Risky | OpenCV GPU builds may require newer CUDA. Avoid -- use FFmpeg scene filter instead. |
| llama-cpp-python | Yes | Risky | Building Python bindings against CUDA 11.4 can have issues. Avoid -- use subprocess to llama-cli. |
| colour-science | No | Yes | NumPy-based, no GPU dependency |

**Key risk:** Any library that builds against CUDA directly (PyTorch, OpenCV-GPU, llama-cpp-python) may have CUDA 11.4 compatibility issues. The stack deliberately avoids all such libraries by keeping GPU operations in FFmpeg and llama-cli (both pre-configured on the system).

---

## Installation

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Core dependencies
pip install typer[all] pydantic pysubs2

# Development dependencies
pip install ruff pytest

# Optional: LUT generation
pip install numpy
# pip install colour-science  # Only if programmatic LUT generation is needed
```

**pyproject.toml dependencies section:**

```toml
[project]
name = "cinecut"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "typer>=0.12,<1.0",
    "rich>=13.0,<14.0",
    "pydantic>=2.6,<3.0",
    "pysubs2>=1.7,<2.0",
]

[project.optional-dependencies]
dev = [
    "ruff>=0.4",
    "pytest>=8.0",
]

[project.scripts]
cinecut = "cinecut.cli:app"
```

**System dependencies (must be on PATH):**
- `ffmpeg` (6.x+)
- `ffprobe` (comes with FFmpeg)
- `llama-cli` (CUDA 11.4 build)

---

## What NOT to Install

| Library | Why Not |
|---------|---------|
| **ffmpeg-python** | Unmaintained, fights precise flag control, adds debugging indirection |
| **moviepy** | Loads video frames into Python memory. A 2-hour film would consume all system memory. |
| **PyTorch / transformers** | CUDA 11.4 compatibility issues. Project constraint is llama-cli, not Python-native inference. |
| **Ollama** | Explicitly out of scope per project constraints |
| **llama-cpp-python** | CUDA 11.4 build issues. Subprocess to llama-cli is simpler and already works. |
| **OpenCV (cv2)** | Heavyweight dependency for features FFmpeg handles natively (frame extraction, scene detection). GPU build has CUDA version risks. |
| **whisper / speech-to-text** | Out of scope -- user always provides subtitles |
| **pysrt** | SRT-only; pysubs2 handles both SRT and ASS |
| **dataclasses-json** | Pydantic v2 handles this better with native JSON support |

---

## Sources & Confidence

| Claim | Source | Confidence |
|-------|--------|------------|
| Typer wraps Click, supports type hints | Training data (well-established library) | MEDIUM -- verify current version on PyPI |
| pysubs2 handles SRT + ASS | Training data (stable library since 2014) | MEDIUM -- verify current version on PyPI |
| Pydantic v2 has Rust core, model_dump_json | Training data (major release mid-2023) | MEDIUM -- verify current API on PyPI |
| ffmpeg-python is unmaintained | Training data (low activity as of 2024) | LOW -- verify on GitHub |
| FFmpeg loudnorm filter syntax | Training data + FFmpeg docs (stable filter) | HIGH |
| FFmpeg lut3d filter reads .cube | Training data + FFmpeg docs (stable filter) | HIGH |
| FFmpeg scene detection filter | Training data + FFmpeg docs (stable filter) | HIGH |
| llama.cpp supports CUDA 11.4 | Training data (Kepler sm_35 supported) | MEDIUM -- verify against llama.cpp releases |
| LLaVA 7B Q4_K_M ~4.5GB VRAM | Training data (approximate, varies by context) | LOW -- measure on actual hardware |
| Free LUT sources (URLs) | Training data | LOW -- URLs may have changed; verify before downloading |
| .cube format is simple RGB triplets | Training data + widespread format spec | HIGH |

**Overall stack confidence: MEDIUM.** Core patterns (subprocess for FFmpeg, Pydantic for JSON, pysubs2 for subtitles) are well-established and unlikely to have changed. Version numbers should be verified at install time. LUT sourcing URLs are lowest confidence.
