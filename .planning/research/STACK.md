# Technology Stack

**Project:** CineCut AI v2.0 — Structural & Sensory Overhaul
**Researched:** 2026-02-28
**Research mode:** Ecosystem (stack additions for v2.0 new features only)
**Scope:** NEW capabilities only. Existing validated stack (Python 3.10+, Typer, Rich, Pydantic, pysubs2,
OpenCV headless, NumPy, requests, FFmpeg subprocess, llama-server HTTP) is NOT re-researched here.

---

## v2.0 New Dependencies Summary

| Library | Version | Feature(s) Served | CUDA Required? |
|---------|---------|-------------------|----------------|
| `librosa` | `>=0.11.0` | BPM detection, beat grid | No — pure CPU |
| `soundfile` | `>=0.12.1` | Audio I/O backend for librosa | No |
| `soxr` | `>=0.3.2` | Resampling for librosa (already dep) | No |
| `msgpack` | `>=1.0.0` | SceneDescription cache persistence | No |
| `sentence-transformers` | `>=3.0.0` | Scene-to-zone text embedding (CPU mode) | Optional |
| `requests` | already in stack | Jamendo API download | No |
| FFmpeg `aevalsrc` / SoX `synth` | system tools | Transition SFX synthesis | No |
| `llama-server` (existing binary) | build 8156 (pinned) | Text-only structural LLM stage | Yes (K6000, CUDA 11.4) |

---

## 1. BPM Detection

### Recommended: `librosa` 0.11.x

**Decision: librosa 0.11.x, `librosa.beat.beat_track()` + `librosa.feature.tempo()`**

Rationale:
- librosa is CPU-only — zero VRAM consumption, zero CUDA dependency. The K6000's 12GB is already
  reserved for llama-server during inference; audio analysis must not contend for it.
- `beat_track()` returns (tempo_bpm, beat_frames), which converts directly to a seconds-indexed beat
  grid via `librosa.frames_to_time()`. This is exactly the BPM pacing grid the v2.0 assembler needs.
- `librosa.feature.tempo()` provides a global BPM estimate without the beat-by-beat frame array —
  useful for choosing a cut density per act without post-processing.
- librosa 0.11.0 (released 2024) uses soundfile as default backend, so loading WAV/FLAC extracted
  from film audio requires no ffmpeg Python bindings — just `subprocess` FFmpeg to extract the audio
  track first, then librosa reads the WAV file.
- Supports OGG (aubio does not), which matters if royalty-free music tracks are OGG-encoded.

**Why not aubio:**
- aubio is a C library with a thin Python wrapper; binary wheel availability on modern pip is inconsistent.
  It is not pure-Python and has caused install failures on Linux when the system `libaudio` is absent.
- aubio's BPM estimator clusters around 107 BPM and can produce half/double tempo errors without
  correction. For a pacing grid where +/-5 BPM matters, this is an unacceptable failure mode.
- aubio excels at real-time beat detection from microphone input — not relevant here.
- librosa's `beat_track()` with `start_bpm` seeded from vibe profile (e.g., 130 BPM for Action,
  80 BPM for Drama) produces more reliable results for offline analysis of known-genre audio.

**Integration pattern:**

```python
import subprocess
import librosa
import numpy as np
from pathlib import Path

def extract_audio_for_analysis(video_path: Path, output_wav: Path) -> None:
    """Extract mono 22050 Hz WAV from video — optimal for librosa analysis."""
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(video_path),
        "-vn",                          # no video
        "-ac", "1",                     # mono
        "-ar", "22050",                 # librosa default sample rate
        "-c:a", "pcm_s16le",           # uncompressed WAV
        str(output_wav),
    ], check=True, capture_output=True)

def detect_bpm_and_beats(
    wav_path: Path,
    start_bpm: float = 120.0,
) -> tuple[float, np.ndarray]:
    """Returns (tempo_bpm, beat_times_seconds).

    start_bpm should be seeded from vibe profile edit rate to avoid
    half/double tempo errors.
    """
    y, sr = librosa.load(str(wav_path), sr=22050, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, start_bpm=start_bpm)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    return float(tempo), beat_times
```

**pyproject.toml additions:**

```toml
"librosa>=0.11.0",
"soundfile>=0.12.1",
"soxr>=0.3.2",   # already pulled in by librosa but pin explicitly
```

**VRAM note:** librosa uses NumPy arrays, no GPU. Analysis of a 2-hour film's extracted audio WAV
takes ~2-5 seconds on CPU with negligible memory. Run this during Stage 2 (ingestion) while
llama-server is NOT running, to avoid any VRAM contention concerns.

---

## 2. Royalty-Free Music Source

### Recommended: Jamendo API v3

**Decision: Jamendo API v3, `requests` (already in stack), no new library needed**

