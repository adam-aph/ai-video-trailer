"""Unit tests for cinecut.inference.cache — msgpack-based SceneDescription persistence.

All tests use tmp_path (pytest's built-in temp directory fixture) for file I/O.
No real model files are required — all tests are pure unit tests.
"""

from pathlib import Path

import pytest

from cinecut.inference.cache import save_cache, load_cache
from cinecut.inference.models import SceneDescription
from cinecut.models import KeyframeRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_record(ts: float, tmp_path: Path) -> KeyframeRecord:
    """Create a fake JPEG file and return a KeyframeRecord pointing to it."""
    f = tmp_path / f"frame_{int(ts * 1000):06d}.jpg"
    f.write_bytes(b"\xff\xd8\xff")  # minimal fake JPEG header
    return KeyframeRecord(timestamp_s=ts, frame_path=str(f), source="subtitle_midpoint")


def make_desc() -> SceneDescription:
    """Return a populated SceneDescription for testing."""
    return SceneDescription(
        visual_content="forest",
        mood="tense",
        action="running",
        setting="night",
    )


def make_source_file(tmp_path: Path, name: str = "film.mkv") -> Path:
    """Create a fake source video file and return its path."""
    src = tmp_path / name
    src.write_bytes(b"\x00" * 1024)  # 1 KiB of zeros — valid for stat()
    return src


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    """Save a list of (record, desc) tuples and load them back; all fields equal."""
    src = make_source_file(tmp_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # 3 records: two with descriptions, one with None
    records = [
        (make_record(1.0, tmp_path), make_desc()),
        (make_record(2.5, tmp_path), make_desc()),
        (make_record(3.75, tmp_path), None),
    ]

    save_cache(records, src, work_dir)
    loaded = load_cache(src, work_dir)

    assert loaded is not None
    assert len(loaded) == len(records)

    for (orig_rec, orig_desc), (load_rec, load_desc) in zip(records, loaded):
        assert load_rec.timestamp_s == orig_rec.timestamp_s
        assert load_rec.frame_path == orig_rec.frame_path
        assert load_rec.source == orig_rec.source

        if orig_desc is None:
            assert load_desc is None
        else:
            assert load_desc is not None
            assert load_desc.visual_content == orig_desc.visual_content
            assert load_desc.mood == orig_desc.mood
            assert load_desc.action == orig_desc.action
            assert load_desc.setting == orig_desc.setting


def test_cache_hit_returns_list(tmp_path: Path) -> None:
    """load_cache() on a valid, matching cache file returns a non-None list."""
    src = make_source_file(tmp_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    records = [
        (make_record(0.5, tmp_path), make_desc()),
        (make_record(1.0, tmp_path), make_desc()),
        (make_record(2.0, tmp_path), make_desc()),
    ]

    save_cache(records, src, work_dir)
    result = load_cache(src, work_dir)

    assert result is not None
    assert isinstance(result, list)
    assert len(result) == len(records)


def test_cache_miss_no_file(tmp_path: Path) -> None:
    """load_cache() with no cache file present returns None (no exception raised)."""
    src = make_source_file(tmp_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # No save_cache() call — cache file does not exist
    result = load_cache(src, work_dir)

    assert result is None


def test_cache_invalidated_mtime_change(tmp_path: Path) -> None:
    """Cache saved for source_a is invalidated when loaded with source_b (different mtime)."""
    # Strategy: save cache for source_a, then call load_cache with source_b
    # (a different file with different mtime/size). The metadata won't match → None.
    source_a = tmp_path / "film_a.mkv"
    source_a.write_bytes(b"\x00" * 512)

    source_b = tmp_path / "film_b.mkv"
    source_b.write_bytes(b"\x00" * 512)
    # Patch mtime to be different from source_a
    import os
    stat_a = source_a.stat()
    os.utime(source_b, (stat_a.st_atime + 1000, stat_a.st_mtime + 1000))

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Save cache keyed on source_a; but the cache filename uses source_a's stem
    # For the load to even find the file, both source files must have the same stem.
    # Use a single stem approach: save for source_a, then rename source_b to same stem
    # but that won't work either — let's use a proper approach:
    # Save with source_a, then overwrite mtime to differ using os.utime on source_a.

    # Cleaner approach: save cache, then modify source_a's mtime so stat differs.
    save_cache(
        [(make_record(1.0, tmp_path), make_desc())],
        source_a,
        work_dir,
    )
    # Now shift source_a mtime forward so stat doesn't match stored metadata
    stat = source_a.stat()
    os.utime(source_a, (stat.st_atime + 3600, stat.st_mtime + 3600))

    result = load_cache(source_a, work_dir)

    assert result is None


def test_cache_invalidated_size_change(tmp_path: Path) -> None:
    """Cache is invalidated after writing extra bytes to the source file (size change)."""
    src = make_source_file(tmp_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    records = [(make_record(1.0, tmp_path), make_desc())]
    save_cache(records, src, work_dir)

    # Append bytes to change the real file size
    with src.open("ab") as f:
        f.write(b"\xde\xad\xbe\xef" * 64)  # +256 bytes

    result = load_cache(src, work_dir)

    assert result is None


def test_corrupt_cache_returns_none(tmp_path: Path) -> None:
    """A corrupt cache file (.scenedesc.msgpack with garbage bytes) returns None."""
    src = make_source_file(tmp_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Write garbage directly to the expected cache path
    cache_file = work_dir / f"{src.stem}.scenedesc.msgpack"
    cache_file.write_bytes(b"\xde\xad\xbe\xef\x00\x01garbage\x80\x99\xff")

    result = load_cache(src, work_dir)

    assert result is None


def test_cache_file_location(tmp_path: Path) -> None:
    """save_cache() writes to work_dir/<stem>.scenedesc.msgpack — no global location."""
    src = make_source_file(tmp_path, name="mymovie.mkv")
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    returned_path = save_cache(
        [(make_record(1.0, tmp_path), make_desc())],
        src,
        work_dir,
    )

    expected = work_dir / "mymovie.scenedesc.msgpack"
    assert returned_path == expected
    assert returned_path.exists()
    # Must NOT be in ~/.cinecut/ or any user-level location
    assert str(returned_path).startswith(str(tmp_path))


def test_none_description_survives_roundtrip(tmp_path: Path) -> None:
    """A result tuple (record, None) saves and loads back as (record, None) without TypeError."""
    src = make_source_file(tmp_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    record = make_record(5.0, tmp_path)
    results = [(record, None)]

    # Must not raise TypeError from asdict(None)
    save_cache(results, src, work_dir)
    loaded = load_cache(src, work_dir)

    assert loaded is not None
    assert len(loaded) == 1
    loaded_record, loaded_desc = loaded[0]
    assert loaded_desc is None
    assert loaded_record.timestamp_s == record.timestamp_s
