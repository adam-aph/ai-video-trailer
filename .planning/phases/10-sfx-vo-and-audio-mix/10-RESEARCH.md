# Phase 10: SFX, VO, and Audio Mix - Research

**Researched:** 2026-02-28
**Domain:** FFmpeg audio filtergraph, aevalsrc SFX synthesis, sidechaincompress ducking, four-stem mix, protagonist VO extraction
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SFXL-01 | A synthesized swoosh/sweep SFX is added at each scene cut transition | `aevalsrc` with a linear chirp expression (`sin(2*PI*(f0 + k*t)*t)`) generates a sweep; rendered to a WAV via `ffmpeg -f lavfi -i "aevalsrc=..."` and mixed at each cut position using `-ss` + `amix` |
| SFXL-02 | SFX intensity varies by cut type: hard cuts get 0.4s sweep; act-boundary transitions get 1.0-1.5s sweep | Two pre-rendered WAV files (`sfx_hard.wav` and `sfx_boundary.wav`) synthesized at Phase start; cut type from `ClipEntry.transition` field |
| SFXL-03 | All SFX synthesized via FFmpeg `aevalsrc` at 48000Hz; no external SFX files | `aevalsrc=...:s=48000:d=0.4` or `:d=1.2`; `-ar 48000 -ac 2 -c:a pcm_s16le sfx_hard.wav` |
| VONR-01 | System identifies protagonist as most frequently-speaking character in subtitle corpus | `pysubs2.load()` → iterate `event.name` field (SSAEvent.name = actor name in ASS); for SRT (no speaker info), fall back to LLM Stage 7 protagonist output or dialogue-line-count heuristic: speaker with most `DialogueEvent.text` lines |
| VONR-02 | Up to 3 protagonist dialogue lines extracted as audio clips (1 Act 1, up to 2 Act 2, 0 Act 3) | Iterate assembly manifest acts; for matching protagonist subtitle timestamps, call `ffmpeg -ss START -i source -t DUR -vn -c:a aac -ar 48000 -ac 2 vo_N.aac`; collect best-scoring Act 1 and Act 2 VO clips |
| VONR-03 | VO clips extracted using output-seeking FFmpeg, re-encoded to AAC 48000Hz stereo, minimum 0.8s | Use `-ss` BEFORE `-i` for output-seeking (faster, frame-accurate at segment boundaries); enforce `duration >= 0.8` before writing; re-encode to `-c:a aac -ar 48000 -ac 2` |
| AMIX-01 | Music bed ducks during protagonist VO and high-emotion shots via FFmpeg sidechaincompress | `[music][vo_sidechain]sidechaincompress=threshold=0.025:ratio=6:attack=100:release=600:makeup=1` in `-filter_complex`; sidechain signal is VO stem (or combined VO+high-emotion) |
| AMIX-02 | All stems normalised independently before mixing; `amix normalize=0` used throughout | Per-stem `loudnorm` two-pass (already used in `conform/pipeline.py`); then `amix=inputs=4:normalize=0`; do NOT use normalize=1 (destroys ducking ratios — hard constraint from STATE.md) |
| AMIX-03 | All audio sources resampled to 48000Hz stereo before mixing | `aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo` applied to each stem before `amix` in the filtergraph |
</phase_requirements>

---

## Summary

Phase 10 adds three new modules under `conform/`: `sfx.py` (SFX synthesis), `vo_extract.py` (VO extraction and protagonist identification), and `audio_mix.py` (four-stem mix with sidechain ducking). These are wired into the conform pipeline in `conform/pipeline.py` as new passes after the existing clip-extraction and concat steps (Pass 3 and Pass 4).

The entire phase is FFmpeg-only. No new Python library dependencies are introduced — only `pysubs2` (already installed) for protagonist name extraction from ASS subtitles and `subprocess` (stdlib) for FFmpeg calls. All SFX are synthesized by `aevalsrc` using a linear chirp expression: `sin(2*PI*(f_start + ((f_end - f_start) / (2 * d)) * t) * t)` at 48000Hz. Two SFX files (`sfx_hard.wav` 0.4s and `sfx_boundary.wav` 1.2s) are rendered once into `work_dir/sfx/` and reused across all cut positions. Protagonist identification works by counting `event.name` occurrences in pysubs2 SSAFile (ASS gives speaker names directly); for SRT files (no `.name` field set), the fallback is counting raw dialogue events per character name derived from Stage 7 LLM output (if available in the manifest) or picking the character speaking the most total subtitle lines by frequency.