Rationale:
- Jamendo offers 600,000+ tracks under Creative Commons licenses. The API is free with a registered
  `client_id` (developer account registration is free and instant).
- The `/tracks/` endpoint supports `tags` parameter (mood, genre, instruments) and returns an
  `audiodownload` field — a direct MP3 download URL requiring only `requests.get()`.
- No authentication token needed for read-only track search: `client_id` query parameter only.
- `zip_allowed` field (added 2021) indicates per-track download permission; filter `zip_allowed=true`
  at query time to avoid downloading tracks that block bulk use.
- The API is stable (v3 since ~2015, still active 2025) with no deprecation signals.

**Why not Free Music Archive (FMA):**
- FMA's programmatic API requires an API key that must be requested (not self-service), and the FMA
  web infrastructure has had availability issues. Jamendo is more reliable for automation.
- FMA does not expose a `mood` filter directly; mood tags are inconsistent across tracks.
- FMA's catalog (~100K tracks) is smaller than Jamendo's (~600K), meaning worse vibe-to-music
  matching for the 18 vibe profiles.

**Why not ccMixter:**
- ccMixter has no formal REST API for automated search and download. It is a community site for
  remix culture, not a structured music library with mood/genre metadata.

**Vibe-to-tag mapping (recommended):**

```python
VIBE_JAMENDO_TAGS: dict[str, list[str]] = {
    "action":       ["action", "epic", "energetic", "fast"],
    "adventure":    ["adventure", "cinematic", "orchestral"],
    "animation":    ["playful", "whimsical", "cartoon"],
    "comedy":       ["funny", "quirky", "playful"],
    "crime":        ["dark", "tension", "noir"],
    "documentary":  ["ambient", "documentary", "neutral"],
    "drama":        ["emotional", "dramatic", "piano"],
    "family":       ["cheerful", "happy", "family"],
    "fantasy":      ["epic", "orchestral", "fantasy"],
    "history":      ["orchestral", "classical", "cinematic"],
    "horror":       ["dark", "horror", "tense", "scary"],
    "music":        ["music", "soundtrack", "instrumental"],
    "mystery":      ["suspense", "mysterious", "dark"],
    "romance":      ["romantic", "love", "soft"],
    "sci-fi":       ["electronic", "futuristic", "sci-fi"],
    "thriller":     ["tension", "suspense", "dark"],
    "war":          ["orchestral", "dramatic", "epic", "military"],
    "western":      ["country", "western", "guitar"],
}
```

**Auto-download pattern (cache on first use):**

```python
import hashlib
import requests
from pathlib import Path

JAMENDO_CLIENT_ID = "YOUR_CLIENT_ID"   # register at developer.jamendo.com
MUSIC_CACHE_DIR = Path("~/.cinecut/music_cache").expanduser()

def fetch_vibe_music(vibe: str, cache_dir: Path = MUSIC_CACHE_DIR) -> Path:
    """Download a royalty-free track for vibe. Returns cached path on subsequent calls."""
    tags = VIBE_JAMENDO_TAGS.get(vibe, ["cinematic"])
    tag_key = hashlib.md5("|".join(tags).encode()).hexdigest()[:8]
    cached = cache_dir / f"{vibe}_{tag_key}.mp3"
    if cached.exists():
        return cached

    cache_dir.mkdir(parents=True, exist_ok=True)
    params = {
        "client_id": JAMENDO_CLIENT_ID,
        "format": "json",
        "limit": 5,
        "tags": "+".join(tags),
        "audioformat": "mp32",          # 320 kbps MP3
        "include": "musicinfo",
        "groupby": "artist_id",         # variety across artists
    }
    resp = requests.get("https://api.jamendo.com/v3.0/tracks/", params=params, timeout=10)
    resp.raise_for_status()
    tracks = resp.json().get("results", [])
    if not tracks:
        raise RuntimeError(f"No Jamendo tracks found for vibe '{vibe}' with tags {tags}")

    # Pick first track with audiodownload available
    for track in tracks:
        dl_url = track.get("audiodownload")
        if dl_url:
            audio = requests.get(dl_url, timeout=30)
            audio.raise_for_status()
            cached.write_bytes(audio.content)
            return cached

    raise RuntimeError(f"No downloadable tracks found for vibe '{vibe}'")
```

**Licensing note:** All Jamendo tracks are Creative Commons. Most are CC-BY or CC-BY-SA, which require
attribution in the final output. For a local tool generating personal-use trailers, this is acceptable.
If the tool is ever distributed with pre-cached music, the most restrictive license (CC-BY-SA) applies.

---

## 3. Transition SFX Synthesis

### Recommended: FFmpeg `aevalsrc` + SoX `synth` via subprocess

**Decision: No new Python library. Synthesize via FFmpeg `aevalsrc` for frequency sweeps; SoX
`synth` for complementary layering. Both are already on PATH.**

