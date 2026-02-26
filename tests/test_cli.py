"""Tests for CLI input validation order.

Verifies that extension checks always fire before existence checks so that
wrong-extension files (even if non-existent) produce our Rich error panels
rather than Typer/Click's plain 'File does not exist' error.
"""

import pytest
from typer.testing import CliRunner

from cinecut.cli import app

runner = CliRunner()


def test_invalid_video_extension_nonexistent_file():
    """Wrong extension + file missing: Rich 'Unsupported video format' panel fires first."""
    result = runner.invoke(
        app,
        ["nonexistent_movie.pdf", "--subtitle", "dummy.srt", "--vibe", "action"],
    )
    assert result.exit_code == 1
    assert "Unsupported video format" in result.output
    assert "File does not exist" not in result.output


def test_invalid_video_extension_existing_file(tmp_path):
    """Wrong extension + file exists: Rich 'Unsupported video format' panel fires."""
    pdf_file = tmp_path / "movie.pdf"
    pdf_file.write_bytes(b"fake pdf content")
    result = runner.invoke(
        app,
        [str(pdf_file), "--subtitle", "dummy.srt", "--vibe", "action"],
    )
    assert result.exit_code == 1
    assert "Unsupported video format" in result.output


def test_valid_video_extension_nonexistent_file():
    """Valid extension + file missing: Rich 'File not found' panel fires (not Click's plain error)."""
    result = runner.invoke(
        app,
        ["nonexistent_movie.mp4", "--subtitle", "dummy.srt", "--vibe", "action"],
    )
    assert result.exit_code == 1
    assert "File not found" in result.output
    assert "File does not exist" not in result.output


def test_invalid_subtitle_extension_nonexistent_file(tmp_path):
    """Valid video + wrong subtitle extension + subtitle missing: subtitle format panel fires."""
    mp4_file = tmp_path / "movie.mp4"
    mp4_file.write_bytes(b"fake mp4 content")
    result = runner.invoke(
        app,
        [str(mp4_file), "--subtitle", "subs.pdf", "--vibe", "action"],
    )
    assert result.exit_code == 1
    assert "Unsupported subtitle format" in result.output


def test_valid_subtitle_extension_nonexistent_file(tmp_path):
    """Valid video (exists) + valid subtitle extension + subtitle missing: 'File not found' panel fires."""
    mp4_file = tmp_path / "movie.mp4"
    mp4_file.write_bytes(b"fake mp4 content")
    result = runner.invoke(
        app,
        [str(mp4_file), "--subtitle", "nonexistent.srt", "--vibe", "action"],
    )
    assert result.exit_code == 1
    assert "File not found" in result.output
