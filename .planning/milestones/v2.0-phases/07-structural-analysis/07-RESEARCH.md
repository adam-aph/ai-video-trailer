# Phase 7: Structural Analysis - Research

**Researched:** 2026-02-28
**Domain:** llama-server text inference, Mistral 7B GGUF, subtitle chunking, manifest schema evolution, VRAM lifecycle management
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| IINF-03 | System resolves all model files (LLaVA GGUF, mmproj, text GGUF) from `~/models` by default; directory overridable via `CINECUT_MODELS_DIR` environment variable | `os.environ.get("CINECUT_MODELS_DIR", str(Path.home() / "models"))` pattern; Path construction documented below |
| IINF-04 | Pipeline uses heuristic zone fallback (5% / 45% / 80% of runtime) when the text model GGUF file is not present in the models directory | `Path.exists()` check before TextEngine startup; heuristic: `BEGIN_T = duration * 0.05`, `ESCALATION_T = duration * 0.45`, `CLIMAX_T = duration * 0.80`; video duration from ffprobe |
| STRC-01 | Text LLM identifies three narrative anchor timestamps (BEGIN_T, ESCALATION_T, CLIMAX_T) from subtitle corpus, processing in chunks of 50-100 events | Subtitle chunking: `list[DialogueEvent]` sliced into chunks of 50-100; prompt pattern documented below; StructuralAnchors dataclass |
| STRC-03 | Zone assignments are stored in TRAILER_MANIFEST.json v2.0 schema alongside existing clip fields | `TrailerManifest.schema_version = "2.0"` + new `structural_anchors: StructuralAnchors` field; Pydantic model extension documented below |
</phase_requirements>

---

## Summary

Phase 7 adds two new modules: `inference/text_engine.py` (TextEngine context manager) and `inference/structural.py` (subtitle chunking, LLM prompt, anchor extraction, heuristic fallback). TextEngine mirrors LlavaEngine exactly — it starts `llama-server` on port 8090 with no `--mmproj` flag, acquires `GPU_LOCK`, polls VRAM before startup, and releases the lock on exit. LlavaEngine (port 8089) and TextEngine (port 8090) must never run concurrently because both consume the Quadro K6000's 12 GB VRAM; the sequential `GPU_LOCK` pattern established in Phase 3 already enforces this.

The structural analysis function (`run_structural_analysis()`) receives the full `list[DialogueEvent]` from Stage 2, chunks it into windows of 50–100 events, submits each chunk to the `/v1/chat/completions` endpoint using the same `json_schema` constrained-generation pattern already proven in LlavaEngine, then collects candidate timestamps and picks the single best BEGIN/ESCALATION/CLIMAX anchor from all chunks. If the Mistral GGUF is absent from the models directory, a heuristic fallback returns `StructuralAnchors(begin_t=duration*0.05, escalation_t=duration*0.45, climax_t=duration*0.80)` and logs a Rich warning — no abort.

The manifest schema bumps from `"1.0"` to `"2.0"` by adding a `structural_anchors: Optional[StructuralAnchors]` field to `TrailerManifest`. The existing Pydantic model in `manifest/schema.py` is backward-compatible: old manifests still load (field defaults to `None`), new manifests carry the anchors block. Stage 5 in `cli.py` becomes Stage 6 of 8 (two new stages inserted: structural analysis as Stage 5 and a new TOTAL_STAGES=8). `CINECUT_MODELS_DIR` is resolved at module import time using `os.environ.get()` and `pathlib.Path.expanduser()`.

**Primary recommendation:** Implement TextEngine as a strict copy of LlavaEngine with three changes: port 8090, drop `--mmproj` flag, set `-c 8192` (Mistral 7B v0.3 context window). Use `/v1/chat/completions` with `json_schema` for anchor extraction, identical to LlavaEngine's `describe_frame()` pattern.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| llama-server | system binary (existing) | HTTP inference for Mistral 7B GGUF | Already used for LLaVA; text-only mode = omit `--mmproj` |
| requests | >=2.31.0 (already installed) | HTTP client for llama-server API | Already used in LlavaEngine; no new dep |
| pydantic | >=2.12.0 (already installed) | StructuralAnchors model validation; manifest schema extension | Already used in manifest/schema.py |
| pathlib.Path | stdlib | Model path construction from CINECUT_MODELS_DIR | Project-wide convention |
| os.environ | stdlib | `CINECUT_MODELS_DIR` environment variable resolution | Standard Python env var pattern |
| subprocess + json | stdlib (existing) | ffprobe duration query for heuristic fallback | Already used in ingestion modules |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Rich console | 13.x (already installed) | Fallback warning message, stage progress | Used throughout cli.py |
| pytest | 9.0.2 (already installed) | Unit tests for structural.py and text_engine.py | All existing modules tested with pytest |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| llama-server HTTP | llama-cpp-python Python binding | llama-cpp-python would be simpler to install but is blocked by CUDA 11.4 / PyTorch incompatibility documented in STATE.md; llama-server already proven in project |
| llama-server HTTP | Ollama | Explicitly excluded in STATE.md ("llama-server ONLY, no Ollama") |
| json_schema constraint | grammar (BNF) | json_schema is already proven in LlavaEngine; grammar adds complexity with no benefit for this use case |
| Single large prompt | Chunked 50-100 events | Single prompt for 2000+ subtitle events exceeds Mistral 7B's context window (~8K tokens); chunking is the only viable approach |