Rationale:
- Both FFmpeg and SoX are already required system dependencies. Zero new installs.
- Synthesis happens at conform time (Stage 6), so it runs AFTER llama-server has exited — no VRAM
  contention. FFmpeg's audio filters are fully CPU-bound.
- The resulting SFX WAV/FLAC files are deterministic: same vibe always generates the same SFX,
  enabling caching with a simple hash of the generation parameters.

**SFX types needed for v2.0 transition types:**

| Transition Type | SFX Description | Generator |
|----------------|----------------|-----------|
| `hard_cut` | Silence (no SFX) | N/A |
| `crossfade` | Soft low-frequency exhale | FFmpeg aevalsrc |
| `fade_to_black` | Low rumble decay | FFmpeg aevalsrc |
| `fade_to_white` | High-frequency sweep out | SoX synth |
| `beat_cut` (new) | Sharp transient punch | SoX synth |
| `whoosh_forward` (new) | Ascending frequency sweep | SoX synth |
| `whoosh_backward` (new) | Descending frequency sweep | SoX synth |

**FFmpeg `aevalsrc` — soft low-frequency exhale (crossfade SFX):**

```bash
# Generate 0.5s low-frequency ambient exhale (100-200 Hz with envelope decay)
ffmpeg -y -f lavfi \
  -i "aevalsrc=0.3*sin(2*PI*120*t)*exp(-3*t):d=0.5:s=44100:c=stereo" \
  -c:a flac crossfade_sfx.flac
```

**SoX `synth` — ascending whoosh (beat_drop, escalation transitions):**

```bash
# Generate 0.4s ascending sine sweep 80Hz->1200Hz (whoosh forward)
sox -n -r 44100 -c 2 whoosh_up.flac \
  synth 0.4 sine 80-1200 \
  fade h 0.01 0.4 0.1 \
  vol 0.6

# Generate 0.4s descending sweep 1200Hz->80Hz (whoosh backward)
sox -n -r 44100 -c 2 whoosh_down.flac \
  synth 0.4 sine 1200-80 \
  fade h 0.01 0.4 0.1 \
  vol 0.6
```

**SoX `synth` — transient punch (beat cut):**

```bash
# Generate 0.15s sharp transient (sub-bass thud with high decay)
sox -n -r 44100 -c 2 punch.flac \
  synth 0.15 sine 60-20 \
  fade h 0.005 0.15 0.05 \
  vol 0.8
```

**Key SoX flags:**
- `-n` — null input (no source file needed)
- `synth [dur] sine [start_hz]-[end_hz]` — frequency sweep over duration
- `fade h [in] [out_point] [out_dur]` — half-cosine fade (smooth envelope)
- `vol [level]` — peak amplitude control

**Python synthesis helper:**

```python
import subprocess
from pathlib import Path

SFX_CACHE = Path("~/.cinecut/sfx_cache").expanduser()

def synthesize_sfx(
    sfx_type: str,   # "whoosh_up" | "whoosh_down" | "punch" | "exhale"
    vibe: str,       # For vibe-specific tuning
    duration_s: float = 0.4,
) -> Path:
    """Generate transition SFX file, cached by type+vibe+duration."""
    SFX_CACHE.mkdir(parents=True, exist_ok=True)
    out = SFX_CACHE / f"{sfx_type}_{vibe}_{duration_s:.2f}.flac"
    if out.exists():
        return out

    if sfx_type == "whoosh_up":
        subprocess.run([
            "sox", "-n", "-r", "44100", "-c", "2", str(out),
            "synth", str(duration_s), "sine", "80-1200",
            "fade", "h", "0.01", str(duration_s), "0.1",
            "vol", "0.6",
        ], check=True, capture_output=True)
    elif sfx_type == "whoosh_down":
        subprocess.run([
            "sox", "-n", "-r", "44100", "-c", "2", str(out),
            "synth", str(duration_s), "sine", "1200-80",
            "fade", "h", "0.01", str(duration_s), "0.1",
            "vol", "0.6",
        ], check=True, capture_output=True)
    elif sfx_type == "punch":
        subprocess.run([
            "sox", "-n", "-r", "44100", "-c", "2", str(out),
            "synth", "0.15", "sine", "60-20",
            "fade", "h", "0.005", "0.15", "0.05",
            "vol", "0.8",
        ], check=True, capture_output=True)
    elif sfx_type == "exhale":
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"aevalsrc=0.3*sin(2*PI*120*t)*exp(-3*t):d={duration_s}:s=44100:c=stereo",
            "-c:a", "flac", str(out),
        ], check=True, capture_output=True)
    return out
```

**VRAM note:** Both FFmpeg and SoX audio synthesis are 100% CPU-bound. SFX generation takes
<100ms per file, is cached after first run, and can run at any pipeline stage.

---

## 4. Scene-to-Zone Matching (Semantic Embedding)

