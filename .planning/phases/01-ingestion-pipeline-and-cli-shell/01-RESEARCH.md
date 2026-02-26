# Phase 1: Ingestion Pipeline and CLI Shell - Research

**Researched:** 2026-02-26
**Domain:** Python CLI tooling, FFmpeg subprocess integration, subtitle parsing, scene-change detection
**Confidence:** HIGH (core stack verified via official docs and PyPI; FFmpeg command patterns verified via official documentation and multiple sources)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PIPE-01 | User can provide MKV/AVI/MP4 source video + SRT/ASS subtitle file as inputs to the CLI | Typer Path argument with `exists=True` handles all three container formats transparently |
| PIPE-02 | System creates a 420p analysis proxy from the source video using FFmpeg before inference | FFmpeg `-vf scale=-2:420,fps=24 -vsync cfr` command pattern; `better-ffmpeg-progress` for Rich progress integration |
| PIPE-03 | System extracts keyframes using hybrid strategy: subtitle midpoints (primary), scene-change detection (supplementary), interval fallback for gaps > 30s | PySceneDetect 0.6.7.1 `ContentDetector`; FFmpeg single-frame extraction at PTS seconds; pysubs2 1.8.0 for midpoint timestamps |
| NARR-01 | System parses SRT and ASS subtitle files and extracts dialogue, timestamps, and emotional keyword classification per event | pysubs2 1.8.0 auto-detects format; `SSAEvent.start`/`.end` in milliseconds; keyword dict approach for classification |
| CLI-01 | User invokes tool as `cinecut <video_file> --subtitle <subtitle_file> --vibe <vibe_name> [--review]` | Typer `app.command()` with positional argument + Options; `[project.scripts]` entry point in pyproject.toml |
| CLI-02 | CLI provides Rich progress indicators for all long-running stages | `better-ffmpeg-progress 4.0.1` (wraps Rich); `rich.progress.Progress` context manager for non-FFmpeg stages |
| CLI-03 | CLI provides actionable error messages when FFmpeg failures occur | Wrap `subprocess.CalledProcessError`; translate stderr to human-readable messages; never surface raw stderr to user |
</phase_requirements>

---

## Summary

Phase 1 builds the foundation on which all later phases depend: a CLI entry point that accepts user inputs, an FFmpeg-based proxy creation pipeline, a keyframe extraction system using a hybrid detection strategy, and a subtitle parser that outputs structured events with emotional classification. The technical stack is a well-established Python ecosystem: Typer for CLI argument parsing, Rich for terminal progress, pysubs2 for subtitle parsing, PySceneDetect for scene-change detection, and direct FFmpeg subprocess calls for video operations.

The most critical technical decision is FFmpeg command construction for the proxy. The proxy must be CFR (constant frame rate) to ensure that PTS seconds translate reliably to frame-accurate positions later in the pipeline. Using `-vf scale=-2:420,fps=24 -vsync cfr` achieves this. Keyframe extraction must store timestamps as PTS seconds (float), never as frame indices, because the downstream LLaVA inference engine (Phase 3) and the conform pipeline (Phase 2) both operate on time-domain coordinates.

Emotional keyword classification at this phase should be a simple curated dictionary approach (no ML model dependency), producing a per-event label (`positive`, `negative`, `neutral`, `intense`, `comedic`, `romantic`) that later phases can use as input signals. Introducing a heavy NLP dependency (VADER, transformers) in Phase 1 is premature — the LLaVA inference in Phase 3 will provide richer scene analysis; Phase 1 only needs a lightweight signal.

