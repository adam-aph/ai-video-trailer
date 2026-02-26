"""Unit tests for cinecut.ingestion.subtitles.

All tests are self-contained: subtitle content is written inline to
``tmp_path`` using pytest fixtures.  No real media files are required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinecut.ingestion.subtitles import classify_emotion, parse_subtitles
from cinecut.models import DialogueEvent


# ---------------------------------------------------------------------------
# Minimal SRT fixture (valid format, 2 real events)
# ---------------------------------------------------------------------------
_SRT_CONTENT = """\
1
00:00:01,000 --> 00:00:03,000
Hello, world!

2
00:00:04,000 --> 00:00:06,000
I must fight for what I believe.

"""

# ---------------------------------------------------------------------------
# Minimal ASS fixture (bare minimum: Script Info + Events section)
# ---------------------------------------------------------------------------
_ASS_CONTENT = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 480

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Forever together we stand.
"""


class TestParseSrt:
    def test_parse_srt_basic(self, tmp_path: Path) -> None:
        """SRT with two events → 2 DialogueEvent objects with correct fields."""
        p = tmp_path / "test.srt"
        p.write_text(_SRT_CONTENT, encoding="utf-8")

        events = parse_subtitles(p)

        assert len(events) == 2
        first = events[0]
        assert isinstance(first, DialogueEvent)
        assert first.text == "Hello, world!"
        assert first.start_ms == 1000
        assert first.end_ms == 3000

    def test_parse_srt_returns_dialogue_events(self, tmp_path: Path) -> None:
        """All returned objects are DialogueEvent instances."""
        p = tmp_path / "test.srt"
        p.write_text(_SRT_CONTENT, encoding="utf-8")
        events = parse_subtitles(p)
        for ev in events:
            assert isinstance(ev, DialogueEvent)

    def test_pts_seconds(self, tmp_path: Path) -> None:
        """start_ms=5000 → start_s=5.0, end_ms=7000 → end_s=7.0."""
        srt = "1\n00:00:05,000 --> 00:00:07,000\nHello!\n\n"
        p = tmp_path / "pts.srt"
        p.write_text(srt, encoding="utf-8")
        events = parse_subtitles(p)
        assert len(events) == 1
        assert events[0].start_s == 5.0
        assert events[0].end_s == 7.0

    def test_midpoint_calculation(self, tmp_path: Path) -> None:
        """Event with start=0ms, end=2000ms → midpoint_s=1.0."""
        srt = "1\n00:00:00,000 --> 00:00:02,000\nTest event.\n\n"
        p = tmp_path / "mid.srt"
        p.write_text(srt, encoding="utf-8")
        events = parse_subtitles(p)
        assert len(events) == 1
        assert events[0].midpoint_s == 1.0


class TestParseAss:
    def test_parse_ass_basic(self, tmp_path: Path) -> None:
        """ASS file with one dialogue event is parsed correctly."""
        p = tmp_path / "test.ass"
        p.write_text(_ASS_CONTENT, encoding="utf-8")

        events = parse_subtitles(p)

        assert len(events) == 1
        assert "Forever" in events[0].text or "forever" in events[0].text.lower()

    def test_parse_ass_returns_dialogue_event(self, tmp_path: Path) -> None:
        """ASS parsing returns DialogueEvent instances (same as SRT)."""
        p = tmp_path / "test.ass"
        p.write_text(_ASS_CONTENT, encoding="utf-8")
        events = parse_subtitles(p)
        for ev in events:
            assert isinstance(ev, DialogueEvent)


class TestSkipsEmptyEvents:
    def test_skips_empty_events(self, tmp_path: Path) -> None:
        """SRT events with only whitespace text produce no DialogueEvents."""
        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\n   \n\n"
            "2\n00:00:04,000 --> 00:00:06,000\nReal line.\n\n"
        )
        p = tmp_path / "blank.srt"
        p.write_text(srt, encoding="utf-8")
        events = parse_subtitles(p)
        # Only the non-blank event should survive
        assert len(events) == 1
        assert events[0].text == "Real line."


class TestClassifyEmotion:
    def test_classify_neutral(self) -> None:
        """Text with no recognised keywords → 'neutral'."""
        assert classify_emotion("hello world") == "neutral"
        assert classify_emotion("") == "neutral"
        assert classify_emotion("the quick brown fox") == "neutral"

    def test_classify_intense(self) -> None:
        """Text containing 'fight' → 'intense'."""
        assert classify_emotion("I must fight") == "intense"
        assert classify_emotion("We will fight them at dawn") == "intense"

    def test_classify_romantic(self) -> None:
        """Text containing 'forever' → 'romantic'."""
        assert classify_emotion("we will be together forever") == "romantic"
        assert classify_emotion("I love you") == "romantic"

    def test_classify_comedic(self) -> None:
        """Text containing 'funny' → 'comedic'."""
        assert classify_emotion("that is so funny") == "comedic"

    def test_classify_negative(self) -> None:
        """Text containing 'afraid' → 'negative'."""
        assert classify_emotion("I am afraid") == "negative"

    def test_classify_positive(self) -> None:
        """Text containing 'happy' → 'positive'."""
        assert classify_emotion("I am so happy today") == "positive"

    def test_intense_priority_over_romantic(self) -> None:
        """'love' alone is romantic; 'love' + 'kill' is intense (priority order)."""
        assert classify_emotion("love") == "romantic"
        assert classify_emotion("love and kill") == "intense"

    def test_emotion_stored_in_event(self, tmp_path: Path) -> None:
        """parse_subtitles stores classify_emotion result in DialogueEvent.emotion."""
        srt = "1\n00:00:00,000 --> 00:00:02,000\nI must fight!\n\n"
        p = tmp_path / "emotion.srt"
        p.write_text(srt, encoding="utf-8")
        events = parse_subtitles(p)
        assert len(events) == 1
        assert events[0].emotion == "intense"