The four-stem audio mix in `audio_mix.py` operates on the concatenated trailer MP4 output from Pass 2 (`conform_manifest`): it extracts the existing film audio, mixes in the music bed (from `work_dir/music_bed.mp3` set by Phase 9), overlays VO clips at their target positions, overlays SFX at cut boundaries, applies `sidechaincompress` ducking on the music bed using the VO+SFX stem as sidechain, and produces a final mixed audio track via `amix normalize=0`. The critical constraint from STATE.md is `amix normalize=0` is MANDATORY — `normalize=1` destroys ducking ratios.

**Primary recommendation:** All three new modules in `conform/`, wired into `conform/pipeline.py` as Pass 3 (SFX+VO overlay) and Pass 4 (four-stem mix). Zero new library dependencies beyond what's already installed.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FFmpeg (subprocess) | system (already used) | aevalsrc SFX synthesis, VO extraction, sidechaincompress mix, amix | Already the project's audio/video processing tool; all requirements are expressible as FFmpeg filtergraph operations |
| pysubs2 | 1.8.0 (already installed) | Load subtitle file; access `SSAEvent.name` for protagonist identification | Already in pyproject.toml; `event.name` is the ASS speaker name field — no additional library needed |
| subprocess | stdlib | Drive FFmpeg commands | Already used throughout `conform/pipeline.py` |
| pathlib.Path | stdlib | Work dir management for SFX and VO files | Already used throughout project |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| collections.Counter | stdlib | Protagonist identification: count speaker name occurrences in `event.name` | VONR-01 dialogue-line-count fallback |
| re | stdlib | Strip SSA tags from `event.name` (some files embed style codes in name field) | VONR-01 name cleaning |
| json | stdlib | Parse loudnorm JSON stats from FFmpeg stderr (already pattern in pipeline.py) | AMIX-02 per-stem loudnorm |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| aevalsrc synthesis | External SFX library (freesound, etc.) | SFXL-03 explicitly forbids external files — synthesis is required |
| aevalsrc synthesis | SoX synth command | SoX availability not guaranteed (STATE.md blockers note); FFmpeg-only approach avoids optional system dep |
| sidechaincompress | Manual volume automation with `volume` filter | Volume automation is step-function; sidechaincompress provides proper attack/release curves |
| pysubs2 SSAEvent.name | Speaker diarization (pyannote.audio) | Speaker diarization requires PyTorch CUDA 12, incompatible with CUDA 11.4 stack — explicitly Out of Scope in REQUIREMENTS.md |

**Installation:** No new dependencies. All tools already in stack.

---

## Architecture Patterns

### Recommended Project Structure

```
src/cinecut/
├── conform/
│   ├── pipeline.py       # MODIFY: add Pass 3 (SFX+VO audio rebuild) and Pass 4 (four-stem mix)
│   ├── sfx.py            # NEW (10-01): synthesize_sfx_files(), apply_sfx_to_concat()
│   ├── vo_extract.py     # NEW (10-02): identify_protagonist(), extract_vo_clips()
│   ├── audio_mix.py      # NEW (10-03): mix_four_stems() with sidechaincompress
│   ├── luts.py           # Unchanged
│   └── __init__.py       # Unchanged
```

### Pattern 1: aevalsrc Linear Chirp for Sweep SFX

**What:** A linear frequency sweep (chirp) generates a swoosh/sweep sound. The correct formula uses the integral of the instantaneous frequency: `sin(2*PI*(f0 + slope*t)*t)` where `slope = (f1 - f0) / (2 * duration)`. Simply writing `sin(2*PI*(f0 + (f1-f0)*t/d)*t)` is WRONG (it ignores the phase integral and produces a non-monotone sweep — this is a classic FFmpeg aevalsrc pitfall).

**When to use:** In `conform/sfx.py`, `synthesize_sfx_files()` called once per pipeline run.