### Recommended: `sentence-transformers` 3.x, CPU mode, all-MiniLM-L6-v2

**Decision: sentence-transformers 3.x with all-MiniLM-L6-v2 model, text-only, CPU inference.**

Context: The two-stage LLM pipeline works as follows:
1. **Stage A** (text-only, this section): Feed subtitle text blocks to a lightweight LLM
   (llama-server) to produce structural anchors: `BEGIN_T`, `ESCALATION_T`, `CLIMAX_T` timestamps.
2. **Stage B** (this section): Match each `SceneDescription.visual_content` string
   (already extracted by LLaVA in Stage 4) to its nearest narrative zone
   (BEGIN / ESCALATION / CLIMAX) using cosine similarity on text embeddings.

Stage B does NOT need vision/image embeddings. The LLaVA model already produced text descriptions
from keyframes. Zone matching is text-to-text cosine similarity between the scene's description
and the zone's defining anchor sentences.

Rationale for sentence-transformers / all-MiniLM-L6-v2:
- `all-MiniLM-L6-v2` is 22 MB, infers on CPU in ~1-2ms per sentence. Embedding all
  SceneDescriptions for a 2-hour film (~150-300 scenes) completes in under 1 second on CPU.
- No CUDA dependency. sentence-transformers auto-detects GPU but falls back gracefully to CPU —
  critical given CUDA 11.4 / Kepler constraints (see CUDA section below).
- Pure text matching avoids the CLIP/PyTorch dependency chain entirely. CLIP requires PyTorch,
  and PyTorch 2.x dropped CUDA 11.4 support (last compatible: PyTorch 1.13.1). Installing
  PyTorch 1.13.1 for a 22MB embedding model is inadvisable.
- The semantic embedding approach is well-suited for narrative zone matching: zones are defined
  by their characteristic language ("conflict", "resolution", "confrontation") and
  SceneDescriptions contain exactly the natural-language descriptions that embed into the same
  space.

**Why not open_clip:**
- open_clip requires PyTorch. PyTorch 2.x does not support CUDA 11.4. PyTorch 1.13.1 supports
  CUDA 11.4 but is EOL (security risk, no updates). The Kepler architecture (compute capability
  3.5) was dropped from PyTorch prebuilt wheels; installing it requires building from source.
- The CLIP image-text embedding approach would add marginal benefit over text-text matching
  because the LLaVA stage already produced rich text descriptions of each frame.
- open_clip adds 400-800 MB of model weight on top of PyTorch's 2GB+ install footprint.
  Avoid entirely.

**CUDA compatibility warning for sentence-transformers:**
sentence-transformers depends on `transformers` which depends on PyTorch. When installing,
force CPU-only PyTorch to avoid pulling in a CUDA-incompatible wheel:

```bash
# Install CPU-only PyTorch FIRST to avoid CUDA wheel auto-selection
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers>=3.0.0
```

This produces a functional install with no CUDA dependency. All-MiniLM-L6-v2 on CPU handles
300 embeddings in <2 seconds — no GPU needed for this workload.

**Zone matching pattern:**

```python
from sentence_transformers import SentenceTransformer
import numpy as np

_model: SentenceTransformer | None = None

def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        # Force CPU — never use GPU for this; VRAM is reserved for llama-server.
        _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return _model

def match_scene_to_zone(
    scene_description: str,
    zone_anchors: dict[str, str],  # {"begin": "...", "escalation": "...", "climax": "..."}
) -> str:
    """Return zone name (begin/escalation/climax) with highest cosine similarity."""
    model = _get_model()
    texts = [scene_description] + list(zone_anchors.values())
    embeddings = model.encode(texts, normalize_embeddings=True)
    scene_emb = embeddings[0]
    zone_embs = embeddings[1:]
    scores = np.dot(zone_embs, scene_emb)     # cosine similarity (normalized)
    best_idx = int(np.argmax(scores))
    return list(zone_anchors.keys())[best_idx]
```

**pyproject.toml addition:**
```toml
# CPU-only PyTorch must be installed BEFORE this in requirements workflow
"sentence-transformers>=3.0.0",
```

---

## 5. Text-Only Structural LLM (Stage A)

### Recommended: Mistral-7B-Instruct-v0.3.Q4_K_M.gguf via existing llama-server

**Decision: Mistral 7B Instruct v0.3 Q4_K_M GGUF, served by the SAME llama-server binary
(build 8156) already on the system, on a different port (8090) to avoid conflict with LLaVA.**

Rationale for Mistral 7B v0.3:
- Q4_K_M quantization = ~4.37 GB VRAM. The K6000 has 12 GB; LLaVA (Stage 4) uses ~5-6 GB.
  These two inference stages never run concurrently (sequential pipeline + GPU_LOCK), so
  Mistral 7B fits comfortably within budget.
