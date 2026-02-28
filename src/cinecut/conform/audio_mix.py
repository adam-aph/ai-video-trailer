"""Four-stem audio mix for CineCut trailer generation.

Implements AMIX-01, AMIX-02, AMIX-03:
- AMIX-01: Sidechain compression for music bed ducking during protagonist VO
- AMIX-02: Independent per-stem loudnorm at -16 LUFS before final mix
- AMIX-03: All stems resampled to 48000Hz stereo; amix normalize=0 mandatory

Public API:
- mix_four_stems(): Four-stem (or three-stem fallback) audio mix with sidechaincompress ducking
- DUCK_THRESHOLD, DUCK_RATIO, DUCK_ATTACK_MS, DUCK_RELEASE_MS: Tuning constants
- STEM_WEIGHTS_FOUR, STEM_WEIGHTS_THREE: amix weight strings
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from cinecut.errors import ConformError

if TYPE_CHECKING:
    from cinecut.conform.vo_extract import VoClip

# ---------------------------------------------------------------------------
# Sidechain ducking parameters — require empirical tuning per STATE.md
# ---------------------------------------------------------------------------
DUCK_THRESHOLD: float = 0.025   # ~-32dB — threshold at which music starts ducking
DUCK_RATIO: float = 6.0          # compression ratio applied above threshold
DUCK_ATTACK_MS: int = 100        # attack time in ms (how fast duck engages)
DUCK_RELEASE_MS: int = 600       # release time in ms (how fast music recovers)

# ---------------------------------------------------------------------------
# amix stem weights (normalize=0 — mandatory to preserve ratios)
# ---------------------------------------------------------------------------
STEM_WEIGHTS_FOUR: str = "1.0 0.7 0.8 1.0"   # film, music, sfx, vo
STEM_WEIGHTS_THREE: str = "1.0 0.8 1.0"        # film, sfx, vo (no music)

# Loudnorm target: -16 LUFS (broadcast standard for trailers)
_LOUDNORM_I: int = -16
_LOUDNORM_LRA: int = 7
_LOUDNORM_TP: int = -2


def _create_stems_dir(work_dir: Path) -> Path:
    """Create and return work_dir/stems/ directory."""
    stems_dir = work_dir / "stems"
    stems_dir.mkdir(parents=True, exist_ok=True)
    return stems_dir


def _loudnorm_stem(input_path: Path, output_path: Path) -> Path:
    """Normalize a single audio stem to -16 LUFS using two-pass loudnorm.

    Pass 1 measures loudness stats; Pass 2 applies linear normalization
    with the measured values.

    Args:
        input_path:  Source audio file (any format FFmpeg supports).
        output_path: Destination AAC file at 48000Hz stereo.

    Returns:
        output_path on success.

    Raises:
        ConformError: If either FFmpeg pass fails or JSON stats cannot be parsed.
    """
    # Pass 1: measure loudness stats (output to /dev/null)
    pass1_cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-af", f"loudnorm=I={_LOUDNORM_I}:LRA={_LOUDNORM_LRA}:tp={_LOUDNORM_TP}:print_format=json",
        "-f", "null",
        "-",
    ]
    pass1_result = subprocess.run(pass1_cmd, capture_output=True, text=True, check=False)

    # Parse JSON stats from stderr
    json_match = re.search(r"\{[^}]+\}", pass1_result.stderr, re.DOTALL)
    if not json_match:
        raise ConformError(
            output_path,
            f"loudnorm pass 1 did not produce JSON stats (rc={pass1_result.returncode}): "
            f"{pass1_result.stderr[-300:]}",
        )

    try:
        stats = json.loads(json_match.group())
    except json.JSONDecodeError as exc:
        raise ConformError(
            output_path,
            f"loudnorm pass 1 JSON parse error: {exc}",
        ) from exc

    input_i = stats.get("input_i", "0")
    input_lra = stats.get("input_lra", "0")
    input_tp = stats.get("input_tp", "0")
    input_thresh = stats.get("input_thresh", "0")
    target_offset = stats.get("target_offset", "0")

    # Pass 2: apply linear normalization with measured stats
    loudnorm_filter = (
        f"loudnorm=I={_LOUDNORM_I}:LRA={_LOUDNORM_LRA}:tp={_LOUDNORM_TP}"
        f":measured_I={input_i}"
        f":measured_LRA={input_lra}"
        f":measured_tp={input_tp}"
        f":measured_thresh={input_thresh}"
        f":offset={target_offset}"
        f":linear=true"
    )
    pass2_cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-af", loudnorm_filter,
        "-c:a", "aac",
        "-ar", "48000",
        "-ac", "2",
        str(output_path),
    ]
    pass2_result = subprocess.run(pass2_cmd, capture_output=True, text=True, check=False)
    if pass2_result.returncode != 0:
        raise ConformError(output_path, pass2_result.stderr[-500:])

    return output_path


def mix_four_stems(
    concat_path: Path,
    sfx_mix: Path,
    vo_clips: list[VoClip],
    music_bed_path: Path | None,
    work_dir: Path,
) -> Path:
    """Mix four audio stems into a final trailer MP4 with sidechain music ducking.

    Stem pipeline:
      1. Extract film audio from concat MP4 (Pass 2 output)
      2. Loudnorm each stem independently to -16 LUFS (AMIX-02)
      3. Build FFmpeg filtergraph:
         - Four-stem (film + music + sfx + vo): sidechaincompress ducts music
           during VO, then amix=inputs=4:normalize=0
         - Three-stem fallback (film + sfx + vo): amix=inputs=3:normalize=0
           (activated when music_bed_path is None or file does not exist)
      4. Produce trailer_final.mp4 with video from concat_path

    amix normalize=0 is MANDATORY throughout — normalize=1 destroys ducking ratios.

    Args:
        concat_path:     Pass 2 concat MP4 (source of video track + film audio).
        sfx_mix:         SFX overlay WAV from apply_sfx_to_timeline().
        vo_clips:        List of VoClip from extract_vo_clips(); may be empty.
        music_bed_path:  Path to music bed audio (e.g. .mp3 from Jamendo cache);
                         None or non-existent path triggers three-stem fallback.
        work_dir:        Pipeline working directory; stems/ and trailer_final.mp4
                         are written here.

    Returns:
        Path to work_dir/trailer_final.mp4.

    Raises:
        ConformError: If any FFmpeg operation fails.
    """
    stems_dir = _create_stems_dir(work_dir)

    # ------------------------------------------------------------------
    # Step 1: Extract raw film audio from concat MP4
    # ------------------------------------------------------------------
    film_audio_raw = stems_dir / "film_audio_raw.aac"
    extract_cmd = [
        "ffmpeg", "-y",
        "-i", str(concat_path),
        "-vn",
        "-c:a", "aac",
        "-ar", "48000",
        "-ac", "2",
        str(film_audio_raw),
    ]
    result = subprocess.run(extract_cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConformError(film_audio_raw, result.stderr[-500:])

    # ------------------------------------------------------------------
    # Step 2: Loudnorm each stem independently (AMIX-02)
    # ------------------------------------------------------------------

    # Film audio
    film_audio_norm = stems_dir / "film_audio.aac"
    _loudnorm_stem(film_audio_raw, film_audio_norm)

    # SFX mix (WAV -> AAC normalized)
    sfx_norm = stems_dir / "sfx_norm.aac"
    _loudnorm_stem(sfx_mix, sfx_norm)

    # Music bed (optional — three-stem fallback if absent)
    use_music = music_bed_path is not None and music_bed_path.exists()
    music_norm: Path | None = None
    if use_music:
        music_norm = stems_dir / "music_norm.aac"
        _loudnorm_stem(music_bed_path, music_norm)  # type: ignore[arg-type]

    # VO stem: combine vo_clips at their timeline positions, or silence placeholder
    vo_mix = stems_dir / "vo_mix.aac"
    if vo_clips:
        _build_vo_mix(vo_clips, vo_mix)
    else:
        # No VO clips — create near-silence placeholder to keep filtergraph consistent
        silence_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "aevalsrc=0:s=48000:d=0.1:c=stereo",
            "-c:a", "aac",
            "-ar", "48000",
            "-ac", "2",
            str(vo_mix),
        ]
        result = subprocess.run(silence_cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ConformError(vo_mix, result.stderr[-500:])

    # ------------------------------------------------------------------
    # Step 3: Strip video audio and build final mix
    # ------------------------------------------------------------------
    trailer_noaudio = work_dir / "trailer_noaudio.mp4"
    strip_cmd = [
        "ffmpeg", "-y",
        "-i", str(concat_path),
        "-an",
        "-c:v", "copy",
        str(trailer_noaudio),
    ]
    result = subprocess.run(strip_cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConformError(trailer_noaudio, result.stderr[-500:])

    trailer_final = work_dir / "trailer_final.mp4"

    if use_music and music_norm is not None:
        # Four-stem mix: film + music (ducked) + sfx + vo
        filter_complex = (
            "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[film];"
            "[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[music];"
            "[3:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[sfx];"
            "[4:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[vo];"
            "[vo]asplit=2[vo_out][vo_sc];"
            f"[music][vo_sc]sidechaincompress=threshold={DUCK_THRESHOLD}:"
            f"ratio={DUCK_RATIO}:attack={DUCK_ATTACK_MS}:release={DUCK_RELEASE_MS}:"
            f"makeup=1[music_ducked];"
            f"[film][music_ducked][sfx][vo_out]amix=inputs=4:normalize=0:"
            f"weights='{STEM_WEIGHTS_FOUR}'[mixed]"
        )
        mix_cmd = [
            "ffmpeg", "-y",
            "-i", str(trailer_noaudio),    # input 0: video (no audio)
            "-i", str(film_audio_norm),    # input 1: film audio
            "-i", str(music_norm),         # input 2: music bed
            "-i", str(sfx_norm),           # input 3: SFX
            "-i", str(vo_mix),             # input 4: VO
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[mixed]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-ar", "48000",
            "-ac", "2",
            str(trailer_final),
        ]
    else:
        # Three-stem fallback: film + sfx + vo (no music / music unavailable)
        filter_complex = (
            "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[film];"
            "[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[sfx];"
            "[3:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[vo];"
            f"[film][sfx][vo]amix=inputs=3:normalize=0:"
            f"weights='{STEM_WEIGHTS_THREE}'[mixed]"
        )
        mix_cmd = [
            "ffmpeg", "-y",
            "-i", str(trailer_noaudio),    # input 0: video (no audio)
            "-i", str(film_audio_norm),    # input 1: film audio
            "-i", str(sfx_norm),           # input 2: SFX
            "-i", str(vo_mix),             # input 3: VO
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[mixed]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-ar", "48000",
            "-ac", "2",
            str(trailer_final),
        ]

    result = subprocess.run(mix_cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConformError(trailer_final, result.stderr[-500:])

    return trailer_final


def _build_vo_mix(vo_clips: list[VoClip], output_path: Path) -> None:
    """Combine VO clips at their timeline positions using adelay.

    Each VoClip is positioned at timeline_s using adelay (milliseconds).
    All clips are then mixed with amix=normalize=0.

    Args:
        vo_clips:    Non-empty list of VoClip instances.
        output_path: Destination AAC file path.

    Raises:
        ConformError: If FFmpeg fails.
    """
    cmd: list[str] = ["ffmpeg", "-y"]

    for vc in vo_clips:
        cmd += ["-i", str(vc.path)]

    filter_parts: list[str] = []
    labels: list[str] = []

    for idx, vc in enumerate(vo_clips):
        delay_ms = int(vc.timeline_s * 1000)
        filter_parts.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms}[vo{idx}]")
        labels.append(f"[vo{idx}]")

    n = len(vo_clips)
    mix_inputs = "".join(labels)
    if n == 1:
        # Single clip: use anull instead of amix (amix with 1 input still works but
        # adelay output can be used directly via aformat)
        filter_parts.append(f"{mix_inputs}aformat=sample_fmts=fltp:channel_layouts=stereo[vo_combined]")
    else:
        filter_parts.append(
            f"{mix_inputs}amix=inputs={n}:normalize=0[vo_combined]"
        )

    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vo_combined]",
        "-c:a", "aac",
        "-ar", "48000",
        "-ac", "2",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConformError(output_path, result.stderr[-500:])