**Primary recommendation:** Use Typer + Rich + pysubs2 + PySceneDetect + direct subprocess FFmpeg. Do not introduce ffmpeg-python (unmaintained) or moviepy (heavyweight) — raw subprocess gives full command control with no abstraction overhead.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| typer | >=0.12.0 | CLI argument parsing, entry point, Path validation | Type-hint native, integrates with Rich, first-class Optional/Path support |
| rich | >=13.0.0 | Progress bars, styled console output, error panels | De facto standard for Python CLI UX; used by better-ffmpeg-progress |
| pysubs2 | 1.8.0 | SRT and ASS subtitle file parsing | Only library that handles both formats with zero dependencies; auto-detects format |
| scenedetect | 0.6.7.1 | Scene-change detection for supplementary keyframe extraction | Production-stable; ContentDetector is proven on film content; FrameTimecode gives PTS seconds |
| better-ffmpeg-progress | 4.0.1 | FFmpeg subprocess wrapper with Rich progress integration | Parses FFmpeg stderr `time=` output; displays % complete + ETA; uses Rich by default |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib (stdlib) | 3.x | All path manipulation | Every file operation — no string path concatenation |
| subprocess (stdlib) | 3.x | FFmpeg and ffprobe invocation | For proxy creation, keyframe extraction, duration probing |
| json (stdlib) | 3.x | ffprobe JSON output parsing | Extracting video duration, stream metadata |
| dataclasses (stdlib) | 3.x | `DialogueEvent`, `KeyframeRecord` data structures | Lightweight typed containers; no validation overhead needed at ingestion |
| re (stdlib) | 3.x | Subtitle text cleaning (strip ASS tags) | pysubs2 does most work; regex needed for residual tag stripping |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| better-ffmpeg-progress | raw subprocess + manual stderr parsing | Hand-rolling `time=` regex + thread + Rich update is 60+ lines; better-ffmpeg-progress is 2 lines |
| pysubs2 | pysrt (SRT only) | pysrt cannot handle ASS files; pysubs2 handles both with identical API |
| PySceneDetect | OpenCV frame-diff loop | PySceneDetect handles VFR, codec edge cases, chunking; hand-rolling misses these |
| typer | click | Typer is built on Click; adds type hint magic and reduces boilerplate |
| dataclasses | Pydantic | Pydantic is correct for Phase 2 manifest validation; Phase 1 ingestion structs don't need validation overhead |

**Installation:**
```bash
pip install typer rich pysubs2 scenedetect[opencv-headless] better-ffmpeg-progress
```

Note: `scenedetect[opencv-headless]` is preferred over `scenedetect[opencv]` because a display is not required and opencv-headless is smaller.

---

## Architecture Patterns

### Recommended Project Structure
```
cinecut/
├── pyproject.toml              # [project.scripts] cinecut = "cinecut.cli:app"
├── src/
│   └── cinecut/
│       ├── __init__.py
│       ├── cli.py              # Typer app, argument parsing, top-level command
│       ├── ingestion/
│       │   ├── __init__.py
│       │   ├── proxy.py        # FFmpeg proxy creation (PIPE-02)
│       │   ├── keyframes.py    # Hybrid keyframe extraction (PIPE-03)
│       │   └── subtitles.py    # SRT/ASS parsing + emotion classification (NARR-01)
│       ├── models.py           # Shared dataclasses: DialogueEvent, KeyframeRecord
│       └── errors.py           # Human-readable error translation layer
└── tests/
    ├── test_proxy.py
    ├── test_keyframes.py
    └── test_subtitles.py
```

### Pattern 1: Typer CLI Entry Point with Path Validation

**What:** Define the `cinecut` command with positional video argument and `--subtitle`, `--vibe`, `--review` options. Typer's `exists=True` handles file existence validation automatically.

**When to use:** Always — this is the CLI shell required by CLI-01.

**Example:**
```python
# Source: https://typer.tiangolo.com/tutorial/parameter-types/path/
# src/cinecut/cli.py
from pathlib import Path
from typing import Annotated, Optional
import typer
from rich.console import Console

app = typer.Typer(help="CineCut AI - Generate a trailer from any feature film.")
console = Console()

@app.command()
def main(
    video: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
            help="Input video file (MKV, AVI, or MP4)",
        ),
    ],
    subtitle: Annotated[
        Path,
        typer.Option(
            "--subtitle",
            "-s",
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
            help="Subtitle file (SRT or ASS)",
        ),
    ],
    vibe: Annotated[
        str,
        typer.Option("--vibe", "-v", help="Trailer vibe profile name"),
    ],
    review: Annotated[
        bool,
        typer.Option("--review", help="Pause after manifest generation for inspection"),
    ] = False,
) -> None:
    """Ingest a film and produce analysis-ready artifacts."""
    # Validate video extension
    if video.suffix.lower() not in {".mkv", ".avi", ".mp4"}:
        console.print(f"[red]Error:[/] Unsupported video format: {video.suffix}")
        raise typer.Exit(1)
    ...
```

