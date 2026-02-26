# Phase 5: Trailer Assembly and End-to-End Pipeline - Research

**Researched:** 2026-02-26
**Domain:** FFmpeg 3-act video assembly, Python checkpoint/resume patterns, end-to-end pipeline orchestration
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EDIT-02 | System assembles clips according to a 3-act trailer structure: cold open, Act 1 setup, beat drop, Act 2 escalation, breath, Act 3 climax montage, title card, button | 3-act ordering is a pure Python sort/grouping step on existing ClipEntry.act labels; no new libraries needed; title card and button are generated FFmpeg black-screen segments |
| EDIT-03 | System implements pacing curves — average cut duration decreases from Act 1 to Act 3 per vibe-defined parameters | VibeProfile already has act1/act2/act3_avg_cut_s; the generator enforces durations via compute_clip_window; Phase 5 adds per-act average measurement and enforces vibe minimums on short clips |
| PIPE-04 | Pipeline persists stage-based checkpoint state files so a run can resume after failure without restarting from scratch | JSON checkpoint file written atomically after each stage completes; on startup, load checkpoint and skip completed stages; stdlib-only (json + tempfile + os.replace) |
</phase_requirements>

## Summary

Phase 5 wires together the existing pipeline stages (Phases 1-4) into a fully orchestrated end-to-end run, adds structural assembly logic for the 3-act trailer format, and introduces a checkpoint/resume system so a 30-60 minute pipeline survives power loss or OOM without restarting. All four phases before this one are complete and unit-tested. Phase 5 adds the "last mile" glue.

The manifest generator (`run_narrative_stage`) already assigns `act` labels to every ClipEntry (`cold_open`, `act1`, `beat_drop`, `act2`, `breath`, `act3`) and clips are written in chronological order. EDIT-02 requires enforcing the canonical 3-act ordering before conform, not just relying on chronological ordering. EDIT-03 requires that the final clip sequence demonstrably decreases average cut duration from Act 1 to Act 3 — this is already encoded in the vibe profiles but needs verification logic and a fallback enforcement pass. Both can be implemented as a new `cinecut/assembly/` package that takes a `TrailerManifest` and returns a reordered, potentially trimmed `TrailerManifest`.

PIPE-04 requires a checkpoint file written atomically after each stage completes. The canonical Python pattern is: write to a temp file, `os.replace()` to atomically swap into place. No third-party library is needed — stdlib `json`, `tempfile`, and `os.replace` cover this completely and correctly.

**Primary recommendation:** Add `cinecut/assembly/` package for 3-act reordering + pacing enforcement; add `cinecut/checkpoint.py` for atomic JSON stage-state; wire both into `cli.py` as Stage 6 (assembly) with checkpoint guards around every existing stage.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib: `json`, `os`, `tempfile` | stdlib | Atomic checkpoint read/write | No dependencies, `os.replace()` is POSIX-atomic, already used throughout project |
| FFmpeg (subprocess) | existing | Generate title-card/button black segments, concat | Already used for all conform work; `lavfi color` source generates black video |
| `pydantic` | >=2.12.0 (pinned) | Extend TrailerManifest or add AssemblyManifest | Already in pyproject.toml; validated by schema.py |
| `pytest` | existing | Unit tests for assembly + checkpoint modules | Existing test infrastructure, no new framework needed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses` (stdlib) | stdlib | Checkpoint dataclass for stage state | Same pattern as models.py; lightweight, no validation overhead at checkpoint layer |
| `subprocess` | stdlib | FFmpeg calls for title-card generation | Same pattern as conform/pipeline.py |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `os.replace()` atomic write | `atomicwrites` PyPI lib | `os.replace()` is sufficient on Linux (POSIX atomic); adding a dep is unnecessary overhead |
| Custom act-sort | Storing act-order index in schema | Implicit ordering by enum index is fragile; explicit sort by canonical list is clearer and safer |
| FFmpeg lavfi for title card | PIL/Pillow text-to-image | FFmpeg lavfi produces a video segment directly, no intermediate image file, correct codec/framerate guaranteed |

**Installation:**
```bash
# No new dependencies. All libraries already installed.
pip install -e .  # confirm existing env
```

## Architecture Patterns

### Recommended Project Structure
```
src/cinecut/
├── assembly/            # NEW: 3-act ordering and pacing enforcement (EDIT-02, EDIT-03)
│   ├── __init__.py
│   ├── ordering.py      # sort_clips_by_act(), enforce_pacing_curve()
│   └── title_card.py   # generate_title_card_clip(), generate_button_clip()
├── checkpoint.py        # NEW: atomic JSON checkpoint read/write (PIPE-04)
├── cli.py               # MODIFIED: checkpoint guards + Stage 6 assembly wiring
└── conform/
    └── pipeline.py      # UNCHANGED: conform_manifest() handles the graded clips
