# Phase 2: Manifest Contract, Vibes, and Conform - Research

**Researched:** 2026-02-26
**Domain:** Pydantic schema validation, FFmpeg conform (lut3d + loudnorm), .cube LUT generation, vibe profiles
**Confidence:** HIGH (core stack verified via official docs and multiple sources)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EDIT-04 | `--review` flag pauses pipeline after manifest generation, waits for user confirmation before FFmpeg conform | `typer.confirm()` / `typer.prompt()` — confirmed via Typer official docs |
| EDIT-05 | Conform pipeline applies manifest against original source with frame-accurate FFmpeg seeking (`-ss` before `-i`) | FFmpeg `-ss` before `-i` with re-encode for accuracy — verified via multiple sources |
| VIBE-01 | All 18 vibe profiles defined with concrete parameters (cut durations, clip count, transitions, LUFS, dialogue ratio, LUT spec, color temp/contrast/saturation, pacing curve) | Research section provides concrete parameter ranges per genre |
| VIBE-02 | `.cube` LUT files for all 18 vibes (sourced from free/open libraries or programmatically generated via NumPy) | Programmatic generation with NumPy is fully feasible; .cube format documented |
| VIBE-03 | Per-vibe LUT applied to output clips via FFmpeg `lut3d` filter during conform | `ffmpeg -vf lut3d=file.cube` — confirmed syntax via FFmpeg filter docs |
| VIBE-04 | Per-vibe LUFS audio normalization via FFmpeg `loudnorm` two-pass analysis and application | Two-pass loudnorm workflow fully documented with exact parameter names |
| CLI-04 | Output is ~2-minute MP4 at source resolution, written to `<source_basename>_trailer_<vibe>.mp4` | FFmpeg concat filter with re-encode produces single output MP4; naming pattern is deterministic |
</phase_requirements>

---

## Summary

Phase 2 builds the output contract for the entire CineCut pipeline: a Pydantic-validated manifest schema that drives a two-stage conform process (per-clip FFmpeg extraction + final concat). The key technical challenge is not complexity of any single piece, but the correct ordering and integration of four independent concerns: schema design, LUT file availability, FFmpeg filter pipeline (lut3d + loudnorm + concat), and the `--review` interactive pause.

Pydantic v2.12.5 (current stable, released November 2025) is the right choice for manifest validation. The project STATE.md explicitly deferred Pydantic to Phase 2 (Phase 1 uses dataclasses). The manifest schema needs careful design because Phase 4 will generate it from real inference output — any schema decisions made here become a contract Phase 4 must satisfy. Design it permissively enough for hand-crafted manifests but strict enough to catch bad AI-generated output.

The FFmpeg conform pipeline breaks cleanly into three operations: (1) extract each clip from the original source using frame-accurate seeking (`-ss` before `-i`, re-encoded), (2) apply lut3d and loudnorm to each extracted clip, and (3) concatenate all clips into the final MP4 using the concat demuxer (stream copy, since all clips will have identical codec/resolution from step 1). The `.cube` LUT files can be generated programmatically using NumPy — the format is a simple text file with a header and 33^3 RGB triplets. No third-party LUT generation library is needed.

**Primary recommendation:** Use Pydantic v2 `model_validate_json()` for manifest loading with `ValidationError` catch and Rich error panel, generate all 18 `.cube` LUTs programmatically via NumPy at install/first-run time, and implement the conform pipeline as per-clip subprocess calls (extract → apply lut3d+loudnorm → concat).

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.12.5 | Manifest schema definition and JSON validation | Current stable (Nov 2025); Rust-backed validation core; `model_validate_json()` is fast; `ValidationError` has structured error reporting; explicitly deferred from Phase 1 for this work |
| numpy | >=1.24 | Programmatic `.cube` LUT generation | Already available in most Python ML environments; 33x33x33 LUT = 35937 RGB triplets, trivially computed via meshgrid |
| subprocess (stdlib) | 3.10+ | FFmpeg conform calls (extract, lut3d, loudnorm, concat) | Phase 1 pattern — subprocess.run with stderr capture; consistent with existing proxy/keyframe code |
| pathlib (stdlib) | 3.10+ | File path construction for output naming | Already used in Phase 1 patterns |
| json (stdlib) | 3.10+ | Parse loudnorm pass-1 JSON output from stderr | Standard; no additional dependency |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| typer | >=0.12.0 | `typer.confirm()` for `--review` pause | Already a project dependency; `abort=True` variant auto-raises `typer.Abort()` on user rejection |
| rich | >=13.0.0 | Progress + error panels during conform | Already a project dependency; use for conform stage progress |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| NumPy LUT generation | pylut (GitHub) | pylut is abandoned (last commit 2017), no PyPI maintenance; NumPy approach is 20 lines and has no dependency |
| NumPy LUT generation | colour-science | colour-science is a 50MB+ package with many transitive deps; overkill for writing a text file |
| subprocess conform | ffmpeg-python | ffmpeg-python is a thin wrapper that doesn't add much vs. raw subprocess; Phase 1 already uses `better-ffmpeg-progress` for progress display, and conform doesn't need per-frame progress |
| concat demuxer | concat filter with filtergraph | concat filter requires complex filtergraph syntax; concat demuxer is simpler and correct when all clips share codec/resolution (which they will after per-clip re-encode) |