### Pattern 2: FFmpeg Proxy Creation with CFR and Progress

**What:** Create a 420p CFR proxy using FFmpeg. Use `better-ffmpeg-progress` to drive a Rich progress bar. Capture stderr on failure and translate to human-readable error.

**When to use:** PIPE-02 — always before any analysis.

**Example:**
```python
# Source: https://pypi.org/project/better-ffmpeg-progress/
# src/cinecut/ingestion/proxy.py
from pathlib import Path
import subprocess
from better_ffmpeg_progress import FfmpegProcess, FfmpegProcessError
from ..errors import ProxyCreationError

def create_proxy(source: Path, work_dir: Path) -> Path:
    """Create a 420p CFR proxy at 24fps, preserving PTS."""
    proxy_path = work_dir / f"{source.stem}_proxy.mp4"
    command = [
        "ffmpeg", "-y",
        "-i", str(source),
        "-vf", "scale=-2:420,fps=24",
        "-vsync", "cfr",
        "-c:v", "libx264",
        "-crf", "28",
        "-preset", "fast",
        "-an",            # No audio needed in proxy
        str(proxy_path),
    ]
    try:
        process = FfmpegProcess(command)
        process.run()
        if process.return_code != 0:
            raise ProxyCreationError(source, "FFmpeg returned non-zero exit code")
    except FfmpegProcessError as e:
        raise ProxyCreationError(source, str(e)) from e
    return proxy_path
```

**CFR flag note:** `-vsync cfr` (or `-fps_mode cfr` on ffmpeg >= 5.1) ensures the output has constant frame rate. This is mandatory for reliable PTS-to-timestamp mapping. `-vf fps=24` alone sets rate in the filter graph; `-vsync cfr` ensures the muxer enforces it. Use both.

### Pattern 3: ffprobe for Video Metadata

**What:** Extract video duration and frame rate as JSON before proxy creation, both for progress estimation and for the interval fallback gap calculation (PIPE-03).

**When to use:** Before proxy creation and before keyframe extraction.

**Example:**
```python
# Source: https://gist.github.com/hiwonjoon/035a1ead72a767add4b87afe03d0dd7b
# src/cinecut/ingestion/proxy.py
import subprocess, json
from pathlib import Path

def probe_video(source: Path) -> dict:
    """Return duration_seconds and r_frame_rate from ffprobe JSON."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-select_streams", "v:0",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    duration = float(stream.get("duration", 0))
    return {"duration_seconds": duration, "r_frame_rate": stream["r_frame_rate"]}
```

### Pattern 4: Hybrid Keyframe Extraction

**What:** Build the keyframe timestamp list by combining three sources, deduplicate, sort, and extract one JPEG per timestamp via FFmpeg.

**When to use:** PIPE-03 — after proxy is created.

