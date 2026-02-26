"""Subtitle parser with emotion classification.

Supports SRT and ASS/SSA subtitle formats via pysubs2.  Non-UTF-8 files
are detected with charset-normalizer before a second parse attempt; if
encoding detection also fails, ``SubtitleParseError`` is raised with a
human-readable message rather than silently dropping events.
"""

from __future__ import annotations

from pathlib import Path

import pysubs2
from charset_normalizer import from_path

from cinecut.errors import SubtitleParseError
from cinecut.models import DialogueEvent


# ---------------------------------------------------------------------------
# Emotion keyword table — evaluated in priority order (first match wins).
# intense > romantic > comedic > negative > positive > neutral
# ---------------------------------------------------------------------------
_EMOTION_KEYWORDS: dict[str, set[str]] = {
    "intense":  {"now", "run", "fight", "stop", "must", "war", "attack", "danger", "kill", "die"},
    "romantic": {"heart", "together", "always", "forever", "kiss", "love", "feel"},
    "comedic":  {"ha", "funny", "joke", "laugh", "silly", "weird", "crazy"},
    "negative": {"hate", "lost", "never", "dead", "fail", "cry", "wrong", "afraid"},
    "positive": {"happy", "wonderful", "hope", "proud", "yes", "win", "joy", "great", "safe"},
}


def classify_emotion(text: str) -> str:
    """Return an emotion label for *text* based on keyword matching.

    Labels (in priority order): ``intense`` > ``romantic`` > ``comedic``
    > ``negative`` > ``positive`` > ``neutral``.

    Parameters
    ----------
    text:
        Raw or cleaned subtitle text.

    Returns
    -------
    str
        One of ``"intense"``, ``"romantic"``, ``"comedic"``, ``"negative"``,
        ``"positive"``, or ``"neutral"``.
    """
    words = set(text.lower().split())
    for label, keywords in _EMOTION_KEYWORDS.items():
        if words & keywords:
            return label
    return "neutral"


def parse_subtitles(subtitle_path: Path) -> list[DialogueEvent]:
    """Parse an SRT or ASS subtitle file into a list of :class:`DialogueEvent`.

    Parameters
    ----------
    subtitle_path:
        Path to a ``.srt`` or ``.ass`` / ``.ssa`` file.

    Returns
    -------
    list[DialogueEvent]
        Events with PTS seconds, midpoint timestamps, and emotion labels.
        Comment events and events with empty text are silently skipped.

    Raises
    ------
    SubtitleParseError
        If the file cannot be loaded (including unresolvable encoding).
    """
    subs = _load_with_encoding_fallback(subtitle_path)

    events: list[DialogueEvent] = []
    for event in subs:
        # Skip comment-only events
        if event.is_comment:
            continue
        # Skip events with no visible text after tag-stripping
        text = event.plaintext.strip()
        if not text:
            continue

        start_s = event.start / 1000.0
        end_s = event.end / 1000.0
        midpoint_s = round((start_s + end_s) / 2.0, 3)

        events.append(
            DialogueEvent(
                start_ms=event.start,
                end_ms=event.end,
                start_s=start_s,
                end_s=end_s,
                midpoint_s=midpoint_s,
                text=text,
                emotion=classify_emotion(text),
            )
        )

    return events


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_with_encoding_fallback(subtitle_path: Path):  # type: ignore[return]
    """Load *subtitle_path* with UTF-8, falling back to charset-normalizer.

    Raises ``SubtitleParseError`` if encoding cannot be determined or the
    file is not valid SRT/ASS syntax.
    """
    try:
        return pysubs2.load(str(subtitle_path), encoding="utf-8")
    except UnicodeDecodeError:
        pass
    except Exception as exc:
        raise SubtitleParseError(subtitle_path, str(exc)) from exc

    # UTF-8 failed — try charset-normalizer
    results = from_path(subtitle_path)
    best = results.best()
    if best is None:
        raise SubtitleParseError(
            subtitle_path,
            "Could not determine file encoding. Re-save as UTF-8.",
        )
    detected_encoding = best.encoding
    try:
        return pysubs2.load(str(subtitle_path), encoding=detected_encoding)
    except Exception as exc:
        raise SubtitleParseError(subtitle_path, str(exc)) from exc