**Installation:**
```bash
pip install "pydantic>=2.12.0"
# numpy may already be present; if not:
pip install numpy
```

Update `pyproject.toml` dependencies:
```toml
dependencies = [
    "typer>=0.12.0",
    "rich>=13.0.0",
    "pysubs2==1.8.0",
    "scenedetect[opencv-headless]==0.6.7.1",
    "better-ffmpeg-progress==4.0.1",
    "charset-normalizer>=3.0.0",
    "pydantic>=2.12.0",    # Phase 2 addition
    "numpy>=1.24.0",       # Phase 2 addition (LUT generation)
]
```

---

## Architecture Patterns

### Recommended Project Structure
```
src/cinecut/
├── ingestion/           # Phase 1 — proxy, subtitles, keyframes
├── manifest/            # Phase 2 NEW
│   ├── __init__.py
│   ├── schema.py        # Pydantic models: TrailerManifest, ClipEntry, etc.
│   ├── loader.py        # load_manifest(path) -> TrailerManifest, wraps ValidationError
│   └── vibes.py         # VIBE_PROFILES dict: all 18 VibeProfile dataclass instances
├── conform/             # Phase 2 NEW
│   ├── __init__.py
│   ├── luts.py          # generate_lut(vibe_name, output_dir) -> Path
│   └── pipeline.py      # conform_manifest(manifest, source, vibe, work_dir) -> Path
├── models.py            # Existing Phase 1 dataclasses
├── errors.py            # Extend with ManifestError, ConformError
└── cli.py               # Extend with --review pause logic and conform stage
```

### Pattern 1: Pydantic v2 Manifest Schema
**What:** Define `TrailerManifest` as a Pydantic `BaseModel` with strict field typing. Load from JSON file using `model_validate_json()`.
**When to use:** Whenever reading a `TRAILER_MANIFEST.json` from disk (both hand-crafted and AI-generated).
**Example:**
```python
# Source: https://docs.pydantic.dev/latest/concepts/models/
from pydantic import BaseModel, Field
from typing import Literal
from pathlib import Path

class ClipEntry(BaseModel):
    source_start_s: float = Field(ge=0.0, description="Clip start in source file (seconds)")
    source_end_s: float = Field(ge=0.0, description="Clip end in source file (seconds)")
    beat_type: Literal[
        "inciting_incident", "character_introduction", "escalation_beat",
        "relationship_beat", "money_shot", "climax_peak", "breath"
    ]
    act: Literal["cold_open", "act1", "beat_drop", "act2", "breath", "act3", "title_card", "button"]
    transition: Literal["hard_cut", "crossfade", "fade_to_black", "fade_to_white"] = "hard_cut"
    dialogue_excerpt: str = ""  # Optional subtitle text for this clip

class TrailerManifest(BaseModel):
    schema_version: str = "1.0"
    source_file: str          # Original source video path
    vibe: str                 # Vibe profile name (must be in VALID_VIBES set)
    clips: list[ClipEntry]    # Ordered clip list

def load_manifest(path: Path) -> TrailerManifest:
    """Load and validate TRAILER_MANIFEST.json. Raises ManifestError on failure."""
    from pydantic import ValidationError
    from cinecut.errors import ManifestError
    try:
        return TrailerManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as e:
        raise ManifestError(path, str(e)) from e
    except (OSError, UnicodeDecodeError) as e:
        raise ManifestError(path, str(e)) from e
```

### Pattern 2: Programmatic .cube LUT Generation
**What:** Generate a 33x33x33 3D LUT as a `.cube` file by writing the header and RGB triplets computed from a color transform.
**When to use:** LUT generation at install-time or first run; store generated LUTs in `work_dir/luts/`.
**Example:**
```python
# Source: cube LUT specification, verified against FFmpeg lut3d filter docs
import numpy as np
from pathlib import Path

def generate_cube_lut(
    title: str,
    size: int,
    # Color adjustments (applied as simple linear transforms)
    temp_shift: float = 0.0,      # positive = warmer (add to R, sub from B)
    saturation: float = 1.0,      # 1.0 = no change; <1 desaturated; >1 boosted
    contrast: float = 1.0,        # 1.0 = no change; applied around midpoint 0.5
    brightness: float = 0.0,      # offset added uniformly
    output_path: Path = None,
) -> Path:
    """Generate a .cube LUT with the given color parameters."""
    # Build identity LUT grid — R changes fastest (inner loop), B slowest (outer loop)
    # .cube format: data is ordered B outer, G middle, R inner (R-major in RGB space)
    vals = np.linspace(0.0, 1.0, size)
    r, g, b = np.meshgrid(vals, vals, vals, indexing='ij')
    # r[ri, gi, bi], but .cube iterates B outer, G middle, R inner:
    # output rows: for bi in range(size): for gi in range(size): for ri in range(size)

    # Apply transforms
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    r_out = luma + saturation * (r - luma)
    g_out = luma + saturation * (g - luma)
    b_out = luma + saturation * (b - luma)

    # Contrast (pivot at 0.5)
    r_out = (r_out - 0.5) * contrast + 0.5
    g_out = (g_out - 0.5) * contrast + 0.5
    b_out = (b_out - 0.5) * contrast + 0.5

    # Temperature shift
    r_out = r_out + temp_shift
    b_out = b_out - temp_shift

    # Brightness
    r_out = r_out + brightness
    g_out = g_out + brightness
    b_out = b_out + brightness

    # Clamp to [0, 1]
    r_out = np.clip(r_out, 0.0, 1.0)
    g_out = np.clip(g_out, 0.0, 1.0)
    b_out = np.clip(b_out, 0.0, 1.0)

    with open(output_path, "w") as f:
        f.write(f"TITLE \"{title}\"\n")
        f.write(f"LUT_3D_SIZE {size}\n")
        f.write("DOMAIN_MIN 0.0 0.0 0.0\n")
        f.write("DOMAIN_MAX 1.0 1.0 1.0\n")
        # .cube data order: R fastest, B slowest
        for bi in range(size):
            for gi in range(size):
                for ri in range(size):
                    f.write(f"{r_out[ri, gi, bi]:.6f} {g_out[ri, gi, bi]:.6f} {b_out[ri, gi, bi]:.6f}\n")
    return output_path
```