```bash
# Source: FFmpeg aevalsrc documentation + chirp signal theory
# Hard cut: short (0.4s), high-to-mid frequency sweep, amplitude fade-out
ffmpeg -y \
  -f lavfi \
  -i "aevalsrc=0.6*exp(-3*t)*sin(2*PI*(3000 + (300-3000)/(2*0.4)*t)*t):s=48000:d=0.4:c=stereo" \
  -ar 48000 -ac 2 -c:a pcm_s16le \
  work_dir/sfx/sfx_hard.wav

# Act-boundary: longer (1.2s), low-to-high sweep, fuller amplitude envelope
ffmpeg -y \
  -f lavfi \
  -i "aevalsrc=0.5*(1-exp(-2*t))*exp(-0.5*(t-0.6)^2/0.15)*sin(2*PI*(200 + (2000-200)/(2*1.2)*t)*t):s=48000:d=1.2:c=stereo" \
  -ar 48000 -ac 2 -c:a pcm_s16le \
  work_dir/sfx/sfx_boundary.wav
```

**Amplitude envelope notes:**
- Hard cut: `0.6*exp(-3*t)` — rapid exponential decay, sharp attack
- Boundary sweep: `0.5*(1-exp(-2*t))*exp(-0.5*(t-0.6)^2/0.15)` — Gaussian envelope centered at 0.6s for rise-and-fall shape

**Critical: `c=stereo` not `cl=stereo`** — the aevalsrc channel layout param is `c`, not `cl`. Single expression with `c=stereo` duplicates the mono expression to both channels.

### Pattern 2: Protagonist Identification via SSAEvent.name

**What:** ASS subtitle files embed the actor/character name in `SSAEvent.name`. SRT files have no speaker field — `event.name` will be empty string for all events. The fallback for SRT is to derive protagonist from Stage 7 structural analysis output (stored in manifest), or failing that, count `DialogueEvent.text` word frequency to identify the most referenced character name.

**When to use:** In `conform/vo_extract.py`, `identify_protagonist()`.

```python
# Source: pysubs2 1.8.0 docs — https://pysubs2.readthedocs.io/en/latest/api-reference.html
import pysubs2
from collections import Counter
from pathlib import Path

def identify_protagonist(subtitle_path: Path) -> str | None:
    """Return the most-speaking character name, or None if indeterminate.

    ASS/SSA: uses SSAEvent.name field (actor attribution per event).
    SRT: no speaker field — returns None (caller uses LLM manifest fallback).
    """
    subs = pysubs2.load(str(subtitle_path), encoding="utf-8")

    # Collect non-empty speaker names from Dialogue events
    names = [
        event.name.strip()
        for event in subs
        if not event.is_comment and event.name.strip()
    ]

    if not names:
        return None  # SRT or ASS with no names — use fallback

    # Most frequent speaker = protagonist
    counter = Counter(names)
    protagonist, _ = counter.most_common(1)[0]
    return protagonist
```

**SRT fallback chain (VONR-01):**
1. Check manifest `structural_anchors.protagonist` (if Phase 7 LLM output stored it)
2. If absent, pick character name most referenced in `DialogueEvent.text` across all events (word frequency over a list of subtitle lines)
3. If still None, skip VO extraction entirely (no protagonist clips — graceful degradation)

### Pattern 3: VO Audio Extraction with Output-Seeking FFmpeg

**What:** Extract a dialogue clip's audio from the source film using output-seeking (`-ss` before `-i`), re-encoded to AAC 48000Hz stereo. Minimum duration enforcement (0.8s) before writing.

**When to use:** In `conform/vo_extract.py`, `extract_vo_clip()`.

```python
# Source: FFmpeg documentation on seeking + VONR-03 requirement
import subprocess
from pathlib import Path

def extract_vo_clip(
    source: Path,
    start_s: float,
    end_s: float,
    output_path: Path,
    min_duration_s: float = 0.8,
) -> Path | None:
    """Extract audio-only clip from source, re-encoded to AAC 48000Hz stereo.

    Returns output_path on success, or None if duration < min_duration_s.
    Uses output-seeking: -ss BEFORE -i for fast seek + re-encode accuracy.
    """
    duration = end_s - start_s
    if duration < min_duration_s:
        return None

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_s),        # output-seeking: before -i
        "-i", str(source),
        "-t", str(duration),
        "-vn",                       # audio only
        "-c:a", "aac",
        "-ar", "48000",
        "-ac", "2",                  # stereo
        "-b:a", "192k",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    return output_path
```

