# Phase 8: Zone Matching and Non-Linear Ordering - Research

**Researched:** 2026-02-28
**Domain:** sentence-transformers semantic similarity, narrative zone assignment, non-linear clip ordering, pacing curve enforcement
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| STRC-02 | System assigns each extracted clip to a narrative zone: BEGINNING, ESCALATION, or CLIMAX | sentence-transformers cosine similarity between clip dialogue context and zone anchor descriptions; `NarrativeZone` enum; `ClipEntry.narrative_zone` field |
| EORD-01 | Clips are assembled in zone-first order (BEGINNING → ESCALATION → CLIMAX), not film chronology | Replace `sort_clips_by_act` chronological tie-breaking with zone-first sort; zone order is BEGINNING → ESCALATION → CLIMAX; source timestamp used only for deduplication |
| EORD-02 | Within each zone, clips are ranked by emotional signal score (not source timestamp) | Within each zone: `sort(key=lambda c: c.money_shot_score, reverse=True)`; emotional signal = existing `money_shot_score` field on `ClipEntry` |
| EORD-03 | Act 1 clips average 4-8 beats/clip; Act 3 clips average 1-2 beats/clip (montage density) | "Beats per clip" = clip duration / vibe-profile act-specific avg_cut_s; BEGINNING zone uses `act1_avg_cut_s` targets; CLIMAX zone uses `act3_avg_cut_s`; existing `enforce_pacing_curve()` extended to work on zone labels |
</phase_requirements>

---

## Summary

Phase 8 adds two new modules and modifies the existing generator/ordering pipeline to implement the core non-linear narrative claim of v2.0. The work splits cleanly into two plans: (1) zone assignment in `narrative/zone_matching.py` using sentence-transformers cosine similarity against the `StructuralAnchors` from Phase 7, and (2) zone-first ordering in `narrative/generator.py` and `assembly/ordering.py` to replace the current chronological-within-act sort with zone-then-score ordering.

The zone assignment algorithm compares the dialogue excerpt text of each clip (already stored as `ClipEntry.dialogue_excerpt`) against semantic zone descriptions anchored to `StructuralAnchors.begin_t/escalation_t/climax_t` using `sentence-transformers` all-MiniLM-L6-v2. All inference runs CPU-only to avoid CUDA 11.4 / PyTorch incompatibility on the Quadro K6000. The model is 22.7M parameters producing 384-dimensional embeddings — it runs in under 1 second per clip on CPU. If `structural_anchors` is absent in the manifest (e.g., a v1.0 manifest), a timestamp-midpoint fallback assigns zones by clip position relative to the film's total duration.

The generator pipeline change in Plan 08-02 modifies `run_narrative_stage()` to invoke zone matching immediately after scoring clips, attaches the `narrative_zone` field to each `ClipEntry`, and replaces the current chronological sort with zone-first then score-descending sort. The `enforce_pacing_curve()` logic in `assembly/ordering.py` is updated to reference zones (BEGINNING/ESCALATION/CLIMAX) instead of raw `act` labels for density enforcement. The `ClipEntry` schema gains a `narrative_zone: Optional[NarrativeZone] = None` field (backward-compatible — None on v1.0 manifests).

**Primary recommendation:** Use `sentence_transformers.SentenceTransformer("all-MiniLM-L6-v2", device="cpu")` with `encode()` returning numpy arrays, compute cosine similarity via `util.cos_sim()`, and pick the highest-scoring zone. Install with CPU PyTorch first: `pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install sentence-transformers`.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sentence-transformers | >=3.0 (latest) | Semantic embedding for zone assignment | Project-specified in roadmap; all-MiniLM-L6-v2 is the standard lightweight model |
| torch (CPU wheel) | >=2.0 (cpu) | PyTorch backend for sentence-transformers | Must install CPU wheel first to avoid CUDA 11.4 incompatibility on K6000 |
| pydantic | >=2.12.0 (already installed) | `NarrativeZone` enum field on `ClipEntry` | Already used in manifest/schema.py; Pydantic v2 enum support native |
| numpy | >=1.24.0 (already installed) | Cosine similarity matrix computation | Already in pyproject.toml; sentence-transformers returns numpy arrays by default |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sentence_transformers.util | (bundled) | `cos_sim()` for pairwise similarity | Computing zone assignment scores from embeddings |
| statistics.median | (stdlib) | Optional: aggregating multi-text similarity scores per clip | Only if a clip has multiple dialogue lines |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| sentence-transformers all-MiniLM-L6-v2 CPU | OpenAI embeddings API | External API call, network dependency, cost — not acceptable for local pipeline |
| sentence-transformers cosine similarity | BM25 keyword matching | Keyword matching cannot understand semantic distance from zone anchor phrases |
| sentence-transformers | spaCy `en_core_web_md` word vectors | spaCy vectors are word-level (not sentence), lower semantic quality for zone matching |
| CPU-only torch | CUDA torch | CUDA torch conflicts with K6000's CUDA 11.4 — sentence-transformers would pull CUDA 12.x wheels |