**CRITICAL: .cube format data ordering** — R is the FASTEST-changing index (innermost loop), B is the SLOWEST (outermost loop). This is the opposite of how NumPy meshgrid 'ij' indexing works — translate carefully. See Anti-Patterns below.

### Pattern 3: FFmpeg Per-Clip Extraction with lut3d + loudnorm
**What:** For each clip in the manifest, extract the segment from the original source, apply LUT and audio normalization in a single FFmpeg pass.
**When to use:** The conform pipeline — one subprocess call per clip.
**Example:**
```python
# Source: FFmpeg docs, verified via multiple secondary sources
import subprocess
import json
import re
from pathlib import Path

def extract_and_grade_clip(
    source: Path,
    start_s: float,
    end_s: float,
    lut_path: Path,
    lufs_target: float,
    output_path: Path,
) -> Path:
    """
    Extract a clip from source with frame-accurate seeking, apply LUT + audio norm.
    LUFS normalization uses two-pass loudnorm.
    """
    duration = end_s - start_s

    # --- Pass 1: Measure loudness ---
    pass1_cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_s), "-i", str(source),
        "-t", str(duration),
        "-af", f"loudnorm=I={lufs_target}:LRA=7:tp=-2:print_format=json",
        "-f", "null", "-",
    ]
    result = subprocess.run(pass1_cmd, capture_output=True, text=True, check=False)
    # loudnorm prints JSON to stderr
    # Extract JSON from stderr (it appears after a line "Input Integrated:")
    stderr = result.stderr
    json_match = re.search(r'\{[^}]+\}', stderr, re.DOTALL)
    if not json_match:
        raise ConformError(output_path, "loudnorm pass 1 did not produce JSON stats")
    loudnorm_stats = json.loads(json_match.group())

    # --- Pass 2: Extract + LUT + normalized audio ---
    pass2_cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_s), "-i", str(source),
        "-t", str(duration),
        "-vf", f"lut3d=file={lut_path}",
        "-af", (
            f"loudnorm=I={lufs_target}:LRA=7:tp=-2"
            f":measured_I={loudnorm_stats['input_i']}"
            f":measured_LRA={loudnorm_stats['input_lra']}"
            f":measured_tp={loudnorm_stats['input_tp']}"
            f":measured_thresh={loudnorm_stats['input_thresh']}"
            f":offset={loudnorm_stats['target_offset']}"
            f":linear=true"
        ),
        "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
        "-c:a", "aac", "-ar", "48000",
        "-avoid_negative_ts", "make_zero",
        str(output_path),
    ]
    result = subprocess.run(pass2_cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConformError(output_path, result.stderr[-500:])
    return output_path
```

### Pattern 4: FFmpeg Concat Demuxer for Final Assembly
**What:** Concatenate all individually-processed clips into a single output MP4 using the concat demuxer (stream copy — no re-encode needed since all clips already share codec/resolution).
**When to use:** After all clips are extracted and graded; final assembly step.
**Example:**
```python
# Source: FFmpeg documentation, verified via mux.com and shotstack.io
import subprocess
from pathlib import Path

def concatenate_clips(clip_paths: list[Path], output_path: Path) -> Path:
    """Concatenate processed clips via concat demuxer (no re-encode). All clips
    must share identical codec, resolution, and frame rate."""
    concat_list = output_path.parent / "_concat_list.txt"
    with open(concat_list, "w") as f:
        for p in clip_paths:
            # Use absolute paths; escape single quotes in filenames
            escaped = str(p).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConformError(output_path, result.stderr[-500:])
    concat_list.unlink(missing_ok=True)
    return output_path
```

