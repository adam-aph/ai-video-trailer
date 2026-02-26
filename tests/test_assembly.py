"""Unit tests for 3-act assembly — EDIT-02, EDIT-03."""
import pytest
from cinecut.manifest.schema import ClipEntry
from cinecut.manifest.vibes import VIBE_PROFILES
from cinecut.assembly.ordering import (
    ACT_ORDER,
    sort_clips_by_act,
    enforce_pacing_curve,
    compute_act_avg_duration,
)


def _make_clip(act: str, start: float, end: float, beat_type: str = "escalation_beat") -> ClipEntry:
    return ClipEntry(source_start_s=start, source_end_s=end, beat_type=beat_type, act=act, transition="hard_cut")


class TestSortClipsByAct:
    """EDIT-02: sort_clips_by_act() produces canonical act order."""

    def test_reorders_out_of_order_acts(self):
        clips = [
            _make_clip("act3", 100.0, 102.0),
            _make_clip("cold_open", 5.0, 9.0, "character_introduction"),
            _make_clip("act1", 30.0, 34.0),
        ]
        ordered = sort_clips_by_act(clips)
        acts = [c.act for c in ordered]
        assert acts == ["cold_open", "act1", "act3"]

    def test_within_same_act_chronological(self):
        """Clips within same act sorted by source_start_s ascending."""
        clips = [
            _make_clip("act3", 120.0, 122.0),
            _make_clip("act3", 90.0, 92.0, "money_shot"),
        ]
        ordered = sort_clips_by_act(clips)
        assert ordered[0].source_start_s == 90.0
        assert ordered[1].source_start_s == 120.0

    def test_full_act_order_sequence(self):
        """All six acts in the right order."""
        clips = [
            _make_clip("act3", 100.0, 102.0, "climax_peak"),
            _make_clip("breath", 80.0, 82.0, "breath"),
            _make_clip("act2", 60.0, 62.0),
            _make_clip("beat_drop", 45.0, 47.0, "money_shot"),
            _make_clip("act1", 20.0, 22.0, "character_introduction"),
            _make_clip("cold_open", 5.0, 7.0, "inciting_incident"),
        ]
        ordered = sort_clips_by_act(clips)
        expected_acts = ["cold_open", "act1", "beat_drop", "act2", "breath", "act3"]
        assert [c.act for c in ordered] == expected_acts

    def test_empty_clips_returns_empty(self):
        assert sort_clips_by_act([]) == []


class TestComputeActAvgDuration:
    """compute_act_avg_duration() correctness."""

    def test_returns_zero_for_missing_act(self):
        clips = [_make_clip("act1", 0.0, 5.0)]
        assert compute_act_avg_duration(clips, "act3") == 0.0

    def test_single_clip(self):
        clips = [_make_clip("act1", 10.0, 14.0)]
        assert compute_act_avg_duration(clips, "act1") == pytest.approx(4.0)

    def test_multiple_clips_average(self):
        clips = [
            _make_clip("act3", 100.0, 102.0),   # 2.0s
            _make_clip("act3", 110.0, 112.5),   # 2.5s
        ]
        avg = compute_act_avg_duration(clips, "act3")
        assert avg == pytest.approx(2.25)


class TestEnforcePacingCurve:
    """EDIT-03: enforce_pacing_curve() trims oversized act3 clips."""

    def test_no_trimming_when_within_threshold(self):
        profile = VIBE_PROFILES["action"]  # act3_avg_cut_s = 1.2, threshold = 1.8
        clips = [_make_clip("act3", 100.0, 101.5, "climax_peak")]  # 1.5s, within 1.8
        result = enforce_pacing_curve(clips, profile)
        assert result[0].source_end_s == pytest.approx(101.5)

    def test_trims_act3_clips_exceeding_threshold(self):
        """Action profile: act3_avg_cut_s=1.2, threshold=1.8. 10s clip should be trimmed."""
        profile = VIBE_PROFILES["action"]  # act3_avg_cut_s = 1.2
        clips = [
            _make_clip("act3", 100.0, 110.0, "climax_peak"),  # 10s >> 1.8 threshold
            _make_clip("act3", 120.0, 130.0, "money_shot"),   # 10s >> 1.8 threshold
        ]
        result = enforce_pacing_curve(clips, profile)
        for clip in result:
            duration = clip.source_end_s - clip.source_start_s
            assert duration <= profile.act3_avg_cut_s * 1.5 + 0.01, f"Clip too long: {duration:.2f}s"

    def test_never_trims_below_min_duration(self):
        """Min clip duration is 0.5s."""
        from cinecut.assembly.ordering import MIN_CLIP_DURATION_S
        profile = VIBE_PROFILES["action"]  # act3_avg_cut_s = 1.2
        # A clip that's already very short but would normally be trimmed further
        clips = [
            _make_clip("act3", 100.0, 110.0, "climax_peak"),  # 10s, gets trimmed to 1.2s
        ]
        result = enforce_pacing_curve(clips, profile)
        for clip in result:
            duration = clip.source_end_s - clip.source_start_s
            assert duration >= MIN_CLIP_DURATION_S

    def test_non_act3_clips_untouched(self):
        """enforce_pacing_curve() must NOT modify act1 or act2 clips."""
        profile = VIBE_PROFILES["action"]
        clips = [
            _make_clip("act1", 0.0, 20.0),   # 20s act1 clip (long but not act3)
            _make_clip("act3", 100.0, 110.0, "climax_peak"),  # gets trimmed
        ]
        result = enforce_pacing_curve(clips, profile)
        act1_result = next(c for c in result if c.act == "act1")
        assert act1_result.source_end_s == pytest.approx(20.0), "act1 clip should not be modified"

    def test_pacing_curve_decreasing_after_enforcement(self):
        """After enforcement, act1_avg > act3_avg (measurable pacing curve, EDIT-03)."""
        profile = VIBE_PROFILES["action"]
        clips = [
            _make_clip("act1", 0.0, 5.0),    # 5.0s act1 (action act1_avg_cut_s=4.0)
            _make_clip("act3", 100.0, 110.0, "climax_peak"),  # 10s -> trimmed to 1.2s
        ]
        result = enforce_pacing_curve(clips, profile)
        act1_avg = compute_act_avg_duration(result, "act1")
        act3_avg = compute_act_avg_duration(result, "act3")
        assert act1_avg > act3_avg, f"Pacing curve violated: act1={act1_avg:.2f}s, act3={act3_avg:.2f}s"
