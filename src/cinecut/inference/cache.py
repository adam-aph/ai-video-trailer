"""msgpack-based SceneDescription cache for LLaVA inference persistence (IINF-01, IINF-02).

Cache file format
-----------------
The cache is stored as a msgpack-encoded dict with two top-level keys:

    {
        "metadata": {
            "source_file": "/abs/path/to/film.mkv",
            "mtime": 1709123456.789,   # float — source file last-modified time
            "size": 12345678901        # int — source file byte size
        },
        "results": [
            {
                "record": {
                    "timestamp_s": 12.5,
                    "frame_path": "/abs/path/to/keyframes/frame_012500.jpg",
                    "source": "subtitle_midpoint"
                },
                "description": {
                    "visual_content": "...",
                    "mood": "...",
                    "action": "...",
                    "setting": "..."
                } | null
            },
            ...
        ]
    }

Invalidation strategy
---------------------
The cache is keyed on (mtime, size) of the source video file — the two fields
returned by os.stat() that change whenever the file is replaced or modified.

If either value differs from the stored metadata, load_cache() returns None
(cache miss) and the caller must re-run inference. This prevents stale
SceneDescriptions from being used against a different source file.

Atomic write
------------
save_cache() follows the same pattern as checkpoint.py:save_checkpoint() —
tempfile.mkstemp() + os.write() + os.fsync() + os.close() + os.replace()
— so the cache file is either fully written or absent, never partially written.

Cache location
--------------
The cache file lives at: work_dir / "{source_file.stem}.scenedesc.msgpack"

Deleting the work directory also clears the cache. No global cache location
(e.g. ~/.cinecut/) is used.
"""

import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import msgpack

from cinecut.inference.models import SceneDescription
from cinecut.models import KeyframeRecord

# Public re-exports (what callers should import)
__all__ = ["save_cache", "load_cache"]


def _cache_path(source_file: Path, work_dir: Path) -> Path:
    """Return the canonical cache file path for the given source file.

    Args:
        source_file: Absolute path to the source video file.
        work_dir: Work directory created by _setup_work_dir().

    Returns:
        Path object pointing to <work_dir>/<source_stem>.scenedesc.msgpack.
    """
    return work_dir / f"{source_file.stem}.scenedesc.msgpack"


def save_cache(
    results: list[tuple[KeyframeRecord, Optional[SceneDescription]]],
    source_file: Path,
    work_dir: Path,
) -> Path:
    """Persist inference results to a msgpack cache file.

    Writes atomically using tempfile.mkstemp() + os.replace() so that
    the cache file is never left in a partially-written state.

    Args:
        results: List of (KeyframeRecord, SceneDescription | None) tuples
                 returned by run_inference_stage().
        source_file: Absolute path to the source video file. Its mtime and
                     size are embedded as invalidation metadata.
        work_dir: Work directory (parent of the cache file).

    Returns:
        Path to the written cache file.
    """
    stat = source_file.stat()

    payload: dict = {
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

    data = msgpack.packb(payload, use_bin_type=True)

    dest = _cache_path(source_file, work_dir)
    fd, tmp_path = tempfile.mkstemp(dir=work_dir, suffix=".cache.tmp")
    try:
        os.write(fd, data)
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp_path, dest)
    except Exception:
        os.close(fd)
        os.unlink(tmp_path)
        raise

    return dest


def load_cache(
    source_file: Path,
    work_dir: Path,
) -> Optional[list[tuple[KeyframeRecord, Optional[SceneDescription]]]]:
    """Load inference results from cache if valid, else return None.

    Performs mtime + size validation against the source file. Returns None
    (never raises) in the following cases:
        - Cache file does not exist (cache miss)
        - Cache metadata does not match current source file stat (invalidated)
        - Cache file is corrupt or unreadable (treated as cache miss)

    Always uses msgpack.unpackb(..., raw=False, strict_map_key=False) to
    avoid KeyError on bytes keys produced by raw=True mode.

    Args:
        source_file: Absolute path to the source video file.
        work_dir: Work directory containing the cache file.

    Returns:
        List of (KeyframeRecord, SceneDescription | None) tuples on a valid
        cache hit, or None on a miss/invalidation/corruption.
    """
    cache_file = _cache_path(source_file, work_dir)

    if not cache_file.exists():
        return None

    try:
        data = cache_file.read_bytes()
        payload = msgpack.unpackb(data, raw=False, strict_map_key=False)

        meta = payload["metadata"]
        stat = source_file.stat()

        # Validate mtime AND size — either change triggers a cache miss
        if meta["mtime"] != stat.st_mtime or meta["size"] != stat.st_size:
            return None

        results: list[tuple[KeyframeRecord, Optional[SceneDescription]]] = []
        for item in payload["results"]:
            record = KeyframeRecord(**item["record"])
            desc_data = item["description"]
            desc = SceneDescription(**desc_data) if desc_data is not None else None
            results.append((record, desc))

        return results

    except Exception:
        # Corrupt file, missing keys, type errors — all treated as cache miss
        return None