### Pattern 5: --review Pause
**What:** After manifest generation (Phase 4) or manifest loading (Phase 2 testing), pause the CLI and wait for user confirmation before running conform.
**When to use:** When `--review` flag is passed.
**Example:**
```python
# Source: https://typer.tiangolo.com/tutorial/prompt/
import typer
from rich.console import Console

console = Console()

def pause_for_review(manifest_path: Path) -> None:
    """Display manifest location and wait for user to confirm before conform."""
    console.print(f"\n[bold yellow]Review mode:[/bold yellow] Manifest written to:\n  {manifest_path}")
    console.print("[dim]Open the file, inspect or edit clip decisions, then confirm to continue.[/dim]\n")
    typer.confirm("Proceed with FFmpeg conform?", abort=True)
    # abort=True: if user enters 'n', typer.Abort() is raised automatically
```

### Anti-Patterns to Avoid
- **Wrong .cube data loop order:** The most common LUT generation bug. The `.cube` format requires R to iterate fastest (innermost), B slowest (outermost). Writing B innermost produces a scrambled LUT that is technically valid but maps colors incorrectly. Always iterate `for bi: for gi: for ri:` and index `[ri, gi, bi]`.
- **lut3d on 16-bit input:** The `lut3d` filter applied to 8-bit video with high-dynamic-range content will clip. Source films should be treated as 8-bit YUV420 from the proxy pipeline — acceptable for trailer color grading.
- **loudnorm single-pass on file content:** Single-pass loudnorm uses dynamic normalization (volume riding), which sounds unnatural for film audio. Always use two-pass for file-based content. The 2x FFmpeg call cost (~30s per clip for a 2hr film) is acceptable.
- **stream copy for concat before per-clip grading:** If you try to extract clips with `-c copy` and then apply lut3d in the same pass, FFmpeg may not seek accurately to the start point. Extract → grade → concat is the correct three-step order.
- **Pydantic v1 syntax:** The project uses Python >=3.10 and Pydantic v2. Do not use `validator` decorators or `class Config`. Use `@field_validator`, `model_config = ConfigDict(...)`, and `model_validate_json()` (not `parse_raw()`).
- **Relative paths in concat list:** FFmpeg concat demuxer requires `-safe 0` when using absolute paths. Without it, FFmpeg will reject paths with leading slashes. Always add `-safe 0` when building the file list with absolute paths.

---

## Vibe Profiles Reference

All 18 vibes defined here provide the concrete parameters for VIBE-01. These values are based on genre cinematography conventions (verified against multiple secondary sources) and should be encoded as Python dataclasses or Pydantic models in `vibes.py`.

### Color Grading Parameters by Genre
Confidence: MEDIUM — from multiple cinematography references, no single authoritative source for exact numeric values. These are design decisions backed by convention.

| Vibe | Temp Shift | Saturation | Contrast | Brightness | LUT Label |
|------|-----------|------------|----------|------------|-----------|
| Action | -0.05 (cool) | 1.15 (boosted) | 1.2 (high) | 0.0 | action_teal_orange |
| Adventure | 0.03 (warm) | 1.10 | 1.1 | 0.02 | adventure_warm |
| Animation | 0.0 | 1.25 (vivid) | 1.0 | 0.03 | animation_vivid |
| Comedy | 0.05 (warm) | 1.10 | 0.9 (soft) | 0.03 | comedy_warm_soft |
| Crime | -0.05 (cool) | 0.75 (desaturated) | 1.25 | -0.02 | crime_noir |
| Documentary | 0.0 | 0.90 (natural) | 1.0 | 0.0 | documentary_neutral |
| Drama | -0.02 (slight cool) | 0.85 | 1.15 | -0.01 | drama_intimate |
| Family | 0.05 (warm) | 1.10 | 0.9 | 0.03 | family_warm |
| Fantasy | 0.0 | 1.15 | 1.1 | 0.02 | fantasy_rich |
| History | 0.07 (warm sepia) | 0.80 | 1.15 | -0.02 | history_sepia |
| Horror | -0.03 (cool-dark) | 0.70 | 1.35 (high) | -0.05 | horror_dark |
| Music | 0.0 | 1.20 | 0.95 | 0.02 | music_vivid |
| Mystery | -0.04 (cool) | 0.75 | 1.20 | -0.03 | mystery_muted |
| Romance | 0.07 (warm) | 1.05 | 0.85 (soft) | 0.04 | romance_warm |
| Sci-Fi | -0.08 (cool-blue) | 0.90 | 1.25 | -0.02 | scifi_cold |
| Thriller | -0.04 (cool) | 0.85 | 1.30 | -0.03 | thriller_tense |
| War | -0.02 | 0.70 (desaturated) | 1.20 | -0.03 | war_desaturated |
| Western | 0.08 (warm amber) | 0.85 | 1.15 | -0.01 | western_amber |

### Audio LUFS Targets by Genre
Confidence: MEDIUM — platform targets are well-established; genre-specific targets are convention-derived.