tests/
├── test_assembly.py     # NEW: unit tests for ordering + pacing
└── test_checkpoint.py   # NEW: unit tests for checkpoint save/load/resume
```

### Pattern 1: Atomic Checkpoint File (PIPE-04)

**What:** Write pipeline stage completion state to a JSON file atomically. On crash and restart, load checkpoint and skip completed stages.
**When to use:** Before and after every long-running stage in cli.py.
**Checkpoint file location:** `<work_dir>/pipeline_checkpoint.json`

```python
# src/cinecut/checkpoint.py
import json
import os
import tempfile
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


@dataclass
class PipelineCheckpoint:
    """Persisted state across all pipeline stages."""
    source_file: str
    vibe: str
    stages_complete: list[str] = field(default_factory=list)

    # Stage outputs (None until stage completes)
    proxy_path: Optional[str] = None
    keyframe_count: Optional[int] = None
    dialogue_event_count: Optional[int] = None
    inference_complete: Optional[bool] = None
    manifest_path: Optional[str] = None
    assembly_manifest_path: Optional[str] = None

    def is_stage_complete(self, stage: str) -> bool:
        return stage in self.stages_complete

    def mark_stage_complete(self, stage: str) -> None:
        if stage not in self.stages_complete:
            self.stages_complete.append(stage)


def load_checkpoint(work_dir: Path) -> Optional[PipelineCheckpoint]:
    """Load existing checkpoint from work_dir. Returns None if not found."""
    ckpt_path = work_dir / "pipeline_checkpoint.json"
    if not ckpt_path.exists():
        return None
    try:
        data = json.loads(ckpt_path.read_text(encoding="utf-8"))
        return PipelineCheckpoint(**data)
    except (json.JSONDecodeError, TypeError):
        return None  # Corrupt checkpoint: restart from scratch


def save_checkpoint(checkpoint: PipelineCheckpoint, work_dir: Path) -> None:
    """Atomically write checkpoint to work_dir/pipeline_checkpoint.json.

    Uses write-to-temp + os.replace() to guarantee atomicity on Linux.
    Power-loss safe: either the old file or the new file is visible, never a partial write.
    """
    ckpt_path = work_dir / "pipeline_checkpoint.json"
    data = json.dumps(asdict(checkpoint), indent=2)

    # Write to temp file in same directory (same filesystem = atomic rename guaranteed)
    fd, tmp_path = tempfile.mkstemp(dir=work_dir, suffix=".tmp")
    try:
        os.write(fd, data.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp_path, ckpt_path)  # POSIX-atomic on Linux
    except Exception:
        os.close(fd)
        os.unlink(tmp_path)
        raise
```

### Pattern 2: 3-Act Clip Ordering (EDIT-02)

**What:** Sort ClipEntry list into the canonical trailer act sequence, inserting generated segments for `title_card` and `button`.
**When to use:** After `run_narrative_stage()` produces a manifest, before `conform_manifest()`.

```python
# src/cinecut/assembly/ordering.py
from cinecut.manifest.schema import ClipEntry, TrailerManifest

