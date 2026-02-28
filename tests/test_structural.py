"""Unit tests for cinecut.inference.structural — no live LLM required."""
import pytest
from unittest.mock import MagicMock

from cinecut.models import DialogueEvent
from cinecut.inference.structural import (
    CHUNK_SIZE,
    _chunk_events,
    _format_subtitle_chunk,
    _clamp_anchors_to_chunk,
    compute_heuristic_anchors,
    run_structural_analysis,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_event(i: int, start_s: float) -> DialogueEvent:
    """Create a minimal DialogueEvent for testing."""
    return DialogueEvent(
        start_ms=int(start_s * 1000),
        end_ms=int((start_s + 2) * 1000),
        start_s=start_s,
        end_s=start_s + 2.0,
        midpoint_s=start_s + 1.0,
        text=f"Hello {i}",
        emotion="neutral",
    )


def make_events(count: int, start_offset: float = 0.0) -> list[DialogueEvent]:
    """Create a sequence of count events, each 3 seconds apart."""
    return [make_event(i, start_offset + i * 3.0) for i in range(count)]


# ---------------------------------------------------------------------------
# _chunk_events tests
# ---------------------------------------------------------------------------

class TestChunkEvents:
    def test_chunk_events_basic(self):
        """150 events should produce two chunks of [75, 75]."""
        events = make_events(150)
        chunks = _chunk_events(events)
        assert len(chunks) == 2
        assert len(chunks[0]) == 75
        assert len(chunks[1]) == 75

    def test_chunk_events_partial(self):
        """80 events should produce [75, 5]."""
        events = make_events(80)
        chunks = _chunk_events(events)
        assert len(chunks) == 2
        assert len(chunks[0]) == 75
        assert len(chunks[1]) == 5

    def test_chunk_events_empty(self):
        """Empty list should return empty list."""
        chunks = _chunk_events([])
        assert chunks == []

    def test_chunk_events_exact_size(self):
        """Exactly CHUNK_SIZE events should produce one chunk."""
        events = make_events(CHUNK_SIZE)
        chunks = _chunk_events(events)
        assert len(chunks) == 1
        assert len(chunks[0]) == CHUNK_SIZE

    def test_chunk_events_single(self):
        """Single event produces one chunk of size 1."""
        events = make_events(1)
        chunks = _chunk_events(events)
        assert len(chunks) == 1
        assert len(chunks[0]) == 1


# ---------------------------------------------------------------------------
# _format_subtitle_chunk tests
# ---------------------------------------------------------------------------

class TestFormatSubtitleChunk:
    def test_format_subtitle_chunk_uses_absolute_timestamps(self):
        """Events with start_s=120.0 must produce '[120.0s]' — NOT '[0.0s]'."""
        events = [
            make_event(0, 120.0),
            make_event(1, 123.0),
        ]
        result = _format_subtitle_chunk(events)
        assert "[120.0s]" in result
        assert "[123.0s]" in result
        assert "[0.0s]" not in result

    def test_format_subtitle_chunk_includes_text(self):
        """Formatted output should include event text."""
        events = [make_event(0, 0.0)]
        result = _format_subtitle_chunk(events)
        assert "Hello 0" in result

    def test_format_subtitle_chunk_one_line_per_event(self):
        """Three events should produce three newline-separated lines."""
        events = make_events(3)
        result = _format_subtitle_chunk(events)
        lines = result.split("\n")
        assert len(lines) == 3


# ---------------------------------------------------------------------------
# _clamp_anchors_to_chunk tests
# ---------------------------------------------------------------------------

class TestClampAnchorsToChunk:
    def test_clamp_anchors_valid(self):
        """All anchors within chunk range should pass through unchanged."""
        chunk = make_events(5, start_offset=100.0)
        # chunk spans 100.0 to 114.0 (last event end_s = 112.0 + 2.0)
        result = {"begin_t": 100.0, "escalation_t": 105.0, "climax_t": 110.0}
        out = _clamp_anchors_to_chunk(result, chunk)
        assert out == result

    def test_clamp_anchors_within_tolerance(self):
        """Anchors up to 10s outside chunk boundaries should be accepted."""
        chunk = make_events(5, start_offset=100.0)
        # chunk_start=100.0, chunk_end ~114.0; tolerance window [90.0, 124.0]
        result = {"begin_t": 91.0, "escalation_t": 105.0, "climax_t": 123.0}
        out = _clamp_anchors_to_chunk(result, chunk)
        assert out == result

    def test_clamp_anchors_hallucinated(self):
        """Anchors far outside chunk range should return None."""
        chunk = make_events(5, start_offset=100.0)
        # begin_t=5000.0 is way outside the chunk — should be rejected
        result = {"begin_t": 5000.0, "escalation_t": 5500.0, "climax_t": 6000.0}
        out = _clamp_anchors_to_chunk(result, chunk)
        assert out is None

    def test_clamp_anchors_partially_out(self):
        """If any single anchor is outside range, full result is discarded."""
        chunk = make_events(5, start_offset=100.0)
        # climax_t is way out of range even though begin_t and escalation_t are fine
        result = {"begin_t": 100.0, "escalation_t": 105.0, "climax_t": 9999.0}
        out = _clamp_anchors_to_chunk(result, chunk)
        assert out is None


# ---------------------------------------------------------------------------
# compute_heuristic_anchors tests
# ---------------------------------------------------------------------------

class TestComputeHeuristicAnchors:
    def test_compute_heuristic_anchors(self):
        """7200s film: begin=360.0, esc=3240.0, climax=5760.0, source='heuristic'."""
        a = compute_heuristic_anchors(7200.0)
        assert a.begin_t == 360.0      # 5% of 7200
        assert a.escalation_t == 3240.0  # 45% of 7200
        assert a.climax_t == 5760.0    # 80% of 7200
        assert a.source == "heuristic"

    def test_compute_heuristic_anchors_90min(self):
        """5400s (90-minute) film: begin=270.0, esc=2430.0, climax=4320.0."""
        a = compute_heuristic_anchors(5400.0)
        assert a.begin_t == 270.0
        assert a.escalation_t == 2430.0
        assert a.climax_t == 4320.0
        assert a.source == "heuristic"

    def test_compute_heuristic_anchors_zero(self):
        """Zero duration produces all-zero anchors."""
        a = compute_heuristic_anchors(0.0)
        assert a.begin_t == 0.0
        assert a.escalation_t == 0.0
        assert a.climax_t == 0.0
        assert a.source == "heuristic"


# ---------------------------------------------------------------------------
# run_structural_analysis tests
# ---------------------------------------------------------------------------

class TestRunStructuralAnalysis:
    def test_run_structural_analysis_single_chunk(self):
        """Single chunk with valid LLM response should return source='llm'.

        Anchor timestamps must be within [chunk_start-10, chunk_end+10] to pass
        _clamp_anchors_to_chunk. Events span 0..29s so use values in that range.
        """
        events = make_events(10, start_offset=0.0)  # 10 events, start_s=0..27, end_s ~31
        engine = MagicMock()
        engine.analyze_chunk.return_value = {
            "begin_t": 3.0,
            "escalation_t": 12.0,
            "climax_t": 24.0,
        }
        result = run_structural_analysis(events, engine)
        assert result.source == "llm"
        assert result.begin_t == 3.0
        assert result.escalation_t == 12.0
        assert result.climax_t == 24.0

    def test_run_structural_analysis_all_chunks_fail(self):
        """When engine.analyze_chunk always returns None, result source='heuristic'."""
        events = make_events(20, start_offset=100.0)
        engine = MagicMock()
        engine.analyze_chunk.return_value = None
        result = run_structural_analysis(events, engine)
        assert result.source == "heuristic"

    def test_run_structural_analysis_median_aggregation(self):
        """Two valid chunks: median of begin_t values from chunk-local timestamps.

        Anchor timestamps must be within [chunk_start-10, chunk_end+10] to survive
        _clamp_anchors_to_chunk. Chunk1 spans 0..222s, chunk2 spans 225..447s.
        """
        chunk1_events = make_events(75, start_offset=0.0)     # start_s: 0..222, end_s ~224
        chunk2_events = make_events(75, start_offset=225.0)   # start_s: 225..447, end_s ~449
        all_events = chunk1_events + chunk2_events

        # Each response uses timestamps within its chunk's span (+/-10s tolerance)
        responses = [
            {"begin_t": 10.0, "escalation_t": 100.0, "climax_t": 200.0},   # chunk1: 0..224
            {"begin_t": 230.0, "escalation_t": 330.0, "climax_t": 430.0},  # chunk2: 225..449
        ]
        engine = MagicMock()
        engine.analyze_chunk.side_effect = responses

        result = run_structural_analysis(all_events, engine)
        assert result.source == "llm"
        assert result.begin_t == 120.0       # median of [10.0, 230.0]
        assert result.escalation_t == 215.0  # median of [100.0, 330.0]
        assert result.climax_t == 315.0      # median of [200.0, 430.0]

    def test_run_structural_analysis_empty_events(self):
        """Empty events list should return heuristic anchors."""
        engine = MagicMock()
        result = run_structural_analysis([], engine)
        assert result.source == "heuristic"
        engine.analyze_chunk.assert_not_called()

    def test_run_structural_analysis_hallucinated_clamped_out(self):
        """Hallucinated timestamps outside chunk range should be clamped to None."""
        events = make_events(10, start_offset=0.0)  # chunk spans ~0-30s
        engine = MagicMock()
        # Return timestamps far outside the chunk — should be clamped
        engine.analyze_chunk.return_value = {
            "begin_t": 99999.0,
            "escalation_t": 99999.0,
            "climax_t": 99999.0,
        }
        result = run_structural_analysis(events, engine)
        # All clamped out -> heuristic fallback
        assert result.source == "heuristic"
