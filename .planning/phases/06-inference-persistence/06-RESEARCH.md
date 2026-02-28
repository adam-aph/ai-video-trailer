# Phase 6: Inference Persistence - Research

**Researched:** 2026-02-28
**Domain:** Python binary serialization (msgpack), cache invalidation, pipeline checkpoint integration
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| IINF-01 | Pipeline resume skips LLaVA inference when a valid SceneDescription cache exists for the source file | Cache module loads `.scenedesc.msgpack`, checks validity, returns `list[tuple[KeyframeRecord, SceneDescription|None]]`; CLI Stage 4 guarded by cache hit check |
| IINF-02 | SceneDescription cache is automatically invalidated when source file mtime or size changes | `os.stat()` captures `st_mtime` + `st_size` at write time; loaded cache metadata compared against current stat before any use |
</phase_requirements>

---

## Summary

Phase 6 adds a single new module (`inference/cache.py`) that wraps the LLaVA inference results in a msgpack binary cache file stored alongside the checkpoint directory. The cache is keyed on the source video's mtime and size so it self-invalidates when the film file changes. The existing CLI Stage 4 block (lines 305-338 in `cli.py`) already contains a `# TODO: inference resume requires persisting SceneDescription results; deferred to v2` marker — Phase 6 replaces that TODO with a load-from-cache guard that skips `run_inference_stage()` entirely on a hit.

The technical surface is narrow: msgpack 1.1.2 (pure pip install, no system deps), `os.stat()` for invalidation metadata, and a `dataclasses.asdict()`-compatible serialization pathway for `SceneDescription`. No new architectural concepts are required; this phase extends the existing checkpoint/resume pattern already proven in Phases 1-5.

The Stage 5 checkpoint guard (mentioned in the roadmap plan) prevents narrative generation from running if inference was skipped via a stale (invalid) cache — the checkpoint's `stages_complete` list already handles this naturally: if Stage 4 is bypassed with a cache hit, it is still marked complete (with a cache-hit flag in the checkpoint), so Stage 5 proceeds normally.

**Primary recommendation:** Implement `inference/cache.py` with `save_cache()` / `load_cache()` using `msgpack.packb` / `msgpack.unpackb`, store cache as `<work_dir>/<source_stem>.scenedesc.msgpack`, embed `{"mtime": float, "size": int}` as metadata in the packed payload, and add a 10-line guard at Stage 4 in `cli.py`.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| msgpack | 1.1.2 | Binary serialization of `list[tuple[KeyframeRecord, SceneDescription\|None]]` | Faster and smaller than JSON; binary-safe for embedded metadata; already in roadmap plan |
| Python stdlib: `os.stat` | stdlib | Read `st_mtime` (float) + `st_size` (int) for invalidation | No external dep; POSIX-standard; sub-millisecond precision sufficient |
| Python stdlib: `dataclasses.asdict` | stdlib | Serialize `SceneDescription` dataclass to dict for msgpack | Already used in `checkpoint.py` (same pattern) |
| Python stdlib: `pathlib.Path` | stdlib | Cache file path construction alongside work_dir | Project-wide convention |
| Python stdlib: `tempfile` + `os.replace` | stdlib | Atomic cache write | Same atomicity pattern as `save_checkpoint()` in `checkpoint.py` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Rich console | 13.x (already installed) | "Cache hit" / "Cache miss" / "Cache invalidated" status messages | Used in all other Stage resume messages in `cli.py` |
| pytest | 9.0.2 (already installed) | Unit tests for `inference/cache.py` | All existing stages tested with pytest |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| msgpack | pickle | pickle is faster to implement but unsafe to load untrusted data; msgpack is portable across Python versions and doesn't allow arbitrary code execution |
| msgpack | json | JSON cannot store binary types cleanly and is ~3-5x larger than msgpack for this data shape; roadmap explicitly specifies msgpack |
| msgpack | shelve / sqlite | Overkill for a single flat list of records; adds complexity with no benefit |
| os.stat mtime+size | content hash (SHA256) | Hash requires reading entire film (30-60min re-hash penalty); mtime+size is instant and sufficient for detecting file replacement or modification |

**Installation:**
```bash
pip install msgpack
```

