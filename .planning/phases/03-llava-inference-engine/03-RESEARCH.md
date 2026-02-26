# Phase 3: LLaVA Inference Engine - Research

**Researched:** 2026-02-26
**Domain:** llama-server HTTP API, multimodal vision inference, VRAM management, subprocess lifecycle
**Confidence:** HIGH (primary sources: local llama-server binary, local llama.cpp source at /home/adamh/llama.cpp, official server README)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFR-01 | System integrates with llama-server HTTP mode for persistent LLaVA inference (no model reload per frame) | llama-server binary confirmed at /usr/local/bin/llama-server (version 8156, build 3769fe6eb). Server stays running between requests. `/v1/chat/completions` or `/chat/completions` endpoints accept image input. Startup sequence: `subprocess.Popen` → poll `/health` until `{"status":"ok"}` → send frames sequentially. |
| INFR-02 | System submits extracted keyframes to LLaVA and stores structured scene descriptions (visual content, mood, action, setting) with validated output format | `/chat/completions` with `image_url` content type (base64 data URI). `json_schema` parameter in request body constrains output to a Pydantic-compatible JSON structure. Output stored as `SceneDescription` dataclass per `KeyframeRecord`. |
| INFR-03 | Inference pipeline stays within 12GB VRAM budget (one frame at a time, VRAM verified before each call) | K6000 has 12203 MiB total VRAM confirmed via `nvidia-smi`. LLaVA 1.5-7B Q4 requires ~5-6 GB VRAM. `nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits` gives free VRAM in MiB before each call. Process strictly one frame per request, no batching. |
| PIPE-05 | All GPU operations run strictly sequentially — llama-server inference and FFmpeg GPU operations never run concurrently | llama-server holds the GPU for the model's lifetime. A module-level or process-level lock (threading.Lock or file lock) ensures no FFmpeg GPU call starts while llama-server is running. Architecture: stop llama-server before any FFmpeg GPU ops, or design the pipeline so inference is a discrete stage that runs to completion before FFmpeg conform. |
</phase_requirements>

---

## Summary

The installed llama-server binary (version 8156, `/usr/local/bin/llama-server`) is confirmed working on the Quadro K6000 (CUDA 11.4, compute capability 3.5 / Kepler sm_35). The binary initializes with CUDA and reports the K6000 successfully. Kepler is deprecated from CUDA 12 but CUDA 11.4 still supports sm_35 — this binary is verified to be compiled and running against CUDA 11.4, so Kepler compatibility is confirmed for this specific build.