| Vibe | LUFS Target | Rationale |
|------|-------------|-----------|
| Action | -14.0 | Loud and punchy — streaming platform standard |
| Adventure | -14.0 | Match streaming platform standard |
| Animation | -16.0 | Slightly dynamic for family-accessible content |
| Comedy | -16.0 | Dialogue clarity; slightly dynamic |
| Crime | -18.0 | Dynamic for tension; lower integrated loudness |
| Documentary | -20.0 | Natural dynamics; broadcast-style |
| Drama | -18.0 | Dynamic range preserves emotional impact |
| Family | -16.0 | Clear and accessible |
| Fantasy | -16.0 | Balanced for score and dialogue |
| History | -18.0 | Broadcast-standard for documentary-adjacent content |
| Horror | -20.0 | Dynamic; silence and jump-scare contrast |
| Music | -14.0 | Streaming platform standard for music-forward |
| Mystery | -18.0 | Dynamic for tension and silence |
| Romance | -18.0 | Soft and dynamic; dialogue-forward |
| Sci-Fi | -14.0 | Impact and scale |
| Thriller | -16.0 | Punchy with dynamic tension |
| War | -16.0 | Impact of action sequences |
| Western | -18.0 | Cinematic dynamics; score-driven |

### Pacing Parameters by Genre
Confidence: MEDIUM — from industry convention; no single authoritative numeric source found.

| Vibe | Act 1 Avg Cut (s) | Act 2 Avg Cut (s) | Act 3 Avg Cut (s) | Clip Count Target | Dialogue Ratio |
|------|-------------------|-------------------|-------------------|-------------------|----------------|
| Action | 4.0 | 2.5 | 1.2 | 25-35 | 0.25 |
| Adventure | 5.0 | 3.5 | 2.0 | 20-30 | 0.35 |
| Animation | 5.0 | 3.5 | 2.5 | 18-25 | 0.40 |
| Comedy | 5.0 | 4.0 | 3.0 | 15-22 | 0.55 |
| Crime | 5.0 | 3.5 | 2.0 | 20-28 | 0.40 |
| Documentary | 7.0 | 5.0 | 4.0 | 12-18 | 0.60 |
| Drama | 7.0 | 5.0 | 3.5 | 14-20 | 0.55 |
| Family | 5.0 | 4.0 | 3.0 | 16-22 | 0.45 |
| Fantasy | 6.0 | 4.0 | 2.5 | 18-26 | 0.35 |
| History | 7.0 | 5.0 | 3.5 | 14-20 | 0.55 |
| Horror | 6.0 | 4.0 | 1.8 | 20-28 | 0.30 |
| Music | 4.0 | 3.0 | 2.0 | 20-28 | 0.20 |
| Mystery | 6.0 | 4.5 | 3.0 | 16-22 | 0.45 |
| Romance | 7.0 | 5.0 | 4.0 | 12-18 | 0.55 |
| Sci-Fi | 5.0 | 3.5 | 2.0 | 22-30 | 0.35 |
| Thriller | 5.0 | 3.0 | 1.5 | 25-35 | 0.30 |
| War | 5.0 | 3.0 | 1.5 | 25-35 | 0.25 |
| Western | 6.0 | 4.5 | 3.0 | 16-22 | 0.45 |

