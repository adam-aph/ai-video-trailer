"""8-signal extraction from keyframe records, scene descriptions, and dialogue events."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

from cinecut.models import DialogueEvent, KeyframeRecord

if TYPE_CHECKING:
    from cinecut.inference.models import SceneDescription

# Load face cascade ONCE at module level to avoid 200ms per-frame penalty
_FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

# Emotion weights for subtitle emotional signal
EMOTION_WEIGHTS: dict[str, float] = {
    "intense": 1.0,
    "romantic": 0.7,
    "negative": 0.6,
    "comedic": 0.5,
    "positive": 0.4,
    "neutral": 0.1,
}


@dataclass
class RawSignals:
    """Raw (unnormalized) signal values for a single keyframe."""

    motion_magnitude: float
    visual_contrast: float
    scene_uniqueness: float  # placeholder; filled by pool computation
    subtitle_emotional_weight: float
    face_presence: float
    llava_confidence: float
    saturation: float
    chronological_position: float
    # Non-field: stored after construction for pool uniqueness computation
    _histogram: object = field(default=None, repr=False, compare=False)


def get_film_duration_s(source_file: Path) -> float:
    """Return film duration in seconds via ffprobe.

    Raises subprocess.CalledProcessError on failure (propagates to caller).
    """
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(source_file),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def get_subtitle_emotional_weight(
    timestamp_s: float,
    dialogue_events: list[DialogueEvent],
    window_s: float = 5.0,
) -> float:
    """Return the emotional weight of the subtitle nearest to timestamp_s.

    If timestamp_s falls within an event's start_s..end_s, return its weight
    immediately. Otherwise, find the nearest event by min distance to its
    start/end boundary and return its weight if within window_s, else 0.0.
    """
    if not dialogue_events:
        return 0.0

    # Check if timestamp falls within any event
    for event in dialogue_events:
        if event.start_s <= timestamp_s <= event.end_s:
            return EMOTION_WEIGHTS.get(event.emotion, 0.0)

    # Find nearest event by distance to boundary
    best_distance = float("inf")
    best_weight = 0.0
    for event in dialogue_events:
        dist = min(
            abs(timestamp_s - event.start_s),
            abs(timestamp_s - event.end_s),
        )
        if dist < best_distance:
            best_distance = dist
            best_weight = EMOTION_WEIGHTS.get(event.emotion, 0.0)

    if best_distance <= window_s:
        return best_weight
    return 0.0


def compute_llava_confidence(desc: "SceneDescription | None") -> float:
    """Return a confidence score [0.0, 1.0] for a SceneDescription.

    Score = 0.5 * completeness + 0.5 * richness.
    completeness: fraction of the 4 fields that are non-empty.
    richness: min(1.0, total_char_len / 200.0).
    Returns 0.0 if desc is None.
    """
    if desc is None:
        return 0.0

    fields = [desc.visual_content, desc.mood, desc.action, desc.setting]
    completeness = sum(1.0 for f in fields if f and f.strip()) / 4.0
    total_chars = sum(len(f) for f in fields if f)
    richness = min(1.0, total_chars / 200.0)
    return 0.5 * completeness + 0.5 * richness


def extract_image_signals(frame_path: str) -> dict:
    """Extract per-image signals from a JPEG frame.

    Returns a dict with keys: visual_contrast, saturation, face_presence,
    and _histogram. On corrupt/missing file, all numeric values are 0.0
    and _histogram is None.
    """
    img = cv2.imread(frame_path)
    if img is None:
        return {
            "visual_contrast": 0.0,
            "saturation": 0.0,
            "face_presence": 0.0,
            "_histogram": None,
        }

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Laplacian variance as visual contrast
    visual_contrast = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # Mean saturation channel
    saturation = float(hsv[:, :, 1].mean())

    # Face detection
    faces = _FACE_CASCADE.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30),
    )
    face_presence = 1.0 if len(faces) > 0 else 0.0

    # Normalized HSV histogram for uniqueness computation
    histogram = cv2.calcHist(
        [hsv], [0, 1], None, [50, 60], [0, 180, 0, 256]
    )
    cv2.normalize(histogram, histogram)

    return {
        "visual_contrast": visual_contrast,
        "saturation": saturation,
        "face_presence": face_presence,
        "_histogram": histogram,
    }


def compute_motion_magnitudes(frame_paths: list[str]) -> list[float]:
    """Compute frame-to-frame motion magnitudes.

    First frame gets 0.0. Each subsequent frame: mean absolute difference
    from previous. If a frame is unreadable, appends 0.0 and keeps previous
    gray unchanged.
    """
    magnitudes: list[float] = []
    prev_gray: np.ndarray | None = None

    for path in frame_paths:
        img = cv2.imread(path)
        if img is None:
            magnitudes.append(0.0)
            # Keep prev_gray unchanged -- skip unreadable frame
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)

        if prev_gray is None:
            magnitudes.append(0.0)
        else:
            magnitude = float(np.abs(gray - prev_gray).mean())
            magnitudes.append(magnitude)

        prev_gray = gray

    return magnitudes


def compute_uniqueness_scores(histograms: list) -> list[float]:
    """Compute per-frame uniqueness scores via O(n^2) pairwise histogram comparison.

    uniqueness[i] = max(0.0, 1.0 - max_similarity_to_others).
    If histogram is None, uniqueness = 0.5. For N < 2, returns [0.5] * N.
    """
    n = len(histograms)
    if n < 2:
        return [0.5] * n

    uniqueness: list[float] = []
    for i, hist_i in enumerate(histograms):
        if hist_i is None:
            uniqueness.append(0.5)
            continue

        max_sim = 0.0
        for j, hist_j in enumerate(histograms):
            if i == j or hist_j is None:
                continue
            sim = cv2.compareHist(hist_i, hist_j, cv2.HISTCMP_CORREL)
            if sim > max_sim:
                max_sim = sim

        uniqueness.append(max(0.0, 1.0 - max(0.0, max_sim)))

    return uniqueness


def extract_all_signals(
    records: list[KeyframeRecord],
    scene_descriptions: "list[SceneDescription | None]",
    dialogue_events: list[DialogueEvent],
    film_duration_s: float,
) -> list[RawSignals]:
    """Main entry point: extract all 8 signals for each keyframe record.

    Args:
        records: List of KeyframeRecord objects.
        scene_descriptions: One SceneDescription (or None) per record.
        dialogue_events: All dialogue events for the film.
        film_duration_s: Total film duration in seconds (for chron_pos).

    Returns:
        List of RawSignals, one per record. scene_uniqueness is filled by
        pool-level uniqueness computation within this function.
    """
    if not records:
        return []

    frame_paths = [r.frame_path for r in records]

    # Compute motion magnitudes across all frames
    motions = compute_motion_magnitudes(frame_paths)

    # Extract per-frame image signals
    img_data = [extract_image_signals(r.frame_path) for r in records]

    # Compute pool-level uniqueness from histograms
    histograms = [d["_histogram"] for d in img_data]
    uniqueness_scores = compute_uniqueness_scores(histograms)

    # Avoid division by zero for chronological position
    safe_duration = max(film_duration_s, 1e-9)

    result: list[RawSignals] = []
    for i, record in enumerate(records):
        desc = scene_descriptions[i] if i < len(scene_descriptions) else None

        sig = RawSignals(
            motion_magnitude=motions[i],
            visual_contrast=img_data[i]["visual_contrast"],
            scene_uniqueness=uniqueness_scores[i],
            subtitle_emotional_weight=get_subtitle_emotional_weight(
                record.timestamp_s, dialogue_events
            ),
            face_presence=img_data[i]["face_presence"],
            llava_confidence=compute_llava_confidence(desc),
            saturation=img_data[i]["saturation"],
            chronological_position=min(1.0, record.timestamp_s / safe_duration),
        )
        sig._histogram = img_data[i]["_histogram"]
        result.append(sig)

    return result
