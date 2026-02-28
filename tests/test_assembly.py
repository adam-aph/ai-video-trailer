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


# ============================================================
# Phase 8 zone ordering tests (EORD-01, EORD-02, EORD-03)
# ============================================================
from typing import Optional
from cinecut.manifest.schema import NarrativeZone


def _make_zone_clip(
    zone: Optional[NarrativeZone],
    score: float,
    start: float = 0.0,
    end: float = 5.0,
    act: str = "act1",
) -> ClipEntry:
    return ClipEntry(
        source_start_s=start,
        source_end_s=end,
        beat_type="escalation_beat",
        act=act,
        transition="hard_cut",
        money_shot_score=score,
        narrative_zone=zone,
    )


class TestSortClipsByZone:
    """EORD-01 and EORD-02: sort_clips_by_zone() — zone-first, score-descending within zone."""

    def test_zone_order_beginning_before_escalation_before_climax(self):
        """Clips in wrong zone order get sorted BEGINNING -> ESCALATION -> CLIMAX."""
        from cinecut.assembly.ordering import sort_clips_by_zone
        clips = [
            _make_zone_clip(NarrativeZone.CLIMAX, 0.8),
            _make_zone_clip(NarrativeZone.BEGINNING, 0.5),
            _make_zone_clip(NarrativeZone.ESCALATION, 0.6),
        ]
        result = sort_clips_by_zone(clips)
        zones = [c.narrative_zone for c in result]
        assert zones == [NarrativeZone.BEGINNING, NarrativeZone.ESCALATION, NarrativeZone.CLIMAX]

    def test_within_zone_score_descending(self):
        """Within the same zone, higher money_shot_score comes first."""
        from cinecut.assembly.ordering import sort_clips_by_zone
        clips = [
            _make_zone_clip(NarrativeZone.ESCALATION, 0.3),
            _make_zone_clip(NarrativeZone.ESCALATION, 0.9),
        ]
        result = sort_clips_by_zone(clips)
        assert result[0].money_shot_score == pytest.approx(0.9)
        assert result[1].money_shot_score == pytest.approx(0.3)

    def test_clips_without_zone_sorted_last(self):
        """Clips with narrative_zone=None appear after all zone-assigned clips."""
        from cinecut.assembly.ordering import sort_clips_by_zone
        clips = [
            _make_zone_clip(None, 0.9),
            _make_zone_clip(NarrativeZone.BEGINNING, 0.5),
            _make_zone_clip(NarrativeZone.CLIMAX, 0.7),
        ]
        result = sort_clips_by_zone(clips)
        assert result[0].narrative_zone == NarrativeZone.BEGINNING
        assert result[1].narrative_zone == NarrativeZone.CLIMAX
        assert result[2].narrative_zone is None

    def test_title_card_and_button_sorted_last(self):
        """Clips with act=title_card or act=button and narrative_zone=None are last."""
        from cinecut.assembly.ordering import sort_clips_by_zone
        clips = [
            ClipEntry(source_start_s=0.0, source_end_s=3.0, beat_type="breath", act="title_card",
                      transition="fade_to_black", narrative_zone=None),
            _make_zone_clip(NarrativeZone.CLIMAX, 0.8),
            ClipEntry(source_start_s=1.0, source_end_s=4.0, beat_type="breath", act="button",
                      transition="fade_to_black", narrative_zone=None),
            _make_zone_clip(NarrativeZone.BEGINNING, 0.4),
        ]
        result = sort_clips_by_zone(clips)
        # First two should be zone-assigned clips
        assert result[0].narrative_zone is not None
        assert result[1].narrative_zone is not None
        # Last two should be None-zone clips
        assert result[2].narrative_zone is None
        assert result[3].narrative_zone is None

    def test_empty_input_returns_empty(self):
        """sort_clips_by_zone([]) returns []."""
        from cinecut.assembly.ordering import sort_clips_by_zone
        assert sort_clips_by_zone([]) == []


class TestEnforceZonePacingCurve:
    """EORD-03: enforce_zone_pacing_curve() trims CLIMAX zone clips to act3 targets."""

    def test_climax_clips_trimmed_to_act3_target(self):
        """CLIMAX zone clips averaging 10s get trimmed to near act3_avg_cut_s."""
        from cinecut.assembly.ordering import enforce_zone_pacing_curve
        profile = VIBE_PROFILES["action"]  # act3_avg_cut_s = 1.2
        clips = [
            _make_zone_clip(NarrativeZone.CLIMAX, 0.8, start=0.0, end=10.0),
            _make_zone_clip(NarrativeZone.CLIMAX, 0.7, start=15.0, end=25.0),
        ]
        result = enforce_zone_pacing_curve(clips, profile)
        for clip in (c for c in result if c.narrative_zone == NarrativeZone.CLIMAX):
            duration = clip.source_end_s - clip.source_start_s
            assert duration <= profile.act3_avg_cut_s * 1.5, (
                f"CLIMAX clip not trimmed: {duration:.2f}s > {profile.act3_avg_cut_s * 1.5:.2f}s"
            )

    def test_beginning_clips_not_trimmed(self):
        """BEGINNING zone clips are not trimmed regardless of length."""
        from cinecut.assembly.ordering import enforce_zone_pacing_curve
        profile = VIBE_PROFILES["action"]  # act3_avg_cut_s = 1.2
        clips = [
            _make_zone_clip(NarrativeZone.BEGINNING, 0.5, start=0.0, end=20.0),
        ]
        result = enforce_zone_pacing_curve(clips, profile)
        beginning_clips = [c for c in result if c.narrative_zone == NarrativeZone.BEGINNING]
        assert len(beginning_clips) == 1
        assert beginning_clips[0].source_end_s == pytest.approx(20.0), (
            "BEGINNING clip should not be trimmed"
        )

    def test_never_below_min_duration(self):
        """After trimming, no CLIMAX clip duration falls below MIN_CLIP_DURATION_S (0.5s)."""
        from cinecut.assembly.ordering import enforce_zone_pacing_curve, MIN_CLIP_DURATION_S
        profile = VIBE_PROFILES["action"]  # act3_avg_cut_s = 1.2
        clips = [
            _make_zone_clip(NarrativeZone.CLIMAX, 0.9, start=0.0, end=10.0),
        ]
        result = enforce_zone_pacing_curve(clips, profile)
        for clip in result:
            duration = clip.source_end_s - clip.source_start_s
            assert duration >= MIN_CLIP_DURATION_S, (
                f"Clip trimmed below min duration: {duration:.2f}s < {MIN_CLIP_DURATION_S}s"
            )

    def test_no_trimming_when_within_threshold(self):
        """CLIMAX clips already within act3_avg_cut_s * 1.5 are returned unchanged."""
        from cinecut.assembly.ordering import enforce_zone_pacing_curve
        profile = VIBE_PROFILES["action"]  # act3_avg_cut_s = 1.2, threshold = 1.8
        clips = [
            _make_zone_clip(NarrativeZone.CLIMAX, 0.7, start=0.0, end=1.5),  # 1.5s < 1.8
        ]
        result = enforce_zone_pacing_curve(clips, profile)
        assert result[0].source_end_s == pytest.approx(1.5), (
            "Clip within threshold should not be modified"
        )