### VibeProfile Data Structure
```python
# In src/cinecut/manifest/vibes.py
from dataclasses import dataclass

@dataclass(frozen=True)
class VibeProfile:
    name: str
    # Color grading (applied to LUT generation)
    temp_shift: float       # +warm/-cool; applied to R and B channels
    saturation: float       # 1.0 = no change
    contrast: float         # 1.0 = no change, pivot at 0.5
    brightness: float       # uniform offset
    # Audio
    lufs_target: float      # integrated loudness target
    # Pacing (seconds per cut, average per act)
    act1_avg_cut_s: float
    act2_avg_cut_s: float
    act3_avg_cut_s: float
    clip_count_min: int
    clip_count_max: int
    # Dialogue fraction (0.0 = all visual; 1.0 = all dialogue clips)
    dialogue_ratio: float
    # Transitions
    primary_transition: str    # "hard_cut" | "crossfade" | "fade_to_black"
    secondary_transition: str  # Used for act boundaries
    # LUT
    lut_filename: str          # e.g. "action_teal_orange.cube"
    # Human description
    pacing_curve: str          # e.g. "fast → very fast montage"
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON schema validation | Custom dict-parsing with manual checks | Pydantic `model_validate_json()` | Pydantic handles nested validation, type coercion, union dispatch, and produces structured `ValidationError` with field-level path reporting |
| LUT file parsing | Custom .cube parser | Write-only (generation only); if reading needed, NumPy text parsing | For generation, no parsing is needed — just write the format directly |
| Audio loudness measurement | Custom audio analysis | FFmpeg `loudnorm` pass 1 with `print_format=json` | EBU R128 compliance is complex; FFmpeg handles the 192kHz upsampling for true-peak detection |
| FFmpeg command-line building | String concatenation | `list[str]` passed to `subprocess.run` | List form avoids shell injection and handles spaces in paths automatically |
| User confirmation pause | `input()` with manual parsing | `typer.confirm(abort=True)` | Abort=True handles the 'n' case cleanly; consistent with Typer framework |

**Key insight:** The conform pipeline is fundamentally a sequence of subprocess calls. The complexity is in correctness (correct lut3d data ordering, correct loudnorm two-pass, correct -ss placement, correct concat list), not in the Python code structure.

---

## Common Pitfalls

### Pitfall 1: .cube Loop Order (B outer, R inner)
**What goes wrong:** LUT is generated with R as the outer loop and B as the inner loop. The file is syntactically valid but maps wrong colors — reds become blues, blues become reds.
**Why it happens:** NumPy `meshgrid` with `indexing='ij'` gives you `r[ri, gi, bi]` naturally but the `.cube` format requires iterating `for bi: for gi: for ri:`. The temptation is to iterate R outermost because it comes first in "RGB".
**How to avoid:** Always write the loops as `for bi in range(size): for gi in range(size): for ri in range(size):` and index arrays as `[ri, gi, bi]`. Test with an identity LUT (temp_shift=0, saturation=1.0, contrast=1.0) and verify it produces no color change on a reference image.
**Warning signs:** Output video has inverted color channels (sky is red, grass is purple).

### Pitfall 2: loudnorm JSON Parsing from stderr
**What goes wrong:** The `print_format=json` output from loudnorm pass 1 is mixed with FFmpeg's normal stderr (progress bars, stream info). A naive JSON parse of the full stderr fails.
**Why it happens:** FFmpeg always writes processing info to stderr; loudnorm appends its JSON after this. The JSON block starts with `{` and ends with `}` but is surrounded by non-JSON lines.
**How to avoid:** Use `re.search(r'\{[^}]+\}', stderr, re.DOTALL)` to extract the JSON substring. Verify the extracted keys include `input_i`, `input_lra`, `input_tp`, `input_thresh`, `target_offset`.
**Warning signs:** `json.JSONDecodeError` during pass-1 parsing; JSON block missing from stderr (older FFmpeg builds may have different format).

### Pitfall 3: Frame-Accurate Seeking Requires Re-encoding
**What goes wrong:** Using `-c copy` with `-ss` before `-i` produces clips that start at the nearest keyframe, not the requested timecode. A 4-second clip may start 2-3 seconds early.
**Why it happens:** Stream copy cannot synthesize new keyframes; it must start at the nearest existing I-frame. For trailer clips (precise timecode is the whole point), this is unacceptable.
**How to avoid:** Always re-encode with `-c:v libx264 -crf 18 -preset veryfast`. The speed cost is acceptable for trailer generation (not real-time). Add `-avoid_negative_ts make_zero` to handle timestamp alignment.
**Warning signs:** Clips begin with wrong content; transitions between clips are jarring because clips are longer than specified.

### Pitfall 4: Manifest Schema Too Strict for Phase 4 Integration
**What goes wrong:** Phase 2 defines the schema with required fields that Phase 4's AI generator might not always populate (e.g., `dialogue_excerpt` might be empty for visual-only beats). Validation rejects real AI output.
**Why it happens:** Phase 2 is defining the schema before Phase 4 exists, so it's easy to over-specify.
**How to avoid:** Make optional fields explicit with default values (`dialogue_excerpt: str = ""`). Only mark fields required that are essential for conform to work (`source_start_s`, `source_end_s`, `beat_type`, `act`). Keep schema permissive on non-critical metadata.
**Warning signs:** Phase 4 integration requires changes to the Phase 2 schema — this is a sign Phase 2 was too strict.

### Pitfall 5: Vibe Name Validation at Manifest Load vs. CLI Level
**What goes wrong:** A manifest with `"vibe": "scifi"` (with no hyphen) fails even though `"Sci-Fi"` is the canonical name. Case and hyphenation inconsistencies cause confusing errors.
**Why it happens:** Vibe names come from both the CLI (`--vibe action`) and the manifest JSON. Without normalization, case and spelling variations cause spurious validation failures.
**How to avoid:** Normalize vibe names to lowercase during CLI parsing and manifest loading. Store the `VALID_VIBES` set as lowercase. Use a `@field_validator` on the `vibe` field to normalize and validate: accept `"sci-fi"`, `"scifi"`, `"Sci-Fi"` as equivalent.
**Warning signs:** Users report "Invalid vibe" errors with slight spelling variations.

### Pitfall 6: FFmpeg concat list with spaces in paths
**What goes wrong:** Paths containing spaces cause the concat demuxer to fail with "No such file or directory" even when the path looks correct in the file.
**Why it happens:** The concat file format uses single-quote delimiters but the file is a plain text format — single quotes inside the path string break the delimiter.
**How to avoid:** Use `str(p).replace("'", "'\\''")` to escape single quotes in filenames when writing the concat list. Always use `-safe 0` flag with absolute paths.
**Warning signs:** Concat step fails when video source is in a directory with spaces (e.g. `/home/user/My Movies/`).

---

## Code Examples

Verified patterns from official sources:

### Pydantic v2 ValidationError Handling
```python
# Source: https://docs.pydantic.dev/latest/concepts/models/
from pydantic import ValidationError
from cinecut.errors import ManifestError
from pathlib import Path

