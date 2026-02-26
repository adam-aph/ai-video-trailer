"""CineCut inference package — LLaVA engine, VRAM management, GPU serialization."""
import threading

# Module-level lock serializing all GPU operations across the process.
# LlavaEngine acquires this on __enter__ and releases on __exit__.
# FFmpeg conform pipeline must acquire this lock before any GPU operations (Phase 5).
GPU_LOCK: threading.Lock = threading.Lock()

from cinecut.inference.models import SceneDescription, SCENE_DESCRIPTION_SCHEMA  # noqa: E402
from cinecut.inference.vram import check_vram_free_mib, VRAM_MINIMUM_MIB  # noqa: E402

__all__ = [
    "GPU_LOCK",
    "SceneDescription",
    "SCENE_DESCRIPTION_SCHEMA",
    "check_vram_free_mib",
    "VRAM_MINIMUM_MIB",
]