The llama-server in version 8156 uses the `libmtmd` multimodal library (PR #12898), replacing the older `clip.cpp`/`libllava` stack. It exposes vision capability via the standard OpenAI-compatible `/chat/completions` endpoint with `image_url` content items. Images can be sent as base64 data URIs (`data:image/jpeg;base64,...`) or as `file://` URLs when `--media-path` is configured. The health endpoint (`GET /health`) returns `{"status":"ok"}` on HTTP 200 when the model is ready. JSON-schema-constrained output is supported via the `json_schema` request field (grammar-based sampling), enabling validated structured scene descriptions directly from the model.

No LLaVA GGUF model files are currently downloaded to the system (only `tinyllama-1.1b-v1.0.Q4_K_M.gguf` exists). A model download task is required as the first plan in this phase. LLaVA 1.5-7B Q4_K_M is the recommended choice: pre-quantized GGUFs are available at HuggingFace (`mys/ggml_llava-v1.5-7b`), requires approximately 5-6 GB VRAM leaving headroom in the 12 GB budget, and is confirmed supported by libmtmd in this llama-server version. The mmproj file (vision encoder) must be downloaded alongside the base model.

**Primary recommendation:** Use llama-server version 8156 (already installed) with `mys/ggml_llava-v1.5-7b` Q4_K_M GGUF + mmproj. Manage the server process with `subprocess.Popen`, poll `/health` for readiness, send frames one at a time via `/chat/completions` with base64 image data URIs, and use `json_schema` in the request to constrain output format.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| llama-server | 8156 (3769fe6eb), installed at /usr/local/bin | LLaVA inference HTTP server | Already installed, confirmed working with K6000/CUDA 11.4, supports libmtmd multimodal |
| requests | 2.31.0 (already installed) | HTTP client for llama-server API | Already in environment, sync API fits sequential frame processing |
| subprocess (stdlib) | Python 3.12 stdlib | Launch/manage llama-server process | No external dependency; `Popen` with `PIPE` for stdout/stderr |
| threading.Lock (stdlib) | Python 3.12 stdlib | Enforce sequential GPU access | Zero-dependency serialization primitive |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| base64 (stdlib) | Python 3.12 stdlib | Encode JPEG keyframes as base64 data URIs | Encoding each frame before submitting to llama-server |
| json (stdlib) | Python 3.12 stdlib | Parse structured scene description responses | Parsing llama-server JSON responses |
| dataclasses (stdlib) | Python 3.12 stdlib | SceneDescription model | Consistent with Phase 1 pattern (DialogueEvent, KeyframeRecord use stdlib dataclasses) |
| pydantic | >=2.12.0 (project dep) | Schema validation of inference output | Use pydantic.TypeAdapter to validate parsed SceneDescription JSON before storage |
| nvidia-smi | system (via subprocess) | Query free VRAM before each inference call | Pre-flight VRAM check; `nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| requests (sync) | httpx (async) | httpx not installed; async adds complexity for sequential single-frame processing |
| subprocess.Popen | llama-cpp-python | llama-cpp-python not installed; project explicitly excludes Python-native LLM loading (REQUIREMENTS.md Out of Scope) |
| LLaVA 1.5-7B Q4_K_M | SmolVLM-256M or SmolVLM-500M | SmolVLM models are smaller (256M/500M vs 7B), may fit in less VRAM, but have lower scene description quality; viable fallback if 7B model hits VRAM issues |
| LLaVA 1.5-7B Q4_K_M | LLaVA 1.6 (7B) | LLaVA 1.6 needs 3000+ context tokens per image vs 1.5's ~576 token image embeddings; higher VRAM for context window |

**Installation:**
```bash
# No pip install needed — all dependencies already installed or stdlib.
# Model download (task in Wave 0):
# wget from HuggingFace mys/ggml_llava-v1.5-7b:
# - ggml-model-q4_k.gguf  (base model)
# - mmproj-model-f16.gguf (vision projector)
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/cinecut/
├── inference/           # Phase 3 module (new)
│   ├── __init__.py      # exports: LlavaEngine, SceneDescription, InferenceError
│   ├── engine.py        # LlavaEngine class: server lifecycle + frame submission
│   ├── vram.py          # check_vram_free_mib() via nvidia-smi subprocess
│   └── models.py        # SceneDescription dataclass, validated via Pydantic TypeAdapter
├── ingestion/           # Phase 1 (existing)
├── manifest/            # Phase 2 (existing)
├── conform/             # Phase 2 (existing)
├── cli.py               # Updated in Phase 3 to wire inference stage
├── errors.py            # Add InferenceError, VramError subclasses
└── models.py            # Existing shared models (DialogueEvent, KeyframeRecord)
```

### Pattern 1: LlavaEngine as Context Manager

**What:** `LlavaEngine` wraps `subprocess.Popen` for llama-server. Implements `__enter__`/`__exit__` so the server is always stopped on exit, preventing zombie processes.

**When to use:** Any code that launches llama-server — the context manager guarantees cleanup even on exceptions.

**Example:**
```python
# Source: local llama.cpp server README + project pattern from Phase 1/2

class LlavaEngine:
    def __init__(self, model_path: Path, mmproj_path: Path, port: int = 8089):
        self.model_path = model_path
        self.mmproj_path = mmproj_path
        self.port = port
        self._process: subprocess.Popen | None = None
        self.base_url = f"http://127.0.0.1:{port}"

    def __enter__(self) -> "LlavaEngine":
        self._start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop()

    def _start(self) -> None:
        cmd = [
            "llama-server",
            "-m", str(self.model_path),
            "--mmproj", str(self.mmproj_path),
            "--port", str(self.port),
            "--host", "127.0.0.1",
            "-ngl", "99",              # offload all layers to GPU
            "-c", "2048",              # context size; LLaVA 1.5 needs ~1200 for image+prompt
            "--no-webui",              # no browser UI needed
            "-np", "1",                # single slot; we're sequential
            "--log-disable",           # suppress llama-server console noise
        ]
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._wait_for_health(timeout_s=120)

    def _wait_for_health(self, timeout_s: float) -> None:
        import time
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
        self._process.terminate()
        raise InferenceError(f"llama-server did not become healthy within {timeout_s}s")

    def _stop(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
```

### Pattern 2: Sequential Frame Submission with Timeout

**What:** Submit one frame at a time via `/chat/completions` with a per-request timeout. On timeout or malformed JSON, log a warning and skip the frame — never raise globally.

**When to use:** Main inference loop processing all `KeyframeRecord` objects.

**Example:**
```python
# Source: llama.cpp tools/server/tests/unit/test_vision_api.py (verified pattern)

import base64

SCENE_DESCRIPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "visual_content": {"type": "string"},
        "mood": {"type": "string"},
        "action": {"type": "string"},
        "setting": {"type": "string"},
    },
    "required": ["visual_content", "mood", "action", "setting"],
    "additionalProperties": False,
}

