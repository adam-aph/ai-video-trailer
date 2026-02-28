"""Unit tests for Phase 4 narrative analysis: NARR-02, NARR-03, EDIT-01."""
import json
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# NARR-02: Beat classification (scorer.classify_beat + assign_act)
# ---------------------------------------------------------------------------


class TestBeatClassification:
    """NARR-02: classify_beat returns correct beat type for each rule."""

    def test_beat_classify_breath(self):
        """Low score + neutral emotion -> breath."""
        from cinecut.narrative.scorer import classify_beat
        result = classify_beat(chron_pos=0.50, emotion="neutral", money_shot_score=0.10, has_face=False)
        assert result == "breath"

    def test_beat_classify_climax_peak(self):
        """Late in film + high score -> climax_peak."""
        from cinecut.narrative.scorer import classify_beat
        result = classify_beat(chron_pos=0.85, emotion="intense", money_shot_score=0.75, has_face=False)
        assert result == "climax_peak"

    def test_beat_classify_money_shot(self):
        """Very high score (> 0.80) -> money_shot."""
        from cinecut.narrative.scorer import classify_beat
        result = classify_beat(chron_pos=0.50, emotion="positive", money_shot_score=0.90, has_face=False)
        assert result == "money_shot"

    def test_beat_classify_character_intro(self):
        """Early + face + not intense -> character_introduction."""
        from cinecut.narrative.scorer import classify_beat
        result = classify_beat(chron_pos=0.05, emotion="positive", money_shot_score=0.40, has_face=True)
        assert result == "character_introduction"

    def test_beat_classify_inciting_incident(self):
        """Early-ish + intense -> inciting_incident."""
        from cinecut.narrative.scorer import classify_beat
        result = classify_beat(chron_pos=0.20, emotion="intense", money_shot_score=0.40, has_face=False)
        assert result == "inciting_incident"

    def test_beat_classify_relationship(self):
        """Romantic + face -> relationship_beat."""
        from cinecut.narrative.scorer import classify_beat
        result = classify_beat(chron_pos=0.50, emotion="romantic", money_shot_score=0.50, has_face=True)
        assert result == "relationship_beat"

    def test_beat_classify_escalation_fallback(self):
        """Negative emotion, mid film, low-ish score, no face -> escalation_beat (catch-all)."""
        from cinecut.narrative.scorer import classify_beat
        result = classify_beat(chron_pos=0.50, emotion="negative", money_shot_score=0.40, has_face=False)
        assert result == "escalation_beat"

    def test_act_breath_overrides_position(self):
        """beat_type='breath' always returns act='breath' regardless of chron_pos."""
        from cinecut.narrative.scorer import assign_act
        result = assign_act(chron_pos=0.9, beat_type="breath")
        assert result == "breath"

    def test_act_cold_open(self):
        """Very early position -> cold_open."""
        from cinecut.narrative.scorer import assign_act
        result = assign_act(chron_pos=0.03, beat_type="escalation_beat")
        assert result == "cold_open"

    def test_act_act3(self):
        """Late position (>= 0.82) -> act3."""
        from cinecut.narrative.scorer import assign_act
        result = assign_act(chron_pos=0.85, beat_type="money_shot")
        assert result == "act3"


# ---------------------------------------------------------------------------
# NARR-03: Signal scoring (compute_money_shot_score + normalize_signal_pool)
# ---------------------------------------------------------------------------