Add to `pyproject.toml` dependencies:
```
"msgpack>=1.1.0",
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/cinecut/
├── inference/
│   ├── __init__.py         # (existing) GPU_LOCK, LlavaEngine exports
│   ├── engine.py           # (existing) run_inference_stage()
│   ├── models.py           # (existing) SceneDescription dataclass
│   ├── vram.py             # (existing) VRAM check
│   └── cache.py            # NEW: save_cache(), load_cache(), invalidate_cache()
├── checkpoint.py           # (existing) PipelineCheckpoint — add cache_hit field
└── cli.py                  # (existing) Stage 4 guard added here
```

### Pattern 1: Cache Payload Schema

**What:** The `.scenedesc.msgpack` file stores a single msgpack-packed dict with two keys: `metadata` (invalidation data) and `results` (the inference output list).

**When to use:** Always — this schema allows the loader to verify invalidation before deserializing the full results.

```python
# Source: msgpack 1.1.2 official docs (https://github.com/msgpack/msgpack-python)

import msgpack
import os
from dataclasses import asdict
from pathlib import Path

CACHE_SUFFIX = ".scenedesc.msgpack"

def _cache_path(work_dir: Path, source_file: Path) -> Path:
    return work_dir / f"{source_file.stem}{CACHE_SUFFIX}"

def save_cache(
    results: list,           # list[tuple[KeyframeRecord, SceneDescription | None]]
    source_file: Path,
    work_dir: Path,
) -> Path:
    """Atomically write inference cache to disk."""
    stat = source_file.stat()
    payload = {
        "metadata": {
            "source_file": str(source_file),
            "mtime": stat.st_mtime,
            "size": stat.st_size,
        },
        "results": [
            {
                "record": asdict(record),
                "description": asdict(desc) if desc is not None else None,
            }
            for record, desc in results
        ],
    }
    cache_path = _cache_path(work_dir, source_file)
    packed = msgpack.packb(payload, use_bin_type=True)
    # Atomic write using same pattern as save_checkpoint()
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=work_dir, suffix=".cache.tmp")
    try:
        os.write(fd, packed)
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp, cache_path)
    except Exception:
        os.close(fd)
        os.unlink(tmp)
        raise
    return cache_path
```

### Pattern 2: Cache Load with Invalidation Check

**What:** Load the cache file, verify mtime+size match current source file stat, reconstruct dataclasses from dicts.

**When to use:** At Stage 4 entry in `cli.py` before calling `run_inference_stage()`.

```python
# Source: msgpack 1.1.2 official docs + os.stat stdlib

from cinecut.inference.models import SceneDescription
from cinecut.models import KeyframeRecord

def load_cache(
    source_file: Path,
    work_dir: Path,
) -> list | None:
    """Return cached results if valid, else None.

    Returns None if:
      - Cache file does not exist
      - Cache file is corrupt (unpack error)
      - Source file mtime or size has changed
    """
    cache_path = _cache_path(work_dir, source_file)
    if not cache_path.exists():
        return None
    try:
        raw = msgpack.unpackb(cache_path.read_bytes(), raw=False, strict_map_key=False)
    except Exception:
        return None  # Corrupt cache — treat as miss

    meta = raw.get("metadata", {})
    stat = source_file.stat()
    if meta.get("mtime") != stat.st_mtime or meta.get("size") != stat.st_size:
        return None  # Invalidated — source file changed

    results = []
    for item in raw.get("results", []):
        record = KeyframeRecord(**item["record"])
        desc_data = item.get("description")
        desc = SceneDescription(**desc_data) if desc_data is not None else None
        results.append((record, desc))
    return results
```

### Pattern 3: CLI Stage 4 Guard

**What:** At Stage 4 entry, attempt `load_cache()`. On hit, print Rich "cache hit" message and skip `run_inference_stage()`. On miss, run inference then call `save_cache()`.

**When to use:** Replaces the existing TODO comment in `cli.py` lines 305-338.

