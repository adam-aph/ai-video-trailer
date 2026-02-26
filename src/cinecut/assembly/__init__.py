"""Assembly package: 3-act ordering, pacing enforcement, title card generation."""
import json
from pathlib import Path

from cinecut.assembly.ordering import sort_clips_by_act, enforce_pacing_curve
from cinecut.assembly.title_card import generate_title_card, get_video_dimensions
from cinecut.manifest.schema import TrailerManifest
from cinecut.manifest.vibes import VIBE_PROFILES


def assemble_manifest(
    manifest: TrailerManifest,
    source_file: Path,
    work_dir: Path,
) -> tuple[TrailerManifest, list[Path]]:
    """Apply 3-act ordering and pacing enforcement to a TrailerManifest.

    Steps:
    1. Sort clips into canonical ACT_ORDER (cold_open → act1 → beat_drop → act2 → breath → act3)
    2. Enforce pacing curve (trim act3 clips if average duration > profile.act3_avg_cut_s * 1.5)
    3. Generate title_card.mp4 and button.mp4 as pre-encoded FFmpeg lavfi segments
    4. Write ASSEMBLY_MANIFEST.json (reordered clips only, excludes generated segments)
    5. Return (reordered_manifest, [title_card_path, button_path])

    The returned list of extra_paths must be appended AFTER act3 clips in the concat list
    by the caller (cli.py). They are NOT ClipEntry objects.

    Args:
        manifest: Original TrailerManifest from run_narrative_stage().
        source_file: Original video file (for resolution detection).
        work_dir: Working directory for ASSEMBLY_MANIFEST.json and generated segments.

    Returns:
        (reordered_manifest, extra_paths) where extra_paths = [title_card_path, button_path]
    """
    profile = VIBE_PROFILES[manifest.vibe]

    # Step 1: Sort into canonical act order
    ordered_clips = sort_clips_by_act(manifest.clips)

    # Step 2: Enforce pacing curve on act3 clips
    paced_clips = enforce_pacing_curve(ordered_clips, profile)

    # Step 3: Generate title card (5s black) and button (2s black fade-out)
    width, height = get_video_dimensions(source_file)
    title_card_path = generate_title_card(
        title_text="",       # Plain black card per research recommendation
        width=width,
        height=height,
        duration_s=5.0,
        output_path=work_dir / "title_card.mp4",
    )
    button_path = generate_title_card(
        title_text="",
        width=width,
        height=height,
        duration_s=2.0,
        output_path=work_dir / "button.mp4",
    )

    # Step 4: Build and write reordered manifest (source clips only)
    reordered_manifest = manifest.model_copy(update={"clips": paced_clips})
    assembly_manifest_path = work_dir / "ASSEMBLY_MANIFEST.json"
    assembly_manifest_path.write_text(
        reordered_manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    return reordered_manifest, [title_card_path, button_path]