**No new pip packages required.** All dependencies are already in pyproject.toml.

---

## Architecture Patterns

### Recommended Project Structure

```
src/cinecut/
├── inference/
│   ├── __init__.py         # (existing) — export TextEngine from here
│   ├── engine.py           # (existing) LlavaEngine
│   ├── models.py           # (existing) SceneDescription
│   ├── cache.py            # (existing, Phase 6) msgpack cache
│   ├── vram.py             # (existing) VRAM check
│   ├── text_engine.py      # NEW (07-01): TextEngine context manager
│   └── structural.py       # NEW (07-02): run_structural_analysis(), StructuralAnchors
├── manifest/
│   ├── schema.py           # MODIFY (07-02): add StructuralAnchors, bump schema_version="2.0"
│   └── ...
└── cli.py                  # MODIFY (07-02): add Stage 5 structural analysis, TOTAL_STAGES=8
```

### Pattern 1: TextEngine Context Manager (mirrors LlavaEngine exactly)

**What:** Context manager that starts `llama-server` on port 8090 without `--mmproj`, acquires `GPU_LOCK`, polls VRAM, terminates server on exit.
**When to use:** Stage 5 in cli.py, wrapping the structural analysis call.

```python
# Source: project src/cinecut/inference/engine.py (LlavaEngine pattern — adapt for text-only)

class TextEngine:
    """Context manager that starts llama-server for Mistral 7B text inference on port 8090.

    Holds GPU_LOCK for its entire lifetime — LlavaEngine and TextEngine never run concurrently.
    Port 8090 (TextEngine) vs port 8089 (LlavaEngine) — never overlap.
    """

    def __init__(
        self,
        model_path: Path,
        port: int = 8090,
        debug: bool = False,
    ) -> None:
        self.model_path = model_path
        self.port = port
        self.debug = debug
        self.base_url = f"http://127.0.0.1:{port}"
        self._process: subprocess.Popen | None = None
        self._log_file = None

    def __enter__(self) -> "TextEngine":
        from cinecut.inference import GPU_LOCK
        assert_vram_available()
        GPU_LOCK.acquire()
        try:
            self._start()
        except Exception:
            GPU_LOCK.release()
            raise
        return self

    def __exit__(self, *_: object) -> None:
        from cinecut.inference import GPU_LOCK
        try:
            self._stop()
        finally:
            GPU_LOCK.release()

    def _start(self) -> None:
        cmd = [
            "llama-server",
            "-m", str(self.model_path),
            "--port", str(self.port),
            "--host", "127.0.0.1",
            "-ngl", "99",           # offload all layers to GPU
            "-c", "8192",           # Mistral 7B v0.3 context window
            "-np", "1",             # single parallel slot
            "--log-disable",
        ]
        # NO --mmproj flag — text-only model
        # CRITICAL: never use subprocess.PIPE (deadlock risk — same as LlavaEngine)
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._wait_for_health(timeout_s=120)
```

**Key difference from LlavaEngine:** No `--mmproj` argument in the command. Everything else is identical.

### Pattern 2: CINECUT_MODELS_DIR Resolution

**What:** Resolve the models directory from environment variable at module level; used by both TextEngine startup and GGUF-existence check.
**When to use:** In `inference/text_engine.py` module scope or in a `get_models_dir()` helper.

```python
# Source: Python stdlib os.environ + pathlib (verified against Python 3 docs)
import os
from pathlib import Path


def get_models_dir() -> Path:
    """Return the models directory, respecting CINECUT_MODELS_DIR env var.

    Default: ~/models
    Override: CINECUT_MODELS_DIR=/custom/path
    """
    env_val = os.environ.get("CINECUT_MODELS_DIR")
    if env_val:
        return Path(env_val).expanduser().resolve()
    return Path.home() / "models"
```

**Critical:** Call `Path(env_val).expanduser().resolve()` — `expanduser()` handles `~` in the env value; `resolve()` makes it absolute. Do NOT use `os.path.expandvars()` — the env var IS the path, not a value containing `$VAR` syntax.

### Pattern 3: Mistral GGUF Existence Check (IINF-04 fallback trigger)

**What:** Before starting TextEngine, check if the GGUF file exists. If absent, skip TextEngine entirely and return heuristic anchors.
**When to use:** At Stage 5 in `cli.py` before `with TextEngine(...)`.

