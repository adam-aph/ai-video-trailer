"""Unit tests for narrative/zone_matching.py (STRC-02).

Tests use mocked sentence-transformers model — no model download required.
"""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from cinecut.narrative.zone_matching import (
    assign_narrative_zone,
    run_zone_matching,
    _zone_by_position,
    ZONE_ANCHORS,
)
from cinecut.manifest.schema import NarrativeZone, StructuralAnchors


def _make_anchors(begin_t: float, escalation_t: float, climax_t: float) -> StructuralAnchors:
    return StructuralAnchors(begin_t=begin_t, escalation_t=escalation_t, climax_t=climax_t)


def _make_mock_cos_result(sim_array: np.ndarray):
    """Build a mock cos_sim result returning sim_array via [0].numpy()."""
    mock_sims = MagicMock()
    mock_sims.numpy.return_value = sim_array

    mock_cos_result = MagicMock()
    mock_cos_result.__getitem__ = lambda self, idx: mock_sims

    return mock_cos_result


def _make_util_mock(sim_array: np.ndarray) -> MagicMock:
    """Build a mock util object whose cos_sim returns sim_array via [0].numpy()."""
    mock_util = MagicMock()
    mock_util.cos_sim.return_value = _make_mock_cos_result(sim_array)
    return mock_util


class TestZoneAnchors:
    def test_zone_anchors_has_all_three_zones(self):
        """ZONE_ANCHORS must contain all three NarrativeZone values."""
        assert NarrativeZone.BEGINNING in ZONE_ANCHORS
        assert NarrativeZone.ESCALATION in ZONE_ANCHORS
        assert NarrativeZone.CLIMAX in ZONE_ANCHORS
        assert len(ZONE_ANCHORS) == 3


class TestZoneByPositionNoAnchors:
    """Position-based fallback using 33%/66% fraction split."""

    def test_zone_by_position_beginning_no_anchors(self):
        """100s / 5400s = 1.85% < 33% -> BEGINNING."""
        z = _zone_by_position(100.0, 5400.0, None)
        assert z == NarrativeZone.BEGINNING

    def test_zone_by_position_escalation_no_anchors(self):
        """2500s / 5400s = 46% — between 33% and 67% -> ESCALATION."""
        z = _zone_by_position(2500.0, 5400.0, None)
        assert z == NarrativeZone.ESCALATION

    def test_zone_by_position_climax_no_anchors(self):
        """4500s / 5400s = 83% > 67% -> CLIMAX."""
        z = _zone_by_position(4500.0, 5400.0, None)
        assert z == NarrativeZone.CLIMAX


class TestZoneByPositionWithStructuralAnchors:
    """Position-based fallback using StructuralAnchors timestamps."""

    def test_before_escalation_t_returns_beginning(self):
        anchors = _make_anchors(begin_t=180, escalation_t=1800, climax_t=3600)
        # midpoint=1000 < escalation_t=1800 -> BEGINNING
        assert _zone_by_position(1000.0, 5400.0, anchors) == NarrativeZone.BEGINNING

    def test_between_escalation_and_climax_returns_escalation(self):
        anchors = _make_anchors(begin_t=180, escalation_t=1800, climax_t=3600)
        # midpoint=2500, 1800 <= 2500 < 3600 -> ESCALATION
        assert _zone_by_position(2500.0, 5400.0, anchors) == NarrativeZone.ESCALATION

    def test_after_climax_t_returns_climax(self):
        anchors = _make_anchors(begin_t=180, escalation_t=1800, climax_t=3600)
        # midpoint=4000 >= climax_t=3600 -> CLIMAX
        assert _zone_by_position(4000.0, 5400.0, anchors) == NarrativeZone.CLIMAX