def load_manifest(path: Path) -> TrailerManifest:
    try:
        return TrailerManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except ValidationError as e:
        # e.errors() returns list of dicts with loc, msg, type
        field_errors = "; ".join(
            f"{' -> '.join(str(x) for x in err['loc'])}: {err['msg']}"
            for err in e.errors()
        )
        raise ManifestError(path, f"Schema validation failed: {field_errors}") from e
```

### FFmpeg loudnorm Two-Pass Command
```bash
# Pass 1 — measure only (produces no output file)
# Source: https://peterforgacs.github.io/2018/05/20/Audio-normalization-with-ffmpeg/
# Verified: https://ayosec.github.io/ffmpeg-filters-docs/7.1/Filters/Audio/loudnorm.html
ffmpeg -ss 60.5 -i source.mkv -t 4.0 \
  -af loudnorm=I=-16:LRA=7:tp=-2:print_format=json \
  -f null -

# Pass 2 — apply (using measured_* values from pass 1 JSON)
ffmpeg -y -ss 60.5 -i source.mkv -t 4.0 \
  -vf "lut3d=file=action_teal_orange.cube" \
  -af "loudnorm=I=-16:LRA=7:tp=-2:measured_I=-24.3:measured_LRA=5.2:measured_tp=-6.1:measured_thresh=-34.5:offset=-0.3:linear=true" \
  -c:v libx264 -crf 18 -preset veryfast \
  -c:a aac -ar 48000 \
  -avoid_negative_ts make_zero \
  clip_001.mp4
```

### FFmpeg Concat Demuxer
```bash
# Source: https://www.mux.com/articles/stitch-multiple-videos-together-with-ffmpeg
# All clips must share codec/resolution/framerate (guaranteed if all came from step above)
cat > /tmp/concat_list.txt << 'EOF'
file '/path/to/clip_001.mp4'
file '/path/to/clip_002.mp4'
file '/path/to/clip_003.mp4'
EOF

ffmpeg -y -f concat -safe 0 -i /tmp/concat_list.txt -c copy output_trailer_action.mp4
```

### Output Naming Convention (CLI-04)
```python
# Source: REQUIREMENTS.md CLI-04 specification
def make_output_path(source: Path, vibe: str) -> Path:
    """Build output path per CLI-04: <source_basename>_trailer_<vibe>.mp4"""
    vibe_slug = vibe.lower().replace("-", "_").replace(" ", "_")
    return source.parent / f"{source.stem}_trailer_{vibe_slug}.mp4"

# Example: /films/Aliens.mkv --vibe action -> /films/Aliens_trailer_action.mp4
```

### Minimal .cube LUT File Format (for reference)
```
# .cube file format — Adobe/Resolve specification
# Source: Adobe Cube LUT Specification 1.0 (multiple secondary verifications)
TITLE "identity"
LUT_3D_SIZE 2
DOMAIN_MIN 0.0 0.0 0.0
DOMAIN_MAX 1.0 1.0 1.0
# Data: R fastest (innermost), B slowest (outermost)
# B=0, G=0, R=0..1:
0.000000 0.000000 0.000000
1.000000 0.000000 0.000000
# B=0, G=1, R=0..1:
0.000000 1.000000 0.000000
1.000000 1.000000 0.000000
# B=1, G=0, R=0..1:
0.000000 0.000000 1.000000
1.000000 0.000000 1.000000
# B=1, G=1, R=0..1:
0.000000 1.000000 1.000000
1.000000 1.000000 1.000000
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pydantic v1 (`@validator`, `class Config`) | Pydantic v2 (`@field_validator`, `ConfigDict`, `model_validate_json`) | June 2023 (v2 release) | v1 syntax is still supported in v2 via compat shims but deprecated; write new code for v2 |
| Single-pass loudnorm | Two-pass loudnorm | Loudnorm filter addition (FFmpeg ~3.x) | Two-pass produces linear normalization (preserves dynamics); single-pass uses dynamic riding (unnatural for film) |
| `-ss` after `-i` (slow seek) | `-ss` before `-i` (fast seek + re-encode for accuracy) | Long-standing FFmpeg best practice | Pre-input seek is fast (keyframe jump); re-encoding ensures frame accuracy at arbitrary timestamps |
| Downloading curated LUTs | Programmatic LUT generation | N/A | Eliminates dependency on external download; LUT parameters are version-controlled; no license concerns |

**Deprecated/outdated:**
- `pydantic.parse_raw()`: Removed in Pydantic v2. Use `model_validate_json()`.
- `pydantic.validator` decorator: Replaced by `@field_validator` in v2.
- ffmpeg-python library: Not used in this project; Phase 1 uses `better-ffmpeg-progress` for proxy creation and raw `subprocess.run` for probing. Phase 2 conform follows the same raw subprocess pattern.

---

## Open Questions

1. **LUT size: 17x17x17 vs 33x33x33**
   - What we know: FFmpeg's `lut3d` filter accepts any size; 33x33x33 is the professional standard (35,937 triplets, ~2MB file). 17x17x17 (4,913 triplets) is faster to generate but has more interpolation error.
   - What's unclear: Whether the simple linear color transforms in this project's LUTs (saturation, contrast, temp shift) produce enough variation to justify 33x33x33 vs 17x17x17. For smooth gradients the difference is negligible.
   - Recommendation: Use 33x33x33 as the standard. Generation is fast (NumPy vectorized), and professional tooling expects it.