**Example:**
```python
# Source: PySceneDetect 0.6.7.1 API + custom logic
# src/cinecut/ingestion/keyframes.py
from pathlib import Path
from scenedetect import detect, ContentDetector
import subprocess

def collect_keyframe_timestamps(
    proxy: Path,
    subtitle_midpoints: list[float],
    gap_threshold_s: float = 30.0,
    interval_s: float = 30.0,
) -> list[float]:
    """Return sorted, deduplicated list of PTS seconds to extract."""
    timestamps = set(subtitle_midpoints)

    # Supplementary: scene-change detection
    scenes = detect(str(proxy), ContentDetector(threshold=27.0))
    for start, end in scenes:
        # Use scene midpoint as keyframe position
        mid = (start.get_seconds() + end.get_seconds()) / 2.0
        timestamps.add(round(mid, 3))

    # Interval fallback: fill gaps > gap_threshold_s
    sorted_ts = sorted(timestamps)
    filled = list(sorted_ts)
    for i in range(len(sorted_ts) - 1):
        gap = sorted_ts[i + 1] - sorted_ts[i]
        if gap > gap_threshold_s:
            t = sorted_ts[i] + interval_s
            while t < sorted_ts[i + 1]:
                filled.append(round(t, 3))
                t += interval_s

    return sorted(set(filled))


def extract_frame(proxy: Path, timestamp_s: float, output_path: Path) -> None:
    """Extract a single JPEG at timestamp_s using fast pre-seek."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(timestamp_s),  # Pre-seek (fast, keyframe-aligned)
            "-i", str(proxy),
            "-frames:v", "1",
            "-q:v", "2",             # JPEG quality (2=high)
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
```

**Seeking note:** Place `-ss` before `-i` for the proxy. The proxy is CFR and composed of libx264 I-frames at regular intervals (typically every 250 frames at crf 28). Pre-seek is fast and accurate enough for 24fps analysis. For exact frame accuracy, move `-ss` after `-i`, but this is significantly slower on long films.

### Pattern 5: Subtitle Parsing with pysubs2

**What:** Load SRT or ASS file, iterate over events, compute midpoint timestamp, clean text, classify emotional tone.

**When to use:** NARR-01 — always paired with video ingestion.

**Example:**
```python
# Source: https://pysubs2.readthedocs.io/en/latest/tutorial.html
# src/cinecut/ingestion/subtitles.py
import pysubs2
from dataclasses import dataclass
from pathlib import Path

@dataclass
class DialogueEvent:
    start_ms: int          # pysubs2 native unit
    end_ms: int
    start_s: float         # PTS seconds for downstream use
    end_s: float
    midpoint_s: float      # Used as primary keyframe timestamp
    text: str              # Cleaned, tag-stripped
    emotion: str           # "positive" | "negative" | "neutral" | "intense" | "comedic" | "romantic"

# Minimal emotional keyword dictionary — expand as needed
_EMOTION_KEYWORDS = {
    "positive": {"love", "happy", "wonderful", "hope", "proud", "yes", "win", "joy"},
    "negative": {"die", "kill", "hate", "lost", "never", "dead", "fail", "cry"},
    "intense":  {"now", "run", "fight", "stop", "must", "war", "attack", "danger"},
    "comedic":  {"ha", "funny", "joke", "laugh", "silly", "weird", "crazy"},
    "romantic": {"heart", "together", "always", "forever", "kiss", "love", "feel"},
}

def classify_emotion(text: str) -> str:
    words = set(text.lower().split())
    for label, keywords in _EMOTION_KEYWORDS.items():
        if words & keywords:
            return label
    return "neutral"

def parse_subtitles(subtitle_path: Path) -> list[DialogueEvent]:
    """Load SRT or ASS file; return structured DialogueEvent list."""
    subs = pysubs2.load(str(subtitle_path), encoding="utf-8")
    events = []
    for event in subs:
        if event.is_comment:
            continue
        text = event.plaintext.strip()
        if not text:
            continue
        start_s = event.start / 1000.0
        end_s = event.end / 1000.0
        events.append(DialogueEvent(
            start_ms=event.start,
            end_ms=event.end,
            start_s=start_s,
            end_s=end_s,
            midpoint_s=round((start_s + end_s) / 2.0, 3),
            text=text,
            emotion=classify_emotion(text),
        ))
    return events
```

**Encoding note:** If UTF-8 fails, retry with `chardet` or `charset-normalizer` to detect encoding. Do not silently swallow encoding errors — surface them as actionable messages (CLI-03).

### Pattern 6: Work Directory Setup