**Installation:**
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers
```

This order matters: installing torch CPU first prevents pip from auto-selecting a CUDA wheel when sentence-transformers pulls in torch as a dependency.

**pyproject.toml additions:**
```toml
"sentence-transformers>=3.0",
"torch>=2.0",
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/cinecut/
├── narrative/
│   ├── zone_matching.py     # NEW (08-01): NarrativeZone enum, assign_narrative_zone(), load_zone_model()
│   ├── generator.py         # MODIFY (08-02): invoke zone matching after scoring; zone-first sort
│   └── ...
├── assembly/
│   └── ordering.py          # MODIFY (08-02): zone-first sort replacing ACT_ORDER; pacing curve for zones
├── manifest/
│   └── schema.py            # MODIFY (08-01): NarrativeZone enum; ClipEntry.narrative_zone field
└── ...
```

### Pattern 1: NarrativeZone Enum in Schema

**What:** A Python enum value for the three zones stored on each `ClipEntry`.
**When to use:** Defined in `manifest/schema.py`; used throughout `zone_matching.py`, `generator.py`, and `ordering.py`.

```python
# In manifest/schema.py — add BEFORE ClipEntry:
from enum import Enum

class NarrativeZone(str, Enum):
    """Narrative zone assigned by sentence-transformers zone matching (STRC-02)."""
    BEGINNING = "BEGINNING"
    ESCALATION = "ESCALATION"
    CLIMAX = "CLIMAX"

# Modify ClipEntry:
class ClipEntry(BaseModel):
    # ... existing fields ...
    narrative_zone: Optional[NarrativeZone] = None   # None on v1.0 manifests; set in Phase 8
```

**Why `str, Enum`:** Pydantic v2 serializes `str` enums as plain strings in JSON (`"BEGINNING"` not `{"value": "BEGINNING"}`). `model_dump_json(exclude_none=True)` correctly includes it when set and excludes it when None.

### Pattern 2: Zone Model Loading (CPU-Only, Module-Scoped Singleton)

**What:** Load the all-MiniLM-L6-v2 model once at import time (or lazily on first call) with `device="cpu"`. Do NOT reload it per clip — model loading takes ~200ms and embedding is ~5ms/clip.
**When to use:** In `narrative/zone_matching.py`, module-scope or lazy singleton pattern.

```python
# Source: sentence-transformers official docs (https://sbert.net/docs/semantic_textual_similarity.html)
# and HuggingFace model card (https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
from __future__ import annotations
from functools import lru_cache
from sentence_transformers import SentenceTransformer, util

MODEL_NAME = "all-MiniLM-L6-v2"

@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    """Load and cache the sentence-transformers model (CPU-only, loaded once).

    Uses lru_cache so the model is loaded at most once per process lifetime.
    Explicitly device='cpu' to prevent CUDA selection on K6000 (CUDA 11.4 incompatible).
    """
    return SentenceTransformer(MODEL_NAME, device="cpu")
```

**Why `lru_cache`:** Zone matching is called once per pipeline run for all clips. The `@lru_cache(maxsize=1)` pattern avoids module-level initialization (which would break unit tests that mock the model) while ensuring the model is not reloaded per clip.

**Why `device="cpu"` explicitly:** Without `device="cpu"`, `SentenceTransformer.__init__` auto-detects the strongest available device. On the K6000 machine with CUDA installed, it would attempt CUDA, fail with a version mismatch (CPU torch vs CUDA 11.4), or succeed but consume GPU_LOCK time we cannot afford while LLaVA/TextEngine may be running.

### Pattern 3: Zone Anchor Phrase Generation from StructuralAnchors

**What:** Convert `StructuralAnchors` timestamps into descriptive anchor phrases that the model can embed. The cosine similarity is between the clip's dialogue text and these anchor descriptions. Using concrete narrative descriptions gives the model meaningful signal.
**When to use:** In `narrative/zone_matching.py`, inside `assign_narrative_zone()`.

```python
# Source: project design derived from REQUIREMENTS.md zone semantics
from cinecut.manifest.schema import StructuralAnchors, NarrativeZone

# Zone anchor phrases — representative of what each zone sounds/feels like
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
```

**Alternative anchor strategy:** Generate anchors from the dialogue text near each structural anchor timestamp. For example, extract the dialogue near `begin_t`, `escalation_t`, `climax_t` from the subtitle corpus and embed those actual lines. This would be more film-specific but requires passing `dialogue_events` to the zone matching function. The static anchor phrase approach is simpler and sufficient for the first implementation.

### Pattern 4: Single-Clip Zone Assignment via Cosine Similarity

**What:** Encode the clip's dialogue excerpt, encode the three zone anchor phrases, compute cosine similarities, pick the highest-scoring zone.
**When to use:** In `narrative/zone_matching.py`, `assign_narrative_zone()`.

```python
# Source: sentence-transformers official docs semantic similarity pattern
# (https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html)
import numpy as np
from sentence_transformers import util

