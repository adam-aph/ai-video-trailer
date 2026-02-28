"""Manifest assembly pipeline: scored/classified scenes -> TRAILER_MANIFEST.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from cinecut.manifest.schema import ClipEntry, TrailerManifest, StructuralAnchors
from cinecut.manifest.vibes import VIBE_PROFILES, VibeProfile
from cinecut.models import DialogueEvent, KeyframeRecord
from cinecut.narrative.signals import RawSignals, extract_all_signals, get_film_duration_s
from cinecut.narrative.scorer import (
    assign_act,
    classify_beat,
    compute_money_shot_score,
    normalize_all_signals,
)


def compute_clip_window(
    timestamp_s: float,
    act: str,
    vibe_profile: VibeProfile,
    film_duration_s: float,
) -> tuple[float, float]:
    """Compute start/end window for a clip centered around its keyframe timestamp.

    Duration mapping by act:
      cold_open, act1 -> act1_avg_cut_s
      beat_drop, act2 -> act2_avg_cut_s
      breath        -> act2_avg_cut_s * 1.5
      act3          -> act3_avg_cut_s
      else          -> act2_avg_cut_s

    Biased 30% before keyframe, 70% after.
    """
    act_to_duration: dict[str, float] = {
        "cold_open": vibe_profile.act1_avg_cut_s,
        "act1": vibe_profile.act1_avg_cut_s,
        "beat_drop": vibe_profile.act2_avg_cut_s,
        "act2": vibe_profile.act2_avg_cut_s,
        "breath": vibe_profile.act2_avg_cut_s * 1.5,
        "act3": vibe_profile.act3_avg_cut_s,
    }
    duration = act_to_duration.get(act, vibe_profile.act2_avg_cut_s)
    start = max(0.0, timestamp_s - duration * 0.3)
    end = min(film_duration_s, timestamp_s + duration * 0.7)
    return (start, end)


def resolve_overlaps(
    windows: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Fix overlapping adjacent windows by shortening the earlier clip's end.

    Guarantees: windows[i][1] <= windows[i+1][0] - 0.5 gap where possible.
    If shortening would make end <= start, sets end = start + 0.1 (degenerate).
    """
    if len(windows) <= 1:
        return list(windows)

    result = list(windows)
    for i in range(len(result) - 1):
        start_i, end_i = result[i]
        start_next, _ = result[i + 1]
        if end_i > start_next:
            new_end = start_next - 0.5
            if new_end <= start_i:
                new_end = start_i + 0.1  # degenerate — will be filtered downstream
            result[i] = (start_i, new_end)
    return result


def get_dialogue_excerpt(
    timestamp_s: float,
    dialogue_events: list[DialogueEvent],
    window_s: float = 5.0,
) -> str:
    """Return text of nearest DialogueEvent within window_s of timestamp_s.

    Prefers events that directly overlap (start_s <= timestamp_s <= end_s).
    Among proximity matches, picks the one with smallest distance to midpoint.
    Returns empty string if no event is found within the window.
    """
    if not dialogue_events:
        return ""

    # Direct overlap: timestamp falls within the event
    for event in dialogue_events:
        if event.start_s <= timestamp_s <= event.end_s:
            return event.text

    # Proximity: nearest event midpoint within window_s
    best_dist = float("inf")
    best_text = ""
    for event in dialogue_events:
        midpoint = (event.start_s + event.end_s) / 2.0
        dist = abs(timestamp_s - midpoint)
        if dist < best_dist:
            best_dist = dist
            best_text = event.text

    if best_dist <= window_s:
        return best_text
    return ""


def get_nearest_emotion(
    timestamp_s: float,
    dialogue_events: list[DialogueEvent],
    window_s: float = 5.0,
) -> str:
    """Return the emotion string of the nearest DialogueEvent within window_s.

    Prefers events that directly overlap. Among proximity matches, picks
    nearest by distance to event midpoint.
    Returns "neutral" if no event is found within the window.
    """
    if not dialogue_events:
        return "neutral"

    # Direct overlap
    for event in dialogue_events:
        if event.start_s <= timestamp_s <= event.end_s:
            return event.emotion

    # Proximity
    best_dist = float("inf")
    best_emotion = "neutral"
    for event in dialogue_events:
        midpoint = (event.start_s + event.end_s) / 2.0
        dist = abs(timestamp_s - midpoint)
        if dist < best_dist:
            best_dist = dist
            best_emotion = event.emotion

    if best_dist <= window_s:
        return best_emotion
    return "neutral"


def get_transition(act: str, vibe_profile: VibeProfile) -> str:
    """Return the appropriate transition type for a given act.

    Act boundaries (cold_open, beat_drop, act3) use secondary_transition.
    All others use primary_transition.
    """
    if act in ("cold_open", "beat_drop", "act3"):
        return vibe_profile.secondary_transition
    return vibe_profile.primary_transition