```python
# Source: project pattern from cli.py Stage 4 cache guard
from cinecut.inference.structural import run_structural_analysis, compute_heuristic_anchors

models_dir = get_models_dir()
text_model_path = models_dir / "mistral-7b-instruct-v0.3.Q4_K_M.gguf"

if not text_model_path.exists():
    console.print(
        f"[yellow]Heuristic fallback:[/] Mistral GGUF not found at "
        f"[dim]{text_model_path}[/dim] — using 5%/45%/80% zone anchors\n"
    )
    structural_anchors = compute_heuristic_anchors(video_duration_s)
else:
    with TextEngine(text_model_path) as engine:
        structural_anchors = run_structural_analysis(dialogue_events, engine)
```

### Pattern 4: Subtitle Chunking for LLM Context

**What:** Slice `list[DialogueEvent]` into windows of 50–100 events; format each chunk as a plain text transcript; submit each chunk to Mistral asking for the narrative anchor in that chunk.
**When to use:** In `inference/structural.py`, `run_structural_analysis()`.

```python
# Source: project pattern (dialogueevent model from src/cinecut/models.py)
# Chunk size: 75 events (midpoint of 50-100 requirement range)
CHUNK_SIZE = 75

def _format_subtitle_chunk(events: list[DialogueEvent]) -> str:
    """Format subtitle events as timestamped transcript for LLM prompt."""
    lines = []
    for ev in events:
        lines.append(f"[{ev.start_s:.1f}s] {ev.text}")
    return "\n".join(lines)

def _chunk_events(events: list[DialogueEvent]) -> list[list[DialogueEvent]]:
    """Slice event list into chunks of CHUNK_SIZE."""
    return [events[i:i + CHUNK_SIZE] for i in range(0, len(events), CHUNK_SIZE)]
```

**Token budget:** At ~20 tokens per subtitle line (timestamp + dialogue), 75 events = ~1500 tokens + system prompt + response = ~2000 tokens total. Well within Mistral's 8K context.

### Pattern 5: StructuralAnchors JSON Schema and Pydantic Model

**What:** Define both the JSON schema (for llama-server constrained generation) and the Pydantic model (for manifest storage).
**When to use:** In `manifest/schema.py` for the manifest model; in `inference/structural.py` for the JSON schema constant.

```python
# In manifest/schema.py — add StructuralAnchors Pydantic model:
from typing import Optional
from pydantic import BaseModel, Field

class StructuralAnchors(BaseModel):
    begin_t: float = Field(ge=0.0, description="BEGIN narrative anchor timestamp (seconds)")
    escalation_t: float = Field(ge=0.0, description="ESCALATION narrative anchor timestamp (seconds)")
    climax_t: float = Field(ge=0.0, description="CLIMAX narrative anchor timestamp (seconds)")
    source: str = "llm"  # "llm" | "heuristic"

# In TrailerManifest — bump schema_version and add structural_anchors:
class TrailerManifest(BaseModel):
    schema_version: str = "2.0"          # bumped from "1.0"
    source_file: str
    vibe: str
    clips: list[ClipEntry] = Field(min_length=1)
    structural_anchors: Optional[StructuralAnchors] = None   # None on v1.0 manifests
```

```python
# In inference/structural.py — JSON schema for llama-server constrained generation:
STRUCTURAL_ANCHORS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "begin_t": {"type": "number", "description": "timestamp in seconds where narrative begins"},
        "escalation_t": {"type": "number", "description": "timestamp in seconds of escalation"},
        "climax_t": {"type": "number", "description": "timestamp in seconds of climax"},
    },
    "required": ["begin_t", "escalation_t", "climax_t"],
    "additionalProperties": False,
}
```

### Pattern 6: Mistral Chat Completion with json_schema

**What:** POST to `/v1/chat/completions` with the Mistral `[INST]...[/INST]` instruction format and `json_schema` parameter for constrained output. This is the same endpoint and parameter as LlavaEngine's `describe_frame()` — just without the image content.
**When to use:** In `TextEngine.analyze_chunk()`.

```python
# Source: project src/cinecut/inference/engine.py (describe_frame pattern)
# Source: llama-server README (https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

def analyze_chunk(self, chunk_text: str, timeout_s: float = 60.0) -> dict | None:
    """Submit one subtitle chunk for structural anchor extraction.

    Returns dict with begin_t, escalation_t, climax_t or None on failure.
    """
    from cinecut.inference.structural import STRUCTURAL_ANCHORS_SCHEMA

    payload = {
        "temperature": 0.1,
        "max_tokens": 128,
        "json_schema": STRUCTURAL_ANCHORS_SCHEMA,
        "messages": [{
            "role": "user",
            "content": (
                "You are a film narrative analyst. Given the subtitle transcript below, "
                "identify the three narrative anchor timestamps (in seconds):\n"
                "- begin_t: when the story truly begins (inciting incident or first conflict)\n"
                "- escalation_t: when tension escalates significantly\n"
                "- climax_t: when the climax or peak emotional moment occurs\n\n"
                "Respond with a JSON object only.\n\n"
                f"TRANSCRIPT:\n{chunk_text}"
            ),
        }],
    }
    try:
        r = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=timeout_s,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return json.loads(content.strip())
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError):
        return None   # chunk failed — skip, never propagate
```

