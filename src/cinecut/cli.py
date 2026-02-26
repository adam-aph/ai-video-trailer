"""CineCut CLI entry point.

Wires all Phase 1 ingestion stages (proxy creation, subtitle parsing, and
keyframe extraction) behind a single ``cinecut`` command with Rich progress
bars and human-readable error panels.

Phase 2 adds --manifest and --review flags for running the FFmpeg conform
pipeline against a hand-crafted or generated TRAILER_MANIFEST.json.

Phase 3 adds --model and --mmproj flags for LLaVA inference stage; runs
automatically after keyframe extraction when no --manifest is provided.

Phase 5 adds checkpoint-guarded resume (PIPE-04), 3-act assembly stage
(EDIT-02, EDIT-03), and updated 7-stage pipeline numbering.
"""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from cinecut.errors import CineCutError, ManifestError, ConformError
from cinecut.ingestion.proxy import create_proxy
from cinecut.ingestion.subtitles import parse_subtitles
from cinecut.ingestion.keyframes import collect_keyframe_timestamps, extract_all_keyframes
from cinecut.inference.engine import run_inference_stage
from cinecut.manifest.loader import load_manifest
from cinecut.manifest.vibes import VIBE_PROFILES
from cinecut.narrative.generator import run_narrative_stage
from cinecut.conform.pipeline import conform_manifest
from cinecut.checkpoint import PipelineCheckpoint, load_checkpoint, save_checkpoint
from cinecut.assembly import assemble_manifest

# Default model paths for LLaVA inference
_DEFAULT_MODEL_PATH = "/home/adamh/models/ggml-model-q4_k.gguf"
_DEFAULT_MMPROJ_PATH = "/home/adamh/models/mmproj-model-f16.gguf"

# Total pipeline stages (proxy, subtitles, keyframes, inference, narrative, assembly, conform)
TOTAL_STAGES = 7

app = typer.Typer(
    name="cinecut",
    help="CineCut AI — Generate a narratively coherent trailer from any feature film.",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)

# Valid input formats
_VALID_VIDEO_EXTS = {".mkv", ".avi", ".mp4"}
_VALID_SUBTITLE_EXTS = {".srt", ".ass"}


def _setup_work_dir(source: Path) -> Path:
    """Create <source_stem>_cinecut_work/ alongside the source file. Idempotent."""
    work_dir = source.parent / f"{source.stem}_cinecut_work"
    work_dir.mkdir(exist_ok=True)
    (work_dir / "keyframes").mkdir(exist_ok=True)
    return work_dir