```python
# Source: project cli.py pattern (existing Stage resume pattern)

# --- Stage 4/7: LLaVA Inference (INFR-01, IINF-01, IINF-02) ---
from cinecut.inference.cache import load_cache, save_cache

console.print(f"[bold]Stage 4/{TOTAL_STAGES}:[/bold] LLaVA inference...")
cached_results = load_cache(video, work_dir)

if cached_results is not None:
    # IINF-01: cache hit — skip inference entirely
    inference_results = cached_results
    console.print(
        f"[yellow]Cache hit:[/] Loaded {len(inference_results)} SceneDescriptions "
        f"from cache — LLaVA inference skipped\n"
    )
else:
    # Cache miss or invalidated (IINF-02) — run inference and write cache
    with Progress(...) as progress:
        inference_results = run_inference_stage(
            keyframe_records, model, mmproj,
            progress_callback=_progress_callback,
        )
    save_cache(inference_results, video, work_dir)
    console.print(f"[green]Inference complete:[/] cache written\n")

skipped = sum(1 for _, desc in inference_results if desc is None)
ckpt.inference_complete = True
save_checkpoint(ckpt, work_dir)
```

### Pattern 4: PipelineCheckpoint Extension

**What:** Add a `cache_hit: Optional[bool]` field to `PipelineCheckpoint` so checkpoint state reflects whether inference was served from cache. This is cosmetic for observability but consistent with the existing `inference_complete` field.

**When to use:** When saving checkpoint after Stage 4.

```python
# In checkpoint.py — add to PipelineCheckpoint dataclass:
cache_hit: Optional[bool] = None
```

### Anti-Patterns to Avoid

- **Store cache in a different directory than work_dir:** The cache must live alongside the checkpoint directory (`<source_stem>_cinecut_work/`) so that clearing the work directory also clears the cache. Do not put it in `~/.cinecut/` — that would outlive work directories.
- **Use source file path as the only cache key:** Path alone does not detect file replacement. Always compare both `st_mtime` AND `st_size`.
- **Raise on corrupt cache:** `load_cache()` must return `None` on any unpack error — never propagate exceptions to the pipeline. Corrupt cache = cache miss.
- **Use `strict_map_key=True` (default) when unpacking nested string keys:** With `raw=False` and `strict_map_key=False`, string keys in nested dicts are decoded normally. With `strict_map_key=True`, only `str` or `bytes` keys are allowed — this is fine here but must be explicitly set to avoid surprises.
- **Read the entire source film to compute a hash:** Content hashing a 20-40GB MKV defeats the purpose of the cache. `os.stat()` is O(1).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Binary serialization of nested dicts | Custom binary format | `msgpack.packb` / `msgpack.unpackb` | msgpack handles all Python primitives, None, nested dicts/lists; no edge cases to worry about |
| Atomic file write | Manual temp-file logic | Reuse the `tempfile.mkstemp` + `os.replace` pattern from `checkpoint.py` | Already battle-tested in the project; POSIX atomic on same filesystem mount |
| Cache invalidation logic | Timestamp comparison | `os.stat().st_mtime` + `st_size` comparison | Sub-millisecond precision; `st_mtime` is float on Linux (nanosecond resolution on ext4) |
| Dataclass serialization | Custom `__dict__` walk | `dataclasses.asdict()` | Recursive, handles nested dataclasses; already used in `checkpoint.py` |

**Key insight:** The entire cache module is under 80 lines. Any hand-rolled serialization format would be longer and less robust than delegating to msgpack.

---

## Common Pitfalls

### Pitfall 1: Cache stored in wrong location

**What goes wrong:** Cache file written to a user-global location (e.g. `~/.cinecut/`) survives work directory cleanup, causing stale cache hits after the user deletes the work directory and re-runs with the same film.

**Why it happens:** Conflating "persistent across runs" (correct) with "persistent across work directories" (wrong).

**How to avoid:** Store cache at `work_dir / f"{source_file.stem}.scenedesc.msgpack"`. Work dir is always alongside the source file and named deterministically.

**Warning signs:** Cache hit reported after user manually deleted the work directory.

### Pitfall 2: mtime precision mismatch on copy

**What goes wrong:** User copies the source file (e.g. `cp film.mkv film2.mkv`). `cp` preserves mtime by default on many systems. A cache built for `film.mkv` could incorrectly validate for `film2.mkv` if both land in the same work directory.

