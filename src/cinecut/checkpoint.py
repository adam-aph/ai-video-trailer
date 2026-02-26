"""Atomic pipeline checkpoint for CineCut stage-based resumability (PIPE-04)."""
import json
import os
import tempfile
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

CHECKPOINT_FILENAME = "pipeline_checkpoint.json"


@dataclass
class PipelineCheckpoint:
    """Persisted state across all pipeline stages. Written atomically after each stage."""
    source_file: str          # Absolute path to source video (used to detect stale checkpoint)
    vibe: str                 # Normalized vibe name

    stages_complete: list[str] = field(default_factory=list)

    # Stage outputs (None until stage completes and checkpoint is saved)
    proxy_path: Optional[str] = None
    keyframe_count: Optional[int] = None
    dialogue_event_count: Optional[int] = None
    inference_complete: Optional[bool] = None
    manifest_path: Optional[str] = None
    assembly_manifest_path: Optional[str] = None

    def is_stage_complete(self, stage: str) -> bool:
        """Return True if the given stage name is in stages_complete."""
        return stage in self.stages_complete

    def mark_stage_complete(self, stage: str) -> None:
        """Append stage to stages_complete if not already present."""
        if stage not in self.stages_complete:
            self.stages_complete.append(stage)


def load_checkpoint(work_dir: Path) -> Optional[PipelineCheckpoint]:
    """Load checkpoint from work_dir, returning None if missing or corrupt."""
    ckpt_path = work_dir / CHECKPOINT_FILENAME
    if not ckpt_path.exists():
        return None
    try:
        data = json.loads(ckpt_path.read_text(encoding="utf-8"))
        return PipelineCheckpoint(**data)
    except (json.JSONDecodeError, TypeError):
        return None


def save_checkpoint(checkpoint: PipelineCheckpoint, work_dir: Path) -> None:
    """Atomically write checkpoint to work_dir using tempfile + os.replace().

    The temp file is created in the same directory as the destination so that
    os.replace() is guaranteed to be atomic on POSIX filesystems (same mount).
    Power-loss safe: the destination is either the old file or the new file,
    never a partially-written file.
    """
    ckpt_path = work_dir / CHECKPOINT_FILENAME
    data = json.dumps(asdict(checkpoint), indent=2).encode("utf-8")
    fd, tmp_path = tempfile.mkstemp(dir=work_dir, suffix=".ckpt.tmp")
    try:
        os.write(fd, data)
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp_path, ckpt_path)
    except Exception:
        os.close(fd)
        os.unlink(tmp_path)
        raise