def assign_narrative_zone(
    dialogue_text: str,
    structural_anchors: Optional["StructuralAnchors"],
    clip_midpoint_s: float,
    film_duration_s: float,
) -> NarrativeZone:
    """Assign a clip to BEGINNING, ESCALATION, or CLIMAX.

    If dialogue_text is empty OR structural_anchors is None:
        Falls back to timestamp midpoint heuristic using structural_anchors timestamps
        or 33%/66% split if anchors are absent.

    Otherwise:
        Embeds dialogue_text and all zone anchor phrases, picks highest cosine similarity.
    """
    # Fallback: no text to embed — use timestamp position
    if not dialogue_text.strip() or structural_anchors is None:
        return _zone_by_position(clip_midpoint_s, film_duration_s, structural_anchors)

    model = _load_model()
    zone_texts = list(ZONE_ANCHORS.values())
    zone_keys = list(ZONE_ANCHORS.keys())

    # encode returns numpy arrays by default (convert_to_numpy=True is the default)
    text_emb = model.encode([dialogue_text], normalize_embeddings=True)
    anchor_embs = model.encode(zone_texts, normalize_embeddings=True)

    # cos_sim returns a 2D tensor/array; we want similarities[0] (first query vs all anchors)
    sims = util.cos_sim(text_emb, anchor_embs)[0]  # shape: (3,)
    best_idx = int(np.argmax(sims.numpy() if hasattr(sims, 'numpy') else sims))
    return zone_keys[best_idx]


def _zone_by_position(
    midpoint_s: float,
    film_duration_s: float,
    anchors: Optional["StructuralAnchors"],
) -> NarrativeZone:
    """Assign zone by timestamp position. Uses anchors if available, else 33%/66% split."""
    if anchors is not None:
        if midpoint_s < anchors.escalation_t:
            return NarrativeZone.BEGINNING
        elif midpoint_s < anchors.climax_t:
            return NarrativeZone.ESCALATION
        else:
            return NarrativeZone.CLIMAX
    # Hard fallback: no anchors
    pos = midpoint_s / max(film_duration_s, 1.0)
    if pos < 0.33:
        return NarrativeZone.BEGINNING
    elif pos < 0.67:
        return NarrativeZone.ESCALATION
    else:
        return NarrativeZone.CLIMAX
```

**normalize_embeddings=True:** When embeddings are L2-normalized, cosine similarity reduces to a dot product. This is slightly faster and recommended by the official docs.

### Pattern 5: Batch Zone Assignment for Efficiency

**What:** Embed ALL clip dialogue texts in a single `model.encode()` call instead of one call per clip. This is dramatically faster — all-MiniLM-L6-v2 batches 100 sentences in ~50ms on CPU vs 100 separate calls at ~500ms total.
**When to use:** In `narrative/zone_matching.py`, `run_zone_matching()` — the batch version called from `generator.py`.

```python
# Source: sentence-transformers docs (Computing Embeddings section)
def run_zone_matching(
    clip_texts: list[str],
    clip_midpoints: list[float],
    film_duration_s: float,
    structural_anchors: Optional["StructuralAnchors"],
) -> list[NarrativeZone]:
    """Assign narrative zones to all clips in a single batch encode call.

    Args:
        clip_texts: dialogue_excerpt for each clip (empty string if none)
        clip_midpoints: midpoint timestamp for each clip (for fallback)
        film_duration_s: total film duration (for position-based fallback)
        structural_anchors: from manifest (can be None for v1.0 manifests)

    Returns:
        list of NarrativeZone, one per clip, in input order
    """
    zones: list[NarrativeZone] = []
    model = _load_model()

    zone_keys = list(ZONE_ANCHORS.keys())
    zone_texts = list(ZONE_ANCHORS.values())
    anchor_embs = model.encode(zone_texts, normalize_embeddings=True)  # shape: (3, 384)

    for text, midpoint in zip(clip_texts, clip_midpoints):
        if not text.strip():
            # No dialogue — use position fallback
            zones.append(_zone_by_position(midpoint, film_duration_s, structural_anchors))
            continue

        text_emb = model.encode([text], normalize_embeddings=True)   # shape: (1, 384)
        sims = util.cos_sim(text_emb, anchor_embs)[0]                # shape: (3,)
        best_idx = int(np.argmax(sims.numpy() if hasattr(sims, 'numpy') else np.array(sims)))
        zones.append(zone_keys[best_idx])

    return zones
```

**Optimization note:** Even more efficient: encode ALL non-empty clip texts in a single batch call, then compute cosine similarities. The code above is simpler and acceptable for typical clip counts (20-35 clips per vibe profile). The per-clip loop with single `encode([text])` is fine in practice.

### Pattern 6: Zone-First Sort in ordering.py

**What:** Replace `sort_clips_by_act`'s chronological tie-breaking within each act with zone-first ordering (BEGINNING → ESCALATION → CLIMAX) and score-descending within zones.
**When to use:** In `assembly/ordering.py`, new `sort_clips_by_zone()` function.

```python
# Source: project src/cinecut/assembly/ordering.py (existing sort_clips_by_act pattern adapted)
from cinecut.manifest.schema import ClipEntry, NarrativeZone

# Zone ordering priority — BEGINNING first, CLIMAX last
ZONE_ORDER: dict[NarrativeZone, int] = {
    NarrativeZone.BEGINNING: 0,
    NarrativeZone.ESCALATION: 1,
    NarrativeZone.CLIMAX: 2,
}