**Why it happens:** Cache key uses mtime + size; copy may preserve both.

**How to avoid:** This is acceptable behavior — the data in the copied file is identical, so the cache is actually correct. Document this in a code comment. The cache is additionally keyed on `work_dir` (which is named after the source file stem), so `film2.mkv` would have its own `film2_cinecut_work/` directory and therefore its own cache namespace.

**Warning signs:** None — this is expected behavior, not a bug.

### Pitfall 3: msgpack key decoding with `raw=False`

**What goes wrong:** Dictionary keys come back as `str` when `raw=False` (default). If packed with `use_bin_type=True` and unpacked without `raw=False`, keys arrive as `bytes`.

**Why it happens:** msgpack has two modes: legacy (raw strings default) and new spec (bin type). Mixing modes causes `KeyError` on unpack.

**How to avoid:** Always specify `use_bin_type=True` on `packb` and `raw=False` on `unpackb`. These are the modern defaults in msgpack >= 1.0 but spell them out explicitly for clarity.

**Warning signs:** `KeyError: b'metadata'` instead of `KeyError: 'metadata'` during unpack.

### Pitfall 4: Inference results contain `None` descriptions

**What goes wrong:** `SceneDescription` is `None` for frames that LLaVA failed to describe. If the serializer tries `asdict(None)`, it raises `TypeError`.

**Why it happens:** `run_inference_stage()` returns `None` for failed frames (by design, see `describe_frame()` docstring).

**How to avoid:** In `save_cache()`, use `asdict(desc) if desc is not None else None`. In `load_cache()`, use `SceneDescription(**desc_data) if desc_data is not None else None`.

**Warning signs:** `TypeError: asdict() should be called on dataclass instances` during save.

### Pitfall 5: Stage 5 (narrative) runs on stale keyframe_records after cache miss

**What goes wrong:** On a cache miss (e.g. after source file change), keyframe extraction re-runs correctly. But `inference_results` now contains results for the NEW keyframes while the checkpoint's `narrative` stage was previously marked complete for OLD keyframes.

**Why it happens:** mtime invalidation clears the inference cache but does NOT automatically clear Stage 5's checkpoint guard.

**How to avoid:** When `load_cache()` returns `None` AND the source file's mtime/size has changed, also invalidate the `narrative` and `assembly` stages in the checkpoint (remove them from `stages_complete`). This is a checkpoint cascade reset for source-file changes.

**Warning signs:** Manifest references frame timestamps that no longer exist in the keyframe directory.

---

## Code Examples

Verified patterns from official sources:

### msgpack pack + unpack with nested dicts

```python
# Source: https://github.com/msgpack/msgpack-python (v1.1.2, October 2025)
import msgpack

# Pack
payload = {"metadata": {"mtime": 1706000000.0, "size": 42000000}, "results": []}
packed = msgpack.packb(payload, use_bin_type=True)

# Unpack — raw=False decodes bytes keys as str
data = msgpack.unpackb(packed, raw=False, strict_map_key=False)
assert data["metadata"]["mtime"] == 1706000000.0
```

### File-based atomic write (existing project pattern)

```python
# Source: cinecut/checkpoint.py (project, Phase 5)
import os, tempfile

fd, tmp_path = tempfile.mkstemp(dir=work_dir, suffix=".cache.tmp")
try:
    os.write(fd, packed)
    os.fsync(fd)
    os.close(fd)
    os.replace(tmp_path, cache_path)
except Exception:
    os.close(fd)
    os.unlink(tmp_path)
    raise
```

### Source file stat for invalidation

```python
# Source: Python stdlib os.stat documentation
import os
from pathlib import Path

stat = Path("/films/movie.mkv").stat()
# st_mtime: float (seconds since epoch, nanosecond precision on ext4)
# st_size: int (bytes)
mtime = stat.st_mtime   # e.g. 1706000000.123456789
size = stat.st_size     # e.g. 42000000000
```

### dataclasses.asdict for SceneDescription