**Note:** The `[INST]` prompt tokens are applied automatically by llama-server when it detects the model's chat template from the GGUF metadata. You do NOT need to manually add `[INST]` markers when using `/v1/chat/completions`.

### Pattern 7: Heuristic Fallback

**What:** When Mistral GGUF is absent, return anchors based on fixed percentages of video runtime.
**When to use:** In `inference/structural.py`, called from cli.py when model file not found.

```python
# Source: REQUIREMENTS.md IINF-04 specification
from cinecut.manifest.schema import StructuralAnchors

def compute_heuristic_anchors(duration_s: float) -> StructuralAnchors:
    """Return 5%/45%/80% heuristic anchors when Mistral GGUF is unavailable."""
    return StructuralAnchors(
        begin_t=round(duration_s * 0.05, 2),
        escalation_t=round(duration_s * 0.45, 2),
        climax_t=round(duration_s * 0.80, 2),
        source="heuristic",
    )
```

**Duration source:** Use `ffprobe` to get video duration. The proxy creation step already runs ffprobe — the proxy duration is available as a float. Pass it from `cli.py` to `compute_heuristic_anchors()`. Do not re-run ffprobe in `structural.py`.

### Pattern 8: Multi-Chunk Anchor Aggregation

**What:** Multiple chunks may each return candidate timestamps. The best strategy is: take the chunk-relative timestamps from each chunk, convert to absolute timestamps using chunk start time, then pick the final anchors as the median across all chunks (or the single result if only one chunk). The median is robust against a bad chunk returning garbage values.
**When to use:** In `run_structural_analysis()` after collecting all chunk results.

```python
# Source: project design (no external library — use stdlib statistics.median)
import statistics

def _aggregate_anchors(
    chunk_results: list[dict],
    chunk_start_times: list[float],
) -> tuple[float, float, float]:
    """Aggregate per-chunk anchor candidates into final (begin_t, escalation_t, climax_t).

    chunk_results: list of dicts with begin_t, escalation_t, climax_t (absolute seconds)
    Returns (begin_t, escalation_t, climax_t) as final float values.
    """
    if not chunk_results:
        raise ValueError("No chunk results to aggregate")
    begin_vals = [r["begin_t"] for r in chunk_results]
    esc_vals = [r["escalation_t"] for r in chunk_results]
    climax_vals = [r["climax_t"] for r in chunk_results]
    return (
        statistics.median(begin_vals),
        statistics.median(esc_vals),
        statistics.median(climax_vals),
    )
```

**Alternative (simpler):** For a single chunk (small subtitle file <75 events), just use the result directly. For multi-chunk, using the results from the chunk with the widest timestamp spread is also reasonable. Median is the most robust to outlier chunks.

### Pattern 9: VRAM Polling Between Model Swaps

**What:** After LlavaEngine exits (GPU_LOCK released), TextEngine must wait for VRAM to be fully freed before asserting VRAM available. The existing `check_vram_free_mib()` function in `vram.py` already does this — but we need a polling loop because VRAM is not freed instantaneously after `llama-server` terminates.
**When to use:** TextEngine `__enter__` — poll VRAM before GPU_LOCK acquire.

```python
# Source: project src/cinecut/inference/vram.py + STATE.md decision
import time

def wait_for_vram(min_free_mib: int = 6144, poll_interval_s: float = 2.0, timeout_s: float = 60.0) -> None:
    """Poll nvidia-smi until at least min_free_mib MiB is free.

    Called between LlavaEngine exit and TextEngine entry.
    Raises VramError if VRAM does not free within timeout_s.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            free_mib = check_vram_free_mib_raw()   # non-raising version
            if free_mib >= min_free_mib:
                return
        except Exception:
            pass
        time.sleep(poll_interval_s)
    raise VramError(f"VRAM did not free within {timeout_s}s after model swap")
```

**Why needed:** On the Quadro K6000 (12 GB VRAM), LLaVA Q4 uses ~4 GB and Mistral Q4_K_M uses ~4.37 GB. Together they would require ~8.4 GB — still within 12 GB total, but llama-server does not release VRAM atomically at process exit. The OS must reclaim the pages. A 2–5s polling wait with 2s interval is sufficient in practice (confirmed by GPU memory behavior from llama-server discussion: "3-5 seconds to unload").

### Anti-Patterns to Avoid