- Mistral 7B Instruct v0.3 introduced function calling support and improved instruction
  following over v0.1 — critical for reliable JSON output from the structural analysis prompt
  (BEGIN_T / ESCALATION_T / CLIMAX_T values must parse deterministically).
- Mistral 7B consistently outperforms LLaMA 2 7B on instruction-following tasks at the same
  quantization level.
- v0.3 is available in Q4_K_M GGUF from multiple verified sources (bartowski, QuantFactory
  on Hugging Face) — no custom build needed.

**Why not LLaMA 3.1 8B:**
- LLaMA 3.1 8B Q4_K_M is ~5.0 GB, leaving tighter margin vs. Mistral 7B's ~4.37 GB.
- More importantly: LLaMA 3.1 uses a BPE tokenizer with a 128K vocab that is SLOWER on the
  K6000 (Kepler architecture) due to the larger embedding lookup. Mistral 7B's tokenizer
  (32K vocab, SentencePiece) is faster on older GPU architectures.
- LLaMA 3.1 GGUF files are architecturally newer and may require a newer llama-server binary.
  Mistral 7B v0.3 GGUF is compatible with the llama.cpp build 8156 already on the system.

**CRITICAL: The existing llama-server binary (build 8156) MUST be used.**
Modern llama.cpp (2024+) dropped prebuilt CUDA support for compute capability 3.5 (Kepler /
K6000). The system's build 8156 was custom-compiled for K6000 + CUDA 11.4 and has the working
mmproj binary patch. Do NOT upgrade llama-server for v2.0 features. The text-only Mistral
inference is a standard completion call — build 8156 fully supports it.

**Two-server vs. one-server approach:**
Run Mistral text analysis on port 8090 as a SEPARATE llama-server instance from the LLaVA
instance (port 8089). They never run simultaneously (GPU_LOCK serializes all inference stages).
This avoids needing to manage model hot-swapping within a single server process and keeps the
LlavaEngine context manager pattern clean.

**Structural analysis prompt design:**

The subtitle text for the entire film is ~15-40 KB. Pass it in a single request with a
structured JSON output requirement:

```python
STRUCTURAL_ANALYSIS_PROMPT = """
You are a film narrative analyst. Given the full subtitle text of a film,
identify three structural turning points. Return ONLY a JSON object with
these exact keys:

{
  "BEGIN_T": <float>,       // Timestamp (seconds) where the story's central
                            // conflict or question becomes clear
  "ESCALATION_T": <float>,  // Timestamp where tension escalates significantly;
                            // often a reversal or revelation
  "CLIMAX_T": <float>       // Timestamp of peak dramatic tension; the point
                            // of no return
}

Subtitle text:
{subtitle_text}
"""
```

**VRAM budget confirmation:**

| Stage | Process | VRAM | When |
|-------|---------|------|------|
| Stage 2 (ingestion) | librosa BPM analysis | 0 MB | Before llama-server |
| Stage 3 (structural LLM) | Mistral 7B Q4_K_M | ~4,370 MB | llama-server port 8090 |
| Stage 4 (LLaVA vision) | LLaVA 7B + mmproj | ~5,500 MB | llama-server port 8089 |
| Stage 5 (zone matching) | sentence-transformers CPU | 0 MB | After llama-server exits |
| Stage 6 (conform) | FFmpeg (CPU) | ~200 MB | After all LLM stages |

GPU_LOCK ensures Stage 3 and Stage 4 never overlap.

---

## 6. Audio Extraction at Exact Timestamps (Protagonist VO)

### Recommended: subprocess FFmpeg with `-ss` / `-t` (existing pattern, no new library)

**Decision: Use the existing `subprocess` FFmpeg pattern. No new library needed.**

Rationale:
- The existing codebase already uses `subprocess.run(["ffmpeg", ...])` for all FFmpeg operations.
  Adding another library (ffmpeg-python, pydub) would create two parallel FFmpeg invocation
  patterns in the same codebase — a maintenance problem.
- FFmpeg's `-ss` (seek) and `-t` (duration) flags with decimal seconds provide millisecond
  precision for audio clip extraction. This matches pysubs2's millisecond timestamps directly.
- The protagonist VO extraction reads from the ORIGINAL high-bitrate source file (not the proxy),
  since audio quality is the goal.

**Exact-timestamp audio extraction pattern:**