**VO selection strategy (VONR-02):**
- For Act 1: find subtitle events in the BEGINNING zone timestamps that match the protagonist name; pick the one with highest `DialogueEvent.emotion` intensity score (intense > positive > neutral)
- For Act 2: find up to 2 events in ESCALATION zone; pick top-2 by intensity
- For Act 3: no VO (requirement explicitly says 0 in Act 3)

### Pattern 4: Four-Stem Audio Mix with Sidechain Ducking

**What:** Mix four audio stems — film audio (already in trailer concat output), music bed (from Phase 9 `~/.cinecut/music/{vibe}.mp3`), SFX WAV, VO AAC clips — using `sidechaincompress` for ducking and `amix normalize=0`. All stems resampled to 48000Hz stereo before mixing.

**When to use:** In `conform/audio_mix.py`, `mix_four_stems()`.

The operation flow:
1. Extract existing trailer audio track from the concat MP4 (Pass 2 output) → `trailer_audio.aac`
2. Prepare SFX audio track: overlay SFX WAVs at cut positions via `adelay` → `sfx_mix.wav`
3. Prepare VO track: silence-pad with `adelay` to position VO clips at correct timestamps → `vo_mix.aac`
4. Mix all four with sidechaincompress + amix → replace audio in trailer video

```bash
# Source: FFmpeg sidechaincompress docs + STATE.md decision: amix normalize=0 is MANDATORY
# Conceptual filtergraph (actual implementation in audio_mix.py builds this dynamically)

ffmpeg -y \
  -i trailer_noaudio.mp4 \       # input 0: video (no audio)
  -i trailer_audio.aac \         # input 1: film audio stem (loudnorm-normalized)
  -i music_bed.mp3 \             # input 2: music stem (loudnorm-normalized)
  -i sfx_mix.wav \               # input 3: SFX stem (pre-normalized)
  -i vo_mix.aac \                # input 4: VO stem (loudnorm-normalized)
  -filter_complex "
    [1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[film];
    [2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[music];
    [3:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[sfx];
    [4:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[vo];
    [vo]asplit=2[vo_out][vo_sc];
    [music][vo_sc]sidechaincompress=threshold=0.025:ratio=6:attack=100:release=600:makeup=1[music_ducked];
    [film][music_ducked][sfx][vo_out]amix=inputs=4:normalize=0:weights='1.0 0.7 0.8 1.0'[mixed]
  " \
  -map 0:v -map "[mixed]" \
  -c:v copy -c:a aac -ar 48000 -ac 2 \
  trailer_final.mp4
```

**Key filtergraph notes:**
- `aresample=48000` then `aformat=sample_fmts=fltp:channel_layouts=stereo` ensures AMIX-03 compliance
- `asplit=2` on VO creates: one copy for the mix output `[vo_out]`, one for the sidechain `[vo_sc]`
- `sidechaincompress`: `threshold=0.025` (approx -32dB), `ratio=6`, `attack=100ms`, `release=600ms` — these are starting parameters; REQUIRE empirical tuning per STATE.md
- `amix normalize=0` — MANDATORY per STATE.md; `weights` balance relative levels
- `music_ducked` output feeds the mix at reduced level when VO is present

### Anti-Patterns to Avoid