- **Run LlavaEngine and TextEngine concurrently:** Both hold `GPU_LOCK` — physically impossible with this design. But do not break this by trying to start TextEngine before LlavaEngine exits.
- **Pass `--mmproj` to TextEngine:** TextEngine is text-only. Adding `--mmproj` would either fail (if the file is not Mistral-compatible) or waste VRAM loading the projector unnecessarily.
- **Use `/completion` endpoint (raw):** Use `/v1/chat/completions` — it applies the model's chat template automatically, which is required for Mistral instruct models to follow instructions correctly.
- **Submit all subtitles in a single prompt:** A feature film has 1000–3000 subtitle events. At ~20 tokens each, that's 20,000–60,000 tokens — far exceeding Mistral 7B's 8K context. Always chunk.
- **Hard-code model file name:** The GGUF file name should be a constant in `text_engine.py` (e.g. `MISTRAL_GGUF_NAME = "mistral-7b-instruct-v0.3.Q4_K_M.gguf"`) so it can be changed without touching CLI code.
- **Raise on chunk failure:** Each chunk call should return `None` on failure; the aggregation function skips `None` results. The pipeline must continue even if some chunks fail.
- **Mutate `schema_version` as a user input:** `schema_version = "2.0"` is a class-level default. The manifest loader must remain backward-compatible — loading a v1.0 manifest should not fail even after the schema bump.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Constrained JSON output from LLM | Custom regex/parser to extract timestamps from free text | `json_schema` parameter in llama-server `/v1/chat/completions` | json_schema is already proven in LlavaEngine; regex on LLM output is fragile |
| HTTP client | urllib3 / http.client directly | `requests` (already installed) | Already used in LlavaEngine; consistent error handling |
| VRAM check | Custom nvidia-smi parsing | Extend existing `vram.py` `check_vram_free_mib()` | Already battle-tested and installed |
| Video duration | Parse mkv headers manually | `ffprobe` subprocess (already used in ingestion) | One subprocess call; ffprobe is always present |
| Timestamp aggregation | Weighted average with model confidence | `statistics.median()` from stdlib | Median is robust to outlier chunks; no new dep |
| Chat template formatting | Manual `[INST]...[/INST]` string wrapping | `/v1/chat/completions` messages API | llama-server applies the model's built-in chat template automatically |

**Key insight:** TextEngine is <100 lines. Everything it needs is already in the project. The only genuinely new logic is `structural.py` — the chunking, prompting, and aggregation functions.

---

## Common Pitfalls

### Pitfall 1: Using /completion Instead of /v1/chat/completions

**What goes wrong:** The `/completion` endpoint accepts a raw `prompt` string without chat template processing. Mistral instruct models require `[INST]...[/INST]` delimiters to follow instructions. Without them, the model treats the text as a document to continue rather than an instruction to obey — producing unstructured prose instead of JSON.

**Why it happens:** LlavaEngine also uses `/v1/chat/completions` (see `engine.py` line 183), but the comment in the code says `# LLaVA uses json_schema constrained generation (NOT response_format)`. A reader might incorrectly infer the endpoint is `/completion`.

**How to avoid:** Always use `/v1/chat/completions` for instruction-following models. The server applies the chat template automatically from the GGUF metadata.

**Warning signs:** LLM returns narrative prose with timestamps buried in sentences instead of a clean JSON object.

### Pitfall 2: VRAM Not Freed Before TextEngine Starts

**What goes wrong:** TextEngine `__enter__` calls `assert_vram_available()` immediately after acquiring `GPU_LOCK`. But `GPU_LOCK` is released the instant LlavaEngine's `__exit__` completes — at that point, llama-server's process has been terminated but the OS has not yet reclaimed the VRAM pages. `nvidia-smi` may still report the old VRAM usage for 2–5 seconds.

**Why it happens:** OS process memory is reclaimed asynchronously. `SIGTERM` → process exit → kernel marks pages for reclaim → actual VRAM freed. This takes 1–5 seconds.

**How to avoid:** In TextEngine `__enter__`, poll VRAM with `wait_for_vram()` (2s interval, 60s timeout) BEFORE calling `assert_vram_available()`. The poll replaces the single-shot check.

**Warning signs:** TextEngine raises `VramError("Only X MiB free VRAM")` when run immediately after LlavaEngine exits, even though total model sizes fit comfortably in 12 GB.

### Pitfall 3: Chunk Timestamps Are Chunk-Relative, Not Film-Absolute

**What goes wrong:** The LLM sees a transcript starting at `[120.5s]`. It returns `begin_t: 132.0`. But if the next chunk starts at `[0s]` (the events were formatted without carrying forward the running timestamp), the LLM returns `begin_t: 12.0` — which is wrong when converted back to film time.

**Why it happens:** The prompt formatter uses `ev.start_s` which is already the absolute film timestamp — this is correct. But if someone normalizes the chunk timestamps to start at 0 to "simplify the LLM's job," the output needs to have the chunk's start time added back.

