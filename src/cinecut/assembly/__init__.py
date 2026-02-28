"""Assembly package: 3-act ordering, pacing enforcement, music bed, BPM snap, title card generation."""
import json
import logging
from pathlib import Path

from cinecut.assembly.ordering import sort_clips_by_act, enforce_pacing_curve
from cinecut.assembly.ordering import generate_silence_segment, insert_silence_at_zone_boundary
from cinecut.assembly.title_card import generate_title_card, get_video_dimensions, get_video_frame_rate
from cinecut.assembly.bpm import generate_beat_grid, snap_to_nearest_beat, BpmGrid as BpmGridDC
from cinecut.assembly.music import fetch_music_for_vibe, MusicBed as MusicBedDC
from cinecut.manifest.schema import TrailerManifest
from cinecut.manifest.schema import BpmGrid as BpmGridModel, MusicBed as MusicBedModel
from cinecut.manifest.vibes import VIBE_PROFILES

_logger = logging.getLogger("cinecut")


def assemble_manifest(
    manifest: TrailerManifest,
    source_file: Path,
    work_dir: Path,
) -> tuple[TrailerManifest, list[Path], dict | None]:
    """Apply 3-act ordering, pacing, music bed, BPM snap, silence insertion, and title card.

    Steps:
    1. Sort clips into canonical ACT_ORDER
    2. Enforce pacing curve (trim act3 clips)
    3. Fetch music for vibe (MUSC-01/02/03 — returns None on failure, pipeline continues)
    4. Detect BPM and generate beat grid (BPMG-01/03 — uses vibe default on failure)
    5. Snap clip start points to beat grid (BPMG-02)
    6. Detect ESCALATION->CLIMAX zone boundary and generate silence segment (EORD-04)
    7. Generate title card and button segments
    8. Record BpmGrid and MusicBed metadata in manifest
    9. Write ASSEMBLY_MANIFEST.json
    10. Return (reordered_manifest, extra_paths, silence_injection) where:
        - extra_paths = [title_card_path, button_path]   (appended after all clips by conform)
        - silence_injection = {"index": boundary_index, "paths": [silence_path]} or None
          (passed to conform_manifest as inject_after_clip=..., inject_paths=...)

    Args:
        manifest: Original TrailerManifest from run_narrative_stage().
        source_file: Original video file (for resolution detection).
        work_dir: Working directory for ASSEMBLY_MANIFEST.json and generated segments.

    Returns:
        (reordered_manifest, extra_paths, silence_injection) where extra_paths =
        [title_card_path, button_path] and silence_injection is {"index": N, "paths": [...]}
        or None if no ESCALATION->CLIMAX zone boundary exists.
    """
    profile = VIBE_PROFILES[manifest.vibe]

    # Step 1: Sort into canonical act order
    ordered_clips = sort_clips_by_act(manifest.clips)

    # Step 2: Enforce pacing curve on act3 clips
    paced_clips = enforce_pacing_curve(ordered_clips, profile)

    # Step 3: Fetch music for vibe (MUSC-01, MUSC-02, MUSC-03)
    music_bed_dc: MusicBedDC | None = fetch_music_for_vibe(manifest.vibe)

    # Step 4: Detect BPM and generate beat grid (BPMG-01, BPMG-03)
    bpm_grid_dc: BpmGridDC | None = None
    if music_bed_dc is not None:
        # Estimate trailer duration from total clip durations
        trailer_duration_s = sum(c.source_end_s - c.source_start_s for c in paced_clips)
        bpm_grid_dc = generate_beat_grid(music_bed_dc.local_path, manifest.vibe, trailer_duration_s)
        music_bed_dc.bpm = bpm_grid_dc.bpm   # Store resolved BPM in music bed

    # Step 5: Snap clip start points to beat grid (BPMG-02)
    if bpm_grid_dc is not None and bpm_grid_dc.beat_times_s:
        snapped = []
        for clip in paced_clips:
            snapped_start = snap_to_nearest_beat(
                clip.source_start_s, bpm_grid_dc.beat_times_s, bpm_grid_dc.bpm
            )
            # Recalculate end to preserve clip duration after snap
            original_duration = clip.source_end_s - clip.source_start_s
            new_end = max(snapped_start + original_duration, snapped_start + 0.5)
            snapped.append(clip.model_copy(update={
                "source_start_s": snapped_start,
                "source_end_s": new_end,
            }))
        paced_clips = snapped

    # Step 6: Generate video dimensions; detect zone boundary and generate silence (EORD-04)
    width, height = get_video_dimensions(source_file)
    frame_rate = get_video_frame_rate(source_file)
    silence_path, boundary_index = insert_silence_at_zone_boundary(
        paced_clips, work_dir, width, height, frame_rate
    )
    # Build silence_injection dict for conform_manifest (None if no zone boundary detected)
    silence_injection: dict | None = None
    if silence_path is not None:
        silence_injection = {"index": boundary_index, "paths": [silence_path]}

    # Step 7: Generate title card and button
    title_card_path = generate_title_card(
        title_text="",
        width=width,
        height=height,
        duration_s=5.0,
        output_path=work_dir / "title_card.mp4",
        frame_rate=frame_rate,
    )
    button_path = generate_title_card(
        title_text="",
        width=width,
        height=height,
        duration_s=2.0,
        output_path=work_dir / "button.mp4",
        frame_rate=frame_rate,
    )

    # Step 8: Build manifest metadata models for BpmGrid and MusicBed
    bpm_grid_model = None
    if bpm_grid_dc is not None:
        bpm_grid_model = BpmGridModel(
            bpm=bpm_grid_dc.bpm,
            beat_count=bpm_grid_dc.beat_count,
            source=bpm_grid_dc.source,
        )

    music_bed_model = None
    if music_bed_dc is not None:
        music_bed_model = MusicBedModel(
            track_id=music_bed_dc.track_id,
            track_name=music_bed_dc.track_name,
            artist_name=music_bed_dc.artist_name,
            license_ccurl=music_bed_dc.license_ccurl,
            local_path=music_bed_dc.local_path,
            bpm=music_bed_dc.bpm,
        )

    # Step 9: Build reordered manifest with Phase 9 metadata
    reordered_manifest = manifest.model_copy(update={
        "clips": paced_clips,
        "bpm_grid": bpm_grid_model,
        "music_bed": music_bed_model,
    })
    assembly_manifest_path = work_dir / "ASSEMBLY_MANIFEST.json"
    assembly_manifest_path.write_text(
        reordered_manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    # Step 10: extra_paths = title_card + button (appended AFTER all clips by conform_manifest)
    # Silence is NOT in extra_paths — it is passed separately via silence_injection
    # so conform_manifest can insert it at the correct position within the clip list
    extra_paths: list[Path] = [title_card_path, button_path]

    return reordered_manifest, extra_paths, silence_injection