- **Incorrect chirp formula:** Writing `sin(2*PI*f(t)*t)` where `f(t)` varies linearly. The correct phase integral for a linear chirp is `sin(2*PI*(f0 + ((f1-f0)/(2*d))*t)*t)` — the `1/(2*d)` factor compensates for the accumulated phase. Getting this wrong produces harmonic artifacts.
- **`normalize=1` in amix:** The default `normalize=1` automatically scales inputs to avoid clipping, which silently destroys the carefully tuned ducking ratios. Always pass `normalize=0`.
- **Seeking placement for VO extraction:** Using `-ss` AFTER `-i` (input-seeking) causes inaccurate cuts at non-keyframe positions. For audio re-encoding, always place `-ss` BEFORE `-i` (output-seeking).
- **Using `event.name` on SRT files:** pysubs2 sets `SSAEvent.name = ''` for all SRT events. Calling `Counter(event.name for event in subs)` on an SRT file will count empty strings. Guard with `if event.name.strip()` before adding to counter.
- **No minimum duration check:** VO clips shorter than 0.8s produce audible truncation artifacts and may cause `sidechaincompress` sidechain to fire on silence. Always check `end_s - start_s >= 0.8` before extraction.
- **SFX at sample-rate mismatch:** If SFX WAV is at a different sample rate than the trailer audio, FFmpeg will resample silently but the `adelay` timing offsets will be wrong. Always synthesize SFX at exactly 48000Hz.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Frequency sweep sound | Custom Python numpy synthesis + soundfile write | FFmpeg aevalsrc | aevalsrc is already in the stack; avoids adding soundfile write dependency; produces exactly the sample rate and format needed |
| Audio ducking | `volume` filter with manual timing | `sidechaincompress` | Manual `volume` automation is frame-aligned step function; `sidechaincompress` gives smooth attack/release curves — required for audible quality |
| Multi-stem level balancing | Clip gain with `volume=Xdb` before amix | Per-stem `loudnorm` + `amix normalize=0` | Loudnorm normalizes LUFS (perceived loudness), not peak; prevents individual stems from over/under-powering regardless of source material |
| Protagonist speaker count | NLP/spaCy character reference extraction | `Counter(event.name)` on ASS events | ASS format already attributes each line to a character; zero-dependency solution |
| VO timing in mix | Custom audio frame splicing | `adelay=OFFSET_MS|OFFSET_MS` filter | adelay precisely positions audio clips at millisecond-accurate positions in the timeline |

**Key insight:** Everything in this phase is an FFmpeg filtergraph composition problem. Resist adding new Python audio processing libraries — the project is already FFmpeg-first by design.

---

## Common Pitfalls

### Pitfall 1: aevalsrc Chirp Formula Off-by-Half

**What goes wrong:** Sweep sounds distorted or produces audible beats (amplitude modulation artifact) instead of a smooth frequency sweep.
**Why it happens:** A linear chirp requires the INTEGRAL of the frequency function as the sine argument's phase term. `sin(2*PI*(f0 + slope*t)*t)` is correct. But `sin(2*PI*(f0*t + (f1-f0)*t*t/d))` makes an algebraic error, producing `sin(2*PI*(f0 + (f1-f0)*t/d)*t)` which forgets to divide the accumulation term by 2. The distinguishing symptom is a chirp that "comes back" — frequency sweeps up then seems to bend back.
**How to avoid:** Use the formula `sin(2*PI*(f0 + ((f1-f0)/(2*d))*t)*t)` where `d` is the total duration and `f0`, `f1` are start/end frequencies.
**Warning signs:** Audible amplitude wobble in the synthesized sweep at playback; phase coherence test: the instantaneous frequency at `t=0` should be `f0` and at `t=d` should be `f1`.

### Pitfall 2: amix normalize=1 Silently Destroying Ducking

**What goes wrong:** Music never audibly ducks during VO; all stems blend at roughly equal loudness.
**Why it happens:** `normalize=1` (the default) rescales the mixed output so all inputs contribute equally regardless of any prior gain reductions from `sidechaincompress`. The ducking effect is applied and then immediately undone by the normalizer.
**How to avoid:** Always pass `normalize=0`. This was explicitly documented in STATE.md as a hard constraint.
**Warning signs:** No audible level change in music during VO playback; ducking ratio empirically measures as 1:1.

### Pitfall 3: adelay Timing Units

**What goes wrong:** SFX or VO placed at wrong position in the timeline (e.g. 1000x too early or late).
**Why it happens:** `adelay` takes milliseconds not seconds: `adelay=5000|5000` = 5 second offset. Passing seconds (e.g. `adelay=5.0`) silently uses `5ms` = 0.005s offset.
**How to avoid:** Always convert seconds to milliseconds: `delay_ms = int(start_s * 1000); f"adelay={delay_ms}|{delay_ms}"`.
**Warning signs:** SFX audible at frame 0 or not audible at expected cut points.

### Pitfall 4: VO Extraction Source vs. Proxy

**What goes wrong:** VO audio extracted from the 420p proxy has degraded quality (proxy was encoded for visual analysis only, not audio fidelity).
**Why it happens:** The proxy is created from `create_proxy()` which down-samples video to 420p. Audio quality in the proxy depends on the encoding settings — if only video is re-encoded, audio may be passthrough. But the proxy exists alongside the source as a visual analysis artifact.
**How to avoid:** Always extract VO from the ORIGINAL source file (`source: Path`), NOT `proxy_path`. The `source` variable is the original `video` argument to `main()`.
**Warning signs:** Noticeable audio quality difference between film audio in clips (extracted from source) and VO clips.