```python
import subprocess
from pathlib import Path

def extract_audio_segment(
    source_path: Path,
    start_s: float,
    end_s: float,
    output_path: Path,
    normalize_lufs: float | None = None,
) -> None:
    """Extract audio clip from video at exact timestamps.

    Uses input-side seeking (-ss before -i) for fast seek,
    then -t for duration to avoid decode-to-timestamp inefficiency.
    """
    duration_s = end_s - start_s
    if duration_s <= 0:
        raise ValueError(f"end_s ({end_s}) must be > start_s ({start_s})")

    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-ss", f"{start_s:.6f}",   # 6 decimal places = microsecond precision
        "-i", str(source_path),
        "-t", f"{duration_s:.6f}",
        "-vn",                      # strip video stream
        "-c:a", "pcm_s16le",       # lossless WAV for VO clips
        "-ar", "48000",             # 48 kHz (broadcast standard)
        "-ac", "2",                 # stereo
        str(output_path),
    ]

    if normalize_lufs is not None:
        # Apply loudnorm for VO level matching — single-pass (VO clips are short)
        cmd = [
            "ffmpeg", "-y", "-hide_banner",
            "-ss", f"{start_s:.6f}",
            "-i", str(source_path),
            "-t", f"{duration_s:.6f}",
            "-vn",
            "-af", f"loudnorm=I={normalize_lufs}:TP=-1.5:LRA=11",
            "-c:a", "pcm_s16le",
            "-ar", "48000",
            "-ac", "2",
            str(output_path),
        ]

    subprocess.run(cmd, check=True, capture_output=True)
```

**Subtitle timestamp → seconds conversion (already in pysubs2 workflow):**

```python
# pysubs2 stores timestamps in milliseconds
start_s = event.start / 1000.0   # e.g., 5423.250 seconds
end_s   = event.end   / 1000.0
```

**Why not pydub:** pydub is a higher-level audio library but requires ffmpeg anyway, adds a
Python data-copy layer for the audio buffer, and has no advantage over direct subprocess FFmpeg
for simple segment extraction.

**Why not ffmpeg-python:** Already documented in existing STACK.md — unmaintained, adds
abstraction indirection. The v2.0 VO extraction is 3 lines of subprocess; no wrapper needed.

---

## 7. SceneDescription Persistence (Cache for Resume)

### Recommended: `msgpack` 1.x + atomic file write (existing pattern)

**Decision: msgpack binary file per run, written atomically, stored alongside the manifest.**

Rationale:
- The existing pipeline uses atomic checkpoint writes (tempfile + os.replace) for
  TRAILER_MANIFEST.json. The same pattern applies to the inference cache.
- msgpack serializes Python dicts/lists to binary ~30% smaller than JSON and ~60% faster to
  deserialize than pickle. For ~300 SceneDescription objects (each a small dict with 4 string
  fields), msgpack deserialization is <10ms.
- msgpack is pure Python wheels available on all platforms — no binary extension compile issues.
- Unlike pickle, msgpack is not executable — loading a corrupted cache cannot execute arbitrary
  code. This is a non-trivial concern when cache files may persist across code changes.
- Unlike SQLite, msgpack requires no schema migration when SceneDescription fields are added in
  future versions (new keys are silently ignored on load; missing keys get defaults).
- msgpack 1.0.x is the stable current release; the API has been stable since 1.0.0 (2020).

**Why not pickle:**
- pickle is CPython-version and class-definition sensitive. If SceneDescription's import path
  changes (e.g., module refactor), the pickle file becomes unreadable.
- Arbitrary code execution risk on load — never acceptable for user-facing tools.

**Why not SQLite:**
- SQLite adds schema management overhead. SceneDescription is a flat dict-of-dicts; relational
  storage adds no query benefit over a flat file.
- SQLite write performance (WAL mode) is slower than a single atomic msgpack file write for
  batch-insert of 300 records at pipeline completion.
- Schema migrations are required when SceneDescription fields change — unacceptable complexity
  for a cache that should be transparent and discardable.

**Why not JSON:**
- JSON stores 300 SceneDescription objects in ~80-120 KB, msgpack in ~50-70 KB. Performance
  difference is marginal at this scale, but msgpack's binary format avoids string escaping
  issues if any SceneDescription text contains special Unicode characters from film subtitles.
- JSON is human-readable, which is a benefit — but the manifest (TRAILER_MANIFEST.json) is
  already the human-readable artifact. The cache is internal/disposable.

**Persistence format:**

```python
import msgpack
import os
import tempfile
from pathlib import Path
from cinecut.inference.models import SceneDescription

CACHE_SCHEMA_VERSION = 1

def save_scene_cache(
    results: list[tuple],   # list[(KeyframeRecord, SceneDescription | None)]
    cache_path: Path,
) -> None:
    """Atomically write SceneDescription cache to disk."""
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "scenes": [
            {
                "timestamp_s": record.timestamp_s,
                "frame_path": record.frame_path,
                "source": record.source,
                "description": {
                    "visual_content": desc.visual_content,
                    "mood": desc.mood,
                    "action": desc.action,
                    "setting": desc.setting,
                } if desc is not None else None,
            }
            for record, desc in results
        ],
    }
    packed = msgpack.packb(payload, use_bin_type=True)

    # Atomic write — same pattern as checkpoint.py
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=cache_path.parent, suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(packed)
        os.replace(tmp_path, cache_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

def load_scene_cache(cache_path: Path) -> list[tuple] | None:
    """Load SceneDescription cache. Returns None if missing or version mismatch."""
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "rb") as f:
            payload = msgpack.unpackb(f.read(), raw=False)
        if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None    # Stale cache — re-run inference
        return payload["scenes"]
    except (msgpack.UnpackException, KeyError, TypeError):
        return None    # Corrupted cache — re-run inference
```

