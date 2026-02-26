"""Unit tests for pipeline checkpoint — PIPE-04."""
import json
import tempfile
from pathlib import Path
import pytest
from cinecut.checkpoint import PipelineCheckpoint, load_checkpoint, save_checkpoint, CHECKPOINT_FILENAME


class TestPipelineCheckpoint:
    """PipelineCheckpoint dataclass behavior."""

    def test_initial_stages_complete_empty(self):
        ckpt = PipelineCheckpoint(source_file="/tmp/film.mkv", vibe="action")
        assert ckpt.stages_complete == []

    def test_mark_stage_complete_appends(self):
        ckpt = PipelineCheckpoint(source_file="/tmp/film.mkv", vibe="action")
        ckpt.mark_stage_complete("proxy")
        assert ckpt.is_stage_complete("proxy")

    def test_mark_stage_complete_idempotent(self):
        ckpt = PipelineCheckpoint(source_file="/tmp/film.mkv", vibe="action")
        ckpt.mark_stage_complete("proxy")
        ckpt.mark_stage_complete("proxy")
        assert ckpt.stages_complete.count("proxy") == 1

    def test_is_stage_complete_false_for_unknown(self):
        ckpt = PipelineCheckpoint(source_file="/tmp/film.mkv", vibe="action")
        assert not ckpt.is_stage_complete("inference")


class TestLoadCheckpoint:
    """load_checkpoint() behavior."""

    def test_missing_checkpoint_returns_none(self, tmp_path):
        assert load_checkpoint(tmp_path) is None

    def test_corrupt_json_returns_none(self, tmp_path):
        (tmp_path / CHECKPOINT_FILENAME).write_text("{broken", encoding="utf-8")
        assert load_checkpoint(tmp_path) is None

    def test_corrupt_type_returns_none(self, tmp_path):
        """Valid JSON but wrong structure -> TypeError -> None."""
        (tmp_path / CHECKPOINT_FILENAME).write_text(json.dumps({"bad": "data"}), encoding="utf-8")
        assert load_checkpoint(tmp_path) is None

    def test_valid_checkpoint_round_trip(self, tmp_path):
        ckpt = PipelineCheckpoint(source_file="/tmp/test.mkv", vibe="drama")
        ckpt.mark_stage_complete("proxy")
        ckpt.proxy_path = "/tmp/work/proxy.mp4"
        ckpt.dialogue_event_count = 55
        save_checkpoint(ckpt, tmp_path)

        loaded = load_checkpoint(tmp_path)
        assert loaded is not None
        assert loaded.source_file == "/tmp/test.mkv"
        assert loaded.vibe == "drama"
        assert loaded.is_stage_complete("proxy")
        assert not loaded.is_stage_complete("inference")
        assert loaded.proxy_path == "/tmp/work/proxy.mp4"
        assert loaded.dialogue_event_count == 55


class TestSaveCheckpoint:
    """save_checkpoint() atomicity guarantees."""

    def test_no_tmp_files_remain_after_save(self, tmp_path):
        ckpt = PipelineCheckpoint(source_file="/tmp/film.mkv", vibe="action")
        save_checkpoint(ckpt, tmp_path)
        tmp_files = list(tmp_path.glob("*.ckpt.tmp"))
        assert tmp_files == [], f"Temp files not cleaned: {tmp_files}"

    def test_checkpoint_file_created(self, tmp_path):
        ckpt = PipelineCheckpoint(source_file="/tmp/film.mkv", vibe="action")
        save_checkpoint(ckpt, tmp_path)
        assert (tmp_path / CHECKPOINT_FILENAME).exists()

    def test_overwrite_existing_checkpoint(self, tmp_path):
        ckpt = PipelineCheckpoint(source_file="/tmp/film.mkv", vibe="action")
        ckpt.mark_stage_complete("proxy")
        save_checkpoint(ckpt, tmp_path)

        ckpt.mark_stage_complete("subtitles")
        save_checkpoint(ckpt, tmp_path)

        loaded = load_checkpoint(tmp_path)
        assert loaded.is_stage_complete("proxy")
        assert loaded.is_stage_complete("subtitles")
