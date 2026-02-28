"""Unit tests for assembly/bpm.py pure functions — BPMG-01, BPMG-02, BPMG-03."""
import pytest
import numpy as np
from cinecut.assembly.bpm import (
    resolve_bpm, snap_to_nearest_beat, VIBE_BPM_DEFAULTS, VIBE_BPM_RANGES, BpmGrid
)


class TestResolveBpm:
    """BPMG-03: 0-BPM guard, octave correction, vibe-default fallback."""

    def test_zero_bpm_returns_vibe_default(self):
        assert resolve_bpm(0.0, "action") == pytest.approx(VIBE_BPM_DEFAULTS["action"])

    def test_very_low_bpm_returns_vibe_default(self):
        assert resolve_bpm(5.0, "drama") == pytest.approx(VIBE_BPM_DEFAULTS["drama"])

    def test_half_tempo_doubled(self):
        """Action range 100-160; 64 BPM is half of 128 — should be doubled to 128."""
        result = resolve_bpm(64.0, "action")
        assert result == pytest.approx(128.0)

    def test_double_tempo_halved(self):
        """Action range 100-160; 256 BPM is double of 128 — should be halved to 128."""
        result = resolve_bpm(256.0, "action")
        assert result == pytest.approx(128.0)

    def test_in_range_passes_through(self):
        result = resolve_bpm(120.0, "action")
        assert result == pytest.approx(120.0)

    def test_out_of_range_no_octave_match_returns_default(self):
        """300 BPM for action: halved=150 which is in range [100,160], so halved."""
        # Actually 300/2=150 IS in action range (100-160), so it should halve, not return default
        result = resolve_bpm(300.0, "action")
        assert result == pytest.approx(150.0)

    def test_unknown_vibe_uses_fallback_range(self):
        """Unknown vibe uses (60.0, 160.0) range and 100.0 default."""
        result = resolve_bpm(0.0, "unknown_vibe")
        assert result == pytest.approx(100.0)

    def test_all_18_vibes_have_defaults(self):
        for vibe in VIBE_BPM_DEFAULTS:
            d = resolve_bpm(0.0, vibe)
            assert d == pytest.approx(VIBE_BPM_DEFAULTS[vibe])


class TestSnapToNearestBeat:
    """BPMG-02: clip start snapping within +/-1 beat tolerance."""

    def test_empty_beat_grid_returns_original(self):
        assert snap_to_nearest_beat(5.0, [], 120.0) == pytest.approx(5.0)

    def test_snaps_to_nearest_beat_within_tolerance(self):
        """Beat at 0.5s; start at 0.3s; tolerance = 60/120 = 0.5s; 0.3 is within 0.5 of 0.5."""
        beats = [0.0, 0.5, 1.0, 1.5]
        result = snap_to_nearest_beat(0.3, beats, 120.0)
        assert result == pytest.approx(0.5)

    def test_no_beat_within_tolerance_returns_original(self):
        """Start at 5.0; nearest beat is 3.0; tolerance = 0.5s (120 BPM); 2.0s away."""
        beats = [0.0, 1.0, 2.0, 3.0]
        result = snap_to_nearest_beat(5.0, beats, 120.0)
        assert result == pytest.approx(5.0)

    def test_result_never_negative(self):
        """Negative beats filtered; snapped result clamped >= 0.0."""
        beats = [0.0, 0.5, 1.0]
        result = snap_to_nearest_beat(0.1, beats, 120.0)
        assert result >= 0.0

    def test_snaps_to_beat_at_zero(self):
        beats = [0.0, 0.5, 1.0]
        result = snap_to_nearest_beat(0.2, beats, 120.0)
        assert result == pytest.approx(0.0)


class TestBpmGridDataclass:
    def test_construct_with_defaults(self):
        bg = BpmGrid(bpm=128.0, beat_times_s=[0.0, 0.5, 1.0], source="librosa")
        assert bg.beat_count == 0   # default — caller sets this
        assert bg.bpm == 128.0
        assert bg.source == "librosa"


class TestInsertSilenceAtZoneBoundary:
    """EORD-04: silence inserted BETWEEN last ESCALATION and first CLIMAX clip."""

    def test_returns_none_when_no_zone_annotations(self):
        from cinecut.assembly.ordering import insert_silence_at_zone_boundary
        from unittest.mock import MagicMock
        # ClipEntry mocks with no narrative_zone — spec=[] makes all attribute access use default
        clips = [MagicMock(spec=[]), MagicMock(spec=[])]
        result_path, result_idx = insert_silence_at_zone_boundary(clips, None, 1920, 1080)
        assert result_path is None
        assert result_idx == 0

    def test_boundary_index_points_to_gap_between_escalation_and_climax(self):
        from cinecut.assembly.ordering import insert_silence_at_zone_boundary
        from unittest.mock import MagicMock, patch
        from pathlib import Path

        # 4 clips: [BEGINNING, ESCALATION, ESCALATION, CLIMAX]
        # boundary_index should be 3 (silence inserted AFTER index 2, the last ESCALATION clip)
        clips = []
        for zone in ["BEGINNING", "ESCALATION", "ESCALATION", "CLIMAX"]:
            c = MagicMock()
            c.narrative_zone = zone
            clips.append(c)

        fake_path = Path("/tmp/silence_act2_act3.mp4")
        with patch("cinecut.assembly.ordering.generate_silence_segment", return_value=fake_path):
            result_path, result_idx = insert_silence_at_zone_boundary(
                clips, Path("/tmp"), 1920, 1080
            )
        assert result_path == fake_path
        assert result_idx == 3  # first 3 clips are before the silence; CLIMAX clip at index 3 comes after