**What:** Create a persistent (not temporary) work directory next to the source file for all phase artifacts. Do NOT use `tempfile` — artifacts must persist across CLI invocations for Phase 3 and Phase 5 checkpoint resumption.

**When to use:** At the start of every `cinecut` invocation.

**Example:**
```python
# src/cinecut/cli.py
def setup_work_dir(source: Path) -> Path:
    """Create <source_stem>_cinecut_work/ alongside the source file."""
    work_dir = source.parent / f"{source.stem}_cinecut_work"
    work_dir.mkdir(exist_ok=True)
    (work_dir / "keyframes").mkdir(exist_ok=True)
    return work_dir
```

### Pattern 7: Human-Readable Error Translation (CLI-03)

**What:** Catch subprocess errors and translate FFmpeg stderr into actionable messages. Never let raw FFmpeg output reach the user.

**When to use:** Every FFmpeg subprocess call.

**Example:**
```python
# src/cinecut/errors.py
from pathlib import Path

class ProxyCreationError(Exception):
    def __init__(self, source: Path, detail: str):
        super().__init__(
            f"Failed to create proxy from '{source.name}'.\n"
            f"  Cause: {detail}\n"
            f"  Check: Is FFmpeg installed? Is the file a valid video?"
        )

class KeyframeExtractionError(Exception):
    def __init__(self, timestamp: float, detail: str):
        super().__init__(
            f"Failed to extract frame at {timestamp:.1f}s.\n"
            f"  Cause: {detail}"
        )

class SubtitleParseError(Exception):
    def __init__(self, path: Path, detail: str):
        super().__init__(
            f"Cannot parse subtitle file '{path.name}'.\n"
            f"  Cause: {detail}\n"
            f"  Check: Is the file valid SRT or ASS format? Try re-encoding as UTF-8."
        )
```

### Anti-Patterns to Avoid

- **Using frame index as timecode:** Store timestamps as PTS float seconds (`event.start / 1000.0`), not frame indices. Frame indices are meaningless across different source frame rates.
- **Using `tempfile.TemporaryDirectory` for work artifacts:** Temp dirs are cleaned up on exit. Work artifacts must survive across invocations for Phase 5 checkpointing.
- **Surfacing raw FFmpeg stderr:** FFmpeg stderr is a wall of codec statistics. Always wrap and translate.
- **Using ffmpeg-python library:** `kkroening/ffmpeg-python` is effectively unmaintained (last commit 2021). Use direct subprocess.
- **Running PySceneDetect on the original source:** Always run scene detection on the proxy (420p). The proxy is 1/6 the resolution of typical HD source — detection is 6x faster.
- **Loading full NLP model for emotion classification:** VADER or a transformer model adds 100MB+ dependency. A keyword dictionary is sufficient for Phase 1 signal quality.
- **Ignoring ASS tag stripping in text:** pysubs2's `.plaintext` property strips ASS formatting tags. Use `.plaintext`, not `.text`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| FFmpeg progress tracking | Manual `time=` regex + thread loop | `better-ffmpeg-progress 4.0.1` | Threading, stderr capture, EOF handling are subtle; library handles all edge cases |
| Subtitle format detection | Check file extension or sniff bytes | `pysubs2.load()` | pysubs2 auto-detects format; handles encoding edge cases; single API for SRT and ASS |
| Scene change detection | Frame-by-frame pixel diff loop | `PySceneDetect 0.6.7.1` | VFR handling, keyframe alignment, chunked processing for large files all built-in |
| CLI Path validation | Manual `os.path.exists()` checks | Typer `exists=True` on Path | Typer generates correct error messages automatically |
| ASS formatting tag stripping | Custom regex `{\\.+?}` | `pysubs2 .plaintext` property | pysubs2 handles nested and complex ASS override tags |

**Key insight:** The FFmpeg + subtitle + scene detection domain has mature libraries for every sub-problem. Custom solutions will rediscover the same edge cases these libraries already handle.

---

## Common Pitfalls

### Pitfall 1: VFR Sources Break PTS Mapping

