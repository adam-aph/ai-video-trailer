from dataclasses import dataclass


@dataclass
class DialogueEvent:
    """A single subtitle dialogue event with timestamps and emotional classification."""

    start_ms: int       # pysubs2 native unit (milliseconds)
    end_ms: int
    start_s: float      # PTS seconds for downstream use
    end_s: float
    midpoint_s: float   # Used as primary keyframe timestamp (PIPE-03)
    text: str           # Cleaned, ASS-tag-stripped text
    emotion: str        # "positive" | "negative" | "neutral" | "intense" | "comedic" | "romantic"


@dataclass
class KeyframeRecord:
    """A single extracted keyframe with its source timestamp."""

    timestamp_s: float  # PTS seconds in the proxy
    frame_path: str     # Absolute path to the JPEG file
    source: str         # "subtitle_midpoint" | "scene_change" | "interval_fallback"