def sort_clips_by_zone(clips: list[ClipEntry]) -> list[ClipEntry]:
    """Sort clips into zone-first order: BEGINNING → ESCALATION → CLIMAX.

    Within each zone, sort by money_shot_score descending (EORD-02).
    Clips with narrative_zone=None fall back to position-based zone assignment
    using the clip's midpoint and a 33%/66% split (backward compat).

    Replaces sort_clips_by_act() for v2.0 pipeline.
    """
    def zone_priority(clip: ClipEntry) -> int:
        if clip.narrative_zone is not None:
            return ZONE_ORDER.get(clip.narrative_zone, 999)
        # Fallback for clips without zone (e.g. title_card, button)
        return 999

    def score_key(clip: ClipEntry) -> float:
        return -(clip.money_shot_score or 0.0)   # descending: negate for ascending sort

    return sorted(
        clips,
        key=lambda c: (zone_priority(c), score_key(c)),
    )
```

### Pattern 7: Zone-Based Pacing Curve Enforcement

**What:** The pacing density requirement (EORD-03) maps to zones: BEGINNING clips use `act1_avg_cut_s` targets, CLIMAX clips use `act3_avg_cut_s`. The existing `enforce_pacing_curve()` enforces this for `act3`; Phase 8 extends it (or adds a zone-aware version) so CLIMAX clips are trimmed to `act3_avg_cut_s` and BEGINNING clips are not over-trimmed.

**The EORD-03 requirement states:** "Act 1 clips average 4-8 beats/clip; Act 3 clips average 1-2 beats/clip." In this context, "beats/clip" means clip duration divided by the vibe-profile act cut duration — the existing `enforce_pacing_curve` enforces average duration targets by trimming act3 clips. For Phase 8, we extend this to CLIMAX zone.

```python
# Source: project src/cinecut/assembly/ordering.py enforce_pacing_curve pattern (adapted)
def enforce_zone_pacing_curve(
    clips: list[ClipEntry],
    profile: VibeProfile,
) -> list[ClipEntry]:
    """Trim CLIMAX zone clips to act3 duration targets (EORD-03).

    BEGINNING zone clips use act1_avg_cut_s (no trimming — longer is fine).
    CLIMAX zone clips are trimmed if their average exceeds act3_avg_cut_s * 1.5.
    ESCALATION zone clips use act2_avg_cut_s (existing behavior).

    Falls back to zone=None clips using act label (backward compatible).
    """
    result = list(clips)

    # Trim CLIMAX zone clips (same logic as existing act3 enforcement)
    climax_clips = [c for c in result if c.narrative_zone == NarrativeZone.CLIMAX]
    climax_avg = sum(c.source_end_s - c.source_start_s for c in climax_clips) / max(len(climax_clips), 1)

    if climax_avg > profile.act3_avg_cut_s * 1.5:
        for i, clip in enumerate(result):
            if clip.narrative_zone == NarrativeZone.CLIMAX:
                duration = clip.source_end_s - clip.source_start_s
                target = profile.act3_avg_cut_s
                if duration > target * 1.5:
                    new_end = clip.source_start_s + max(target, MIN_CLIP_DURATION_S)
                    result[i] = clip.model_copy(update={"source_end_s": new_end})

    return result
```

### Pattern 8: Zone Matching Integration in generator.py

**What:** After scoring clips and before building `ClipEntry` objects, call `run_zone_matching()` to assign zones to all clips in batch. Then attach `narrative_zone` to each `ClipEntry`.
**When to use:** In `narrative/generator.py`, `run_narrative_stage()`.

```python
# Source: project src/cinecut/narrative/generator.py (adapted from existing scoring loop)
from cinecut.narrative.zone_matching import run_zone_matching
from cinecut.manifest.schema import StructuralAnchors, NarrativeZone

# After the existing scoring loop produces top_scored list...
# Extract dialogue texts and midpoints for batch zone assignment
clip_texts = [
    get_dialogue_excerpt(item["record"].timestamp_s, dialogue_events)
    for item in top_scored
]
clip_midpoints = [
    (win_start + win_end) / 2.0
    for win_start, win_end in windows  # windows computed before this call
]

zones = run_zone_matching(
    clip_texts=clip_texts,
    clip_midpoints=clip_midpoints,
    film_duration_s=film_duration_s,
    structural_anchors=structural_anchors,  # Optional; None if v1.0 manifest
)