def build_reasoning(record: KeyframeRecord, desc, beat_type: str, score: float) -> str:
    """Construct a short reasoning string for a clip entry.

    Format: "Beat: {beat_type}. Score: {score:.2f}. Source: {record.source}. " +
            visual info from desc if present.
    """
    visual_info = (
        f"Visual: {desc.mood}, {desc.action}."
        if desc is not None
        else "No visual description."
    )
    return (
        f"Beat: {beat_type}. Score: {score:.2f}. "
        f"Source: {record.source}. {visual_info}"
    )


def run_narrative_stage(
    inference_results: list,       # list[tuple[KeyframeRecord, SceneDescription | None]]
    dialogue_events: list,         # list[DialogueEvent]
    vibe: str,                     # e.g. "action"
    source_file: Path,             # original MKV/AVI/MP4 (NOT the proxy)
    work_dir: Path,                # directory to write TRAILER_MANIFEST.json
    progress_callback: Callable[[int, int], None] | None = None,
    structural_anchors: Optional[StructuralAnchors] = None,   # Phase 7 structural anchors
) -> Path:                         # path to written TRAILER_MANIFEST.json
    """Full manifest assembly pipeline.

    1. Determine film duration.
    2. Extract signals from all keyframes.
    3. Normalize signals across the pool.
    4. Score, classify, and assign act for each frame.
    5. Select top-N by score (limited to clip_count_max).
    6. Sort selected frames chronologically.
    7. Compute clip windows, resolve overlaps.
    8. Build ClipEntry objects and assemble TrailerManifest.
    9. Write TRAILER_MANIFEST.json and return the path.
    """
    film_duration_s = get_film_duration_s(source_file)

    # Unpack inference results
    records: list[KeyframeRecord] = [r for r, _ in inference_results]
    descriptions = [d for _, d in inference_results]

    # Extract and normalize signals
    raw_signals = extract_all_signals(records, descriptions, dialogue_events, film_duration_s)
    normalized = normalize_all_signals(raw_signals)

    vibe_profile = VIBE_PROFILES[vibe]
    total = len(records)

    # Score, classify, and collect metadata for each frame
    scored: list[dict] = []
    for i, (record, desc) in enumerate(zip(records, descriptions)):
        norm = normalized[i]
        score = compute_money_shot_score(norm)
        emotion = get_nearest_emotion(record.timestamp_s, dialogue_events)
        has_face = raw_signals[i].face_presence > 0.5
        chron_pos = raw_signals[i].chronological_position

        beat_type = classify_beat(chron_pos, emotion, score, has_face)
        act = assign_act(chron_pos, beat_type)

        scored.append({
            "record": record,
            "desc": desc,
            "score": score,
            "beat_type": beat_type,
            "act": act,
            "emotion": emotion,
            "raw": raw_signals[i],
            "index": i,
        })

        if progress_callback is not None:
            progress_callback(i + 1, total)

    # Select top-N by score descending, limited to clip_count_max
    n_clips = min(len(scored), vibe_profile.clip_count_max)
    top_scored = sorted(scored, key=lambda x: x["score"], reverse=True)[:n_clips]

    # Sort selected clips chronologically
    top_scored.sort(key=lambda x: x["record"].timestamp_s)

    # Compute clip windows for selected records
    windows = [
        compute_clip_window(
            item["record"].timestamp_s,
            item["act"],
            vibe_profile,
            film_duration_s,
        )
        for item in top_scored
    ]

    # Resolve overlaps
    windows = resolve_overlaps(windows)

    # Build ClipEntry objects
    clip_entries: list[ClipEntry] = []
    for item, (win_start, win_end) in zip(top_scored, windows):
        # Skip degenerate windows (end <= start from resolve_overlaps)
        if win_end <= win_start:
            continue

        record = item["record"]
        desc = item["desc"]
        beat_type = item["beat_type"]
        act = item["act"]
        score = item["score"]
        emotion = item["emotion"]
        raw = item["raw"]

        # Build optional analysis fields
        visual_analysis = (
            f"{desc.visual_content}. {desc.mood}. {desc.action}. {desc.setting}."
            if desc is not None
            else None
        )
        subtitle_analysis = (
            f"Emotion: {emotion}. Weight: {raw.subtitle_emotional_weight:.2f}."
            if emotion != "neutral"
            else None
        )

        clip_entries.append(ClipEntry(
            source_start_s=win_start,
            source_end_s=win_end,
            beat_type=beat_type,
            act=act,
            transition=get_transition(act, vibe_profile),
            dialogue_excerpt=get_dialogue_excerpt(record.timestamp_s, dialogue_events),
            reasoning=build_reasoning(record, desc, beat_type, score),
            visual_analysis=visual_analysis,
            subtitle_analysis=subtitle_analysis,
            money_shot_score=round(score, 4),
        ))

    # Assemble and write manifest
    manifest = TrailerManifest(
        source_file=str(source_file),
        vibe=vibe,
        clips=clip_entries,
        structural_anchors=structural_anchors,   # None is fine; field is Optional
    )
    output_path = work_dir / "TRAILER_MANIFEST.json"
    output_path.write_text(
        manifest.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )
    return output_path