```python
# Source: Python stdlib dataclasses (used in checkpoint.py same project)
from dataclasses import asdict
from cinecut.inference.models import SceneDescription

desc = SceneDescription(
    visual_content="dark forest",
    mood="tense",
    action="man running",
    setting="night woods",
)
d = asdict(desc)
# {'visual_content': 'dark forest', 'mood': 'tense', 'action': 'man running', 'setting': 'night woods'}
restored = SceneDescription(**d)
```

### Rich cache-hit message (matching project CLI convention)

```python
# Source: cinecut/cli.py existing resume messages
console.print(
    f"[yellow]Cache hit:[/] Loaded {len(inference_results)} SceneDescriptions "
    f"from [dim]{cache_path.name}[/dim] — LLaVA inference skipped\n"
)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `msgpack-python` package name | `msgpack` package name | v0.5 (several years ago) | `pip install msgpack` (not `pip install msgpack-python`) |
| `raw=True` default (bytes keys) | `raw=False` default (str keys) in modern usage | msgpack 1.0 | Always specify `raw=False` on unpack for string keys |
| Stage 4 always re-runs inference | Stage 4 skipped on cache hit (Phase 6) | This phase | 30-60 minute time saving on resume |

**Deprecated/outdated:**
- `msgpack-python`: Old package name — do not use. Install `msgpack` instead.
- `use_bin_type=False` (legacy raw mode): Only needed for compatibility with very old msgpack implementations. Not needed here.

---

## Open Questions

1. **Float mtime precision on NFS/network filesystems**
   - What we know: `os.stat().st_mtime` is float with nanosecond precision on ext4/ext3. NFS may round to second precision.
   - What's unclear: Whether this project is ever run against network-mounted film files.
   - Recommendation: Compare with `==` (not `math.isclose`). If NFS is ever used, users can manually delete the cache to force re-inference. Document in code comment.

2. **Cache invalidation cascade when source file changes (Pitfall 5)**
   - What we know: The checkpoint stores `stages_complete` as a list. If the source changes, `narrative` and `assembly` stages are stale.
   - What's unclear: Whether the plan should actively remove stale stages from `stages_complete` or rely on the user starting fresh.
   - Recommendation: The planner should include a task to clear `narrative` and `assembly` from `stages_complete` when `load_cache()` returns `None` due to mtime/size mismatch (as distinct from "cache file doesn't exist yet").

---

## Validation Architecture

> `workflow.nyquist_validation` is not present in `.planning/config.json` — skip this section.

*(config.json has `workflow.research`, `workflow.plan_check`, and `workflow.verifier` but no `nyquist_validation` key. Validation section omitted.)*

---

## Sources

### Primary (HIGH confidence)

- msgpack 1.1.2 GitHub README — https://github.com/msgpack/msgpack-python — installation, `packb`/`unpackb` API, `use_bin_type`, `raw` parameters
- msgpack 1.0 API reference docs — https://msgpack-python.readthedocs.io/en/latest/api.html — `packb`, `unpackb`, `pack`, `unpack` signatures and key parameters
- Project source: `src/cinecut/checkpoint.py` — atomic write pattern with `tempfile.mkstemp` + `os.replace`
- Project source: `src/cinecut/cli.py` — existing Stage resume guards, Rich output convention
- Project source: `src/cinecut/inference/models.py` — `SceneDescription` dataclass fields
- Project source: `src/cinecut/models.py` — `KeyframeRecord` dataclass fields
- Python stdlib: `os.stat`, `dataclasses.asdict`, `pathlib.Path` — no citation needed

### Secondary (MEDIUM confidence)

- msgpack v1.1.2 confirmed as October 8, 2025 release via GitHub (verified via WebFetch)

### Tertiary (LOW confidence)

- NFS mtime precision behavior — training data knowledge, not verified against production NFS implementations

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — msgpack API verified against official docs and GitHub README; all other libraries are stdlib or already-installed project deps
- Architecture: HIGH — cache module design mirrors existing `checkpoint.py` pattern already proven in the project; no novel patterns
- Pitfalls: HIGH — pitfalls derived from direct code inspection of `cli.py` TODO comment, `engine.py` None-return behavior, and msgpack key encoding docs

**Research date:** 2026-02-28
**Valid until:** 2026-03-30 (msgpack is stable; stdlib patterns are permanent)