# Canonical act order for a trailer.
# Acts not represented by any clips are silently skipped.
ACT_ORDER = [
    "cold_open",
    "act1",
    "beat_drop",
    "act2",
    "breath",
    "act3",
    "title_card",  # Generated segment, not from source film
    "button",      # Generated segment (optional stinger)
]


def sort_clips_by_act(clips: list[ClipEntry]) -> list[ClipEntry]:
    """Sort clips into canonical 3-act trailer order.

    Within the same act, preserve chronological order (source_start_s ascending).
    title_card and button entries are not present in the input clips list;
    they are injected by generate_title_card_clip() separately.
    """
    act_priority = {act: i for i, act in enumerate(ACT_ORDER)}
    return sorted(
        clips,
        key=lambda c: (act_priority.get(c.act, 999), c.source_start_s),
    )
```

### Pattern 3: Pacing Curve Enforcement (EDIT-03)

**What:** After act ordering, verify that average cut duration decreases from Act 1 to Act 3. If a vibe's act3 clips are too long (e.g., due to sparse selection), trim their windows.
**When to use:** After `sort_clips_by_act()`, before conforming.

```python
# src/cinecut/assembly/ordering.py (continued)
from cinecut.manifest.vibes import VibeProfile


def compute_act_avg_duration(clips: list[ClipEntry], act: str) -> float:
    """Return mean clip duration for a specific act. Returns 0.0 if no clips."""
    act_clips = [c for c in clips if c.act == act]
    if not act_clips:
        return 0.0
    return sum(c.source_end_s - c.source_start_s for c in act_clips) / len(act_clips)


def enforce_pacing_curve(
    clips: list[ClipEntry],
    profile: VibeProfile,
) -> list[ClipEntry]:
    """Trim clip durations to enforce act1 > act2 > act3 average cut length.

    If measured act3 avg duration exceeds profile.act3_avg_cut_s * 1.5,
    each act3 clip is trimmed to the profile target. Uses source_end_s adjustment
    since source_start_s is the anchor (30/70 bias in compute_clip_window).

    Min clip duration: 0.5s (never trim below 0.5s to avoid empty clips).
    """
    MIN_CLIP_DURATION = 0.5
    result = list(clips)
    for i, clip in enumerate(result):
        if clip.act == "act3":
            duration = clip.source_end_s - clip.source_start_s
            target = profile.act3_avg_cut_s
            if duration > target * 1.5:
                new_end = clip.source_start_s + max(target, MIN_CLIP_DURATION)
                # Pydantic ClipEntry is immutable; rebuild with model_copy
                result[i] = clip.model_copy(update={"source_end_s": new_end})
    return result
```

### Pattern 4: Title Card Generation (EDIT-02)

**What:** Generate a standalone black MP4 segment with `drawtext` for the title card slot. Written to `<work_dir>/title_card.mp4`.
**When to use:** After assembly ordering, before final concat.

The title card and button slots in ClipEntry.act are markers — they don't correspond to source film timecodes. The conform pipeline currently processes `clip.source_start_s / source_end_s` against the original film. Title card and button must be generated as separate pre-encoded segments and injected into the concat list.

**Strategy:** Generate title card as a pre-encoded 5-second black-with-title clip using FFmpeg lavfi. Inject its path into the concat list between act3 clips and any button clip.

```python
# src/cinecut/assembly/title_card.py
import subprocess
from pathlib import Path
from cinecut.errors import ConformError


def generate_title_card(
    title_text: str,
    width: int,
    height: int,
    duration_s: float,
    output_path: Path,
    font_size: int = 64,
) -> Path:
    """Generate a black title card clip with centered white text via FFmpeg lavfi.

    Args:
        title_text: Film title or blank for a plain black card.
        width: Video width in pixels (match source resolution).
        height: Video height in pixels.
        duration_s: Duration of the title card in seconds.
        output_path: Destination MP4 path.
        font_size: Text size in pixels.

    Returns:
        output_path on success.

    Raises:
        ConformError: If FFmpeg fails.
    """
    # drawtext filter: white centered text on black background
    # Use built-in FFmpeg font to avoid font-file dependency
    if title_text:
        vf = (
            f"color=c=black:s={width}x{height}:r=24,"
            f"drawtext=text='{title_text}':fontsize={font_size}"
            f":fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2"
        )
    else:
        vf = f"color=c=black:s={width}x{height}:r=24"

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", vf,
        "-t", str(duration_s),
        "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=stereo:sample_rate=48000",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-ar", "48000",
        "-t", str(duration_s),
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConformError(output_path, result.stderr[-500:])
    return output_path
