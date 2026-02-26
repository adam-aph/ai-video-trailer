"""CineCut CLI entry point.

Wires all Phase 1 ingestion stages (proxy creation, subtitle parsing, and
keyframe extraction) behind a single ``cinecut`` command with Rich progress
bars and human-readable error panels.

Phase 2 adds --manifest and --review flags for running the FFmpeg conform
pipeline against a hand-crafted or generated TRAILER_MANIFEST.json.
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
from cinecut.manifest.loader import load_manifest
from cinecut.manifest.vibes import VIBE_PROFILES
from cinecut.conform.pipeline import conform_manifest

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

    try:
        trailer_manifest = None

        if manifest is not None:
            # --manifest provided: skip ingestion, load manifest, jump to conform
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
        else:
            # --- Stage 1: Proxy creation (PIPE-02) ---
            # better-ffmpeg-progress handles its own Rich progress bar during the FFmpeg call.
            console.print("[bold]Stage 1/3:[/bold] Creating 420p analysis proxy...")
            proxy_path = create_proxy(video, work_dir)
            console.print(f"[green]Proxy ready: [dim]{proxy_path.name}[/dim]\n")

            # --- Stage 2: Subtitle parsing (NARR-01) ---
            console.print("[bold]Stage 2/3:[/bold] Parsing subtitles...")
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
            console.print(f"[green]Parsed {len(dialogue_events)} dialogue events\n")

            # --- Stage 3: Keyframe extraction (PIPE-03) ---
            console.print("[bold]Stage 3/3:[/bold] Extracting keyframes...")
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
            console.print(f"[green]Extracted {len(keyframe_records)} keyframes\n")

            # --- Summary ---
            console.print(Panel(
                f"[bold green]Ingestion complete[/bold green]\n\n"
                f"  Proxy:      [dim]{proxy_path.name}[/dim]\n"
                f"  Subtitles:  {len(dialogue_events)} events\n"
                f"  Keyframes:  {len(keyframe_records)} frames\n"
                f"  Work dir:   [dim]{work_dir}[/dim]",
                title="[green]Phase 1 Complete[/green]",
                border_style="green",
            ))

        # --- Stage 4: Conform (EDIT-05 / CLI-04) ---
        if trailer_manifest is not None:
            # --review pause (EDIT-04): inspect manifest before conform
            if review:
                console.print(f"\n[bold yellow]Review mode:[/bold yellow] Manifest loaded from:\n  {manifest}")
                console.print("[dim]Inspect clip decisions in the manifest, then confirm to continue.[/dim]\n")
                typer.confirm("Proceed with FFmpeg conform?", abort=True)

            console.print("[bold]Stage 4/4:[/bold] Running FFmpeg conform...")
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                conform_task = progress.add_task(
                    f"Processing {len(trailer_manifest.clips)} clips...", total=None
                )
                output_path = conform_manifest(trailer_manifest, video, work_dir)
                progress.update(conform_task, description="Conform complete")

            console.print(Panel(
                f"[bold green]Conform complete[/bold green]\n\n"
                f"  Output: [dim]{output_path}[/dim]\n"
                f"  Clips:  {len(trailer_manifest.clips)}\n"
                f"  Vibe:   {trailer_manifest.vibe}",
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
