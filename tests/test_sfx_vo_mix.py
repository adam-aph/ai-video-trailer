"""Unit tests for Phase 10 audio modules — sfx.py, vo_extract.py, audio_mix.py.

All tests mock subprocess.run to avoid actual FFmpeg calls. Tests verify:
- SFX synthesis idempotency (skips FFmpeg if files already exist)
- Linear chirp formula correctness (slope = (f1-f0)/(2*d))
- Protagonist identification returns None for SRT (no event.name)
- adelay uses milliseconds (not seconds)
- amix normalize=0 in four-stem filtergraph
- Three-stem fallback when music_bed_path is None
"""
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import call, patch, MagicMock

import pysubs2
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completed_proc(returncode: int = 0, stderr: str = ""):
    """Build a MagicMock that looks like a subprocess.CompletedProcess."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.stderr = stderr
    mock.stdout = ""
    return mock


# Fake loudnorm JSON stats that pass the JSON parse in _loudnorm_stem pass 1.
_FAKE_LOUDNORM_STDERR = (
    '{"input_i": "-20.0", "input_lra": "7.0", "input_tp": "-2.0", '
    '"input_thresh": "-30.0", "target_offset": "1.0"}'
)


def _loudnorm_side_effect(cmd, *args, **kwargs):
    """Return loudnorm JSON on stderr for pass-1 calls; empty otherwise."""
    cmd_str = " ".join(str(a) for a in cmd)
    if "print_format=json" in cmd_str or "loudnorm" in cmd_str and "-f null" in cmd_str:
        return _make_completed_proc(0, stderr=_FAKE_LOUDNORM_STDERR)
    return _make_completed_proc(0)


# ---------------------------------------------------------------------------
# SFX tests
# ---------------------------------------------------------------------------

class TestSynthesizeSfxFiles:
    def test_idempotent_skips_ffmpeg(self, tmp_path):
        """If both WAV files already exist, synthesize_sfx_files must not call FFmpeg."""
        from cinecut.conform.sfx import synthesize_sfx_files

        sfx_dir = tmp_path / "sfx"
        sfx_dir.mkdir()
        (sfx_dir / "sfx_hard.wav").touch()
        (sfx_dir / "sfx_boundary.wav").touch()

        with patch("cinecut.conform.sfx.subprocess.run") as mock_run:
            sfx_hard, sfx_boundary = synthesize_sfx_files(tmp_path)

        mock_run.assert_not_called()
        assert sfx_hard.name == "sfx_hard.wav"
        assert sfx_boundary.name == "sfx_boundary.wav"

    def test_chirp_formula_slopes(self, tmp_path):
        """Verify aevalsrc expressions contain the correct linear chirp slopes.

        sfx_hard.wav:     3000Hz -> 300Hz over 0.4s  => slope = (300-3000)/(2*0.4) = -3375
        sfx_boundary.wav: 200Hz -> 2000Hz over 1.2s  => slope = (2000-200)/(2*1.2) = 750
        """
        from cinecut.conform.sfx import synthesize_sfx_files

        with patch("cinecut.conform.sfx.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_proc(0)
            synthesize_sfx_files(tmp_path)

        assert mock_run.call_count == 2, "Expected 2 FFmpeg calls (one per SFX tier)"

        # First call is sfx_hard.wav
        hard_call_args = mock_run.call_args_list[0][0][0]  # positional list arg
        hard_cmd_str = " ".join(str(a) for a in hard_call_args)
        assert "-3375" in hard_cmd_str, (
            f"Expected slope -3375 in sfx_hard cmd, got: {hard_cmd_str}"
        )

        # Second call is sfx_boundary.wav
        boundary_call_args = mock_run.call_args_list[1][0][0]
        boundary_cmd_str = " ".join(str(a) for a in boundary_call_args)
        assert "750" in boundary_cmd_str, (
            f"Expected slope 750 in sfx_boundary cmd, got: {boundary_cmd_str}"
        )


# ---------------------------------------------------------------------------
# Protagonist identification tests
# ---------------------------------------------------------------------------

class TestIdentifyProtagonist:
    def test_srt_returns_none(self, tmp_path):
        """SRT files have no event.name; identify_protagonist must return None."""
        from cinecut.conform.vo_extract import identify_protagonist

        subs = pysubs2.SSAFile()
        for text in ["Hello world.", "Another line.", "More dialogue."]:
            event = pysubs2.SSAEvent(start=0, end=2000, text=text)
            # SRT events have empty name
            event.name = ""
            subs.append(event)

        srt_path = tmp_path / "test.srt"
        subs.save(str(srt_path), format_="srt")

        result = identify_protagonist(srt_path)
        assert result is None

    def test_ass_returns_most_frequent(self, tmp_path):
        """ASS files with speaker names return the most-frequent speaker."""
        from cinecut.conform.vo_extract import identify_protagonist

        subs = pysubs2.SSAFile()

        # HERO appears 5 times
        for i in range(5):
            event = pysubs2.SSAEvent(start=i * 3000, end=i * 3000 + 2000, text=f"Hero line {i}.")
            event.name = "HERO"
            subs.append(event)

        # VILLAIN appears 2 times
        for i in range(2):
            event = pysubs2.SSAEvent(start=20000 + i * 3000, end=20000 + i * 3000 + 2000, text=f"Villain line {i}.")
            event.name = "VILLAIN"
            subs.append(event)

        ass_path = tmp_path / "test.ass"
        subs.save(str(ass_path), format_="ass")

        result = identify_protagonist(ass_path)
        assert result == "HERO"


# ---------------------------------------------------------------------------
# adelay milliseconds test
# ---------------------------------------------------------------------------

class TestAdelayMilliseconds:
    def test_adelay_uses_milliseconds(self, tmp_path):
        """adelay offset for a cut at t=5.0s must be ~4900ms (5000 - 100ms lead).

        Hard cut lead = SFX_HARD_DURATION_S / 4 = 0.4 / 4 = 0.1s = 100ms.
        Position = max(0.0, 5.0 - 0.1) = 4.9s = 4900ms.
        """
        from cinecut.conform.sfx import apply_sfx_to_timeline
        from cinecut.manifest.schema import TrailerManifest, ClipEntry

        # Two-clip manifest: clip0 (0-5s) and clip1 (5-10s, hard_cut transition)
        manifest = TrailerManifest(
            source_file="fake.mkv",
            vibe="action",
            clips=[
                ClipEntry(
                    source_start_s=0.0, source_end_s=5.0,
                    beat_type="character_introduction", act="act1", transition="hard_cut",
                ),
                ClipEntry(
                    source_start_s=10.0, source_end_s=15.0,
                    beat_type="escalation_beat", act="act2", transition="hard_cut",
                ),
            ],
        )

        sfx_dir = tmp_path / "sfx"
        sfx_dir.mkdir()
        sfx_hard = sfx_dir / "sfx_hard.wav"
        sfx_boundary = sfx_dir / "sfx_boundary.wav"
        sfx_hard.touch()
        sfx_boundary.touch()

        with patch("cinecut.conform.sfx.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_proc(0)
            apply_sfx_to_timeline(manifest, sfx_hard, sfx_boundary, tmp_path, concat_duration_s=10.0)

        # Find the filtergraph argument
        assert mock_run.call_count >= 1
        cmd_args = mock_run.call_args_list[-1][0][0]
        cmd_str = " ".join(str(a) for a in cmd_args)

        # clip1 cut is at t=5.0s, lead=0.1s, so delay = 4900ms
        assert "4900" in cmd_str, (
            f"Expected adelay of 4900ms in SFX filtergraph, got: {cmd_str}"
        )
        # Must NOT use fractional seconds
        assert "4.9" not in cmd_str, "adelay must use integer ms, not seconds"


# ---------------------------------------------------------------------------
# audio_mix.py normalize=0 and three-stem fallback tests
# ---------------------------------------------------------------------------

class TestMixFourStemsNormalizeZero:
    def test_normalize_zero_in_filtergraph(self, tmp_path):
        """Four-stem mix must use normalize=0 in the amix filter — never normalize=1."""
        from cinecut.conform.audio_mix import mix_four_stems

        # Create fake input files so path.exists() returns True
        concat_path = tmp_path / "concat.mp4"
        sfx_mix = tmp_path / "sfx_mix.wav"
        music_path = tmp_path / "music.mp3"
        for p in [concat_path, sfx_mix, music_path]:
            p.touch()

        # Fake VoClip
        @dataclass
        class FakeVoClip:
            path: Path
            timeline_s: float
            act_zone: str

        vo_clip_path = tmp_path / "vo_0.aac"
        vo_clip_path.touch()
        vo_clips = [FakeVoClip(path=vo_clip_path, timeline_s=10.0, act_zone="act1")]

        with patch("cinecut.conform.audio_mix.subprocess.run") as mock_run:
            mock_run.side_effect = _loudnorm_side_effect
            mix_four_stems(
                concat_path=concat_path,
                sfx_mix=sfx_mix,
                vo_clips=vo_clips,
                music_bed_path=music_path,
                work_dir=tmp_path,
            )

        # Collect all cmd strings from subprocess.run calls
        all_cmds = []
        for c in mock_run.call_args_list:
            cmd_list = c[0][0]
            all_cmds.append(" ".join(str(a) for a in cmd_list))

        full_cmd_text = "\n".join(all_cmds)

        # normalize=0 must appear (in the amix filter)
        assert "normalize=0" in full_cmd_text, (
            f"normalize=0 not found in any FFmpeg call. Calls:\n{full_cmd_text}"
        )

        # normalize=1 must NOT appear in any command argument
        # (it may appear in docstrings/comments but never as an FFmpeg argument)
        for cmd_str in all_cmds:
            assert "normalize=1" not in cmd_str, (
                f"FORBIDDEN normalize=1 found in FFmpeg cmd: {cmd_str}"
            )

    def test_three_stem_fallback_when_no_music(self, tmp_path):
        """When music_bed_path=None, mix must use amix=inputs=3 (not 4) and no sidechaincompress."""
        from cinecut.conform.audio_mix import mix_four_stems

        concat_path = tmp_path / "concat.mp4"
        sfx_mix = tmp_path / "sfx_mix.wav"
        concat_path.touch()
        sfx_mix.touch()

        with patch("cinecut.conform.audio_mix.subprocess.run") as mock_run:
            mock_run.side_effect = _loudnorm_side_effect
            mix_four_stems(
                concat_path=concat_path,
                sfx_mix=sfx_mix,
                vo_clips=[],          # no VO clips
                music_bed_path=None,  # triggers three-stem fallback
                work_dir=tmp_path,
            )

        all_cmds = []
        for c in mock_run.call_args_list:
            cmd_list = c[0][0]
            all_cmds.append(" ".join(str(a) for a in cmd_list))

        full_cmd_text = "\n".join(all_cmds)

        # Three-stem mix (film + sfx + vo)
        assert "amix=inputs=3" in full_cmd_text, (
            f"Expected amix=inputs=3 in three-stem fallback. Got:\n{full_cmd_text}"
        )

        # Four-stem mix must NOT appear
        assert "amix=inputs=4" not in full_cmd_text, (
            f"amix=inputs=4 found when music_bed_path=None; expected three-stem only"
        )

        # sidechaincompress must NOT appear (no music to duck)
        assert "sidechaincompress" not in full_cmd_text, (
            f"sidechaincompress found in three-stem fallback — must not be present without music"
        )