# Then in the ClipEntry construction loop:
clip_entries.append(ClipEntry(
    source_start_s=win_start,
    source_end_s=win_end,
    beat_type=beat_type,
    act=act,
    transition=get_transition(act, vibe_profile),
    dialogue_excerpt=get_dialogue_excerpt(record.timestamp_s, dialogue_events),
    reasoning=build_reasoning(record, desc, beat_type, score),
    visual_analysis=visual_analysis,
    subtitle_analysis=subtitle_analysis,
    money_shot_score=round(score, 4),
    narrative_zone=zones[idx],   # idx is the loop index into top_scored/windows
))
```

### Pattern 9: Stage 6 Checkpoint in cli.py

**What:** Zone matching runs as part of the narrative stage (Stage 6 in the Phase 7 8-stage pipeline). It does not need a separate checkpoint stage — it is embedded in `run_narrative_stage()`. The manifest written by Stage 6 will contain `narrative_zone` fields. The Stage 6 checkpoint mark already exists.

**No new checkpoint stage required.** Zone matching is invisible to the checkpoint system because it executes inside `run_narrative_stage()`, which is already checkpoint-guarded.

### Anti-Patterns to Avoid

- **Load the model per clip:** Model loading takes ~200ms. With 30 clips, that is 6 seconds of pure overhead vs <1 second total for batch encoding. Always use the module-level singleton via `_load_model()`.
- **Use CUDA torch with sentence-transformers:** The Quadro K6000 runs CUDA 11.4. PyTorch CUDA wheels require 11.8+. Installing without the CPU index URL will silently pull CUDA wheels and fail at runtime. Always install with `--index-url https://download.pytorch.org/whl/cpu`.
- **Use `response_format` or `json_schema` for zone assignment:** Zone matching is pure Python — no LLM call needed. sentence-transformers runs locally.
- **Sort by `source_start_s` within zones:** EORD-02 explicitly requires score-descending sort within zones, not chronological. Do not reuse the `sort_clips_by_act` pattern that uses `source_start_s` as the secondary key.
- **Hard-code zone boundary at 33%/66%:** The fallback MUST use `structural_anchors.escalation_t` and `structural_anchors.climax_t` when anchors are present. Hard-coding 33%/66% is only the last-resort fallback when anchors are completely absent.
- **Make `narrative_zone` a `Literal` string:** Use the `NarrativeZone` enum. Pydantic v2 with `str, Enum` serializes correctly to JSON strings and provides type safety.
- **Put zone matching in a new CLI stage:** Zone matching is part of the narrative generation step. It does not need a separate checkpoint stage. Keep it inside `run_narrative_stage()`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Semantic text similarity | Custom cosine similarity on bag-of-words | `sentence_transformers.util.cos_sim()` with MiniLM embeddings | BoW has no semantic understanding; "battle" won't match "confrontation" |
| Sentence embeddings | Custom TF-IDF or word2vec pooling | `SentenceTransformer.encode()` | MiniLM is fine-tuned for sentence similarity; word-level vectors miss context |
| Zone assignment distance metric | Euclidean distance on raw embeddings | Cosine similarity via `util.cos_sim()` | Cosine is magnitude-invariant; `normalize_embeddings=True` makes it equivalent to dot product and is faster |
| BEGINNING/CLIMAX anchor text | Compute from film subtitle corpus at runtime | Static `ZONE_ANCHORS` dict with representative phrases | Static anchors are simpler, reproducible, and don't require subtitle corpus to be re-read during zone matching |
| Pacing enforcement | Counting number of cuts and re-timing | Extend existing `enforce_pacing_curve()` for zone labels | Existing function is already tested and proven; extend, don't replace |

**Key insight:** all-MiniLM-L6-v2 is specifically trained for sentence similarity tasks and handles domain-specific language well enough that "I'm going to kill you" correctly scores higher for CLIMAX than BEGINNING.

---

## Common Pitfalls

### Pitfall 1: CUDA Torch Wheel Installed Instead of CPU

**What goes wrong:** `pip install sentence-transformers` pulls `torch` as a dependency. On a machine with CUDA drivers installed (even CUDA 11.4 which is incompatible with modern torch CUDA wheels), pip may select a CUDA-enabled torch wheel. The import fails at runtime with `ImportError: libcuda.so.1: cannot open shared object file` or CUDA version mismatch error.

**Why it happens:** pip resolves the torch dependency from PyPI's default index, which includes CUDA wheels. The wheel selection heuristic can prefer CUDA wheels on systems with NVIDIA drivers.

