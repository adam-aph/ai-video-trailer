# **🎬 CineCut AI: Video Trailer Architect**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![CUDA](https://img.shields.io/badge/CUDA-11.4-green?logo=nvidia)
![FFmpeg](https://img.shields.io/badge/FFmpeg-required-orange?logo=ffmpeg)
![Tests](https://img.shields.io/badge/tests-207%20passing-brightgreen)
![License](https://img.shields.io/badge/License-Apache_2.0-lightgrey)

CineCut AI transforms any long-form film into a polished, genre-aware trailer using a fully local AI stack — no cloud APIs, no manual editing. Feed it a video and a subtitle file; it returns a cinematic MP4 trailer with color grading, a licensed music bed, sound effects, and voice-over — all cut to beat.

---

## Pipeline Overview

```
Input Film (.mkv/.mp4) + Subtitles (.srt/.ass)
          │
          ▼
  [1] Proxy Creation        420p downscale for fast processing
          │
          ▼
  [2] Subtitle Parsing      Dialogue events with emotion labels
          │
          ▼
  [3] Keyframe Extraction   Hybrid: subtitle midpoints + scene changes + interval
          │
          ▼
  [4] LLaVA Vision          Per-frame scene descriptions (visual, mood, action)
          │
          ▼
  [5] Structural Analysis   Mistral 7B extracts BEGIN_T / ESCALATION_T / CLIMAX_T
          │
          ▼
  [6] Zone Matching         Sentence-transformers assigns clips to narrative zones
          │
          ▼
  [7] Assembly              Zone-ordered, signal-ranked, beat-snapped manifest
          │
          ▼
  [8] Conform               LUT grading + loudnorm + SFX + VO + music → final MP4
```

All intermediate results are checkpointed — resume a failed pipeline from any stage without re-running prior work.

---

## Hardware Requirements

> **Warning — GPU requirements are non-trivial.** This project was developed and tested on an **Nvidia Quadro K6000 (12 GB VRAM)** with **CUDA 11.4**. The two AI models (LLaVA 1.5-7B and Mistral 7B) are loaded sequentially (never concurrently) via llama.cpp with `-ngl 99` (all layers on GPU). Each model requires a minimum of **6 GB free VRAM** at inference time.

- **GPU:** Nvidia GPU with ≥ 8 GB VRAM (12 GB recommended)
- **CUDA:** 11.4 or compatible driver
- **RAM:** 16 GB minimum, 32 GB recommended (scene detection + sentence-transformers)
- **Storage:** ~15 GB for models + working files per film

The pipeline degrades gracefully to CPU inference if no GPU is available, but expect drastically longer runtimes (hours instead of minutes for a feature-length film).

---

## Features

### 18 Vibe Profiles

Each vibe profile controls cut pacing, color grading, dialogue ratio, audio loudness, and LUT selection:

| Vibe | Pacing | Color Aesthetic |
|------|--------|-----------------|
| `action` | Fast → montage | Teal/orange high-contrast |
| `adventure` | Steady | Warm, natural |
| `animation` | Dialogue-heavy | Bright, vivid |
| `comedy` | Relaxed → lively | Warm, soft contrast |
| `crime` | Moderate | Noir, desaturated |
| `documentary` | Slowest | Neutral |
| `drama` | Intimate | Cool, muted |
| `family` | Steady | Warm, soft |
| `fantasy` | Moderate | Rich, elevated contrast |
| `history` | Measured | Sepia, warm |
| `horror` | Tense → barrage | Dark, maximum contrast |
| `music` | Fast, high-energy | Vivid, minimal dialogue |
| `mystery` | Deliberate | Muted, cool |
| `romance` | Slow | Warm, soft |
| `sci-fi` | Escalating | Cold, desaturated |
| `thriller` | Fast escalation | Cool, high-contrast |
| `war` | Heavy → assault | Desaturated, stark |
| `western` | Measured | Amber, warm |

### 3-Act Narrative Structure

CineCut AI does not cut trailers chronologically. The Mistral 7B language model reads the subtitle corpus and identifies three narrative anchors:

- **BEGIN_T** — The inciting incident (typically ~5% into the film)
- **ESCALATION_T** — Where tension rises (~45%)
- **CLIMAX_T** — The story's peak moment (~80%)

Clips are assigned to one of three zones (BEGINNING → ESCALATION → CLIMAX) using sentence-transformer cosine similarity, then ranked within each zone by an emotional signal score combining visual mood, dialogue emotion, and money-shot classification. This produces a non-chronological, emotionally coherent trailer structure:

```
Act 1  (BEGINNING)   Cold open + character introduction  ← longest cuts
Act 2  (ESCALATION)  Rising tension + relationship beats ← medium cuts
       ─── silence beat (3–5s black) ───────────────────
Act 3  (CLIMAX)      Montage barrage + climax peak       ← shortest cuts
       ─── title card + button ──────────────────────────
```

Clip start times are snapped to the nearest beat of the detected BPM (librosa analysis with octave-error correction).

### Audio System

- **Music bed:** Fetches a CC-licensed track from Jamendo API v3 matched to the vibe, cached permanently at `~/.cinecut/music/{vibe}.mp3`
- **SFX:** Synthesized via FFmpeg `aevalsrc` — high-frequency chirp on hard cuts, low-to-high sweep at act boundaries
- **Voice-over:** Extracted from the film's own audio track, placed in Acts 1–2
- **4-stem mix:** Film audio + music bed + SFX + VO, each loudnorm-normalized to a per-vibe LUFS target with sidechain ducking

---

## Installation

### 1. System Dependencies

```bash
# Ubuntu/Debian
sudo apt install ffmpeg python3-dev

# Verify versions
ffmpeg -version      # ≥ 4.4 recommended
python3 --version    # ≥ 3.10
```

### 2. llama.cpp Server

The pipeline requires `llama-server` from [llama.cpp](https://github.com/ggerganov/llama.cpp). Build from source with CUDA support:

```bash
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j$(nproc)
sudo cp build/bin/llama-server /usr/local/bin/
```

Verify: `llama-server --version`

### 3. Download Models

Create the models directory (default: `~/models`, override with `CINECUT_MODELS_DIR`):

```bash
mkdir -p ~/models
```

Download all three required model files:

| Model | File | Size | Purpose |
|-------|------|------|---------|
| LLaVA 1.5-7B | `ggml-model-q4_k.gguf` | ~4.1 GB | Vision: per-frame scene description |
| LLaVA projection | `mmproj-model-f16.gguf` | ~624 MB | Vision encoder projection weights |
| Mistral 7B Instruct v0.3 | `mistral-7b-instruct-v0.3.Q4_K_M.gguf` | ~4.4 GB | Text: narrative anchor extraction |

Recommended sources: [HuggingFace — mys/ggml_llava-v1.5-7b](https://huggingface.co/mys/ggml_llava-v1.5-7b) and [HuggingFace — MaziyarPanahi/Mistral-7B-Instruct-v0.3-GGUF](https://huggingface.co/MaziyarPanahi/Mistral-7B-Instruct-v0.3-GGUF).

Place all files directly in `~/models/`.

### 4. Install CineCut

```bash
git clone https://github.com/your-org/cinecut.git
cd cinecut
pip3 install -e . --break-system-packages
```

### 5. (Optional) Jamendo API Key

For automatic music bed fetching, register for a free client ID at [developer.jamendo.com](https://developer.jamendo.com) and set:

```bash
export JAMENDO_CLIENT_ID="your_client_id"
```

Without this, the pipeline skips the music bed and produces a trailer without background music.

---

## Usage

```bash
cinecut <video> --subtitle <srt_or_ass> --vibe <name> [--review]
```

### Examples

```bash
# Generate an action trailer
cinecut film.mkv --subtitle film.srt --vibe action

# Generate a thriller trailer with human review step
cinecut film.mkv --subtitle film.en.ass --vibe thriller --review

# Use a custom models directory
CINECUT_MODELS_DIR=/mnt/storage/models cinecut film.mkv --subtitle film.srt --vibe sci-fi

# Resume a previously interrupted pipeline (auto-detected from work_dir)
cinecut film.mkv --subtitle film.srt --vibe drama
```

The `--review` flag pauses the pipeline after manifest generation, allowing you to inspect and edit `TRAILER_MANIFEST.json` before conform begins.

### Output

The trailer is written to `<video_stem>_trailer.mp4` in the current directory. A work directory (`<video_stem>_work/`) holds all intermediate files and the checkpoint.

---

## TRAILER_MANIFEST.json — Human-in-the-Loop Editing

The manifest is the declarative contract between the AI analysis stages and the final FFmpeg conform stage. Every clip, its source timestamps, beat type, act assignment, transition, and narrative zone are written here before any video encoding begins.

With `--review`, you can edit this file directly:

```json
{
  "schema_version": "2.0",
  "source_file": "/path/to/film.mkv",
  "vibe": "thriller",
  "clips": [
    {
      "source_start_s": 120.5,
      "source_end_s": 123.8,
      "beat_type": "inciting_incident",
      "act": "cold_open",
      "transition": "hard_cut",
      "dialogue_excerpt": "We need to move. Now.",
      "narrative_zone": "BEGINNING",
      "money_shot_score": 0.91
    }
  ],
  "structural_anchors": {
    "begin_t": 120.5,
    "escalation_t": 1842.0,
    "climax_t": 2714.0,
    "source": "llm"
  },
  "bpm_grid": {
    "bpm": 128.0,
    "beat_count": 310
  },
  "music_bed": {
    "track_name": "Dark Pulse",
    "artist_name": "SomeArtist",
    "license_ccurl": "https://creativecommons.org/licenses/by/3.0/",
    "local_path": "~/.cinecut/music/thriller.mp3"
  }
}
```

**Common edits:**
- Remove a clip entirely by deleting its entry
- Swap `act` assignments to reorder the narrative structure
- Override `transition` on any clip
- Change `vibe` to re-grade with a different LUT on the next conform run

---

## Technical Stats

### Milestone History

| Milestone | Phases | Shipped | Highlights |
|-----------|--------|---------|------------|
| **v1.0 MVP** | 1–5 | 2026-02-27 | End-to-end pipeline: ingestion → manifest → LLaVA inference → beat extraction → assembly + conform |
| **v2.0 Structural & Sensory Overhaul** | 6–10 | 2026-02-28 | Inference cache (msgpack), Mistral structural analysis, zone-based non-linear ordering, BPM grid snapping, Jamendo music bed, SFX synthesis, 4-stem audio mix |

### Codebase

| Metric | Value |
|--------|-------|
| Python source lines | 5,644 |
| Source files | 30+ |
| Unit tests | 207 |
| Test pass rate | 100% |
| Vibe profiles | 18 |
| Pipeline stages | 8 |

---

## Architecture Notes

- **Checkpointing:** Atomic JSON writes via tempfile + `os.replace`. Resume from any of 8 stages without reprocessing prior work.
- **Inference cache:** LLaVA results stored as msgpack binary at `work_dir/.scenedesc.msgpack`, invalidated on source file mtime/size change.
- **GPU serialization:** A module-level `threading.Lock` ensures LLaVA and Mistral never run concurrently — VRAM is fully released between models.
- **FFmpeg-first:** All video/audio processing (proxy creation, clip extraction, LUT grading, SFX synthesis, audio mixing) is driven by direct FFmpeg subprocess calls. No moviepy.
- **`amix normalize=0`:** The audio mixer mandates `normalize=0` everywhere — `normalize=1` destroys the per-stem LUFS targets and sidechain ducking.

---

## License

Apache-2.0 license — see [LICENSE](LICENSE).

Music beds sourced from [Jamendo](https://www.jamendo.com) under Creative Commons licenses.