### Pitfall 5: pysubs2 SSAEvent.name for SRT Files

**What goes wrong:** `identify_protagonist()` always returns `None` for SRT input files, disabling VO extraction.
**Why it happens:** SRT format has no speaker attribution field. pysubs2 sets `SSAEvent.name = ''` for every event loaded from SRT. The `Counter` will count empty strings.
**How to avoid:** Check `if not names: return None` after filtering — the caller must implement the fallback chain (manifest protagonist → dialogue-count heuristic → skip VO).
**Warning signs:** `identify_protagonist()` returns None for all test subtitle files in CI; VO clips directory is empty for SRT inputs.

### Pitfall 6: Four-Stem Mix on No-Music Pipeline

**What goes wrong:** `mix_four_stems()` crashes when Phase 9 music bed is absent (MUSC-03 graceful degradation path).
**Why it happens:** `audio_mix.py` tries to open `~/.cinecut/music/{vibe}.mp3` which doesn't exist if Jamendo was unavailable.
**How to avoid:** Check `music_bed_path.exists()` before constructing the filtergraph; fall back to a three-stem mix (film audio + SFX + VO) when music is absent. Same pattern as Phase 9's graceful degradation.
**Warning signs:** `FileNotFoundError` in conform stage on machines without network access.

### Pitfall 7: SFX Rendering Once vs. Per-Run

**What goes wrong:** SFX files are re-synthesized on every pipeline run, adding ~2-3s of unnecessary FFmpeg calls.
**Why it happens:** `synthesize_sfx_files()` called unconditionally.
**How to avoid:** Check if `work_dir/sfx/sfx_hard.wav` and `work_dir/sfx/sfx_boundary.wav` already exist before calling FFmpeg synthesis. Since SFX are deterministic (no inputs), files in `work_dir` are always valid if present.
**Warning signs:** FFmpeg SFX synthesis runs logged even on resume (checkpoint hit).

---

## Code Examples

Verified patterns from official sources:

### aevalsrc Stereo Chirp Synthesis

```bash
# Source: FFmpeg aevalsrc documentation (ffmpeg.org/ffmpeg-filters.html)
# Linear chirp: f0=3000Hz down to f1=300Hz over d=0.4s, stereo, 48000Hz
# Amplitude: 0.6 * exp(-3t) — exponential decay envelope
# slope = (f1 - f0) / (2 * d) = (300 - 3000) / (2 * 0.4) = -3375
ffmpeg -y \
  -f lavfi \
  -i "aevalsrc=0.6*exp(-3*t)*sin(2*PI*(3000+(-3375)*t)*t):s=48000:d=0.4:c=stereo" \
  -ar 48000 -ac 2 -c:a pcm_s16le \
  sfx_hard.wav
```

### amix with normalize=0 and weights

```bash
# Source: FFmpeg amix documentation (ayosec.github.io/ffmpeg-filters-docs/8.0/Filters/Audio/amix.html)
# Four-stem mix: normalize=0 is MANDATORY per STATE.md decision
# weights: film=1.0, music=0.7, sfx=0.8, vo=1.0
[film][music_ducked][sfx][vo_out]amix=inputs=4:normalize=0:weights='1.0 0.7 0.8 1.0'[mixed]
```

### sidechaincompress for Music Ducking

```bash
# Source: FFmpeg sidechaincompress docs (ayosec.github.io/ffmpeg-filters-docs/8.0/Filters/Audio/sidechaincompress.html)
# Music input [2:a] ducked by VO sidechain [vo_sc]
# threshold=0.025 (~-32dB), ratio=6, attack=100ms, release=600ms
[music][vo_sc]sidechaincompress=threshold=0.025:ratio=6:attack=100:release=600:makeup=1[music_ducked]
```

### adelay for Timeline Positioning

```bash
# Source: FFmpeg adelay documentation (ffmpeg.org/ffmpeg-filters.html)
# Position VO clip starting at 45.7s in the trailer timeline
# adelay takes MILLISECONDS: 45.7s * 1000 = 45700ms
[4:a]adelay=45700|45700[vo_positioned]
```

### pysubs2 Protagonist Identification