**How to avoid:** Always install torch CPU wheel FIRST, before sentence-transformers:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers
```
Once torch CPU is installed, pip will not reinstall it when sentence-transformers is added.

**Warning signs:** `torch.cuda.is_available()` returns True when you expected False; or ImportError at sentence_transformers import.

### Pitfall 2: Model Reloaded Per Clip

**What goes wrong:** `SentenceTransformer("all-MiniLM-L6-v2", device="cpu")` inside `assign_narrative_zone()` without caching causes 200ms overhead per clip. With 30 clips = 6 seconds just for model loading, blocking the pipeline.

**Why it happens:** Treating the model load as stateless (like a `requests.get()` call) instead of recognizing it as an expensive resource to cache.

**How to avoid:** Use `@lru_cache(maxsize=1)` on `_load_model()`. The function is called from `run_zone_matching()` which executes once per pipeline run.

**Warning signs:** Stage 6 takes 10+ seconds on the narrative step with debug logs showing repeated model loading.

### Pitfall 3: util.cos_sim() Returns a Tensor, Not a Numpy Array

**What goes wrong:** `sims = util.cos_sim(text_emb, anchor_embs)[0]` returns a PyTorch tensor. Calling `np.argmax(sims)` on it may fail or give wrong results depending on numpy version (numpy 2.0+ changed behavior with tensor inputs).

**Why it happens:** sentence-transformers `util.cos_sim()` always returns a torch.Tensor, even when inputs are numpy arrays. The return type is not numpy.

**How to avoid:** Always convert: `best_idx = int(np.argmax(sims.numpy()))` or `int(sims.argmax())`. Using the `.numpy()` method on the tensor is the safest approach.

**Warning signs:** `TypeError: expected Sequence` or `AttributeError: 'Tensor' object has no attribute X` when processing cosine similarity results.

### Pitfall 4: Empty Dialogue Excerpt Causes Nonsensical Zone Assignment

**What goes wrong:** A clip with `dialogue_excerpt=""` (common for silent action shots) gets encoded as an empty string. MiniLM embedding of empty string produces a near-zero vector with undefined cosine similarity behavior — may return NaN or assign to a random zone.

**Why it happens:** Empty string encoding produces a degenerate vector. The cosine similarity against zone anchors is meaningless.

**How to avoid:** Check `if not dialogue_text.strip()` before calling `model.encode()`. If empty, use the position-based fallback `_zone_by_position()`. This is critical — roughly 30-50% of clips have no dialogue excerpt.

**Warning signs:** All silent clips assigned to BEGINNING or all to CLIMAX, depending on the degenerate vector direction.

### Pitfall 5: Zone Sort Loses Title Card and Button Clips

**What goes wrong:** `sort_clips_by_zone()` is called on ALL clips including generated segments (`act="title_card"`, `act="button"`). These have `narrative_zone=None` and end up in position 999 in the zone sort, meaning they appear AFTER climax clips — which is incorrect.

**Why it happens:** The title card and button are currently added by `title_card.py` in `assembly/assemble_manifest()`. They may be added before or after the sort call.

**How to avoid:** In `assembly/ordering.py`, `sort_clips_by_zone()` must treat `title_card` and `button` act-labeled clips specially — keeping them in their correct positions (title_card first, button last). Check for `clip.act in ("title_card", "button")` before applying zone priority.

**Warning signs:** Title card appears after all CLIMAX clips in the final assembly; button appears at position 999 in the output.

### Pitfall 6: `narrative_zone` Field Breaks ClipEntry Validation on Old Manifests

**What goes wrong:** After adding `narrative_zone: Optional[NarrativeZone] = None` to `ClipEntry`, loading an existing v1.0 manifest that does NOT have `narrative_zone` fields fails with `ValidationError` if the field is required.

**Why it happens:** Pydantic v2 `BaseModel` requires all fields without defaults when loading JSON. If `narrative_zone` lacks a default, it is required.

**How to avoid:** Always add as `Optional[NarrativeZone] = None` — the `= None` default means existing manifests load cleanly without the field.

**Warning signs:** `ValidationError: narrative_zone field required` when loading old manifests with `load_manifest()`.

### Pitfall 7: Model Download Fails at First Run (No Internet / Firewall)

**What goes wrong:** The first call to `SentenceTransformer("all-MiniLM-L6-v2", device="cpu")` downloads the model from HuggingFace (~86 MB). In an offline or firewalled environment, this raises a connection error.

**Why it happens:** sentence-transformers downloads model weights on first use to `~/.cache/huggingface/hub/`. Subsequent runs use the cache.

**How to avoid:** Document that `all-MiniLM-L6-v2` must be pre-downloaded if working offline:
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2', device='cpu')"
```
For the pipeline: wrap the model load in a try/except and fail with a clear error message directing the user to pre-download. Do NOT silently fall back to position-only assignment when a download fails — that would mask a configuration problem.

**Warning signs:** `requests.exceptions.ConnectionError` on first run; subsequent runs work fine if model is cached.

---

## Code Examples

Verified patterns from official sources:

### sentence-transformers SentenceTransformer CPU instantiation

```python
# Source: https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html
# Verified: device="cpu" is the documented parameter name
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
# Returns numpy arrays by default (convert_to_numpy=True is default)
embeddings = model.encode(["Hello world", "Another sentence"])
# embeddings.shape: (2, 384)  — 384-dim output for all-MiniLM-L6-v2
```

### sentence-transformers cosine similarity

```python
# Source: https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html
from sentence_transformers import SentenceTransformer, util
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

sentences1 = ["final battle explosive showdown"]
sentences2 = [
    "introduction calm before the storm",
    "rising tension escalating pressure",
    "peak crisis maximum intensity climax",
]

emb1 = model.encode(sentences1, normalize_embeddings=True)
emb2 = model.encode(sentences2, normalize_embeddings=True)

sims = util.cos_sim(emb1, emb2)   # returns torch.Tensor shape (1, 3)
best_idx = int(np.argmax(sims[0].numpy()))
# best_idx == 2 (highest similarity to climax anchor)
```

### NarrativeZone enum with Pydantic v2