**How to avoid:** Always format chunks using absolute `ev.start_s` values. Do not normalize to 0. The LLM can handle large timestamp values — they are just numbers.

**Warning signs:** Structural anchors cluster suspiciously close to 0, 45%, and 80% of the chunk duration rather than the film duration.

### Pitfall 4: schema_version "2.0" Breaks Existing Manifest Loading

**What goes wrong:** After bumping `schema_version = "2.0"` as the Pydantic default, `load_manifest()` on a v1.0 manifest (which has `"schema_version": "1.0"`) fails if the loader validates the version field as a `Literal["2.0"]`.

**Why it happens:** Overly strict schema version validation.

**How to avoid:** Do NOT use `Literal["2.0"]` for `schema_version`. Keep it as `str` with default `"2.0"`. The manifest loader loads whatever version is in the file. Optionally add a `@field_validator` that emits a warning (not error) for v1.0 manifests.

**Warning signs:** `ValidationError: schema_version: value is not a valid enumeration member` when loading existing manifests.

### Pitfall 5: GGUF File Not Found — Pipeline Aborts Instead of Using Fallback

**What goes wrong:** If the Mistral GGUF check is done inside `TextEngine.__enter__()` rather than before the `with` statement, a missing file raises `InferenceError` and the pipeline aborts.

**Why it happens:** The check and the engine startup are conflated.

**How to avoid:** Check `text_model_path.exists()` in `cli.py` BEFORE the `with TextEngine(...)` block. If absent, call `compute_heuristic_anchors()` and skip the TextEngine entirely. The `with TextEngine(...)` block is only entered when the GGUF is confirmed present.

**Warning signs:** Pipeline raises `InferenceError` or `FileNotFoundError` instead of logging a yellow fallback warning and continuing.

### Pitfall 6: Hard-Coded Model Path Ignores CINECUT_MODELS_DIR

**What goes wrong:** `cli.py` currently has `_DEFAULT_MODEL_PATH = "/home/adamh/models/ggml-model-q4_k.gguf"`. If the same hard-coding pattern is repeated for the Mistral model, `CINECUT_MODELS_DIR` will be ignored — breaking IINF-03.

**Why it happens:** Phase 7 is the first phase to introduce the `CINECUT_MODELS_DIR` convention, so no existing code uses it. It's easy to copy the v1 `_DEFAULT_MODEL_PATH` pattern.

**How to avoid:** The `get_models_dir()` function must be called at runtime (inside `main()`), not at module import time. Then all three model paths (LLaVA GGUF, mmproj, Mistral GGUF) must use `get_models_dir() / <filename>`.

**Warning signs:** Setting `CINECUT_MODELS_DIR=/custom/path` has no effect on model loading.

---

## Code Examples

Verified patterns from project source and official docs:

### TextEngine startup command (no --mmproj)

```python
# Source: project src/cinecut/inference/engine.py LlavaEngine._start() — adapted
cmd = [
    "llama-server",
    "-m", str(self.model_path),
    "--port", str(self.port),       # 8090
    "--host", "127.0.0.1",
    "-ngl", "99",
    "-c", "8192",                   # Mistral 7B v0.3 context
    "-np", "1",
    "--log-disable",
    # NO --mmproj — text-only
]
self._process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
self._wait_for_health(timeout_s=120)
```

### Health check polling (identical to LlavaEngine)

```python
# Source: project src/cinecut/inference/engine.py _wait_for_health()
deadline = time.monotonic() + timeout_s
while time.monotonic() < deadline:
    if self._process.poll() is not None:
        raise InferenceError("llama-server exited during startup")
    try:
        r = requests.get(f"{self.base_url}/health", timeout=2)
        if r.status_code == 200 and r.json().get("status") == "ok":
            return
    except requests.RequestException:
        pass
    time.sleep(1.0)
raise InferenceError(f"llama-server did not become healthy within {timeout_s}s")
```

### CINECUT_MODELS_DIR resolution

```python
# Source: Python 3 stdlib os.environ + pathlib
import os
from pathlib import Path

def get_models_dir() -> Path:
    env_val = os.environ.get("CINECUT_MODELS_DIR")
    if env_val:
        return Path(env_val).expanduser().resolve()
    return Path.home() / "models"

# All model paths derive from this:
models_dir = get_models_dir()
llava_gguf = models_dir / "ggml-model-q4_k.gguf"
mmproj_gguf = models_dir / "mmproj-model-f16.gguf"
mistral_gguf = models_dir / "mistral-7b-instruct-v0.3.Q4_K_M.gguf"
```

### run_structural_analysis top-level function

