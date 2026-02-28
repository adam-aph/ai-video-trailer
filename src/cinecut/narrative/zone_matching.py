"""Zone matching: assign each clip to BEGINNING, ESCALATION, or CLIMAX.

Uses sentence-transformers all-MiniLM-L6-v2 (CPU-only, 22.7M params, 384-dim)
with cosine similarity against static zone anchor phrases.

CPU-only is mandatory: CUDA 11.4 on Quadro K6000 is incompatible with modern
PyTorch CUDA wheels. Install order: pip install torch --index-url
https://download.pytorch.org/whl/cpu && pip install sentence-transformers

Anti-patterns avoided:
  - Model NOT loaded per clip (uses lru_cache singleton — ~200ms load cost)
  - CUDA device NOT used (explicit device='cpu')
  - Empty strings NOT embedded (position fallback instead)
  - util.cos_sim() returns Tensor — always call .numpy() before np.argmax()
"""
from __future__ import annotations

import numpy as np
from functools import lru_cache
from typing import TYPE_CHECKING, Optional

from cinecut.manifest.schema import NarrativeZone

if TYPE_CHECKING:
    from cinecut.manifest.schema import StructuralAnchors
    from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"

# Static zone anchor phrases. Represent the semantic character of each zone.
# These are stable across films — no subtitle corpus re-reading required.
ZONE_ANCHORS: dict[NarrativeZone, str] = {
    NarrativeZone.BEGINNING: (
        "introduction setup ordinary world character establishment calm before the storm"
    ),
    NarrativeZone.ESCALATION: (
        "rising tension conflict confrontation danger intensifying stakes escalating pressure"
    ),
    NarrativeZone.CLIMAX: (
        "peak crisis final battle decisive moment maximum intensity explosive showdown climax"
    ),
}


@lru_cache(maxsize=1)
def _load_model() -> "SentenceTransformer":
    """Load and cache all-MiniLM-L6-v2 CPU model (loaded at most once per process).

    lru_cache with no arguments means the function is called once on first use
    and the result is returned on all subsequent calls. This avoids the ~200ms
    model loading cost being incurred per clip (30 clips = 6s overhead otherwise).

    Raises RuntimeError if sentence_transformers is not installed or if the
    model cannot be downloaded (offline environment without cached model).
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise RuntimeError(
            "sentence-transformers not installed. Run: "
            "pip install torch --index-url https://download.pytorch.org/whl/cpu "
            "&& pip install sentence-transformers"
        ) from e
    return SentenceTransformer(MODEL_NAME, device="cpu")


def _zone_by_position(
    midpoint_s: float,
    film_duration_s: float,
    anchors: "Optional[StructuralAnchors]",
) -> NarrativeZone:
    """Assign zone by timestamp position relative to structural anchors.

    Uses anchors.escalation_t and anchors.climax_t when available.
    Falls back to 33%/66% split when anchors is None.
    This fallback handles: empty dialogue excerpt, absent structural_anchors (v1.0 manifest).
    """
    if anchors is not None:
        if midpoint_s < anchors.escalation_t:
            return NarrativeZone.BEGINNING
        elif midpoint_s < anchors.climax_t:
            return NarrativeZone.ESCALATION
        else:
            return NarrativeZone.CLIMAX
    # Hard fallback: no anchors at all
    pos = midpoint_s / max(film_duration_s, 1.0)
    if pos < 0.33:
        return NarrativeZone.BEGINNING
    elif pos < 0.67:
        return NarrativeZone.ESCALATION
    else:
        return NarrativeZone.CLIMAX


def assign_narrative_zone(
    dialogue_text: str,
    structural_anchors: "Optional[StructuralAnchors]",
    clip_midpoint_s: float,
    film_duration_s: float,
) -> NarrativeZone:
    """Assign a single clip to BEGINNING, ESCALATION, or CLIMAX.

    If dialogue_text is empty (silent shot) or structural_anchors is None:
        Uses position-based fallback via _zone_by_position().

    Otherwise:
        Embeds dialogue_text with all-MiniLM-L6-v2, computes cosine similarity
        against ZONE_ANCHORS phrases, returns highest-scoring zone.

    normalize_embeddings=True: L2-normalized embeddings make cosine similarity
    equivalent to dot product — faster and recommended by sbert.net docs.
    """
    if not dialogue_text.strip():
        return _zone_by_position(clip_midpoint_s, film_duration_s, structural_anchors)

    model = _load_model()
    zone_keys = list(ZONE_ANCHORS.keys())
    zone_texts = list(ZONE_ANCHORS.values())

    text_emb = model.encode([dialogue_text], normalize_embeddings=True)      # shape: (1, 384)
    anchor_embs = model.encode(zone_texts, normalize_embeddings=True)        # shape: (3, 384)

    from sentence_transformers import util
    sims = util.cos_sim(text_emb, anchor_embs)[0]  # Tensor shape: (3,)
    # CRITICAL: util.cos_sim returns torch.Tensor — must call .numpy() for np.argmax
    best_idx = int(np.argmax(sims.numpy()))
    return zone_keys[best_idx]


def run_zone_matching(
    clip_texts: list[str],
    clip_midpoints: list[float],
    film_duration_s: float,
    structural_anchors: "Optional[StructuralAnchors]",
) -> list[NarrativeZone]:
    """Assign narrative zones to all clips, called once per pipeline run.

    Encodes anchor phrases once, then processes each clip text.
    Clips with empty text use position-based fallback (no model encode call).

    Args:
        clip_texts: dialogue_excerpt for each clip (empty string if no dialogue)
        clip_midpoints: midpoint timestamp (seconds) for each clip (for fallback)
        film_duration_s: total film duration (for position-based fallback)
        structural_anchors: StructuralAnchors from manifest (None for v1.0 manifests)

    Returns:
        list of NarrativeZone, one per clip, in same order as clip_texts
    """
    zones: list[NarrativeZone] = []
    zone_keys = list(ZONE_ANCHORS.keys())
    zone_texts = list(ZONE_ANCHORS.values())

    # Pre-encode anchor phrases once for all clips (3ms total vs per-clip overhead)
    # Only load model if any clips have dialogue text
    has_text = any(t.strip() for t in clip_texts)
    anchor_embs = None
    if has_text:
        model = _load_model()
        anchor_embs = model.encode(zone_texts, normalize_embeddings=True)  # shape: (3, 384)

    for text, midpoint in zip(clip_texts, clip_midpoints):
        if not text.strip() or anchor_embs is None:
            zones.append(_zone_by_position(midpoint, film_duration_s, structural_anchors))
            continue

        text_emb = model.encode([text], normalize_embeddings=True)   # shape: (1, 384)
        from sentence_transformers import util
        sims = util.cos_sim(text_emb, anchor_embs)[0]                # Tensor shape: (3,)
        best_idx = int(np.argmax(sims.numpy()))
        zones.append(zone_keys[best_idx])

    return zones