**Cache file naming convention:** Store alongside the manifest as
`TRAILER_MANIFEST.scene_cache.msgpack`. Deleted automatically on full pipeline re-run.
User can delete manually to force inference re-run (equivalent behavior to v1.0).

**pyproject.toml addition:**
```toml
"msgpack>=1.0.0",
```

---

## Complete v2.0 pyproject.toml Additions

```toml
# ADD to existing dependencies list in pyproject.toml:
"librosa>=0.11.0",
"soundfile>=0.12.1",
"soxr>=0.3.2",
"msgpack>=1.0.0",
"sentence-transformers>=3.0.0",
```

**Install order matters for sentence-transformers (CPU-only PyTorch):**

```bash
# Step 1: Install CPU-only PyTorch to prevent CUDA wheel selection
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Step 2: Install remaining dependencies
pip install -e ".[dev]"
```

Add to project documentation / Makefile to prevent accidental CUDA PyTorch install.

---

## CUDA 11.4 Compatibility Matrix (v2.0 Additions)

| Component | CUDA Relevant? | K6000 Compatible? | Notes |
|-----------|---------------|-------------------|-------|
| librosa 0.11 | No | Yes | Pure CPU/NumPy |
| soundfile 0.12 | No | Yes | libsndfile C extension, no CUDA |
| soxr 0.3 | No | Yes | C resampler, no CUDA |
| msgpack 1.0 | No | Yes | Pure Python |
| sentence-transformers 3.x | Optional | Yes (CPU mode) | Force `device="cpu"` |
| torch (CPU wheel) | No | Yes | Install CPU-only wheel explicitly |
| Jamendo API (requests) | No | Yes | Already in stack |
| FFmpeg aevalsrc | No | Yes | CPU audio filter |
| SoX synth | No | Yes | CPU audio synthesis |
| Mistral 7B (llama-server) | Yes (K6000) | Yes (pinned build 8156) | MUST use existing binary |

**Critical constraint reiteration:** Do NOT upgrade llama-server for v2.0. The build 8156
binary is the ONLY confirmed working build for K6000 + CUDA 11.4 + the mmproj patch. Modern
llama.cpp prebuilt wheels target compute capability 6.1+ (Pascal+) and will NOT run on the
K6000 (3.5 Kepler). Verify this before any `apt upgrade` or manual llama.cpp build.

---

## System Dependency: SoX

SoX must be available on PATH for transition SFX synthesis.

```bash
# Ubuntu/Debian (likely already installed on this system)
sudo apt-get install sox

# Verify
sox --version   # expected: SoX v14.4.2 or similar
```

SoX is a dependency-free audio tool (no Python package, no CUDA). If SoX is unavailable,
fall back to FFmpeg-only synthesis (aevalsrc covers the exhale/rumble SFX types; whoosh
sweeps can also be approximated with `aevalsrc='0.5*sin(2*PI*(80+1120*t/0.4)*t)'`).

---

## What NOT to Add