def describe_frame(
    self,
    record: KeyframeRecord,
    timeout_s: float = 60.0,
) -> SceneDescription | None:
    """Submit one frame to LLaVA. Returns None on timeout/error (skip with warning)."""
    img_bytes = Path(record.frame_path).read_bytes()
    b64 = base64.b64encode(img_bytes).decode("ascii")
    data_uri = f"data:image/jpeg;base64,{b64}"

    payload = {
        "temperature": 0.1,
        "max_tokens": 256,
        "json_schema": SCENE_DESCRIPTION_SCHEMA,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Describe this film scene. "
                            "Respond with a JSON object with keys: "
                            "visual_content, mood, action, setting."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    },
                ],
            }
        ],
    }
    try:
        r = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=timeout_s,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return SceneDescription(**json.loads(content))
    except Exception as exc:
        # Log warning; return None so the frame is skipped, not the whole pipeline
        return None
```

### Pattern 3: VRAM Pre-flight Check

**What:** Before calling `_start()`, query `nvidia-smi` for free VRAM. If insufficient, raise `VramError` with a human-readable message.

**When to use:** Before starting llama-server and before each inference call (the server holds VRAM while running, so the check mainly guards the startup phase).

**Example:**
```python
# Source: nvidia-smi confirmed on this machine; K6000 has 12203 MiB total