**What goes wrong:** MKV files from screen recordings, remuxes, and some encoders have variable frame rates. If you compute `frame_index / fps` as your timestamp, you get the wrong PTS second. Any seeking using that timestamp will land on the wrong frame.

**Why it happens:** VFR sources have non-uniform PTS intervals. The `r_frame_rate` from ffprobe is the "container declared" rate, which may not match actual frame spacing.

**How to avoid:** The 420p proxy is always CFR (enforced by `-vsync cfr`). All downstream timestamp computation is done against the proxy's actual PTS values, not frame indices. When using pysubs2, `event.start / 1000.0` gives ms-to-seconds PTS directly from the subtitle file — no frame arithmetic.

**Warning signs:** Keyframes that consistently land a few seconds early or late when visually inspected.

### Pitfall 2: PySceneDetect Produces Too Many Scenes on Action Films

**What goes wrong:** Action films have rapid camera movement that triggers ContentDetector at every cut. For a 2-hour action film with 3000 cuts, you'd extract 3000 keyframes — far more than needed and too slow for LLaVA inference.

**Why it happens:** Default `threshold=27.0` is calibrated for general video. Action content has higher inter-frame delta.

**How to avoid:** Use PySceneDetect results as supplementary timestamps only. The hybrid strategy already caps density by deduplicating against subtitle midpoints. Consider raising threshold to 35–40 for action content, or limiting total scene-detected keyframes to the top N by score.

**Warning signs:** More than 500 keyframes extracted from a 2-hour film.

### Pitfall 3: FFmpeg Exits Zero But Proxy Is Corrupt

**What goes wrong:** FFmpeg occasionally exits 0 but writes an incomplete or corrupt MP4 (e.g., power loss mid-encode, disk full, codec negotiation warnings treated as non-fatal).

**Why it happens:** Some FFmpeg errors are warnings at the codec level but still produce a technically valid container with broken frames.

**How to avoid:** After proxy creation, run a quick `ffprobe` validation: check that `duration` > 0 and `streams` contains a video stream with correct codec. If validation fails, delete the proxy and re-encode.

**Warning signs:** ffprobe reports duration=N/A or stream count = 0.

### Pitfall 4: Subtitle Encoding Mismatch Causes Silent Drops

**What goes wrong:** SRT files distributed with non-English films are commonly encoded in Latin-1, Windows-1252, or CP1250. Loading with UTF-8 raises `UnicodeDecodeError`, which if caught too broadly results in zero dialogue events being parsed.

**Why it happens:** pysubs2 defaults to UTF-8. Non-UTF-8 files fail silently if errors are swallowed.

**How to avoid:** Catch `UnicodeDecodeError` explicitly. On failure, try `charset-normalizer` (or `chardet`) to detect encoding, then retry. If detection fails, surface as `SubtitleParseError` with clear guidance. Never default to `errors='ignore'`.

**Warning signs:** `parse_subtitles()` returns an empty list for a subtitle file that visually contains events.

### Pitfall 5: Work Directory Collides Across Multiple Films

**What goes wrong:** If two films have the same stem (e.g., `film.mkv` and `film.mp4` in different directories), `setup_work_dir()` based on stem alone produces the same path.

**Why it happens:** Stem-only naming ignores the source directory.

**How to avoid:** Use `source.parent / f"{source.stem}_cinecut_work"` — the work dir is always placed next to the source file, so collision only occurs if two identically-named files are in the same directory (which the user controls).

### Pitfall 6: -fps_mode vs -vsync Deprecation

**What goes wrong:** FFmpeg >= 5.1 deprecated `-vsync` in favor of `-fps_mode`. Using `-vsync cfr` on newer FFmpeg versions emits a deprecation warning that can be mistaken for an error.

**Why it happens:** FFmpeg API evolves across versions; the system FFmpeg version is unknown.

**How to avoid:** Use `-vsync cfr` initially (it still works on all versions, just emits a warning on 5.1+). If warnings are a concern, probe FFmpeg version first and choose the correct flag. For robustness, parse the deprecation warning in the error translator so it isn't shown to the user.

