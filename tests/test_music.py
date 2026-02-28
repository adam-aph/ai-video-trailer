"""Unit tests for assembly/music.py pure functions — MUSC-01, MUSC-02, MUSC-03."""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from cinecut.assembly.music import (
    MusicBed, fetch_music_for_vibe, get_music_cache_dir, VIBE_TO_JAMENDO_TAG
)


class TestMusicBedDataclass:
    def test_construct_minimal(self):
        mb = MusicBed(
            track_id="1", track_name="Test Track", artist_name="Artist",
            license_ccurl="https://creativecommons.org/licenses/by/4.0/",
            local_path="/home/user/.cinecut/music/action.mp3",
        )
        assert mb.bpm is None
        assert mb.local_path.endswith(".mp3")

    def test_bpm_assignable(self):
        mb = MusicBed(track_id="1", track_name="T", artist_name="A", license_ccurl="", local_path="/tmp/x.mp3")
        mb.bpm = 128.0
        assert mb.bpm == 128.0


class TestVibeTagMapping:
    def test_all_vibes_mapped(self):
        expected_vibes = {
            "action", "adventure", "animation", "comedy", "crime", "documentary",
            "drama", "family", "fantasy", "history", "horror", "music",
            "mystery", "romance", "sci-fi", "thriller", "war", "western",
        }
        assert set(VIBE_TO_JAMENDO_TAG.keys()) == expected_vibes

    def test_tags_are_strings(self):
        for vibe, tag in VIBE_TO_JAMENDO_TAG.items():
            assert isinstance(tag, str) and len(tag) > 0, f"Empty tag for vibe '{vibe}'"


class TestFetchMusicGracefulDegradation:
    """MUSC-03: fetch_music_for_vibe returns None on any failure."""

    def test_returns_none_when_client_id_missing(self, monkeypatch, tmp_path):
        monkeypatch.delenv("JAMENDO_CLIENT_ID", raising=False)
        # Redirect cache to tmp_path so no cache hit
        monkeypatch.setattr("cinecut.assembly.music.get_music_cache_dir", lambda: tmp_path)
        result = fetch_music_for_vibe("action")
        assert result is None

    def test_returns_none_on_network_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JAMENDO_CLIENT_ID", "test-id")
        # Ensure no cache exists
        monkeypatch.setattr("cinecut.assembly.music.get_music_cache_dir", lambda: tmp_path)
        with patch("cinecut.assembly.music.requests.get", side_effect=ConnectionError("timeout")):
            result = fetch_music_for_vibe("action")
        assert result is None

    def test_returns_cached_musicbed_on_cache_hit(self, monkeypatch, tmp_path):
        """MUSC-02: cache hit returns MusicBed without API call."""
        # Create a fake cached file
        cached_file = tmp_path / "action.mp3"
        cached_file.write_bytes(b"fake-mp3-content")
        monkeypatch.setattr("cinecut.assembly.music.get_music_cache_dir", lambda: tmp_path)

        result = fetch_music_for_vibe("action")
        assert result is not None
        assert result.track_id == "cached"
        assert result.local_path == str(cached_file)
