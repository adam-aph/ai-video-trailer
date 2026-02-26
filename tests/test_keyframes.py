"""Unit tests for cinecut.ingestion.keyframes.

All tests are pure-logic: no real video or FFmpeg calls are made.
PySceneDetect's ``detect()`` is mocked to return an empty scene list
wherever scene detection would otherwise be invoked.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cinecut.ingestion.keyframes import (
    _infer_source,
    collect_keyframe_timestamps,
)


# ---------------------------------------------------------------------------
# collect_keyframe_timestamps tests
# ---------------------------------------------------------------------------

MOCK_TARGET = "cinecut.ingestion.keyframes.detect"


class TestCollectNoGaps:
    def test_collect_no_gaps(self) -> None:
        """Subtitle midpoints evenly spaced at 20s intervals → no interval fallback added."""
        midpoints = [0.0, 20.0, 40.0, 60.0, 80.0]
        with patch(MOCK_TARGET, return_value=[]):
            result = collect_keyframe_timestamps(
                proxy=None,  # type: ignore[arg-type]  # not used when detect is mocked
                subtitle_midpoints=midpoints,
                gap_threshold_s=30.0,
                interval_s=30.0,
            )
        # All midpoints should be present; no extras added (gaps <= 30s)
        assert set(midpoints).issubset(set(result))
        # The result should only contain the original midpoints (no fallback)
        assert sorted(result) == sorted(midpoints)


class TestCollectGapFilled:
    def test_collect_gap_filled(self) -> None:
        """Midpoints at 0s and 90s → interval fallback adds timestamps at 30s and 60s."""
        midpoints = [0.0, 90.0]
        with patch(MOCK_TARGET, return_value=[]):
            result = collect_keyframe_timestamps(
                proxy=None,  # type: ignore[arg-type]
                subtitle_midpoints=midpoints,
                gap_threshold_s=30.0,
                interval_s=30.0,
            )
        assert 0.0 in result
        assert 90.0 in result
        assert 30.0 in result
        assert 60.0 in result

    def test_collect_gap_large(self) -> None:
        """Gap of 120s → three fallback timestamps inserted at 30s, 60s, 90s."""
        midpoints = [0.0, 120.0]
        with patch(MOCK_TARGET, return_value=[]):
            result = collect_keyframe_timestamps(
                proxy=None,  # type: ignore[arg-type]
                subtitle_midpoints=midpoints,
                gap_threshold_s=30.0,
                interval_s=30.0,
            )
        assert 30.0 in result
        assert 60.0 in result
        assert 90.0 in result
        assert 120.0 in result


class TestCollectDeduplicates:
    def test_collect_deduplicates(self) -> None:
        """Subtitle midpoint and scene midpoint at same second → only one entry in output."""
        midpoints = [10.0, 50.0]

        # Simulate a scene whose midpoint equals an existing subtitle midpoint
        class FakeSceneStart:
            def get_seconds(self):
                return 0.0

        class FakeSceneEnd:
            def get_seconds(self):
                return 20.0  # midpoint = 10.0 — same as subtitle_midpoints[0]

        fake_scenes = [(FakeSceneStart(), FakeSceneEnd())]

        with patch(MOCK_TARGET, return_value=fake_scenes):
            result = collect_keyframe_timestamps(
                proxy=None,  # type: ignore[arg-type]
                subtitle_midpoints=midpoints,
                gap_threshold_s=30.0,
                interval_s=30.0,
            )

        # 10.0 must appear exactly once
        assert result.count(10.0) == 1


class TestCollectSorted:
    def test_collect_sorted(self) -> None:
        """Timestamps from multiple sources arrive unsorted → output is sorted ascending."""
        # Provide midpoints out of order
        midpoints = [80.0, 20.0, 50.0, 5.0]
        with patch(MOCK_TARGET, return_value=[]):
            result = collect_keyframe_timestamps(
                proxy=None,  # type: ignore[arg-type]
                subtitle_midpoints=midpoints,
            )
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# _infer_source tests
# ---------------------------------------------------------------------------

class TestInferSource:
    def test_infer_source_subtitle(self) -> None:
        """Timestamp in subtitle_midpoints set → 'subtitle_midpoint'."""
        assert _infer_source(5.0, {5.0, 10.0, 15.0}) == "subtitle_midpoint"

    def test_infer_source_scene(self) -> None:
        """Timestamp not in subtitle_midpoints → 'scene_change'."""
        assert _infer_source(7.5, {5.0, 10.0, 15.0}) == "scene_change"

    def test_infer_source_empty_set(self) -> None:
        """Empty subtitle_midpoints set → any timestamp returns 'scene_change'."""
        assert _infer_source(42.0, set()) == "scene_change"

    def test_infer_source_exact_match(self) -> None:
        """Exact float membership check works correctly."""
        ts = 12.345
        assert _infer_source(ts, {ts}) == "subtitle_midpoint"
        assert _infer_source(ts, {ts + 0.001}) == "scene_change"