class TestAssignNarrativeZoneEmpty:
    """Empty/whitespace dialogue uses position fallback without calling model."""

    def test_empty_dialogue_uses_position_fallback(self):
        """Empty string -> position fallback, no model load."""
        with patch("cinecut.narrative.zone_matching._load_model", side_effect=AssertionError("Model must not be loaded for empty dialogue")):
            z = assign_narrative_zone("", None, 100.0, 5400.0)
        assert z == NarrativeZone.BEGINNING

    def test_whitespace_dialogue_uses_position_fallback(self):
        """Whitespace-only string -> position fallback, no model load."""
        with patch("cinecut.narrative.zone_matching._load_model", side_effect=AssertionError("Model must not be loaded for whitespace dialogue")):
            z = assign_narrative_zone("   ", None, 100.0, 5400.0)
        assert z == NarrativeZone.BEGINNING


class TestAssignNarrativeZoneSemantic:
    """Semantic assignment via mocked sentence-transformers model.

    util is a module-level attribute (set to None initially, populated by _load_model).
    We patch cinecut.narrative.zone_matching.util directly to inject a mock cos_sim.
    """

    def test_semantic_assignment_climax(self):
        """Mock cos_sim result favoring CLIMAX zone — verify CLIMAX returned."""
        # sim_array: [BEGINNING=0.1, ESCALATION=0.2, CLIMAX=0.9]
        sim_array = np.array([0.1, 0.2, 0.9])
        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros((1, 384))
        mock_util = _make_util_mock(sim_array)

        with patch("cinecut.narrative.zone_matching._load_model", return_value=mock_model):
            with patch("cinecut.narrative.zone_matching.util", mock_util):
                result = assign_narrative_zone("I will destroy you", None, 100.0, 5400.0)

        assert result == NarrativeZone.CLIMAX

    def test_semantic_assignment_beginning(self):
        """Mock cos_sim favoring BEGINNING — verify BEGINNING returned."""
        sim_array = np.array([0.9, 0.1, 0.1])
        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros((1, 384))
        mock_util = _make_util_mock(sim_array)

        with patch("cinecut.narrative.zone_matching._load_model", return_value=mock_model):
            with patch("cinecut.narrative.zone_matching.util", mock_util):
                result = assign_narrative_zone("Nice to meet you, I am new here", None, 100.0, 5400.0)

        assert result == NarrativeZone.BEGINNING


class TestRunZoneMatching:
    """run_zone_matching() batch interface tests."""

    def test_run_zone_matching_all_empty_no_model_load(self):
        """All-empty clip texts use position fallback; model must NOT be loaded."""
        with patch("cinecut.narrative.zone_matching._load_model", side_effect=AssertionError("Model must not load for all-empty input")):
            zones = run_zone_matching(["", "", ""], [100.0, 3000.0, 5000.0], 5400.0, None)
        assert zones[0] == NarrativeZone.BEGINNING
        assert zones[1] == NarrativeZone.ESCALATION
        assert zones[2] == NarrativeZone.CLIMAX

    def test_run_zone_matching_length_matches_input(self):
        """Output list length must equal input list length."""
        sim_array = np.array([0.1, 0.2, 0.9])
        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros((5, 384))
        mock_util = _make_util_mock(sim_array)

        with patch("cinecut.narrative.zone_matching._load_model", return_value=mock_model):
            with patch("cinecut.narrative.zone_matching.util", mock_util):
                clip_texts = ["text one", "text two", "text three", "text four", "text five"]
                clip_midpoints = [100.0, 500.0, 1000.0, 2000.0, 4000.0]
                result = run_zone_matching(clip_texts, clip_midpoints, 5400.0, None)

        assert len(result) == 5

    def test_run_zone_matching_returns_narrative_zone_enum(self):
        """All returned values must be NarrativeZone instances."""
        sim_array = np.array([0.1, 0.2, 0.9])
        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros((3, 384))
        mock_util = _make_util_mock(sim_array)

        with patch("cinecut.narrative.zone_matching._load_model", return_value=mock_model):
            with patch("cinecut.narrative.zone_matching.util", mock_util):
                clip_texts = ["fight scene", "introduction", "crisis moment"]
                clip_midpoints = [100.0, 2000.0, 4500.0]
                result = run_zone_matching(clip_texts, clip_midpoints, 5400.0, None)

        assert all(isinstance(z, NarrativeZone) for z in result), (
            f"Expected all NarrativeZone, got: {[type(z) for z in result]}"
        )