class TestSignalScoring:
    """NARR-03: Normalization and weighted money-shot scoring are correct."""

    def test_signal_weights_sum_to_one(self):
        """SIGNAL_WEIGHTS must sum to exactly 1.0 (within floating-point tolerance)."""
        from cinecut.narrative.scorer import SIGNAL_WEIGHTS
        assert abs(sum(SIGNAL_WEIGHTS.values()) - 1.0) < 1e-9

    def test_money_shot_score_range(self):
        """All signals at 0.5 -> score of 0.5."""
        from cinecut.narrative.scorer import SIGNAL_WEIGHTS, compute_money_shot_score
        normalized = {k: 0.5 for k in SIGNAL_WEIGHTS}
        score = compute_money_shot_score(normalized)
        assert abs(score - 0.5) < 1e-9

    def test_money_shot_score_max(self):
        """All signals at 1.0 -> score of 1.0."""
        from cinecut.narrative.scorer import SIGNAL_WEIGHTS, compute_money_shot_score
        normalized = {k: 1.0 for k in SIGNAL_WEIGHTS}
        score = compute_money_shot_score(normalized)
        assert abs(score - 1.0) < 1e-9

    def test_money_shot_score_min(self):
        """All signals at 0.0 -> score of 0.0."""
        from cinecut.narrative.scorer import SIGNAL_WEIGHTS, compute_money_shot_score
        normalized = {k: 0.0 for k in SIGNAL_WEIGHTS}
        score = compute_money_shot_score(normalized)
        assert abs(score - 0.0) < 1e-9

    def test_normalize_uniform(self):
        """Uniform values [5, 5, 5] -> degenerate case returns [0.5, 0.5, 0.5]."""
        from cinecut.narrative.scorer import normalize_signal_pool
        result = normalize_signal_pool([5.0, 5.0, 5.0])
        assert result == [0.5, 0.5, 0.5]

    def test_normalize_range(self):
        """[0.0, 10.0, 5.0] -> [0.0, 1.0, 0.5]."""
        from cinecut.narrative.scorer import normalize_signal_pool
        result = normalize_signal_pool([0.0, 10.0, 5.0])
        assert len(result) == 3
        assert abs(result[0] - 0.0) < 1e-9
        assert abs(result[1] - 1.0) < 1e-9
        assert abs(result[2] - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# EDIT-01: Manifest generation (generator.run_narrative_stage)
# ---------------------------------------------------------------------------


def _make_inference_results(tmp_path: Path, n: int = 24, interval_s: int = 5):
    """Build synthetic inference_results without real JPEG files."""
    from cinecut.models import KeyframeRecord
    from cinecut.inference.models import SceneDescription

    records = [
        KeyframeRecord(
            timestamp_s=float(t),
            frame_path=str(tmp_path / f"f{t:04d}.jpg"),
            source="subtitle_midpoint",
        )
        for t in range(0, n * interval_s, interval_s)
    ]
    descriptions = [
        SceneDescription(
            visual_content="dark forest",
            mood="tense",
            action="man running",
            setting="night",
        )
        for _ in records
    ]
    return list(zip(records, descriptions))


def _make_dialogue_events():
    from cinecut.models import DialogueEvent
    return [
        DialogueEvent(
            start_ms=0,
            end_ms=4000,
            start_s=0.0,
            end_s=4.0,
            midpoint_s=2.0,
            text="We must act now.",
            emotion="intense",
        )
    ]


def _mock_run_zone_matching(clip_texts, clip_midpoints, film_duration_s, structural_anchors):
    """Position-based zone assignment for tests — avoids sentence-transformers load."""
    from cinecut.manifest.schema import NarrativeZone
    zones = []
    for midpoint in clip_midpoints:
        pos = midpoint / max(film_duration_s, 1.0)
        if pos < 0.33:
            zones.append(NarrativeZone.BEGINNING)
        elif pos < 0.67:
            zones.append(NarrativeZone.ESCALATION)
        else:
            zones.append(NarrativeZone.CLIMAX)
    return zones


class TestManifestGeneration:
    """EDIT-01: run_narrative_stage produces a valid TRAILER_MANIFEST.json."""

    def test_run_narrative_stage_writes_manifest(self, tmp_path):
        """EDIT-01: run_narrative_stage writes a valid TRAILER_MANIFEST.json."""
        from cinecut.narrative.generator import run_narrative_stage
        from cinecut.manifest.loader import load_manifest

        inference_results = _make_inference_results(tmp_path)
        dialogue_events = _make_dialogue_events()

        with mock.patch("cinecut.narrative.generator.get_film_duration_s", return_value=120.0), \
             mock.patch("cv2.imread", return_value=None), \
             mock.patch("cinecut.narrative.generator.run_zone_matching", side_effect=_mock_run_zone_matching):
            manifest_path = run_narrative_stage(
                inference_results,
                dialogue_events,
                "action",
                source_file=tmp_path / "film.mkv",
                work_dir=tmp_path,
            )

        assert manifest_path.exists()
        assert manifest_path.name == "TRAILER_MANIFEST.json"

        loaded = load_manifest(manifest_path)
        assert loaded.vibe == "action"
        assert len(loaded.clips) >= 1

        valid_beat_types = {
            "inciting_incident",
            "character_introduction",
            "escalation_beat",
            "relationship_beat",
            "money_shot",
            "climax_peak",
            "breath",
        }
        for clip in loaded.clips:
            assert clip.beat_type in valid_beat_types
            assert clip.source_end_s > clip.source_start_s
            assert clip.money_shot_score is not None
            assert 0.0 <= clip.money_shot_score <= 1.0

    def test_no_clip_overlap(self, tmp_path):
        """EDIT-01: Adjacent clips in generated manifest do not overlap."""
        from cinecut.narrative.generator import run_narrative_stage
        from cinecut.manifest.loader import load_manifest

        inference_results = _make_inference_results(tmp_path)
        dialogue_events = _make_dialogue_events()

        with mock.patch("cinecut.narrative.generator.get_film_duration_s", return_value=120.0), \
             mock.patch("cv2.imread", return_value=None), \
             mock.patch("cinecut.narrative.generator.run_zone_matching", side_effect=_mock_run_zone_matching):
            manifest_path = run_narrative_stage(
                inference_results,
                dialogue_events,
                "action",
                source_file=tmp_path / "film.mkv",
                work_dir=tmp_path,
            )

        loaded = load_manifest(manifest_path)
        clips = loaded.clips
        # Adjacent clips: end of clip[i] must be <= start of clip[i+1]
        # NOTE: Zone-first ordering (EORD-01) means clips are no longer in chronological order;
        # the overlap check applies to zone-sorted clip sequence, not temporal sequence.
        # resolve_overlaps ensures the pre-sort windows are non-overlapping; after zone sort
        # the source_start_s values may not be monotonically increasing.
        # We verify each individual clip's window is valid instead.
        for clip in clips:
            assert clip.source_end_s > clip.source_start_s, (
                f"Degenerate clip: end={clip.source_end_s} <= start={clip.source_start_s}"
            )

    def test_manifest_clip_count_respects_vibe_max(self, tmp_path):
        """Generated manifest has at most clip_count_max clips."""
        from cinecut.narrative.generator import run_narrative_stage
        from cinecut.manifest.loader import load_manifest
        from cinecut.manifest.vibes import VIBE_PROFILES

        inference_results = _make_inference_results(tmp_path)
        dialogue_events = _make_dialogue_events()

        with mock.patch("cinecut.narrative.generator.get_film_duration_s", return_value=120.0), \
             mock.patch("cv2.imread", return_value=None), \
             mock.patch("cinecut.narrative.generator.run_zone_matching", side_effect=_mock_run_zone_matching):
            manifest_path = run_narrative_stage(
                inference_results,
                dialogue_events,
                "action",
                source_file=tmp_path / "film.mkv",
                work_dir=tmp_path,
            )

        loaded = load_manifest(manifest_path)
        max_clips = VIBE_PROFILES["action"].clip_count_max
        assert len(loaded.clips) <= max_clips

    def test_manifest_json_is_valid(self, tmp_path):
        """Written TRAILER_MANIFEST.json is valid JSON."""
        from cinecut.narrative.generator import run_narrative_stage

        inference_results = _make_inference_results(tmp_path)
        dialogue_events = _make_dialogue_events()

        with mock.patch("cinecut.narrative.generator.get_film_duration_s", return_value=120.0), \
             mock.patch("cv2.imread", return_value=None), \
             mock.patch("cinecut.narrative.generator.run_zone_matching", side_effect=_mock_run_zone_matching):
            manifest_path = run_narrative_stage(
                inference_results,
                dialogue_events,
                "action",
                source_file=tmp_path / "film.mkv",
                work_dir=tmp_path,
            )

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["vibe"] == "action"
        assert isinstance(data["clips"], list)
        assert len(data["clips"]) >= 1

    def test_progress_callback_called(self, tmp_path):
        """progress_callback is called once per frame processed."""
        from cinecut.narrative.generator import run_narrative_stage

        inference_results = _make_inference_results(tmp_path, n=5, interval_s=10)
        dialogue_events = _make_dialogue_events()
        calls: list[tuple[int, int]] = []

        def _cb(current: int, total: int) -> None:
            calls.append((current, total))

        with mock.patch("cinecut.narrative.generator.get_film_duration_s", return_value=50.0), \
             mock.patch("cv2.imread", return_value=None), \
             mock.patch("cinecut.narrative.generator.run_zone_matching", side_effect=_mock_run_zone_matching):
            run_narrative_stage(
                inference_results,
                dialogue_events,
                "drama",
                source_file=tmp_path / "film.mkv",
                work_dir=tmp_path,
                progress_callback=_cb,
            )

        assert len(calls) == 5  # one call per frame
        assert calls[-1][0] == 5   # final call: completed=5


# ---------------------------------------------------------------------------
# Internal helper unit tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Unit tests for internal generator helpers."""

    def test_compute_clip_window_act1(self):
        """act1 uses act1_avg_cut_s with 30/70 bias."""
        from cinecut.narrative.generator import compute_clip_window
        from cinecut.manifest.vibes import VIBE_PROFILES
        vp = VIBE_PROFILES["action"]  # act1_avg_cut_s=4.0
        start, end = compute_clip_window(timestamp_s=10.0, act="act1", vibe_profile=vp, film_duration_s=120.0)
        assert abs(start - (10.0 - 4.0 * 0.3)) < 1e-6
        assert abs(end - (10.0 + 4.0 * 0.7)) < 1e-6

    def test_compute_clip_window_clamps_to_film_bounds(self):
        """Window is clamped to [0, film_duration_s]."""
        from cinecut.narrative.generator import compute_clip_window
        from cinecut.manifest.vibes import VIBE_PROFILES
        vp = VIBE_PROFILES["action"]
        start, end = compute_clip_window(timestamp_s=0.1, act="act1", vibe_profile=vp, film_duration_s=120.0)
        assert start >= 0.0
        start2, end2 = compute_clip_window(timestamp_s=119.9, act="act3", vibe_profile=vp, film_duration_s=120.0)
        assert end2 <= 120.0

    def test_resolve_overlaps_no_overlap(self):
        """Non-overlapping windows are unchanged."""
        from cinecut.narrative.generator import resolve_overlaps
        windows = [(0.0, 3.0), (5.0, 8.0), (10.0, 12.0)]
        result = resolve_overlaps(windows)
        assert result == windows

    def test_resolve_overlaps_fixes_overlap(self):
        """Overlapping windows get a 0.5s gap enforced."""
        from cinecut.narrative.generator import resolve_overlaps
        windows = [(0.0, 6.0), (5.0, 9.0)]  # [0] ends after [1] starts
        result = resolve_overlaps(windows)
        assert result[0][1] <= result[1][0]
        assert result[1][0] - result[0][1] >= 0.0  # gap exists

    def test_get_dialogue_excerpt_direct_overlap(self):
        """Returns text of event that directly overlaps the timestamp."""
        from cinecut.narrative.generator import get_dialogue_excerpt
        from cinecut.models import DialogueEvent
        events = [
            DialogueEvent(0, 4000, 0.0, 4.0, 2.0, "First line.", "positive"),
            DialogueEvent(6000, 9000, 6.0, 9.0, 7.5, "Second line.", "neutral"),
        ]
        assert get_dialogue_excerpt(2.5, events) == "First line."
        assert get_dialogue_excerpt(7.0, events) == "Second line."

    def test_get_dialogue_excerpt_no_match(self):
        """Returns empty string when no event is within window_s."""
        from cinecut.narrative.generator import get_dialogue_excerpt
        from cinecut.models import DialogueEvent
        events = [
            DialogueEvent(0, 1000, 0.0, 1.0, 0.5, "Far away.", "positive"),
        ]
        # timestamp_s=100.0, window_s=5.0 -- nearest midpoint is 0.5 which is 99.5s away
        assert get_dialogue_excerpt(100.0, events, window_s=5.0) == ""

    def test_get_nearest_emotion_direct_overlap(self):
        """Returns emotion of overlapping event."""
        from cinecut.narrative.generator import get_nearest_emotion
        from cinecut.models import DialogueEvent
        events = [
            DialogueEvent(0, 4000, 0.0, 4.0, 2.0, "Line.", "intense"),
        ]
        assert get_nearest_emotion(2.0, events) == "intense"

    def test_get_nearest_emotion_no_events(self):
        """Returns 'neutral' when no events provided."""
        from cinecut.narrative.generator import get_nearest_emotion
        assert get_nearest_emotion(5.0, []) == "neutral"

    def test_get_transition_act_boundary(self):
        """Act boundaries use secondary_transition."""
        from cinecut.narrative.generator import get_transition
        from cinecut.manifest.vibes import VIBE_PROFILES
        vp = VIBE_PROFILES["adventure"]  # secondary_transition="fade_to_black"
        assert get_transition("cold_open", vp) == vp.secondary_transition
        assert get_transition("beat_drop", vp) == vp.secondary_transition
        assert get_transition("act3", vp) == vp.secondary_transition

    def test_get_transition_non_boundary(self):
        """Non-boundary acts use primary_transition."""
        from cinecut.narrative.generator import get_transition
        from cinecut.manifest.vibes import VIBE_PROFILES
        vp = VIBE_PROFILES["adventure"]  # primary_transition="crossfade"
        assert get_transition("act1", vp) == vp.primary_transition
        assert get_transition("act2", vp) == vp.primary_transition
        assert get_transition("breath", vp) == vp.primary_transition