---

## Code Examples

Verified patterns from official sources:

### pysubs2: Load and Iterate Subtitle Events
```python
# Source: https://pysubs2.readthedocs.io/en/latest/tutorial.html
import pysubs2

subs = pysubs2.load("subtitles.srt", encoding="utf-8")
for event in subs:
    print(event.start)      # int, milliseconds
    print(event.end)        # int, milliseconds
    print(event.plaintext)  # str, tags stripped
```

### PySceneDetect: Detect Scenes and Get PTS Seconds
```python
# Source: https://www.scenedetect.com/docs/latest/api.html (v0.6.7.1)
from scenedetect import detect, ContentDetector

scenes = detect("proxy.mp4", ContentDetector(threshold=27.0))
for start, end in scenes:
    start_s = start.get_seconds()   # float, PTS seconds
    end_s = end.get_seconds()       # float, PTS seconds
    midpoint_s = (start_s + end_s) / 2.0
```

### FFmpeg: Extract Single Frame at Timestamp
```python
# Source: https://gist.github.com/hiwonjoon/035a1ead72a767add4b87afe03d0dd7b
import subprocess

subprocess.run(
    ["ffmpeg", "-y", "-ss", "123.5", "-i", "proxy.mp4",
     "-frames:v", "1", "-q:v", "2", "keyframe_0123.jpg"],
    check=True,
    capture_output=True,
)
```

### better-ffmpeg-progress: Proxy Creation with Progress
```python
# Source: https://pypi.org/project/better-ffmpeg-progress/ (v4.0.1)
from better_ffmpeg_progress import FfmpegProcess, FfmpegProcessError

process = FfmpegProcess([
    "ffmpeg", "-y", "-i", "input.mkv",
    "-vf", "scale=-2:420,fps=24",
    "-vsync", "cfr", "-c:v", "libx264",
    "-crf", "28", "-preset", "fast", "-an",
    "proxy.mp4"
])
try:
    process.run()
except FfmpegProcessError as e:
    raise ProxyCreationError(source, str(e)) from e
```

### Typer: Entry Point with Validated Paths
```python
# Source: https://typer.tiangolo.com/tutorial/parameter-types/path/
from pathlib import Path
from typing import Annotated
import typer

app = typer.Typer()

@app.command()
def main(
    video: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, resolve_path=True)],
    subtitle: Annotated[Path, typer.Option("--subtitle", exists=True, file_okay=True, dir_okay=False)],
    vibe: str = typer.Option(..., "--vibe"),
    review: bool = typer.Option(False, "--review"),
) -> None:
    ...
```

