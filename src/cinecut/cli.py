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

import json
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
from cinecut.inference.cache import load_cache, save_cache
from cinecut.inference.text_engine import TextEngine, get_models_dir, MISTRAL_GGUF_NAME
from cinecut.inference.structural import run_structural_analysis, compute_heuristic_anchors
from cinecut.manifest.schema import StructuralAnchors
from cinecut.narrative.signals import get_film_duration_s
from cinecut.manifest.loader import load_manifest
from cinecut.manifest.vibes import VIBE_PROFILES
from cinecut.narrative.generator import run_narrative_stage
from cinecut.conform.pipeline import conform_manifest
from cinecut.checkpoint import PipelineCheckpoint, load_checkpoint, save_checkpoint
from cinecut.assembly import assemble_manifest

# Total pipeline stages (proxy, subtitles, keyframes, inference, structural, narrative, assembly, conform)
TOTAL_STAGES = 8

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
        Optional[Path],
        typer.Option(
            "--model",
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
            help="Path to LLaVA GGUF model (default: CINECUT_MODELS_DIR/ggml-model-q4_k.gguf).",
        ),
    ] = None,
    mmproj: Annotated[
        Optional[Path],
        typer.Option(
            "--mmproj",
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
            help="Path to mmproj GGUF (default: CINECUT_MODELS_DIR/mmproj-model-f16.gguf).",
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

    # Resolve model paths at runtime — respects CINECUT_MODELS_DIR (IINF-03)
    models_dir = get_models_dir()
    if model is None:
        model = models_dir / "ggml-model-q4_k.gguf"
    if mmproj is None:
        mmproj = models_dir / "mmproj-model-f16.gguf"

    # --- Checkpoint init (PIPE-04) ---
    ckpt = load_checkpoint(work_dir)
    if ckpt is not None and ckpt.source_file != str(video):
        console.print("[yellow]Warning:[/] Stale checkpoint (different source file). Starting fresh.")
        ckpt = None
    if ckpt is None:
        ckpt = PipelineCheckpoint(source_file=str(video), vibe=vibe_normalized)

    try:
        trailer_manifest = None
        silence_injection: dict | None = None

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
            reordered_manifest, extra_paths, silence_injection = assemble_manifest(trailer_manifest, video, work_dir)
        else:
            # --- Stage 1/8: Proxy creation (PIPE-02) ---
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

            # Capture proxy duration for heuristic fallback (Stage 5)
            if ckpt.proxy_duration_s is None:
                try:
                    ckpt.proxy_duration_s = get_film_duration_s(proxy_path)
                    save_checkpoint(ckpt, work_dir)
                except Exception:
                    ckpt.proxy_duration_s = 0.0  # safe default; heuristic will use subtitle span instead
            proxy_duration_s = ckpt.proxy_duration_s

            # --- Stage 2/8: Subtitle parsing (NARR-01) ---
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

            # --- Stage 3/8: Keyframe extraction (PIPE-03) ---
            _timestamps_cache = work_dir / "keyframe_timestamps.json"
            subtitle_midpoints = [e.midpoint_s for e in dialogue_events]

            if not ckpt.is_stage_complete("keyframes"):
                console.print(f"[bold]Stage 3/{TOTAL_STAGES}:[/bold] Extracting keyframes...")

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
                    _timestamps_cache.write_text(json.dumps(timestamps), encoding="utf-8")
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
                # Load cached timestamps — skip scene detection on resume
                console.print(f"[yellow]Resuming:[/] Stage 3 already complete — loading cached timestamps\n")
                if _timestamps_cache.exists():
                    timestamps = json.loads(_timestamps_cache.read_text(encoding="utf-8"))
                else:
                    # Fallback: timestamps file missing (old work dir) — re-run scene detection
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        TimeElapsedColumn(),
                        console=console,
                        transient=True,
                    ) as fb_progress:
                        fb_progress.add_task("Re-running scene detection (timestamps cache missing)...", total=None)
                        timestamps = collect_keyframe_timestamps(proxy_path, subtitle_midpoints)
                    _timestamps_cache.write_text(json.dumps(timestamps), encoding="utf-8")
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("{task.completed}/{task.total}"),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    kf_task = progress.add_task("Extracting frames...", total=len(timestamps))
                    keyframe_records = extract_all_keyframes(
                        proxy_path,
                        timestamps,
                        work_dir / "keyframes",
                        subtitle_midpoints=set(subtitle_midpoints),
                        progress_callback=lambda: progress.advance(kf_task),
                    )

            # --- Stage 4/8: LLaVA Inference (INFR-01, IINF-01, IINF-02) ---
            console.print(f"[bold]Stage 4/{TOTAL_STAGES}:[/bold] LLaVA inference...")
            cached_results = load_cache(video, work_dir)

            if cached_results is not None:
                # IINF-01: cache hit — skip inference entirely
                inference_results = cached_results
                ckpt.cache_hit = True
                cache_path = work_dir / f"{video.stem}.scenedesc.msgpack"
                console.print(
                    f"[yellow]Cache hit:[/] Loaded {len(inference_results)} SceneDescriptions "
                    f"from [dim]{cache_path.name}[/dim] — LLaVA inference skipped\n"
                )
            else:
                # Cache miss or invalidated (IINF-02) — cascade reset then run inference
                # If source file changed (mtime/size differs), clear downstream stages
                # so Stage 5 (narrative) doesn't run against stale keyframes (Research Pitfall 5)
                for stale_stage in ("narrative", "assembly"):
                    if stale_stage in ckpt.stages_complete:
                        ckpt.stages_complete.remove(stale_stage)
                        ckpt.manifest_path = None if stale_stage == "narrative" else ckpt.manifest_path
                        ckpt.assembly_manifest_path = None if stale_stage == "assembly" else ckpt.assembly_manifest_path

                ckpt.cache_hit = False
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

                save_cache(inference_results, video, work_dir)
                console.print(f"[green]Inference complete:[/] cache written\n")

            skipped = sum(1 for _, desc in inference_results if desc is None)
            ckpt.inference_complete = True
            save_checkpoint(ckpt, work_dir)

            # --- Stage 5/8: Structural Analysis (IINF-03, IINF-04, STRC-01, STRC-03) ---
            if not ckpt.is_stage_complete("structural"):
                console.print(f"[bold]Stage 5/{TOTAL_STAGES}:[/bold] Structural analysis...")
                models_dir = get_models_dir()
                mistral_path = models_dir / MISTRAL_GGUF_NAME
                if not mistral_path.exists():
                    console.print(
                        f"[yellow]Heuristic fallback:[/] Mistral GGUF not found at "
                        f"[dim]{mistral_path}[/dim] — using 5%/45%/80% zone anchors\n"
                    )
                    structural_anchors = compute_heuristic_anchors(proxy_duration_s)
                else:
                    with TextEngine(mistral_path) as text_engine:
                        structural_anchors = run_structural_analysis(dialogue_events, text_engine)
                ckpt.structural_anchors = structural_anchors.model_dump()
                ckpt.mark_stage_complete("structural")
                save_checkpoint(ckpt, work_dir)
                console.print(
                    f"[green]Structural anchors:[/] BEGIN={structural_anchors.begin_t:.1f}s "
                    f"ESCALATION={structural_anchors.escalation_t:.1f}s "
                    f"CLIMAX={structural_anchors.climax_t:.1f}s "
                    f"([dim]source={structural_anchors.source}[/dim])\n"
                )
            else:
                structural_anchors = StructuralAnchors(**ckpt.structural_anchors)
                console.print(f"[yellow]Resuming:[/] Stage 5 already complete\n")

            # --- Stage 6/8: Narrative beat extraction and manifest generation (NARR-02, NARR-03, EDIT-01) ---
            if not ckpt.is_stage_complete("narrative"):
                console.print(f"[bold]Stage 6/{TOTAL_STAGES}:[/bold] Extracting narrative beats and generating manifest...")

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
                        structural_anchors=structural_anchors,   # in scope from Stage 5
                    )

                ckpt.manifest_path = str(manifest_path)
                ckpt.mark_stage_complete("narrative")
                save_checkpoint(ckpt, work_dir)
                console.print(f"[green]Manifest written: [dim]{manifest_path.name}[/dim]\n")
            else:
                manifest_path = Path(ckpt.manifest_path)
                console.print(f"[yellow]Resuming:[/] Stage 6 already complete (manifest: {manifest_path.name})\n")

            trailer_manifest = load_manifest(manifest_path)

            # --- Stage 7/8: 3-act assembly and pacing enforcement (EDIT-02, EDIT-03) ---
            if not ckpt.is_stage_complete("assembly"):
                console.print(f"[bold]Stage 7/{TOTAL_STAGES}:[/bold] Assembling 3-act structure...")
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    TimeElapsedColumn(),
                    console=console,
                    transient=True,
                ) as progress:
                    asm_task = progress.add_task("Ordering clips and generating title card...", total=None)
                    reordered_manifest, extra_paths, silence_injection = assemble_manifest(trailer_manifest, video, work_dir)
                    progress.update(asm_task, description="Assembly complete")
                ckpt.assembly_manifest_path = str(work_dir / "ASSEMBLY_MANIFEST.json")
                ckpt.mark_stage_complete("assembly")
                save_checkpoint(ckpt, work_dir)
                console.print(f"[green]Assembly complete: {len(reordered_manifest.clips)} clips ordered\n")
            else:
                # Re-run assemble_manifest to pick up any newly-cached music/BPM
                # (old saved manifest may have music_bed=null if run before JAMENDO was set).
                reordered_manifest, extra_paths, silence_injection = assemble_manifest(trailer_manifest, video, work_dir)
                console.print(f"[yellow]Resuming:[/] Stage 7 already complete\n")

            # --- Stage 7/8: Music fetch and BPM detection (MUSC-01, MUSC-02, BPMG-01) ---
            if not ckpt.is_stage_complete("music"):
                console.print(f"[bold]Stage 7/{TOTAL_STAGES}:[/bold] Fetching music bed and detecting BPM...")
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    TimeElapsedColumn(),
                    console=console,
                    transient=True,
                ) as progress:
                    asm_task = progress.add_task("Fetching music for vibe...", total=None)
                    # Music and BPM ran inside assemble_manifest (Stage 7); here we checkpoint the result
                    progress.update(asm_task, description="Music stage complete")
                ckpt.mark_stage_complete("music")
                save_checkpoint(ckpt, work_dir)
                if reordered_manifest.bpm_grid is not None:
                    console.print(
                        f"[green]BPM detected:[/] {reordered_manifest.bpm_grid.bpm:.1f} BPM "
                        f"({reordered_manifest.bpm_grid.source}) — "
                        f"{reordered_manifest.bpm_grid.beat_count} beats\n"
                    )
                else:
                    console.print("[yellow]Music bed:[/] unavailable — trailer proceeds without music\n")
            else:
                console.print(f"[yellow]Resuming:[/] Stage 7 already complete (music/BPM)\n")

            # --- Summary ---
            bpm_line = (
                f"  BPM:        {reordered_manifest.bpm_grid.bpm:.1f} ({reordered_manifest.bpm_grid.source})\n"
                if reordered_manifest.bpm_grid else ""
            )
            console.print(Panel(
                f"[bold green]Pipeline complete[/bold green]\n\n"
                f"  Proxy:      [dim]{proxy_path.name}[/dim]\n"
                f"  Subtitles:  {len(dialogue_events)} events\n"
                f"  Keyframes:  {len(keyframe_records)} frames\n"
                f"  Described:  {len(inference_results) - skipped} frames ({skipped} skipped)\n"
                f"  Manifest:   [dim]{manifest_path.name}[/dim]\n"
                f"  Assembly:   {len(reordered_manifest.clips)} clips ordered\n"
                + bpm_line +
                f"  Work dir:   [dim]{work_dir}[/dim]",
                title="[green]Phase 9 Complete[/green]",
                border_style="green",
            ))

        # --- Stage 8/8: FFmpeg conform (EDIT-05 / CLI-04) ---
        if trailer_manifest is not None:
            # --review pause (EDIT-04): inspect manifest before conform
            if review:
                console.print(f"\n[bold yellow]Review mode:[/bold yellow] Manifest loaded from:\n  {manifest}")
                console.print("[dim]Inspect clip decisions in the manifest, then confirm to continue.[/dim]\n")
                typer.confirm("Proceed with FFmpeg conform?", abort=True)

            console.print(f"[bold]Stage 8/{TOTAL_STAGES}:[/bold] Running FFmpeg conform...")
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                conform_task = progress.add_task(
                    f"Processing {len(reordered_manifest.clips)} clips...", total=None
                )
                output_path = conform_manifest(
                    reordered_manifest,
                    video,
                    work_dir,
                    extra_clip_paths=extra_paths,
                    inject_after_clip=silence_injection["index"] if silence_injection else None,
                    inject_paths=silence_injection["paths"] if silence_injection else None,
                )
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