2. **LUT application: on extracted clip vs. on concat output**
   - What we know: Applying lut3d per-clip (before concat) means per-clip consistency but requires a re-encode on every clip. Applying lut3d in the concat filtergraph would require the complex filtergraph approach (not the simple demuxer) and requires one large FFmpeg call.
   - What's unclear: Performance difference for a 2-hour source film with 25-35 clips.
   - Recommendation: Apply lut3d per-clip (during extract step). Simpler code, restartable at any clip, consistent with Phase 1 sequential GPU operation constraint (PIPE-05).

3. **loudnorm on clips < 3 seconds**
   - What we know: The EBU R128 standard requires minimum 3 seconds of audio for accurate integrated loudness measurement. Short clips (Act 3 montage at ~1.2s avg) may produce unreliable loudnorm results.
   - What's unclear: Whether FFmpeg's loudnorm filter will fail, warn, or silently produce bad results on sub-3-second clips.
   - Recommendation: Implement a clip-length check. For clips < 3.0 seconds, skip loudnorm pass 1 and apply a fixed gain via the `volume` filter instead (e.g., `-af "volume=-3dB"`). Document this in the vibe profile as a fallback.

4. **--review flow: manifest path is from Phase 4**
   - What we know: Phase 2 tests will use hand-crafted manifests. In Phase 4, the manifest is generated by the AI pipeline. The `--review` flag must pause between manifest generation and conform.
   - What's unclear: In Phase 2 (testing only), where does the manifest come from? For testing the `--review` flow, the CLI needs a `--manifest` flag or the manifest path needs to be agreed upon (e.g., `work_dir/TRAILER_MANIFEST.json`).
   - Recommendation: Define a canonical manifest path: `work_dir/TRAILER_MANIFEST.json`. For Phase 2 testing, add a `--manifest` CLI option that accepts a path directly, bypassing AI generation. This enables end-to-end conform testing without Phase 4.

---

## Sources

### Primary (HIGH confidence)
- https://docs.pydantic.dev/latest/concepts/models/ — Pydantic v2 model definition, `model_validate_json()`, `ValidationError`
- https://pypi.org/project/pydantic/ — current stable version 2.12.5 (Nov 2025)
- https://ayosec.github.io/ffmpeg-filters-docs/7.1/Filters/Audio/loudnorm.html — loudnorm filter parameters, two-pass parameter names (`measured_I`, `measured_LRA`, `measured_tp`, `measured_thresh`, `offset`, `print_format`)
- https://typer.tiangolo.com/tutorial/prompt/ — `typer.confirm(abort=True)` for `--review` pause
- https://peterforgacs.github.io/2018/05/20/Audio-normalization-with-ffmpeg/ — exact two-pass loudnorm command syntax

### Secondary (MEDIUM confidence)
- https://www.codestudy.net/blog/how-to-extract-time-accurate-video-segments-with-ffmpeg/ — `-ss` before `-i`, `-avoid_negative_ts make_zero`, re-encode for accuracy
- https://www.mux.com/articles/clip-sections-of-a-video-with-ffmpeg — FFmpeg segment extraction patterns
- Multiple sources on FFmpeg concat demuxer (mux.com, shotstack.io, cloudinary.com) — consistent `-f concat -safe 0 -i list.txt -c copy` syntax
- https://noamkroll.com/the-psychology-of-color-grading-its-emotional-impact-on-your-audience/ — genre-based color grading conventions
- Adobe Cube LUT Specification 1.0 (PDF, referenced from multiple sources) — .cube format: R fastest, B slowest; TITLE/LUT_3D_SIZE/DOMAIN_MIN/DOMAIN_MAX header
- https://luts.iwltbap.com/ and other LUT collection sites — confirmed no genre-organized free .cube library exists; programmatic generation is the right approach

### Tertiary (LOW confidence)
- Pacing cut duration tables (Act 1/2/3 seconds by genre) — derived from genre convention research; no single authoritative numeric source found. Values are design decisions documented here for consistency.
- LUFS targets by genre — the broadcast (-23 LUFS) and streaming (-14 LUFS) standards are HIGH confidence; the per-genre variations are LOW confidence design decisions.

---

## Metadata

**Confidence breakdown:**
- Standard stack (Pydantic, subprocess, NumPy): HIGH — verified against official docs and PyPI
- FFmpeg filter syntax (lut3d, loudnorm, concat): HIGH — verified against official FFmpeg filter docs
- .cube LUT format (header, loop order): MEDIUM — Adobe spec referenced but PDF unreadable; loop order confirmed from multiple secondary sources
- Vibe profiles (color params, LUFS, pacing): MEDIUM — genre conventions verified from cinematography sources; specific numeric values are design decisions
- Architecture patterns: HIGH — consistent with Phase 1 patterns in codebase

**Research date:** 2026-02-26
**Valid until:** 2026-05-26 (Pydantic stable; FFmpeg APIs are very stable)