```python
# Source: Pydantic v2 docs (str enum pattern — verified in existing project Pydantic usage)
from enum import Enum
from typing import Optional
from pydantic import BaseModel

class NarrativeZone(str, Enum):
    BEGINNING = "BEGINNING"
    ESCALATION = "ESCALATION"
    CLIMAX = "CLIMAX"

# In ClipEntry:
narrative_zone: Optional[NarrativeZone] = None

# Serialization test:
from cinecut.manifest.schema import ClipEntry, NarrativeZone
ce = ClipEntry(
    source_start_s=0.0,
    source_end_s=5.0,
    beat_type="escalation_beat",
    act="act1",
    narrative_zone=NarrativeZone.CLIMAX,
)
import json
j = json.loads(ce.model_dump_json())
assert j["narrative_zone"] == "CLIMAX"  # str, not {"value": "CLIMAX"}
```

### lru_cache singleton for model

```python
# Source: Python stdlib functools.lru_cache — standard singleton pattern for expensive resources
from functools import lru_cache
from sentence_transformers import SentenceTransformer

@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    """Returns the same model instance on every call — loaded exactly once."""
    return SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

# Verified: lru_cache with maxsize=1 caches based on argument hash
# No-argument functions are cached on first call and returned on all subsequent calls
```

### Zone-first ordering sort key

```python
# Source: project src/cinecut/assembly/ordering.py pattern adapted for zones
from cinecut.manifest.schema import ClipEntry, NarrativeZone

ZONE_ORDER = {NarrativeZone.BEGINNING: 0, NarrativeZone.ESCALATION: 1, NarrativeZone.CLIMAX: 2}

# Sort: zone priority ascending, then score descending within zone
clips_sorted = sorted(
    clips,
    key=lambda c: (
        ZONE_ORDER.get(c.narrative_zone, 999),   # zone priority (title_card/button fall to end)
        -(c.money_shot_score or 0.0),             # score descending (negate for ascending sort)
    ),
)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Chronological sort within act (v1.0) | Zone-first then score-descending (v2.0 Phase 8) | Phase 8 | Core narrative claim: trailer is not a highlight reel — it has a dramatic arc independent of film order |
| Act labels (cold_open/act1/act2/act3) as ordering key | NarrativeZone (BEGINNING/ESCALATION/CLIMAX) as ordering key | Phase 8 | Three zones vs six acts — simpler, more reliable at small clip counts (20-35 clips) |
| `sort_clips_by_act()` with `source_start_s` tiebreak | `sort_clips_by_zone()` with `money_shot_score` tiebreak | Phase 8 | Score-descending within zones ensures best clips appear first in each zone |
| `enforce_pacing_curve()` targeting `act3` label | `enforce_zone_pacing_curve()` targeting `NarrativeZone.CLIMAX` | Phase 8 | CLIMAX zone clips trimmed to act3 targets regardless of their original act label |

**Backward compatibility:** The `act` field on `ClipEntry` is preserved for conform pipeline use (transition selection, etc.). The `narrative_zone` field is ADDITIVE — it controls ordering, while `act` continues to control visual treatment (LUT, transition type). Both fields coexist.

---

## Open Questions

1. **Conflict between `act` label and `narrative_zone`**
   - What we know: `act` is used by `get_transition()` in `generator.py` and `enforce_pacing_curve()` in `ordering.py`. `narrative_zone` will be used only for ordering and pacing.
   - What's unclear: If a clip is classified as `act3` (by chron position) but gets zone=BEGINNING (because its dialogue is introductory), do we apply act3 clip duration or BEGINNING clip duration?
   - Recommendation: `narrative_zone` controls ordering and pacing duration targets (EORD-03). `act` label controls visual treatment (transition type, LUT). Do NOT conflate them. BEGINNING zone clips get `act1_avg_cut_s` targets; CLIMAX clips get `act3_avg_cut_s` targets — regardless of their `act` label.

2. **Where zone matching should be invoked in the current pipeline**
   - What we know: Phase 7 will add Stage 5 (structural) and renumber stages to 8 total. `run_narrative_stage()` becomes Stage 6. Zone matching outputs `narrative_zone` fields that go into the manifest.
   - What's unclear: Phase 7 has not been executed yet (STATE.md shows Phase 7 is next). Phase 8 plans must be written assuming Phase 7 will complete as designed.
   - Recommendation: Phase 8 plans should reference the Phase 7 artifact contracts as documented in 07-01-PLAN.md and 07-02-PLAN.md. Specifically: `structural_anchors` parameter on `run_narrative_stage()` (07-02 adds this); Stage 6 numbering (07-02 renumbers); `TOTAL_STAGES=8` (07-02 sets this). Phase 8 will bump `TOTAL_STAGES` to 8 only if Phase 7 left it at 7 — but Phase 7 sets it to 8 already. No TOTAL_STAGES change needed in Phase 8.

3. **Whether to pre-cache zone anchor embeddings at module import**
   - What we know: The three ZONE_ANCHORS phrases are static and never change. Encoding them takes ~3ms on CPU. They could be pre-computed at module import or at first call.
   - What's unclear: Whether module-level pre-computation would slow import time noticeably (it includes model loading: ~200ms).
   - Recommendation: Use lazy loading via `_load_model()` singleton. Encode zone anchors inside `run_zone_matching()` on first call (they are tiny to re-encode). Pre-caching adds complexity for 3ms savings — not worth it.

4. **Handling clips that have no dialogue_excerpt after Phase 7 generator.py changes**
   - What we know: `get_dialogue_excerpt()` returns `""` when no subtitle event is within 5s of the keyframe timestamp. Silent action shots frequently have no dialogue.
   - What's unclear: What fraction of selected clips will have empty dialogue. In action vibes, potentially 40-60% of clips.
   - Recommendation: The `_zone_by_position()` fallback (using `structural_anchors` timestamps) is the correct handling. Research confirms this is robust — clips near `climax_t` in the film are genuinely more likely to be CLIMAX-zone even without dialogue.

---

## Validation Architecture

> nyquist_validation is not set in .planning/config.json (no `workflow.nyquist_validation` key) — using existing pytest infrastructure.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 (already installed) |
| Config file | none (pytest discovers tests/ automatically) |
| Quick run command | `cd /home/adamh/ai-video-trailer && pytest tests/test_zone_matching.py -x -q` |
| Full suite command | `cd /home/adamh/ai-video-trailer && pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STRC-02 | Zone assigned to each clip (BEGINNING/ESCALATION/CLIMAX) | unit | `pytest tests/test_zone_matching.py -x -q` | Wave 0 |
| STRC-02 | Empty dialogue falls back to position assignment | unit | `pytest tests/test_zone_matching.py::test_empty_dialogue_uses_position_fallback -x` | Wave 0 |
| STRC-02 | Semantic text correctly assigned (climax-like text → CLIMAX) | unit | `pytest tests/test_zone_matching.py::test_semantic_assignment_climax -x` | Wave 0 |
| EORD-01 | Zone-first sort: BEGINNING before ESCALATION before CLIMAX | unit | `pytest tests/test_assembly.py::TestSortClipsByZone -x -q` | Wave 0 |
| EORD-02 | Within zone, highest score appears first | unit | `pytest tests/test_assembly.py::TestSortClipsByZone::test_within_zone_score_descending -x` | Wave 0 |
| EORD-03 | CLIMAX clips trimmed to act3_avg_cut_s targets | unit | `pytest tests/test_assembly.py::TestEnforceZonePacingCurve -x -q` | Wave 0 |