### pyproject.toml: Package Entry Point
```toml
# Source: https://typer.tiangolo.com/tutorial/package/
[project.scripts]
cinecut = "cinecut.cli:app"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ffmpeg-python (kkroening) | Direct subprocess + better-ffmpeg-progress | 2021 (ffmpeg-python abandoned) | ffmpeg-python has unfixed bugs; subprocess gives full control |
| pysrt (SRT only) | pysubs2 (SRT + ASS + more) | ~2019 | Single library handles all required formats |
| `-vsync cfr` flag | `-fps_mode cfr` flag | FFmpeg 5.1 (2022) | Both work; `-fps_mode` is the future; `-vsync` still functional |
| frame index timecodes | PTS float seconds | Best practice, always | Frame indices break on VFR sources; seconds are universal |
| NLP for subtitle classification | Curated keyword dict (Phase 1) + LLaVA (Phase 3) | Design choice | LLaVA provides richer scene analysis; Phase 1 only needs a lightweight signal |

**Deprecated/outdated:**
- `ffmpeg-python` (kkroening): Last commit 2021, multiple open bugs, no active maintenance. Do not use.
- `moviepy`: Heavy dependency, wraps ffmpeg-python internally, overkill for this use case.
- Frame-index seeking (`-vframes N` to seek): Wrong for arbitrary timestamps; use `-ss` + `-frames:v 1`.

---

## Open Questions

1. **FFmpeg version on target system**
   - What we know: The system runs Linux with a Quadro K6000; FFmpeg is likely installed via apt or compiled
   - What's unclear: Whether FFmpeg is >= 5.1 (where `-vsync` is deprecated) or older
   - Recommendation: Add a startup check `ffmpeg -version` and parse the version number; use `-fps_mode cfr` if >= 5.1, else `-vsync cfr`. Surface the version in verbose output.

2. **Optimal ContentDetector threshold for feature films**
   - What we know: Default is 27.0; action content may produce too many scenes
   - What's unclear: Whether a single threshold works well across genres at the proxy stage
   - Recommendation: Use 27.0 as default; expose as a hidden CLI flag (`--scene-threshold`) for debugging. The interval fallback ensures minimum coverage regardless.

3. **Subtitle encoding detection dependency**
   - What we know: `charset-normalizer` (the modern successor to `chardet`) can auto-detect encoding
   - What's unclear: Whether to add it as a hard dependency or handle encoding errors more simply
   - Recommendation: Add `charset-normalizer` as a dependency (it is already a transitive dependency of `requests`); use it only on UTF-8 decode failure as a fallback.

4. **Work directory naming collision on re-runs**
   - What we know: Work dir uses `{stem}_cinecut_work/` pattern
   - What's unclear: Whether re-running on the same source should clean or reuse the work dir
   - Recommendation: Reuse by default (idempotent); add `--clean` flag for future use. Keyframe files are deterministically named by timestamp so re-extraction is safe.

---

## Sources

### Primary (HIGH confidence)
- pysubs2 1.8.0 official docs — https://pysubs2.readthedocs.io/en/latest/tutorial.html — API tutorial, SSAEvent structure, encoding
- PySceneDetect 0.6.7.1 official docs — https://www.scenedetect.com/docs/latest/api.html — detect(), FrameTimecode.get_seconds(), ContentDetector threshold
- PySceneDetect PyPI — https://pypi.org/project/scenedetect/ — version, Python requirements, optional extras
- pysubs2 PyPI — https://pypi.org/project/pysubs2/ — version 1.8.0, Python >=3.9, no external dependencies
- better-ffmpeg-progress PyPI — https://pypi.org/project/better-ffmpeg-progress/ — version 4.0.1, Rich integration
- Typer official docs (Path validation) — https://typer.tiangolo.com/tutorial/parameter-types/path/ — exists=True, file_okay, resolve_path
- Typer official docs (package) — https://typer.tiangolo.com/tutorial/package/ — pyproject.toml [project.scripts] pattern
- Rich official docs (progress) — https://rich.readthedocs.io/en/stable/progress.html — Progress context manager, indeterminate bars

### Secondary (MEDIUM confidence)
- ffprobe subprocess pattern — https://gist.github.com/hiwonjoon/035a1ead72a767add4b87afe03d0dd7b — validated against multiple sources
- FFmpeg stderr time= parsing — https://pypi.org/project/better-ffmpeg-progress/ — cross-verified with better-ffmpeg-progress implementation
- PySceneDetect ContentDetector threshold — https://www.scenedetect.com/docs/latest/api/detectors.html — threshold=27.0 default confirmed

### Tertiary (LOW confidence)
- FFmpeg -vsync cfr deprecation in 5.1: reported in multiple forum posts and changelogs but not directly verified in official FFmpeg release notes at time of research; treat as probable

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified on PyPI with current versions and Python support matrix
- Architecture: HIGH — patterns follow official library documentation; structure is conventional Python CLI
- FFmpeg commands: MEDIUM — core flags verified across multiple sources; `-vsync cfr` deprecation is LOW
- Pitfalls: MEDIUM — VFR pitfall and encoding pitfall are well-documented; scene detection tuning is from domain knowledge

**Research date:** 2026-02-26
**Valid until:** 2026-03-28 (stable libraries; FFmpeg flag deprecation situation may clarify sooner)