```python
# Source: project design derived from run_inference_stage() pattern in engine.py
from cinecut.manifest.schema import StructuralAnchors

def run_structural_analysis(
    dialogue_events: list,   # list[DialogueEvent]
    engine: "TextEngine",
) -> StructuralAnchors:
    """Run structural analysis on subtitle corpus.

    Chunks events into windows of CHUNK_SIZE, submits each to TextEngine,
    aggregates results. Falls back to heuristic if all chunks fail.
    """
    chunks = _chunk_events(dialogue_events)
    results = []
    for i, chunk in enumerate(chunks):
        chunk_text = _format_subtitle_chunk(chunk)
        result = engine.analyze_chunk(chunk_text)
        if result is not None:
            results.append(result)

    if not results:
        # All chunks failed — use first/last event timestamps as minimal heuristic
        first_t = dialogue_events[0].start_s if dialogue_events else 0.0
        last_t = dialogue_events[-1].end_s if dialogue_events else 0.0
        duration = last_t - first_t
        return StructuralAnchors(
            begin_t=round(first_t + duration * 0.05, 2),
            escalation_t=round(first_t + duration * 0.45, 2),
            climax_t=round(first_t + duration * 0.80, 2),
            source="heuristic",
        )

    import statistics
    return StructuralAnchors(
        begin_t=round(statistics.median([r["begin_t"] for r in results]), 2),
        escalation_t=round(statistics.median([r["escalation_t"] for r in results]), 2),
        climax_t=round(statistics.median([r["climax_t"] for r in results]), 2),
        source="llm",
    )
```

### Manifest schema v2.0 (backward-compatible extension)

```python
# Source: project src/cinecut/manifest/schema.py (existing TrailerManifest)
# MODIFY: add StructuralAnchors, bump schema_version default

class StructuralAnchors(BaseModel):
    begin_t: float = Field(ge=0.0)
    escalation_t: float = Field(ge=0.0)
    climax_t: float = Field(ge=0.0)
    source: str = "llm"   # "llm" | "heuristic"

class TrailerManifest(BaseModel):
    schema_version: str = "2.0"          # was "1.0"
    source_file: str
    vibe: str
    clips: list[ClipEntry] = Field(min_length=1)
    structural_anchors: Optional[StructuralAnchors] = None  # NEW — None on v1.0 manifests
```

### CLI Stage 5 insertion (new stage between narrative beat and assembly)

```python
# Source: project src/cinecut/cli.py Stage 4 cache guard pattern
TOTAL_STAGES = 8   # was 7; new Stage 5 = structural analysis

# After Stage 4 (LLaVA inference), before Stage 5 (was narrative):
# --- Stage 5/8: Structural Analysis (IINF-03, IINF-04, STRC-01, STRC-03) ---
if not ckpt.is_stage_complete("structural"):
    console.print(f"[bold]Stage 5/{TOTAL_STAGES}:[/bold] Structural analysis...")
    models_dir = get_models_dir()
    mistral_path = models_dir / MISTRAL_GGUF_NAME
    if not mistral_path.exists():
        console.print(
            f"[yellow]Heuristic fallback:[/] Mistral GGUF absent — "
            f"using 5%/45%/80% anchors\n"
        )
        structural_anchors = compute_heuristic_anchors(proxy_duration_s)
    else:
        with TextEngine(mistral_path) as text_engine:
            structural_anchors = run_structural_analysis(dialogue_events, text_engine)
    ckpt.structural_anchors = structural_anchors.model_dump()
    ckpt.mark_stage_complete("structural")
    save_checkpoint(ckpt, work_dir)
    console.print(
        f"[green]Structural anchors:[/] BEGIN={structural_anchors.begin_t}s "
        f"ESCALATION={structural_anchors.escalation_t}s "
        f"CLIMAX={structural_anchors.climax_t}s "
        f"([dim]source={structural_anchors.source}[/dim])\n"
    )
else:
    # Reconstruct from checkpoint
    structural_anchors = StructuralAnchors(**ckpt.structural_anchors)
    console.print(f"[yellow]Resuming:[/] Stage 5 already complete\n")
```

**Note:** `PipelineCheckpoint` needs a new `structural_anchors: Optional[dict] = None` field — same pattern as `cache_hit: Optional[bool] = None` added in Phase 6.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `response_format: {type: json_schema}` in OpenAI API | `json_schema` direct parameter in llama-server | Always llama-server specific | Use `json_schema` key directly in llama-server payload, not `response_format` wrapper |
| Grammar (BNF) for constrained output | `json_schema` for constrained output | llama-server ~b3000+ | `json_schema` is simpler; grammar is for complex CFGs |
| Hard-coded model paths in CLI | `CINECUT_MODELS_DIR` env var | Phase 7 (this phase) | All model paths now resolve from configurable directory |
| `schema_version: "1.0"` | `schema_version: "2.0"` | Phase 7 (this phase) | New `structural_anchors` field added; old manifests still load |

