"""Normalization, weighted money shot scoring, beat classification, and act assignment."""

from __future__ import annotations

from cinecut.narrative.signals import RawSignals

# Signal weights — must sum to exactly 1.0
SIGNAL_WEIGHTS: dict[str, float] = {
    "motion_magnitude":          0.20,
    "visual_contrast":           0.15,
    "scene_uniqueness":          0.15,
    "subtitle_emotional_weight": 0.20,
    "face_presence":             0.10,
    "llava_confidence":          0.10,
    "saturation":                0.05,
    "chronological_position":    0.05,
}
assert abs(sum(SIGNAL_WEIGHTS.values()) - 1.0) < 1e-9, (
    f"SIGNAL_WEIGHTS must sum to 1.0, got {sum(SIGNAL_WEIGHTS.values())}"
)


def normalize_signal_pool(raw_values: list[float]) -> list[float]:
    """Min-max normalize a pool of raw signal values to [0.0, 1.0].

    If all values are equal (max == min), returns [0.5] * len(raw_values).
    """
    if not raw_values:
        return []

    min_val = min(raw_values)
    max_val = max(raw_values)

    if max_val == min_val:
        return [0.5] * len(raw_values)

    rng = max_val - min_val
    return [(v - min_val) / rng for v in raw_values]


def normalize_all_signals(
    raw_signals: list[RawSignals],
) -> list[dict[str, float]]:
    """Normalize all 8 signals across the pool of records.

    For each signal name, collects raw values across all records, normalizes
    the pool, then rebuilds per-record normalized dicts.

    Returns:
        List of dicts, each with exactly the 8 SIGNAL_WEIGHTS keys,
        values in [0.0, 1.0].
    """
    if not raw_signals:
        return []

    signal_names = list(SIGNAL_WEIGHTS.keys())

    # Collect per-signal pools
    pools: dict[str, list[float]] = {
        name: [getattr(sig, name) for sig in raw_signals]
        for name in signal_names
    }

    # Normalize each pool
    normalized_pools: dict[str, list[float]] = {
        name: normalize_signal_pool(values)
        for name, values in pools.items()
    }

    # Rebuild per-record dicts
    result: list[dict[str, float]] = []
    for i in range(len(raw_signals)):
        record_dict = {name: normalized_pools[name][i] for name in signal_names}
        result.append(record_dict)

    return result


def compute_money_shot_score(normalized: dict[str, float]) -> float:
    """Compute weighted money shot score from normalized signal dict.

    Returns a float in [0.0, 1.0] (assuming inputs are normalized).
    """
    return sum(SIGNAL_WEIGHTS[k] * normalized[k] for k in SIGNAL_WEIGHTS)


def classify_beat(
    chron_pos: float,
    emotion: str,
    money_shot_score: float,
    has_face: bool,
) -> str:
    """Classify a scene into one of 7 beat type strings.

    Rule-based priority: earlier rule wins.

    Valid return values (matching ClipEntry.beat_type Literal):
        "inciting_incident", "character_introduction", "escalation_beat",
        "relationship_beat", "money_shot", "climax_peak", "breath"
    """
    # 1. Low score + neutral emotion → breath
    if money_shot_score < 0.20 and emotion == "neutral":
        return "breath"

    # 2. Late in film + high score → climax
    if chron_pos > 0.75 and money_shot_score > 0.70:
        return "climax_peak"

    # 3. Very high score → money shot
    if money_shot_score > 0.80:
        return "money_shot"

    # 4. Early + face + not intense → character introduction
    if chron_pos < 0.15 and has_face and emotion not in ("intense",):
        return "character_introduction"

    # 5. Early-ish + intense → inciting incident
    if chron_pos < 0.30 and emotion == "intense":
        return "inciting_incident"

    # 6. Romantic + face → relationship beat
    if emotion == "romantic" and has_face:
        return "relationship_beat"

    # 7. Catch-all
    return "escalation_beat"


def assign_act(chron_pos: float, beat_type: str) -> str:
    """Assign an act label based on beat_type and chronological position.

    Beat type wins first: "breath" beat_type always returns "breath" act.
    Otherwise, position-based assignment.

    Valid return values (matching ClipEntry.act Literal):
        "cold_open", "act1", "beat_drop", "act2", "breath", "act3",
        "title_card", "button"
    """
    # Beat type overrides everything
    if beat_type == "breath":
        return "breath"

    # Position-based assignment
    if chron_pos < 0.08:
        return "cold_open"
    if chron_pos < 0.35:
        return "act1"
    if chron_pos < 0.55:
        return "act2"
    if chron_pos < 0.65:
        return "beat_drop"
    if chron_pos < 0.82:
        return "act2"
    return "act3"