| Library | Why Not |
|---------|---------|
| `ffmpeg-python` | Already rejected in v1.0 STACK.md. Still unmaintained. VO extraction uses existing subprocess pattern. |
| `pydub` | Wraps FFmpeg with a Python buffer copy layer. No benefit over direct subprocess FFmpeg for segment extraction. |
| `aubio` | C extension with inconsistent binary wheels. Half/double tempo errors on film audio. librosa is strictly better. |
| `open_clip` | Requires PyTorch. PyTorch CUDA 11.4 / Kepler support requires building from source. Text-to-text zone matching via sentence-transformers is sufficient. |
| `transformers` (standalone) | sentence-transformers bundles what is needed. Standalone transformers adds model-loading boilerplate. |
| `torchaudio` | PyTorch dependency chain again. librosa handles all audio analysis needs. |
| `yt-dlp` / `mutagen` | No music downloading from streaming platforms (licensing). Jamendo provides direct download URLs via its API. |
| `SQLite` (new) | msgpack flat file is sufficient for inference cache. SQLite adds schema migration overhead with no query benefit. |
| `pickle` | Executable on load, class-path sensitive, breaks on module refactor. msgpack is safer and similarly fast. |
| `Ollama` | Explicitly out of scope per PROJECT.md constraints. |
| PyTorch (CUDA wheel) | CUDA 11.4 Kepler not supported in PyTorch 2.x prebuilt wheels. CPU-only wheel must be installed explicitly. |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| BPM detection | librosa 0.11 | aubio | C extension binary issues; half/double tempo errors |
| BPM detection | librosa 0.11 | essentia | Much heavier ML library; VRAM overhead; overkill for BPM only |
| Music source | Jamendo API v3 | Free Music Archive | Less reliable API, smaller catalog, no self-service API key |
| Music source | Jamendo API v3 | ccMixter | No REST API; community site not suitable for automation |
| SFX synthesis | FFmpeg + SoX subprocess | pydub + librosa | pydub wraps FFmpeg anyway; adds buffer copy overhead |
| SFX synthesis | FFmpeg + SoX subprocess | External SFX library | Out of scope per PROJECT.md — "no external SFX files" |
| Zone matching | sentence-transformers CPU | open_clip | Requires PyTorch CUDA; K6000 Kepler incompatible with PyTorch 2.x |
| Zone matching | sentence-transformers CPU | spacy similarity | spacy's word vectors are less accurate for semantic zone matching |
| Text LLM model | Mistral 7B v0.3 Q4_K_M | LLaMA 3.1 8B | Slightly larger; newer architecture may require newer llama-server |
| Text LLM model | Mistral 7B v0.3 Q4_K_M | LLaMA 2 7B | Mistral 7B outperforms LLaMA 2 7B on instruction-following at same quantization |
| VO extraction | subprocess FFmpeg | ffmpeg-python | Already rejected; subprocess is established pattern in codebase |
| VO extraction | subprocess FFmpeg | pydub | Extra buffer copy; no precision benefit |
| Cache persistence | msgpack 1.0 | pickle | Executable on load; class-path sensitive; breaks on refactor |
| Cache persistence | msgpack 1.0 | SQLite | Schema migration overhead; no query benefit for flat inference cache |
| Cache persistence | msgpack 1.0 | JSON | Minor performance difference; Unicode escaping risk with subtitle text |

---

## Sources

| Claim | Source | Confidence |
|-------|--------|------------|
| librosa 0.11.0 is current stable version | [PyPI](https://pypi.org/project/librosa/) | HIGH |
| librosa is CPU-only (no CUDA) | [librosa.org install docs](https://librosa.org/doc/0.11.0/install.html) | HIGH |
| librosa.beat.beat_track() API signature | [librosa 0.11.0 docs](https://librosa.org/doc/main/generated/librosa.beat.beat_track.html) | HIGH |
| librosa soundfile backend is default since v0.7 | [librosa ioformats docs](https://librosa.org/doc/0.11.0/ioformats.html) | HIGH |
| aubio half/double tempo errors documented | Web search — multiple community reports | MEDIUM |
| Jamendo API v3 active, free client_id, audiodownload field | [developer.jamendo.com/v3.0](https://developer.jamendo.com/v3.0) + web search | HIGH |
| Jamendo 600K+ CC tracks | Web search — multiple sources consistent | MEDIUM |
| SoX synth frequency sweep syntax `sine 80-1200` | [sox cheat sheet gist](https://gist.github.com/ideoforms/d64143e2bad16b18de6e97b91de494fd) + sox man page | HIGH |
| FFmpeg aevalsrc sine expression with envelope | [ffmpeg aevalsrc examples](https://hhsprings.bitbucket.io/docs/programming/examples/ffmpeg/audio_sources/aevalsrc.html) | HIGH |
| PyTorch 2.x dropped CUDA 11.4 / compute capability 3.5 | [PyTorch forum discussion](https://discuss.pytorch.org/t/which-pytorch-version-2-0-1-support-cuda-11-4/190446) + [llama-cpp-cffi PyPI](https://pypi.org/project/llama-cpp-cffi/) | HIGH |
| sentence-transformers auto-detects GPU, falls back to CPU | [sbert.net docs](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | HIGH |
| all-MiniLM-L6-v2 is 22 MB | [Hugging Face model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | HIGH |
| Mistral 7B v0.3 Q4_K_M GGUF ~4.37 GB | [Hugging Face bartowski/Mistral-7B-Instruct-v0.3-GGUF](https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF) | HIGH |
| Mistral 7B outperforms LLaMA 2 7B on MT-Bench | Web search — Mistral AI announcement + benchmarks | MEDIUM |
| llama.cpp build 8156 K6000 compatibility | PROJECT.md — documented as working; mmproj patch noted | HIGH (system confirmed) |
| Modern llama.cpp excludes compute capability 3.5 | [llama-cpp-cffi PyPI CUDA ARCHITECTURES list](https://pypi.org/project/llama-cpp-cffi/), [Ollama issue #1756](https://github.com/ollama/ollama/issues/1756) | HIGH |
| msgpack 1.0 stable, ~30% smaller than JSON | [msgpack PyPI](https://pypi.org/project/msgpack/) + web search benchmarks | MEDIUM |
| msgpack deserialization faster than pickle | Web search — 2024 Python serialization benchmark | MEDIUM |