```python
# Source: pysubs2 1.8.0 docs (pysubs2.readthedocs.io/en/latest/api-reference.html)
import pysubs2
from collections import Counter

def identify_protagonist(subtitle_path: str) -> str | None:
    subs = pysubs2.load(subtitle_path, encoding="utf-8")
    names = [
        event.name.strip()
        for event in subs
        if not event.is_comment and event.name.strip()
    ]
    if not names:
        return None
    return Counter(names).most_common(1)[0][0]
```

### FFmpeg VO Extraction (output-seeking)

```bash
# Source: FFmpeg documentation on seeking (ffmpeg.org/ffmpeg.html#toc-Advanced-options)
# -ss BEFORE -i = output-seeking (accurate for audio re-encode, VONR-03)
ffmpeg -y \
  -ss 1234.56 \          # output seek position
  -i source.mkv \
  -t 3.2 \               # duration
  -vn \                  # no video
  -c:a aac \
  -ar 48000 \
  -ac 2 \
  -b:a 192k \
  vo_clip_0.aac
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| External SFX file libraries | aevalsrc synthesis | Project inception | Zero file dependencies; SFX fully reproducible from code |
| `amix normalize=1` (default) | `amix normalize=0` + per-stem loudnorm | STATE.md decision | Preserves ducking ratios; prevents normalization from defeating sidechaincompress |
| Speaker diarization (pyannote.audio) | SSAEvent.name counter (ASS) + fallback (SRT) | Out of Scope (REQUIREMENTS.md) | Avoids CUDA 12 requirement; subtitle-attributed speaker ID is sufficient for protagonist VO |
| `volume` filter for ducking | `sidechaincompress` | Phase 10 design | Smooth attack/release curves instead of step-function volume changes |

**Deprecated/outdated:**
- `amerge` filter for multi-stem mix: use `amix` instead — `amerge` sums channels within streams (for upmixing) not mixing separate streams together
- `-ss` after `-i` for audio extraction: "input-seeking" seeks to the nearest keyframe, causing inaccurate cut points; always use output-seeking (`-ss` before `-i`) for accurate extraction

---

## Integration Points with Phase 9 Output

Phase 10 consumes outputs from Phase 9:
- `work_dir/music_bed.mp3` (or `~/.cinecut/music/{vibe}.mp3`) — the downloaded Jamendo track for the music stem
- `TrailerManifest.bpm_grid` — beat timestamps for SFX alignment (SFX placed at beat-aligned cut positions from Phase 9)
- `TrailerManifest.clips[*].transition` — `"hard_cut"` vs `"crossfade"` / `"fade_to_black"` determines which SFX tier (SFXL-02: 0.4s vs 1.2s)
- Act boundary detection: Phase 8 `narrative_zone` field identifies ESCALATION→CLIMAX boundary position for act-boundary SFX

Phase 10 produces:
- Two SFX WAV files in `work_dir/sfx/` (synthesized once, reused)
- Up to 3 VO AAC clips in `work_dir/vo/` (protagonist dialogue clips)
- Final mixed trailer MP4 (replaces Pass 2 concat output with four-stem audio)

### Conform Pipeline Pass Structure (after Phase 10)

```
Pass 1: extract_and_grade_clip() × N    — existing: clip extraction + LUT + loudnorm
Pass 2: concatenate_clips()             — existing: concat demuxer → trailer_concat.mp4
Pass 3: sfx + vo overlay               — NEW: synthesize_sfx_files(), extract_vo_clips()
Pass 4: mix_four_stems()               — NEW: sidechaincompress + amix → trailer_final.mp4
```

Pass 3 and Pass 4 operate on the `trailer_concat.mp4` from Pass 2, not on individual clips. This avoids re-processing each clip separately for audio and keeps the filtergraph manageable.

---

## Open Questions

1. **SFX beat-aligned positioning vs. fixed cut-point positioning**
   - What we know: SFXL-01 says "at each scene cut transition"; Phase 9 BPM grid snaps clip start points to beats
   - What's unclear: Should SFX be placed at the exact `source_start_s` of each clip in the timeline, or at the beat-snapped position? (Difference is within ±1 beat, typically < 0.1s)
   - Recommendation: Use the beat-snapped clip start position (from the assembled manifest's clip ordering). This ensures SFX lands exactly on the beat, which is the perceptually correct position.

2. **sidechaincompress parameter tuning**
   - What we know: STATE.md explicitly documents "FFmpeg audio filtergraph parameter tuning requires empirical validation against real film audio — treat as implementation-time iteration"
   - What's unclear: Optimal `threshold`, `attack`, `release` values vary significantly by film genre and loudness profile
   - Recommendation: Starting values `threshold=0.025:ratio=6:attack=100:release=600` (research-derived); document these as `DUCK_THRESHOLD`, `DUCK_RATIO`, `DUCK_ATTACK_MS`, `DUCK_RELEASE_MS` named constants in `audio_mix.py` for easy tuning.

3. **VO selection when protagonist has no lines in Act 1 zone**
   - What we know: VONR-02 says "1 in Act 1, up to 2 in Act 2" — but the protagonist may have few lines in the BEGINNING zone
   - What's unclear: Fall back to any protagonist line from the full film when no Act 1 match? Or skip Act 1 VO?
   - Recommendation: If no protagonist subtitle event falls within the BEGINNING zone timestamps, skip Act 1 VO (result: 0 Act 1 VO clips). Do not reach outside the assembled clips' time range, as that could introduce anachronistic audio.

4. **SFX overlap with existing film audio at cut points**
   - What we know: Film audio is already loudnorm-normalized as part of the clip extraction
   - What's unclear: SFX placed exactly at a cut point will overlap with the ambient sound of both clips
   - Recommendation: Position SFX WAV at `cut_position_s - (sfx_duration / 4)` so the sweep peaks at the cut point rather than starting at it. This matches how SFX is used in professional trailer editing.

---

## Sources

### Primary (HIGH confidence)
- FFmpeg official filters documentation (ffmpeg.org/ffmpeg-filters.html) — aevalsrc parameters, sidechaincompress, amix normalize, adelay
- FFmpeg aevalsrc source code (github.com/FFmpeg/FFmpeg/blob/master/libavfilter/aeval.c) — confirmed: `c` for channel_layout, `|` for channel separation in exprs, `s` for sample rate
- FFmpeg sidechaincompress docs v8.0 (ayosec.github.io/ffmpeg-filters-docs/8.0/Filters/Audio/sidechaincompress.html) — confirmed: threshold/ratio/attack/release/makeup parameters
- FFmpeg amix docs v8.0 (ayosec.github.io/ffmpeg-filters-docs/8.0/Filters/Audio/amix.html) — confirmed: `normalize=0`, `weights` parameter syntax
- pysubs2 1.8.0 API reference (pysubs2.readthedocs.io/en/latest/api-reference.html) — confirmed: `SSAEvent.name` is "Actor name" field; auto-detect format on `pysubs2.load()`
- Project STATE.md — hard constraint: `amix normalize=0` is MANDATORY; sidechaincompress params require empirical tuning

### Secondary (MEDIUM confidence)
- FFmpeg mailing list sidechaincompress example (gist.github.com/mhavo/533fa9586bdd090836116bac71c769f0) — confirmed sidechaincompress filtergraph syntax; cross-referenced with official docs
- FFmpeg filter guide sidechaincompress examples (ffmpeg.media/articles/extract-replace-mix-audio-tracks) — multi-stem mixing patterns verified against official docs
- Chirp signal theory (gaussianwaves.com) — confirmed phase integral formula for linear chirp: `sin(2*PI*(f0 + slope*t)*t)` with `slope = (f1-f0)/(2*d)`

### Tertiary (LOW confidence)
- Starting values for sidechaincompress parameters (threshold=0.025, ratio=6, attack=100, release=600) — derived from community examples; STATE.md explicitly notes these require empirical validation; treat as starting point only

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pure FFmpeg + stdlib + already-installed pysubs2; zero new dependencies
- Architecture: HIGH — three-module pattern mirrors existing phase structure; Pass 3/Pass 4 conform extension is clean integration point
- Pitfalls: HIGH — adevalsrc chirp formula, adelay milliseconds vs. seconds, normalize=0 constraint all verified via official docs and source code
- sidechaincompress params: LOW — values need empirical tuning per STATE.md; starting values are community-sourced

**Research date:** 2026-02-28
**Valid until:** 2026-08-28 (stable domain — FFmpeg audio filtergraph API is very stable; pysubs2 1.8.0 is pinned in pyproject.toml)