def check_vram_free_mib() -> int:
    """Return free VRAM in MiB. Raises VramError if nvidia-smi fails."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        return int(result.stdout.strip().splitlines()[0])
    except (subprocess.CalledProcessError, ValueError, IndexError) as exc:
        raise VramError(f"nvidia-smi query failed: {exc}") from exc

VRAM_MINIMUM_MIB = 6144  # 6 GB minimum for LLaVA 1.5-7B Q4 model + context
```

### Pattern 4: GPU Serialization Lock

**What:** A module-level `threading.Lock` (`GPU_LOCK`) held whenever llama-server is running. FFmpeg conform pipeline must acquire the same lock before executing GPU operations.

**When to use:** Phase 5 will need this when the full pipeline runs inference then conform. For Phase 3, the key constraint is that llama-server must be shut down (via `__exit__`) before FFmpeg GPU operations begin.

**Example:**
```python
# In src/cinecut/inference/__init__.py
import threading

GPU_LOCK = threading.Lock()

# Usage in engine:
class LlavaEngine:
    def __enter__(self) -> "LlavaEngine":
        GPU_LOCK.acquire()  # Hold lock for entire inference stage
        self._start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop()
        GPU_LOCK.release()
```

### Anti-Patterns to Avoid

- **Starting llama-server with `-hf` flag:** The `-hf` flag downloads models from HuggingFace at runtime and requires internet access. Use `-m` + `--mmproj` with local files instead.
- **Passing `--parallel N` > 1:** Increases KV cache VRAM usage. Keep `-np 1` for single-slot sequential processing.
- **Using `PIPE` for llama-server stderr:** llama-server writes verbose logs to stderr. If `PIPE` is used without continuous reading, the pipe buffer fills and the server hangs. Use `subprocess.DEVNULL` to discard, or use `--log-file` to redirect to a log file.
- **Bare `requests.post()` without timeout:** llama-server can hang on malformed images or very long prompts. Always set `timeout=` on every request.
- **Parsing response text directly:** llama-server returns `choices[0].message.content` as a string; it may have surrounding whitespace or extra tokens. Use `json.loads(content.strip())` then validate with Pydantic TypeAdapter.
- **Calling `process.terminate()` without `wait()`:** Leaves zombie processes. Always follow terminate with `process.wait(timeout=10)`, then `process.kill()` if it times out.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON-constrained LLM output | Custom prompt engineering + regex parsing | `json_schema` request field in llama-server | Grammar-based sampling guarantees valid JSON structure; regex will fail on edge cases |
| HTTP client for llama-server | Custom socket code | `requests` library (already installed) | Connection pooling, timeout handling, error codes; requests is already in the venv |
| VRAM measurement | Parsing `/proc/driver/nvidia/` | `nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits` | Authoritative, works on K6000/CUDA 11.4 confirmed |
| Process health polling | Custom TCP probe | `GET /health` endpoint (returns 200 + `{"status":"ok"}` when ready) | Official endpoint, documented in llama.cpp server README |
| Zombie process prevention | Custom signal handling | Context manager `__enter__`/`__exit__` with `terminate()` + `wait()` | Straightforward; handles exceptions automatically |

**Key insight:** llama-server's built-in JSON schema constrained generation eliminates the need for output parsing heuristics. The `json_schema` field uses grammar-based sampling to guarantee that the model output can always be parsed as valid JSON matching the schema.

---

## Common Pitfalls

### Pitfall 1: llama-server stderr Pipe Buffer Deadlock

**What goes wrong:** If llama-server is started with `stderr=subprocess.PIPE` and the calling code never reads from that pipe, the server's stderr buffer fills (~64KB on Linux), causing the server process to block waiting to write. The server stops responding to HTTP requests while blocked.

**Why it happens:** OS pipe buffers are finite. llama-server logs heavily to stderr (model loading info, token stats). If nobody reads the pipe, it fills.

**How to avoid:** Use `stderr=subprocess.DEVNULL` to discard server logs, or `stderr=open(log_file, "w")` to write to a file. Never use `stderr=subprocess.PIPE` without a background thread reading it.

**Warning signs:** Server starts, `/health` times out, `process.poll()` returns None (server not crashed).

### Pitfall 2: Port Conflict with Existing llama-server Instance

**What goes wrong:** Default port 8080 is commonly used. If another llama-server or web server is running on 8080, the new server process will exit immediately with a bind error, but `process.poll()` may not show this immediately.

**How to avoid:** Use a non-standard port (e.g., 8089). Check `process.poll()` during the health-polling loop — if the process exits, raise `InferenceError` immediately rather than polling until timeout.

**Warning signs:** Health poll loop exits because `process.poll() is not None` (process exited) rather than reaching the health OK state.

### Pitfall 3: LLaVA Model and mmproj Version Mismatch

**What goes wrong:** Using a base model GGUF from one LLaVA version with an mmproj from a different version causes garbled output or crashes. For example: LLaVA 1.5 base with LLaVA 1.6 mmproj.

**Why it happens:** The mmproj encodes a specific projection architecture tied to the base model's embedding dimension.

**How to avoid:** Download both base model and mmproj from the same HuggingFace repository. For `mys/ggml_llava-v1.5-7b`, both files are in the same repo.

**Warning signs:** llama-server starts without error but produces incoherent scene descriptions or crashes during image encoding.

### Pitfall 4: json_schema and response_format Conflict

**What goes wrong:** Using both `json_schema` (non-OAI field) and `response_format` (OAI field) in the same request triggers a "Either 'json_schema' or 'grammar' can be specified, but not both" error (GitHub issue #11847, Feb 2025).

**How to avoid:** Use only `json_schema` (the non-OAI llama-server native field) in the request body. Do not add `response_format`. The `json_schema` field is confirmed supported by version 8156.

**Warning signs:** HTTP 400 or HTTP 500 response with "grammar" mentioned in the error body.

### Pitfall 5: VRAM Not Released After Server Crash

**What goes wrong:** If llama-server crashes (segfault, OOM, assertion failure) rather than being cleanly terminated, VRAM may not be released immediately. Subsequent nvidia-smi queries may show incorrect free VRAM.

**Why it happens:** CUDA contexts are not always cleaned up synchronously on crash.

**How to avoid:** After detecting a server crash (`process.poll() is not None`), sleep 2-3 seconds before querying VRAM again. Add `nvidia-smi --gpu-reset` is not available on K6000 (consumer feature only), so wait and re-query.

**Warning signs:** VRAM check shows less free memory than expected after server termination.

### Pitfall 6: llama-server Kepler sm_35 / CUDA 11.4 Limitations

**What goes wrong:** Flash Attention (`-fa on`) may not work on sm_35 Kepler GPUs due to CUDA architecture requirements. The server may silently fall back to slower attention or crash.

**Why it happens:** Flash Attention requires compute capability >= 7.5 (Volta+). K6000 is sm_35 (Kepler).

**How to avoid:** Do not pass `-fa on` to llama-server. The default is `-fa auto` which should detect and skip Flash Attention on K6000. Also avoid `--kv-offload` if it causes instability (Kepler has limited unified memory support).

**Warning signs:** Server starts but inference is very slow or crashes after loading the model.

---

## Code Examples

Verified patterns from official sources:

### Health Check Response (from llama.cpp server README)
```python
# Source: /home/adamh/llama.cpp/tools/server/README.md
# GET /health returns:
# HTTP 503: {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}
# HTTP 200: {"status": "ok"}

import requests

def wait_for_server(base_url: str, timeout_s: float = 120) -> None:
    import time
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            r = requests.get(f"{base_url}/health", timeout=2)
            if r.status_code == 200 and r.json().get("status") == "ok":
                return
        except requests.RequestException:
            pass
        time.sleep(1.0)
    raise RuntimeError(f"Server not healthy after {timeout_s}s")
```

### Vision Chat Completion Request (from llama.cpp server test_vision_api.py)
```python
# Source: /home/adamh/llama.cpp/tools/server/tests/unit/test_vision_api.py (lines 76-95)
# Confirmed working format for /chat/completions with image_url

payload = {
    "temperature": 0.0,
    "top_k": 1,
    "messages": [
        {"role": "user", "content": [
            {"type": "text", "text": "What is this:\n"},
            {"type": "image_url", "image_url": {
                "url": "data:image/jpeg;base64,<base64_data>",
            }},
        ]},
    ],
}
r = requests.post("http://127.0.0.1:8089/chat/completions", json=payload, timeout=60)
content = r.json()["choices"][0]["message"]["content"]
```

### JSON Schema Constrained Output
```python
# Source: /home/adamh/llama.cpp/tools/server/README.md (json_schema field documentation)
# The json_schema field uses grammar-based sampling to constrain output format

SCHEMA = {
    "type": "object",
    "properties": {
        "visual_content": {"type": "string"},
        "mood":           {"type": "string"},
        "action":         {"type": "string"},
        "setting":        {"type": "string"},
    },
    "required": ["visual_content", "mood", "action", "setting"],
    "additionalProperties": False,
}

payload = {
    "temperature": 0.1,
    "max_tokens": 256,
    "json_schema": SCHEMA,   # NOT response_format; use json_schema native field
    "messages": [...],       # include text + image_url content as above
}
```

### VRAM Query via nvidia-smi
```python
# Source: nvidia-smi confirmed available on this machine; K6000 confirmed 12203 MiB total
import subprocess

def get_vram_free_mib() -> int:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True, timeout=10,
    )
    return int(result.stdout.strip().splitlines()[0])

# Example on this machine: returns ~12203 when idle
```

### llama-server Launch Command
```python
# Source: /home/adamh/llama.cpp/tools/server/README.md + flags verified via --help
cmd = [
    "llama-server",
    "-m", "/home/adamh/models/ggml-model-q4_k.gguf",
    "--mmproj", "/home/adamh/models/mmproj-model-f16.gguf",
    "--port", "8089",
    "--host", "127.0.0.1",
    "-ngl", "99",          # all layers to GPU
    "-c", "2048",          # context; LLaVA 1.5 uses ~576 + prompt tokens per image
    "--no-webui",          # disable browser UI
    "-np", "1",            # 1 slot for sequential access
    "--log-disable",       # suppress console log spam
]
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| clip.cpp / libllava / llava-cli binary | libmtmd library / llama-mtmd-cli + llama-server | PR #12849, #13012 (late 2024) | LLaVA still supported; mmproj file format unchanged; server HTTP API stable |
| Separate model-specific binaries (qwen2vl-cli, minicpmv-cli) | Unified llama-server + mmproj flag | 2024-2025 | Single binary for all vision models; less operational complexity |
| Old llava-cli (no HTTP server) | llama-server HTTP mode | 2024 | Persistent model load; no reload per frame; enables efficient batch processing |

**Deprecated/outdated:**
- `llava-cli` binary: Still present in the build as `llama-mtmd-cli` but superseded by `llama-server` for HTTP-mode persistent inference. Do not use llama-mtmd-cli for this phase.
- `libllava` (`llava.h`): Scheduled for removal; `libmtmd` replaces it. Version 8156 uses libmtmd.
- Old `/completion` endpoint with `image_data` field: Still supported but the OAI-compatible `/chat/completions` with `image_url` is the preferred approach per docs and tests.

---

## Open Questions

1. **LLaVA 1.5-7B model does not exist on disk yet**
   - What we know: Only `tinyllama-1.1b-v1.0.Q4_K_M.gguf` is present at `/home/adamh/models/`. No LLaVA GGUF exists.
   - What's unclear: Download method preference (wget, huggingface-cli, or llama-server `-hf`). Using `-hf` risks network dependency at runtime — better to download once during setup.
   - Recommendation: Wave 0 task downloads the model files using `wget` or `curl` from HuggingFace direct URLs. Store at `/home/adamh/models/`. Do not use `-hf` in production llama-server launch.

2. **LLaVA 1.5-7B actual VRAM usage on K6000**
   - What we know: Q4_K_M quantized 7B models typically use 5-6 GB VRAM. K6000 has 12,203 MiB. The mmproj (vision encoder) adds ~1 GB.
   - What's unclear: Exact VRAM with context window 2048 on K6000 CUDA 11.4 with this llama-server build.
   - Recommendation: First task in Wave 1 validates actual VRAM usage with a smoke test before building the full inference loop. Set `VRAM_MINIMUM_MIB = 6144` (6 GB) as the guard threshold; adjust based on observation.

3. **`--no-webui` flag availability in build 8156**
   - What we know: `--webui/--no-webui` appears in the README. The `--help` output was checked but `--no-webui` was not explicitly confirmed in the grep output above.
   - What's unclear: Whether this flag silently ignores unknown flags or errors.
   - Recommendation: Verify with `llama-server --no-webui --help` before relying on it. If not present, omit — the web UI does not block inference functionality.

4. **`--log-disable` flag vs file redirect**
   - What we know: `--log-disable` is documented. Using `stderr=subprocess.DEVNULL` drops all server logs.
   - What's unclear: Whether dropped logs make debugging harder during development.
   - Recommendation: In development, redirect to a log file (`stderr=open(work_dir/"llama-server.log", "w")`). In production/tests, use `subprocess.DEVNULL`. Make this configurable via a `debug` flag on `LlavaEngine`.

---

## Validation Architecture

`workflow.nyquist_validation` is not set in `.planning/config.json` (key absent), so this section is included as a best-effort guide aligned with the existing project test pattern.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml (detected by pytest; currently no `[tool.pytest.ini_options]` section) |
| Quick run command | `python3 -m pytest tests/test_inference.py -x -q` |
| Full suite command | `python3 -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFR-01 | llama-server launches and `/health` returns `{"status":"ok"}` | integration | `python3 -m pytest tests/test_inference.py::test_server_health -x` | ❌ Wave 0 |
| INFR-01 | Server does not reload model between frame submissions | integration | `python3 -m pytest tests/test_inference.py::test_no_model_reload -x` | ❌ Wave 0 |
| INFR-02 | `describe_frame()` returns `SceneDescription` with all required fields | unit (mock server) | `python3 -m pytest tests/test_inference.py::test_describe_frame_structure -x` | ❌ Wave 0 |
| INFR-02 | Invalid/malformed LLaVA response returns `None` (not exception) | unit (mock server) | `python3 -m pytest tests/test_inference.py::test_malformed_response_skipped -x` | ❌ Wave 0 |
| INFR-03 | VRAM check raises `VramError` when free VRAM < minimum | unit | `python3 -m pytest tests/test_inference.py::test_vram_check -x` | ❌ Wave 0 |
| PIPE-05 | `GPU_LOCK` is held during inference and released on `__exit__` | unit | `python3 -m pytest tests/test_inference.py::test_gpu_lock -x` | ❌ Wave 0 |

**Note:** Integration tests (INFR-01) require actual llama-server and LLaVA model. Unit tests (INFR-02, INFR-03, PIPE-05) mock the server and nvidia-smi. The unit tests can run in CI; integration tests require the GPU environment.

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_inference.py -x -q`
- **Per wave merge:** `python3 -m pytest tests/ -q`
- **Phase gate:** Full suite (65 existing + new) green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_inference.py` — covers all Phase 3 requirements (INFR-01, INFR-02, INFR-03, PIPE-05)
- [ ] Download LLaVA 1.5-7B GGUF + mmproj to `/home/adamh/models/` (one-time setup, not automated)
- [ ] Add `requests` to pyproject.toml dependencies (it's available in the venv but not declared)

---

## Sources

### Primary (HIGH confidence)
- `/home/adamh/llama.cpp/tools/server/README.md` — Full API endpoint documentation, health check format, multimodal support note, json_schema field, server flags
- `/home/adamh/llama.cpp/tools/server/tests/unit/test_vision_api.py` — Authoritative working request format for `/chat/completions` with `image_url` and base64 data URIs
- `/home/adamh/llama.cpp/docs/multimodal.md` — Confirmed LLaVA 1.5/1.6 support, mmproj requirement, `-m` + `--mmproj` usage pattern
- `/home/adamh/llama.cpp/docs/multimodal/llava.md` — LLaVA 1.5 and 1.6 GGUF download locations, chat template requirement (`vicuna`), context size notes
- `/home/adamh/llama.cpp/tools/mtmd/README.md` — libmtmd history, architecture, mmproj explanation
- `llama-server --help` (version 8156) — Confirmed available flags: `-mm`, `--mmproj`, `-ngl`, `-np`, `--host`, `--port`, `--log-disable`, `-c`, `json_schema` in body
- `nvidia-smi` output — Confirmed: K6000, 12203 MiB total VRAM, CUDA 11.4, compute capability 3.5

### Secondary (MEDIUM confidence)
- [llama.cpp server README on GitHub](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) — Cross-verified with local copy; file:// URL supported via `--media-path` flag
- [llama.cpp GitHub issue #8010](https://github.com/ggml-org/llama.cpp/issues/8010) — Historical context on multimodal removal/restoration; resolved in PR #12898 which is in build 8156
- [Simon Willison's llama.cpp vision article (May 2025)](https://simonwillison.net/2025/May/10/llama-cpp-vision/) — Confirms server works via `/v1/chat/completions` with image_url for newer models

### Tertiary (LOW confidence — needs validation)
- LLaVA 1.5-7B Q4 VRAM usage estimate (5-6 GB): Multiple secondary sources agree on this range but exact usage on K6000/CUDA 11.4 with this build is unverified. Validate in Wave 1 smoke test.
- `--no-webui` flag: Documented in README but not confirmed in `--help` grep output above. Verify before use.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — llama-server binary confirmed installed and working; requests available; all other libs are stdlib
- Architecture: HIGH — patterns drawn from actual test files in local llama.cpp source; verified API call format
- Pitfalls: MEDIUM — most pitfalls verified by official docs/code; VRAM release timing (Pitfall 5) is extrapolated from GPU behavior knowledge
- Model selection: MEDIUM — LLaVA 1.5-7B Q4_K_M is known-good but not yet downloaded/tested on this machine

**Research date:** 2026-02-26
**Valid until:** 2026-03-28 (30 days — llama-server API is relatively stable but libmtmd is under "very heavy development" per own README)