**Note on `response_format` vs `json_schema`:** There is an open bug in llama-server (Issue #11847) where `response_format` in `/v1/chat/completions` conflicts with `json_schema`. The workaround — already used in LlavaEngine — is to pass `json_schema` directly in the request payload rather than inside a `response_format` wrapper. This is the proven approach for this project.

---

## Open Questions

1. **Proxy duration availability in cli.py**
   - What we know: `create_proxy()` returns a `Path`. Duration is not explicitly returned.
   - What's unclear: Whether `cli.py` already has the proxy duration, or whether Stage 5 must run `ffprobe` to get it.
   - Recommendation: Add duration extraction in Stage 1 using `ffprobe` (one-liner subprocess call); store `proxy_duration_s: Optional[float] = None` in `PipelineCheckpoint`. Pass to Stage 5 for heuristic fallback.

2. **Mistral GGUF file name constant — where to define it**
   - What we know: `mistral-7b-instruct-v0.3.Q4_K_M.gguf` is the expected file.
   - What's unclear: Whether to define it in `text_engine.py`, `structural.py`, or `cli.py`.
   - Recommendation: Define `MISTRAL_GGUF_NAME = "mistral-7b-instruct-v0.3.Q4_K_M.gguf"` in `inference/text_engine.py`; import it in `cli.py`.

3. **Multiple chunks returning anchors outside dialogue range**
   - What we know: Mistral can hallucinate timestamps outside the submitted chunk's timestamp range.
   - What's unclear: How often this happens in practice.
   - Recommendation: In `run_structural_analysis()`, clamp each chunk result: `begin_t` must be within the chunk's start/end timestamp range; discard chunk results where anchors are outside that range. This prevents hallucinated timestamps from polluting the median.

4. **LLaVA model path migration to CINECUT_MODELS_DIR**
   - What we know: The existing `_DEFAULT_MODEL_PATH = "/home/adamh/models/ggml-model-q4_k.gguf"` in cli.py is hard-coded. IINF-03 requires all three model files (LLaVA, mmproj, Mistral) to resolve from `CINECUT_MODELS_DIR`.
   - What's unclear: Whether Phase 7 should retroactively update the LLaVA path resolution (it should — IINF-03 says "all model files").
   - Recommendation: Yes — Plan 07-01 (TextEngine) should also update `cli.py` to replace `_DEFAULT_MODEL_PATH` and `_DEFAULT_MMPROJ_PATH` with `get_models_dir() / "ggml-model-q4_k.gguf"` etc. Remove the hardcoded paths.

---

## Sources

### Primary (HIGH confidence)

- Project source: `src/cinecut/inference/engine.py` — LlavaEngine pattern; TextEngine is a direct adaptation
- Project source: `src/cinecut/inference/vram.py` — VRAM check and `nvidia-smi` pattern; extended for polling
- Project source: `src/cinecut/manifest/schema.py` — existing Pydantic schema; v2.0 extension pattern
- Project source: `src/cinecut/checkpoint.py` — PipelineCheckpoint extension pattern (same as Phase 6 `cache_hit` field)
- Project source: `src/cinecut/cli.py` — Stage checkpoint guard pattern; stage numbering
- Project source: `src/cinecut/models.py` — `DialogueEvent` dataclass fields (used in chunking/formatting)
- llama-server README — https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md — `/completion`, `/v1/chat/completions`, `json_schema`, health endpoint, startup flags (verified via WebFetch)
- `.planning/STATE.md` decisions — TextEngine port 8090, VRAM polling requirement, llama-server ONLY constraint
- `.planning/REQUIREMENTS.md` — IINF-03, IINF-04, STRC-01, STRC-03 verbatim requirements

### Secondary (MEDIUM confidence)

- bartowski/Mistral-7B-Instruct-v0.3-GGUF on HuggingFace — Q4_K_M file size 4.37 GB; `<s>[INST]...[/INST]</s>` chat template applied automatically by llama-server (verified via WebFetch)
- llama-server Issue #11847 — `response_format` conflict with `json_schema`; workaround: pass `json_schema` directly (verified via WebSearch; consistent with existing LlavaEngine code)
- VRAM release timing: "3-5 seconds" after llama-server process exits (llama-server GitHub Discussion #12800, multiple corroborating sources)

### Tertiary (LOW confidence)

- Mistral 7B v0.3 context window "8K tokens" — stated in multiple community posts; not verified against official Mistral model card (HF model card did not return this value in WebFetch)
- `statistics.median` as best aggregation strategy for multi-chunk timestamps — design reasoning, not verified against LLM benchmarks

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries are existing project deps; no new packages; TextEngine pattern is a direct copy of LlavaEngine
- Architecture: HIGH — TextEngine structure verified against existing LlavaEngine source; manifest schema extension pattern verified against existing Pydantic models; llama-server API verified against official README
- Pitfalls: HIGH — derived from direct code inspection of LlavaEngine, cli.py stage patterns, and llama-server known issues; VRAM release timing from official GitHub discussions

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (llama-server API is stable; Mistral GGUF format stable; all other patterns are project-internal)
