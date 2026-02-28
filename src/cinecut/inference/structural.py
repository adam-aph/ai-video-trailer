"""Structural analysis: subtitle chunking + LLM anchor extraction + heuristic fallback."""
import statistics
from typing import TYPE_CHECKING

from cinecut.models import DialogueEvent

if TYPE_CHECKING:
    from cinecut.inference.text_engine import TextEngine

CHUNK_SIZE = 75  # midpoint of 50-100 requirement range; ~1500 tokens per chunk

STRUCTURAL_ANCHORS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "begin_t": {"type": "number", "description": "timestamp in seconds where narrative begins"},
        "escalation_t": {"type": "number", "description": "timestamp in seconds of escalation"},
        "climax_t": {"type": "number", "description": "timestamp in seconds of climax"},
    },
    "required": ["begin_t", "escalation_t", "climax_t"],
    "additionalProperties": False,
}


def _format_subtitle_chunk(events: list[DialogueEvent]) -> str:
    """Format a list of DialogueEvents as a readable transcript string.

    Uses absolute start_s timestamps — never normalized to 0.
    """
    return "\n".join(f"[{ev.start_s:.1f}s] {ev.text}" for ev in events)


def _chunk_events(events: list[DialogueEvent]) -> list[list[DialogueEvent]]:
    """Split events list into chunks of CHUNK_SIZE."""
    return [events[i:i + CHUNK_SIZE] for i in range(0, len(events), CHUNK_SIZE)]


def _clamp_anchors_to_chunk(result: dict, chunk: list[DialogueEvent]) -> dict | None:
    """Return result unchanged if all anchor timestamps are within chunk range.

    Discards (returns None) results where any timestamp is more than 10 seconds
    outside the chunk boundaries — guards against LLM hallucinations.
    """
    chunk_start = chunk[0].start_s
    chunk_end = chunk[-1].end_s
    low = chunk_start - 10.0
    high = chunk_end + 10.0
    for key in ("begin_t", "escalation_t", "climax_t"):
        val = result.get(key)
        if val is None or not (low <= val <= high):
            return None
    return result


def compute_heuristic_anchors(duration_s: float) -> "StructuralAnchors":
    """Return structural anchors using 5%/45%/80% zone heuristic.

    Used as fallback when Mistral GGUF is absent or LLM chunks all fail.
    """
    from cinecut.manifest.schema import StructuralAnchors  # inline to avoid circular import
    return StructuralAnchors(
        begin_t=round(duration_s * 0.05, 2),
        escalation_t=round(duration_s * 0.45, 2),
        climax_t=round(duration_s * 0.80, 2),
        source="heuristic",
    )


def run_structural_analysis(
    dialogue_events: list[DialogueEvent],
    engine: "TextEngine",
) -> "StructuralAnchors":
    """Analyse subtitle corpus with LLM and return structural anchors.

    Processes subtitle events in chunks of CHUNK_SIZE, aggregating results via
    median to smooth out per-chunk variation. Falls back to heuristic anchors
    if no valid LLM results are obtained.
    """
    from cinecut.manifest.schema import StructuralAnchors  # inline to avoid circular import

    chunks = _chunk_events(dialogue_events)
    valid_results: list[dict] = []

    for chunk in chunks:
        chunk_text = _format_subtitle_chunk(chunk)
        raw = engine.analyze_chunk(chunk_text)
        if raw is None:
            continue
        clamped = _clamp_anchors_to_chunk(raw, chunk)
        if clamped is not None:
            valid_results.append(clamped)

    if not valid_results:
        # All chunks failed — derive from subtitle span using heuristic ratios
        if dialogue_events:
            span = dialogue_events[-1].end_s - dialogue_events[0].start_s
            return compute_heuristic_anchors(span)
        return compute_heuristic_anchors(0.0)

    return StructuralAnchors(
        begin_t=round(statistics.median([r["begin_t"] for r in valid_results]), 2),
        escalation_t=round(statistics.median([r["escalation_t"] for r in valid_results]), 2),
        climax_t=round(statistics.median([r["climax_t"] for r in valid_results]), 2),
        source="llm",
    )