### Sampling Rate

- **Per task commit:** `cd /home/adamh/ai-video-trailer && pytest tests/test_zone_matching.py tests/test_assembly.py -x -q`
- **Per wave merge:** `cd /home/adamh/ai-video-trailer && pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_zone_matching.py` — covers STRC-02 zone assignment, fallback behavior, batch assignment
- [ ] Add `TestSortClipsByZone` and `TestEnforceZonePacingCurve` classes to `tests/test_assembly.py` — covers EORD-01, EORD-02, EORD-03
- [ ] No framework install needed — pytest already present

*(Existing `test_assembly.py` covers `sort_clips_by_act` and `enforce_pacing_curve` — new zone-based equivalents must be added without removing existing tests.)*

---

## Sources

### Primary (HIGH confidence)

- Project source: `src/cinecut/assembly/ordering.py` — existing sort and pacing logic; directly extended in Phase 8
- Project source: `src/cinecut/manifest/schema.py` — existing `ClipEntry` and `TrailerManifest`; `NarrativeZone` added here
- Project source: `src/cinecut/narrative/generator.py` — `run_narrative_stage()` signature and clip construction loop; zone matching wired here
- Project source: `.planning/phases/07-structural-analysis/07-02-PLAN.md` — `run_narrative_stage(structural_anchors=...)` kwarg contract; Stage 6 numbering; `TOTAL_STAGES=8` — Phase 8 depends on these
- `.planning/REQUIREMENTS.md` — STRC-02, EORD-01, EORD-02, EORD-03 verbatim specifications
- `.planning/STATE.md` — CPU PyTorch install order constraint documented as project decision
- sentence-transformers official docs (https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html) — verified encode/cos_sim patterns
- sentence-transformers SentenceTransformer API (https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) — `device` parameter, `convert_to_numpy` default, `normalize_embeddings` param
- HuggingFace model card (https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) — 22.7M params, 384 dimensions, CPU supported, 256 token max input

### Secondary (MEDIUM confidence)

- sentence-transformers PyPI installation docs (https://pypi.org/project/sentence-transformers/) — Python 3.10+, torch 1.11+ requirement; install order for CPU
- Multiple community sources confirming CPU-first install prevents CUDA wheel selection conflict

### Tertiary (LOW confidence)

- Inference time estimate "<1 second per clip, ~50ms batch for 100 clips" — derived from model size (22.7M) and typical CPU benchmarks; not verified against K6000 CPU specifically

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — sentence-transformers API verified against official docs; model card confirms 384-dim output and CPU support; install order from STATE.md decision
- Architecture: HIGH — zone_matching.py design derived directly from existing project patterns (generator.py scoring loop, ordering.py sort functions); Pydantic enum pattern verified in project
- Pitfalls: HIGH — CUDA torch conflict is a known documented issue (STATE.md cites it); empty string edge case is a logical necessity; lru_cache model singleton is standard Python; tensor vs numpy is verified API behavior
- Validation: HIGH — existing pytest infrastructure; test file gaps clearly identified

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (sentence-transformers API is stable; all-MiniLM-L6-v2 model is unchanged; project patterns are internal)