@app.command()
def main(
    video: Annotated[
        Path,
        typer.Argument(
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
            help="Input video file (MKV, AVI, or MP4).",
        ),
    ],
    subtitle: Annotated[
        Path,
        typer.Option(
            "--subtitle", "-s",
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
            help="Subtitle file (SRT or ASS).",
        ),
    ],
    vibe: Annotated[
        str,
        typer.Option("--vibe", "-v", help="Trailer vibe profile name (e.g. action, drama, horror)."),
    ],
    review: Annotated[
        bool,
        typer.Option("--review", help="Pause after manifest generation for inspection before conform."),
    ] = False,
    manifest: Annotated[
        Optional[Path],
        typer.Option(
            "--manifest", "-m",
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
            help="Path to TRAILER_MANIFEST.json. Skips ingestion stages and runs conform directly.",
        ),
    ] = None,
    model: Annotated[
        Path,
        typer.Option(
            "--model",
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
            help=f"Path to LLaVA GGUF model file (default: {_DEFAULT_MODEL_PATH}).",
        ),
    ] = Path(_DEFAULT_MODEL_PATH),
    mmproj: Annotated[
        Path,
        typer.Option(
            "--mmproj",
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
            help=f"Path to mmproj GGUF file (default: {_DEFAULT_MMPROJ_PATH}).",
        ),
    ] = Path(_DEFAULT_MMPROJ_PATH),
) -> None:
    """Ingest a film and produce analysis-ready artifacts for trailer generation."""
    # --- Input validation (PIPE-01) ---
    if video.suffix.lower() not in _VALID_VIDEO_EXTS:
        err_console.print(Panel(
            f"Unsupported video format: [bold]{video.suffix}[/bold]\n"
            f"Supported formats: {', '.join(sorted(_VALID_VIDEO_EXTS))}",
            title="[red]Input Error[/red]",
            border_style="red",
        ))
        raise typer.Exit(1)

    if not video.exists():
        err_console.print(Panel(
            f"File not found: [bold]{video}[/bold]\n"
            f"Check that the path is correct and the file is accessible.",
            title="[red]Input Error[/red]",
            border_style="red",
        ))
        raise typer.Exit(1)

    if subtitle.suffix.lower() not in _VALID_SUBTITLE_EXTS:
        err_console.print(Panel(
            f"Unsupported subtitle format: [bold]{subtitle.suffix}[/bold]\n"
            f"Supported formats: {', '.join(sorted(_VALID_SUBTITLE_EXTS))}",
            title="[red]Input Error[/red]",
            border_style="red",
        ))
        raise typer.Exit(1)

    if not subtitle.exists():
        err_console.print(Panel(
            f"File not found: [bold]{subtitle}[/bold]\n"
            f"Check that the path is correct and the file is accessible.",
            title="[red]Input Error[/red]",
            border_style="red",
        ))
        raise typer.Exit(1)

    # --- Vibe validation ---
    vibe_normalized = vibe.lower().replace(" ", "-")
    if vibe_normalized not in VIBE_PROFILES:
        err_console.print(Panel(
            f"Unknown vibe: [bold]{vibe}[/bold]\n"
            f"Valid vibes: {', '.join(sorted(VIBE_PROFILES))}",
            title="[red]Input Error[/red]",
            border_style="red",
        ))
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]CineCut AI[/bold cyan] — [dim]{video.name}[/dim]  vibe=[bold]{vibe}[/bold]\n")

    # --- Work directory setup ---
    work_dir = _setup_work_dir(video)
    console.print(f"Work directory: [dim]{work_dir}[/dim]\n")

    # --- Checkpoint init (PIPE-04) ---
    ckpt = load_checkpoint(work_dir)
    if ckpt is not None and ckpt.source_file != str(video):
        console.print("[yellow]Warning:[/] Stale checkpoint (different source file). Starting fresh.")
        ckpt = None
    if ckpt is None:
        ckpt = PipelineCheckpoint(source_file=str(video), vibe=vibe_normalized)

    try:
        trailer_manifest = None

        if manifest is not None:
            # --manifest provided: skip ingestion, load manifest, run assembly then conform
            if not manifest.exists():
                err_console.print(Panel(
                    f"Manifest file not found: {manifest}",
                    title="[red]Input Error[/red]",
                    border_style="red",
                ))
                raise typer.Exit(1)

            # Load and validate manifest (raises ManifestError on failure)
            trailer_manifest = load_manifest(manifest)

            # Validate manifest vibe matches CLI vibe
            if trailer_manifest.vibe != vibe_normalized:
                err_console.print(Panel(
                    f"Manifest vibe '[bold]{trailer_manifest.vibe}[/bold]' does not match --vibe '[bold]{vibe}[/bold]'.\n"
                    f"Either update the manifest or pass --vibe {trailer_manifest.vibe}",
                    title="[red]Input Error[/red]",
                    border_style="red",
                ))
                raise typer.Exit(1)

            # Assembly for --manifest path (no checkpoint)
            reordered_manifest, extra_paths = assemble_manifest(trailer_manifest, video, work_dir)
        else:
            # --- Stage 1/7: Proxy creation (PIPE-02) ---
            if not ckpt.is_stage_complete("proxy"):
                console.print(f"[bold]Stage 1/{TOTAL_STAGES}:[/bold] Creating 420p analysis proxy...")
                # better-ffmpeg-progress handles its own Rich progress bar during the FFmpeg call.
                proxy_path = create_proxy(video, work_dir)
                ckpt.proxy_path = str(proxy_path)
                ckpt.mark_stage_complete("proxy")
                save_checkpoint(ckpt, work_dir)
                console.print(f"[green]Proxy ready: [dim]{proxy_path.name}[/dim]\n")
            else:
                proxy_path = Path(ckpt.proxy_path)
                console.print(f"[yellow]Resuming:[/] Stage 1 already complete (proxy: {proxy_path.name})\n")

            # --- Stage 2/7: Subtitle parsing (NARR-01) ---
            if not ckpt.is_stage_complete("subtitles"):
                console.print(f"[bold]Stage 2/{TOTAL_STAGES}:[/bold] Parsing subtitles...")
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    TimeElapsedColumn(),
                    console=console,
                    transient=True,
                ) as progress:
                    task = progress.add_task("Parsing subtitle events...", total=None)
                    dialogue_events = parse_subtitles(subtitle)
                    progress.update(task, description=f"Parsed {len(dialogue_events)} dialogue events")
                ckpt.dialogue_event_count = len(dialogue_events)
                ckpt.mark_stage_complete("subtitles")
                save_checkpoint(ckpt, work_dir)
                console.print(f"[green]Parsed {len(dialogue_events)} dialogue events\n")
            else:
                console.print(f"[yellow]Resuming:[/] Stage 2 already complete — re-parsing subtitles for downstream use\n")
                dialogue_events = parse_subtitles(subtitle)

            # --- Stage 3/7: Keyframe extraction (PIPE-03) ---
            if not ckpt.is_stage_complete("keyframes"):
                console.print(f"[bold]Stage 3/{TOTAL_STAGES}:[/bold] Extracting keyframes...")
                subtitle_midpoints = [e.midpoint_s for e in dialogue_events]

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("{task.completed}/{task.total}"),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    ts_task = progress.add_task("Collecting timestamps (scene detection)...", total=None)
                    timestamps = collect_keyframe_timestamps(proxy_path, subtitle_midpoints)
                    progress.update(ts_task, description=f"Collected {len(timestamps)} keyframe timestamps", completed=1, total=1)

                    kf_task = progress.add_task("Extracting frames...", total=len(timestamps))
                    keyframe_records = extract_all_keyframes(
                        proxy_path,
                        timestamps,
                        work_dir / "keyframes",
                        subtitle_midpoints=set(subtitle_midpoints),
                        progress_callback=lambda: progress.advance(kf_task),
                    )
                ckpt.keyframe_count = len(keyframe_records)
                ckpt.mark_stage_complete("keyframes")
                save_checkpoint(ckpt, work_dir)
                console.print(f"[green]Extracted {len(keyframe_records)} keyframes\n")
            else:
                # Keyframe files are already in work_dir/keyframes/ — re-run extraction (idempotent)
                console.print(f"[yellow]Resuming:[/] Stage 3 already complete — re-extracting keyframes for inference\n")
                subtitle_midpoints = [e.midpoint_s for e in dialogue_events]
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("{task.completed}/{task.total}"),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    ts_task = progress.add_task("Collecting timestamps (scene detection)...", total=None)
                    timestamps = collect_keyframe_timestamps(proxy_path, subtitle_midpoints)
                    progress.update(ts_task, description=f"Collected {len(timestamps)} keyframe timestamps", completed=1, total=1)

                    kf_task = progress.add_task("Extracting frames...", total=len(timestamps))
                    keyframe_records = extract_all_keyframes(
                        proxy_path,
                        timestamps,
                        work_dir / "keyframes",
                        subtitle_midpoints=set(subtitle_midpoints),
                        progress_callback=lambda: progress.advance(kf_task),
                    )

            # --- Stage 4/7: LLaVA Inference (INFR-02) ---
            # TODO: inference resume requires persisting SceneDescription results; deferred to v2
            console.print(f"[bold]Stage 4/{TOTAL_STAGES}:[/bold] Running LLaVA inference on keyframes...")
            inference_results = []

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                infer_task = progress.add_task(
                    "Describing frames...", total=len(keyframe_records)
                )

                def _progress_callback(current: int, total: int) -> None:
                    progress.update(infer_task, completed=current)

                inference_results = run_inference_stage(
                    keyframe_records,
                    model,
                    mmproj,
                    progress_callback=_progress_callback,
                )

            skipped = sum(1 for _, desc in inference_results if desc is None)
            ckpt.inference_complete = True
            save_checkpoint(ckpt, work_dir)
            console.print(
                f"[green]Inference complete:[/] {len(inference_results)} frames processed, "
                f"{skipped} skipped\n"
            )

            # --- Stage 5/7: Narrative beat extraction and manifest generation (NARR-02, NARR-03, EDIT-01) ---
            if not ckpt.is_stage_complete("narrative"):
                console.print(f"[bold]Stage 5/{TOTAL_STAGES}:[/bold] Extracting narrative beats and generating manifest...")

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("{task.completed}/{task.total}"),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    narr_task = progress.add_task(
                        "Scoring and classifying scenes...", total=len(inference_results)
                    )

                    def _narr_callback(current: int, total: int) -> None:
                        progress.update(narr_task, completed=current)

                    manifest_path = run_narrative_stage(
                        inference_results,
                        dialogue_events,
                        vibe_normalized,
                        video,      # original source, NOT proxy
                        work_dir,
                        progress_callback=_narr_callback,
                    )

                ckpt.manifest_path = str(manifest_path)
                ckpt.mark_stage_complete("narrative")
                save_checkpoint(ckpt, work_dir)
                console.print(f"[green]Manifest written: [dim]{manifest_path.name}[/dim]\n")
            else:
                manifest_path = Path(ckpt.manifest_path)
                console.print(f"[yellow]Resuming:[/] Stage 5 already complete (manifest: {manifest_path.name})\n")

            trailer_manifest = load_manifest(manifest_path)

            # --- Stage 6/7: 3-act assembly and pacing enforcement (EDIT-02, EDIT-03) ---
            if not ckpt.is_stage_complete("assembly"):
                console.print(f"[bold]Stage 6/{TOTAL_STAGES}:[/bold] Assembling 3-act structure...")
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    TimeElapsedColumn(),
                    console=console,
                    transient=True,
                ) as progress:
                    asm_task = progress.add_task("Ordering clips and generating title card...", total=None)
                    reordered_manifest, extra_paths = assemble_manifest(trailer_manifest, video, work_dir)
                    progress.update(asm_task, description="Assembly complete")
                ckpt.assembly_manifest_path = str(work_dir / "ASSEMBLY_MANIFEST.json")
                ckpt.mark_stage_complete("assembly")
                save_checkpoint(ckpt, work_dir)
                console.print(f"[green]Assembly complete: {len(reordered_manifest.clips)} clips ordered\n")
            else:
                from cinecut.manifest.loader import load_manifest as _lm
                reordered_manifest = _lm(Path(ckpt.assembly_manifest_path))
                _, extra_paths = assemble_manifest(trailer_manifest, video, work_dir)
                console.print(f"[yellow]Resuming:[/] Stage 6 already complete\n")

            # --- Summary ---
            console.print(Panel(
                f"[bold green]Pipeline complete[/bold green]\n\n"
                f"  Proxy:      [dim]{proxy_path.name}[/dim]\n"
                f"  Subtitles:  {len(dialogue_events)} events\n"
                f"  Keyframes:  {len(keyframe_records)} frames\n"
                f"  Described:  {len(inference_results) - skipped} frames ({skipped} skipped)\n"
                f"  Manifest:   [dim]{manifest_path.name}[/dim]\n"
                f"  Assembly:   {len(reordered_manifest.clips)} clips ordered\n"
                f"  Work dir:   [dim]{work_dir}[/dim]",
                title="[green]Phase 5 Complete[/green]",
                border_style="green",
            ))

        # --- Stage 7/7: FFmpeg conform (EDIT-05 / CLI-04) ---
        if trailer_manifest is not None:
            # --review pause (EDIT-04): inspect manifest before conform
            if review:
                console.print(f"\n[bold yellow]Review mode:[/bold yellow] Manifest loaded from:\n  {manifest}")
                console.print("[dim]Inspect clip decisions in the manifest, then confirm to continue.[/dim]\n")
                typer.confirm("Proceed with FFmpeg conform?", abort=True)

            console.print(f"[bold]Stage 7/{TOTAL_STAGES}:[/bold] Running FFmpeg conform...")
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                conform_task = progress.add_task(
                    f"Processing {len(reordered_manifest.clips)} clips...", total=None
                )
                output_path = conform_manifest(reordered_manifest, video, work_dir, extra_clip_paths=extra_paths)
                progress.update(conform_task, description="Conform complete")

            console.print(Panel(
                f"[bold green]Conform complete[/bold green]\n\n"
                f"  Output: [dim]{output_path}[/dim]\n"
                f"  Clips:  {len(reordered_manifest.clips)}\n"
                f"  Vibe:   {reordered_manifest.vibe}",
                title="[green]Trailer Ready[/green]",
                border_style="green",
            ))

    except CineCutError as e:
        # Translate all typed pipeline errors to a Rich panel — never show tracebacks (CLI-03)
        # ManifestError and ConformError both inherit from CineCutError, so caught here.
        err_console.print(Panel(
            str(e),
            title="[red]Pipeline Error[/red]",
            border_style="red",
        ))
        raise typer.Exit(1)