```

### Pattern 5: Source Resolution Detection

**What:** Title card must match source resolution. Detect source video dimensions with `ffprobe` before generating the title card.

```python
import json
import subprocess
from pathlib import Path


def get_video_dimensions(source: Path) -> tuple[int, int]:
    """Return (width, height) of first video stream via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        str(source),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return (1920, 1080)  # safe fallback
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if streams:
        return (streams[0]["width"], streams[0]["height"])
    return (1920, 1080)
```

### Pattern 6: CLI Stage 6 — Assembly Wiring

**What:** Insert assembly step between manifest generation (Stage 5) and conform (existing). Checkpoint guards skip completed stages on resume.

The CLI currently has 5 numbered stages. Stage 6 is the new assembly step:
1. Proxy creation (Stage 1)
2. Subtitle parsing (Stage 2)
3. Keyframe extraction (Stage 3)
4. LLaVA inference (Stage 4)
5. Narrative manifest generation (Stage 5)
6. **[NEW] 3-act assembly and pacing enforcement (Stage 6)**
7. Conform (previously called "Stage 4" in the manifest-only path — renumber to Stage 7)

**Checkpoint guard pattern:**
```python
# At CLI startup
ckpt = load_checkpoint(work_dir) or PipelineCheckpoint(
    source_file=str(video), vibe=vibe_normalized
)

# Before each stage:
if not ckpt.is_stage_complete("proxy"):
    proxy_path = create_proxy(video, work_dir)
    ckpt.proxy_path = str(proxy_path)
    ckpt.mark_stage_complete("proxy")
    save_checkpoint(ckpt, work_dir)
else:
    proxy_path = Path(ckpt.proxy_path)
    console.print(f"[yellow]Resuming:[/] Stage 1 already complete (proxy: {proxy_path.name})")
```

### Anti-Patterns to Avoid

- **Relying on chronological sort for 3-act structure:** `run_narrative_stage()` sorts chronologically, but `cold_open` clips must come first regardless of source position. Explicit act-priority sort is required.
- **Single-pass loudnorm on title card:** Title card is a generated segment with silence; use `volume=0dB` (already the short-clip path in pipeline.py) or skip loudnorm entirely.
- **Writing checkpoint after partial stage work:** Only write checkpoint AFTER a stage fully completes. Writing mid-stage creates false "complete" signals.
- **Title card as a ClipEntry with source timecodes:** Title card has no source timecode. Do NOT add fake `source_start_s=0, source_end_s=5` to a ClipEntry — it will extract 5 seconds of film at timestamp 0 instead. Generate it separately.
- **`os.rename()` across filesystems:** Checkpoint temp file must be in the same directory (same filesystem) as the target for `os.replace()` to be atomic. Use `tempfile.mkstemp(dir=work_dir)`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic file write | Custom lock/write logic | `os.replace()` + `tempfile.mkstemp(dir=same_fs)` | POSIX guarantees atomicity; already proven pattern in all Unix tools |
| Video resolution detection | Parse ffmpeg output manually | `ffprobe -print_format json -show_streams` | Structured JSON output; handles all codecs, containers, rotation metadata |
| Title card video generation | PIL/Pillow image + video mux | FFmpeg lavfi `color` source + `drawtext` | Already in the FFmpeg subprocess path; guarantees codec/framerate match with clips |
| Clip duration enforcement | Re-running inference | Trim `source_end_s` in ClipEntry | Duration is just arithmetic on the existing timecode; no re-inference needed |
| 3-act ordering | Complex state machine | Sort by `ACT_ORDER` priority list | Clips already have `act` labels from Phase 4; sorting is O(n log n) |

**Key insight:** Phases 1-4 already solved the hard problems. Phase 5 is structural glue — sorting, arithmetic, JSON file I/O, and a few new FFmpeg subprocess calls.

## Common Pitfalls

### Pitfall 1: Title Card Injected as Source ClipEntry

**What goes wrong:** A `ClipEntry` with `act="title_card"` and `source_start_s=0, source_end_s=5` gets passed to `extract_and_grade_clip()`, which extracts 5 seconds from the beginning of the source film.
**Why it happens:** Forgetting that `title_card` and `button` are generated segments with no source timecode.
**How to avoid:** Never create ClipEntry objects for `title_card` or `button` acts. Keep them out of the manifest entirely. Generate them as pre-encoded files in `work_dir/` and inject paths into the FFmpeg concat list after act3 clips are processed.
**Warning signs:** Final trailer opens with the first 5 seconds of the film again after the climax.

### Pitfall 2: Checkpoint Written Before Stage Completion

**What goes wrong:** Checkpoint records Stage 3 as complete but the keyframe extraction loop was interrupted midway. On resume, Stage 3 is skipped but keyframes are missing.
**Why it happens:** Writing checkpoint optimistically at stage start instead of at stage end.
**How to avoid:** Write checkpoint only in the success path, after the stage function returns successfully. Never write in an exception handler.
**Warning signs:** Resume run crashes immediately on Stage 4 with missing keyframe files.

### Pitfall 3: Pacing Curve Not Measurable in Output

**What goes wrong:** EDIT-03 success criterion requires pacing curves to be "observable in output" — average cut duration must decrease from Act 1 to Act 3. But if sparse scene selection produces only 2 act3 clips with long durations, the curve inverts.
**Why it happens:** `run_narrative_stage()` selects top-N by money shot score regardless of act distribution. A film with few high-scoring late scenes produces under-populated act3.
**How to avoid:** In `enforce_pacing_curve()`, hard-trim act3 clips exceeding `profile.act3_avg_cut_s * 1.5`. Also add a verification assertion in tests: `act1_avg > act2_avg > act3_avg`.
**Warning signs:** Test `test_pacing_curve_decreasing()` fails with `act1_avg=4.1, act3_avg=5.3`.

### Pitfall 4: Corrupt Checkpoint on OOM Kill

**What goes wrong:** Python process is OOM-killed mid-write to checkpoint. JSON file is truncated/corrupt. Next run fails to load checkpoint and crashes instead of falling back to clean restart.
**Why it happens:** Trusting that `Path.write_text()` is atomic (it is not — it truncates then writes).
**How to avoid:** Always use `os.replace()` pattern. Add a `try/except` in `load_checkpoint()` that returns `None` on any parse error, triggering a clean restart.
**Warning signs:** `json.JSONDecodeError` during restart.

### Pitfall 5: Stage Count Mismatch in CLI Progress Messages

**What goes wrong:** CLI prints "Stage 4/4: Running FFmpeg conform..." but there are now 6 stages. Users see incorrect progress labels, which confuses human verify steps.
**Why it happens:** Stage numbers are hardcoded strings in cli.py prints.
**How to avoid:** Update all stage number strings in cli.py to match the new 6-stage pipeline: proxy(1), subtitles(2), keyframes(3), inference(4), narrative(5), assembly(6), conform(7). Or define `TOTAL_STAGES = 7` constant.
**Warning signs:** "Stage 4/4" appears before the final conform step.

### Pitfall 6: ffprobe Not Available

**What goes wrong:** `get_video_dimensions()` calls `ffprobe`, which may not be in PATH in some environments even when `ffmpeg` is.
**Why it happens:** `ffprobe` is a separate binary; some minimal FFmpeg installs omit it.
**How to avoid:** Check `ffprobe` at startup alongside `ffmpeg` (or use `ffmpeg -i` stderr output for dimension parsing as fallback). On this machine, both are confirmed available — but document the fallback.
**Warning signs:** `FileNotFoundError: [Errno 2] No such file or directory: 'ffprobe'`.

## Code Examples

Verified patterns from official sources and existing codebase:

### Atomic Checkpoint Write (stdlib pattern)
```python
# Source: POSIX spec (os.replace is atomic), stdlib docs
import json
import os
import tempfile
from pathlib import Path

def save_checkpoint(data: dict, work_dir: Path) -> None:
    ckpt_path = work_dir / "pipeline_checkpoint.json"
    encoded = json.dumps(data, indent=2).encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=work_dir, suffix=".ckpt.tmp")
    try:
        os.write(fd, encoded)
        os.fsync(fd)   # flush kernel buffer to disk
        os.close(fd)
        os.replace(tmp, ckpt_path)  # atomic on POSIX
    except Exception:
        os.close(fd)
        os.unlink(tmp)
        raise
```

### Generate Black Segment with lavfi (FFmpeg subprocess pattern)
```python
# Source: FFmpeg lavfi documentation + conform/pipeline.py patterns
import subprocess

cmd = [
    "ffmpeg", "-y",
    "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=24",
    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
    "-t", "5",
    "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
    "-c:a", "aac", "-ar", "48000",
    "title_card.mp4",
]
result = subprocess.run(cmd, capture_output=True, text=True, check=False)
```

### Act-Priority Sort
```python
# Source: project codebase (schema.py ClipEntry.act Literal)
ACT_ORDER = ["cold_open", "act1", "beat_drop", "act2", "breath", "act3"]
priority = {act: i for i, act in enumerate(ACT_ORDER)}

sorted_clips = sorted(
    clips,
    key=lambda c: (priority.get(c.act, 999), c.source_start_s)
)
```

### Pydantic model_copy for Immutable Updates
```python
# Source: Pydantic v2 docs — model_copy(update={...})
# ClipEntry is a Pydantic BaseModel (not frozen), so model_copy works:
trimmed_clip = clip.model_copy(update={"source_end_s": new_end})
```

### Resume Guard in CLI
```python
# Pattern for checkpoint-guarded stage execution
if not ckpt.is_stage_complete("proxy"):
    proxy_path = create_proxy(video, work_dir)
    ckpt.proxy_path = str(proxy_path)
    ckpt.mark_stage_complete("proxy")
    save_checkpoint(ckpt, work_dir)
    console.print(f"[green]Proxy ready: {proxy_path.name}")
else:
    proxy_path = Path(ckpt.proxy_path)
    console.print(f"[yellow]Skipping Stage 1:[/] proxy already exists ({proxy_path.name})")
```

### Verify Pacing Curve (Test Helper)
```python
def assert_pacing_curve(clips: list[ClipEntry]) -> None:
    """Assert act1 avg duration > act2 avg duration > act3 avg duration."""
    def avg(act: str) -> float:
        cs = [c for c in clips if c.act == act]
        return sum(c.source_end_s - c.source_start_s for c in cs) / len(cs) if cs else 0.0

    act1_avg = avg("act1")
    act2_avg = avg("act2")
    act3_avg = avg("act3")

    if act1_avg > 0 and act2_avg > 0:
        assert act1_avg >= act2_avg, f"Pacing curve violated: act1={act1_avg:.2f} < act2={act2_avg:.2f}"
    if act2_avg > 0 and act3_avg > 0:
        assert act2_avg >= act3_avg, f"Pacing curve violated: act2={act2_avg:.2f} < act3={act3_avg:.2f}"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Re-encode all clips at concat time | Concat demuxer (`-c copy`) when codecs match | FFmpeg 2.1+ | Zero-latency concat for pre-encoded clips |
| Shell-script pipeline with no state | Checkpoint JSON + `os.replace()` | Standard Python practice | Resumable without heavyweight workflow engine |
| Separate image → video conversion for title card | FFmpeg lavfi `color` source inline | FFmpeg 2.0+ | No PIL/Pillow dependency, guaranteed codec match |
| `Path.write_text()` for state files | `tempfile` + `os.replace()` | N/A (atomic always correct) | Power-loss safe; corrupt state file impossible |

**Deprecated/outdated:**
- Using `os.rename()` without same-filesystem check: on systems where `work_dir` is on a different mount from `/tmp`, `tempfile.NamedTemporaryFile()` without `dir=work_dir` will fail with `EXDEV` (cross-device link). Always pass `dir=work_dir` to `tempfile.mkstemp()`.

## Open Questions

1. **Does the conform pipeline need to be refactored to accept a pre-ordered clip list?**
   - What we know: `conform_manifest()` iterates `manifest.clips` in the order given; it does not enforce act order itself.
   - What's unclear: Whether to (a) mutate `manifest.clips` in place before calling `conform_manifest()`, or (b) create a new `TrailerManifest` with reordered clips, or (c) add an `ordered_clips` parameter.
   - Recommendation: Create a new `TrailerManifest` with reordered clips (option b). This keeps `conform_manifest()` unchanged, preserves immutability, and the reordered manifest can be written to `work_dir/ASSEMBLY_MANIFEST.json` for inspection/debugging.

2. **Title card text: what to display?**
   - What we know: EDIT-02 success criterion mentions "title card" as a structural position. The system has the source file name available.
   - What's unclear: Whether to display the film title (derived from filename), a blank black frame, or a placeholder. No requirement specifies text content.
   - Recommendation: Default to a plain black frame (no text) for Phase 5. Title text extraction from filename can be a simple enhancement if desired. A blank title card satisfies the structural requirement.

3. **Does the button (stinger) slot need to be populated?**
   - What we know: `button` is listed in the `ClipEntry.act` Literal in schema.py, and in EDIT-02 success criteria.
   - What's unclear: Whether Phase 5 needs a real "button" clip (a joke/stinger after title card) or just a 2-second black fade-out.
   - Recommendation: Implement button as a 2-second black fade-out segment generated by FFmpeg lavfi, identical to the title card pattern but shorter. This satisfies the structural requirement without requiring narrative selection of a button clip.

4. **Checkpoint invalidation: what happens when the source file changes?**
   - What we know: Checkpoint stores `source_file` path. If the user re-runs with a different source, the work directory may still contain a stale checkpoint.
   - What's unclear: Whether to validate that checkpoint.source_file == current video path.
   - Recommendation: On `load_checkpoint()`, validate that `ckpt.source_file == str(video)`. If mismatch, log a warning and ignore the checkpoint (start fresh).

## Sources

### Primary (HIGH confidence)
- Existing project codebase (`src/cinecut/`) — direct inspection of conform/pipeline.py, narrative/generator.py, manifest/schema.py, manifest/vibes.py, cli.py, errors.py, models.py
- POSIX spec for `os.replace()` atomicity — documented in Python stdlib docs (rename(2) is atomic on POSIX)
- FFmpeg lavfi color source — documented in FFmpeg formats documentation

### Secondary (MEDIUM confidence)
- [FFmpeg Formats Documentation](https://ffmpeg.org/ffmpeg-formats.html) — concat demuxer and lavfi source details
- [Python os.replace() docs](https://docs.python.org/3/library/os.html#os.replace) — POSIX atomicity guarantee
- [atomicwrites README](https://github.com/untitaker/python-atomicwrites) — confirmed `os.replace()` pattern is canonical and sufficient

### Tertiary (LOW confidence)
- WebSearch results for FFmpeg drawtext title card — patterns verified against FFmpeg filter docs structure but not Context7-validated

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries are already in pyproject.toml; no new dependencies needed
- Architecture: HIGH — direct inspection of existing code confirms extension points (conform_manifest, TrailerManifest, ClipEntry); patterns derived from existing codebase conventions
- Pitfalls: HIGH — most are derived from direct code reading (title_card as ClipEntry, checkpoint timing); one (ffprobe availability) is MEDIUM from system knowledge

**Research date:** 2026-02-26
**Valid until:** 2026-03-28 (stable domain; FFmpeg APIs and Python stdlib are highly stable)
