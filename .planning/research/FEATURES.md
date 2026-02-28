# Feature Landscape

**Domain:** AI-driven video trailer generation — v2.0 Structural & Sensory Overhaul
**Researched:** 2026-02-28
**Confidence:** MEDIUM-HIGH (WebSearch verified against industry sources; BPM detection verified via librosa official docs; ducking thresholds from multiple production sources)

> **Scope note:** This document covers ONLY the eight v2.0 features. The v1.0 table stakes
> (beat classification, money shot scoring, manifest generation, vibe profiles, LUT pipeline,
> audio normalization, FFmpeg conform) are already built and are NOT re-researched here.

---

## Table Stakes (v2.0)

Features that, if missing, make the v2.0 milestone fail to deliver its stated goal
("transform the flat chronological highlight reel into a dramatically structured, sonically layered trailer").

| Feature | Why Expected | Complexity | v1 Dependency | Notes |
|---------|--------------|------------|---------------|-------|
| Non-linear scene ordering | Without zone-based resequencing, clips remain chronological — the core v2 promise is broken | High | Beat classifier (7 types), 3-act manifest | Zone tags (BEGIN/ESCALATION/CLIMAX) assigned by LLM; assembly pulls from each zone non-chronologically |
| BPM-driven cut timing | Human editors always sync cuts to music beats; without this, edit rhythm feels random | Medium | Edit Profiles (existing pacing curves) | librosa `beat_track()` generates beat timestamps; clip durations snapped to beat grid |
| Music bed per vibe | Silence during the trailer is the wrong default; music carries emotional vibe | Medium | 18 vibe profiles | Royalty-free archive; vibe-matched selection (not genre-matched — vibe IS the selection key) |
| SceneDescription persistence | Without it, any crash forces 30-60 min full re-inference of Stage 4 | Low | Stage 4 inference pipeline | JSON cache keyed by source file hash + timestamp range; written atomically (tempfile + os.replace) |
| Three-act segmentation with zone labels | LLM must assign BEGIN_T / ESCALATION_T / CLIMAX_T semantic zones before scene matching | High | Text-only subtitle parsing stage | Stage 1 of the two-stage pipeline; pure text (no vision) for speed |

---

## Differentiators (v2.0)

Features that make the output distinguishable from a basic clip reel — the "sensory layer."

| Feature | Value Proposition | Complexity | v1 Dependency | Notes |
|---------|-------------------|------------|---------------|-------|
| Dynamic music ducking | Music auto-attenuates during high-emotion shots so dialogue/VO is intelligible; swells at visual peaks | Medium | LUFS normalization (existing) | Target: -12 dB duck during VO/dialogue clips; attack 100ms, release 300ms via FFmpeg sidechaincompress |
| Silence / breathing room segments | Deliberate 3–5s quiet gaps before climax; creates contrast so the following hit lands harder ("stopdown") | Low | 3-act assembly | 1–2 silence segments per trailer; placed at act 2→3 boundary and optionally after inciting incident |
| SFX transitions (synthesized) | Whoosh/swoosh on cuts adds professional cinematic texture without external SFX files | Medium | FFmpeg lavfi (existing) | Hard cuts get sharp high-freq sweep; dissolves get slower broad mid sweep; synthesized via `aevalsrc` chirp |
| Hero VO narration | Protagonist dialogue extracted from film audio gives a "voice of the film" layer — not a hired narrator | High | Subtitle timestamps, FFmpeg audio extract | Acts 1 and 2 only; 2–3 lines maximum; EQ treatment (mild reverb, low-pass warmth) |
| Two-stage LLM pipeline | Separates structural analysis (text) from scene matching (vision+text) — higher accuracy, faster overall | High | llama-server (existing), beat types | Stage 1: subtitle-only structural analysis → zone tagging; Stage 2: zone-tagged manifest drives scene matching |

---

## Anti-Features

Features to explicitly NOT build for v2.0. These represent scope risks, dead-ends, or requirements that contradict existing constraints.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| External SFX file library | No royalty-free SFX bundling; adds distribution/license burden | Synthesize all SFX via FFmpeg `aevalsrc` chirp + `phaser` filter — no external files |
| Real hired VO / TTS narrator | Cloud TTS violates local-only constraint; local TTS (flite, espeak) sounds obviously synthetic and breaks immersion | Extract protagonist dialogue from film audio at SRT timestamps — "voice of the film" approach |
| Per-frame BPM sync | Snapping every single frame to a beat is over-engineering; trailers allow ±10% timing flex | Snap clip START points to beat grid; allow clip natural duration within ±1 beat tolerance |
| Music generation / AI composition | Generative music is a separate discipline; CUDA 11.4 / K6000 cannot run audio diffusion models | Use royalty-free pre-composed tracks from Freesound or CCHD-licensed archive |
| Speaker diarization for protagonist detection | Full speaker diarization (pyannote.audio) requires PyTorch >= 1.x + CUDA 12 — incompatible with CUDA 11.4 stack | Use subtitle dialogue frequency heuristic: count unique-name occurrences in SRT/ASS speaker tags; fall back to dialogue line count |
| Coreference resolution / NLP entity linking | SpaCy / BookNLP dependency chain is heavy; adds 500MB+ to install | Protagonist = character name appearing in the most subtitle dialogue lines (simple tally, no NLP library) |
| Dissolve/fade transitions (visual) | v1 already has transition style per Edit Profile; adding dissolve SFX couples audio and video editing steps | Keep visual transitions in Edit Profile; SFX layer is audio-only overlay, separate from video transition type |
| Interactive music waveform editor | CLI-only by project constraint | All music sync is algorithmic; `--review` manifest inspection covers human override |
| Variable-tempo BPM stretching | Time-stretching music to fit trailer duration adds rubato artifacts | Cut/loop music to fit; do not stretch |

---

## Feature Dependency Graph

```
[v1: subtitle parsing]
    └─→ [v2: Zone tagging (Stage 1 LLM)] ──→ [v2: Non-linear ordering]
                                                      │
                                          [v1: beat classifier] ──→ [v2: Zone assignment per beat]

[v2: Music bed (vibe-matched)] ──→ [v2: BPM extraction (librosa)]
                                          │
                                   [v2: Beat grid] ──→ [v2: Cut timing snap]
                                                              │
                                                    [v2: SFX on transitions]

[v2: Music bed] ──→ [v2: Dynamic ducking] ──→ [v2: Hero VO extraction]

[v2: Silence segments] ← placed by [v2: Three-act segmentation] (act 2→3 boundary)

[v1: Stage 4 inference] ──→ [v2: SceneDescription persistence] (crash-safe resume)
```

---

## Feature Details

### Feature 1: Non-Linear Scene Ordering

**How professional editors do it:**
Trailer editors do not follow film chronology. They work from semantic zones: introduce the world (BEGINNING), escalate stakes (ESCALATION), detonate (CLIMAX). Juxtaposition is the core editorial tool — audiences derive meaning not from individual shots but from the relationship between adjacent shots. A sad scene cut next to a violent scene reads as consequence; the same sad scene cut next to a celebration reads as irony.

The standard algorithmic approach (per academic trailer generation research including TRAILDREAMS 2025):
1. Model narrative as a graph: nodes = shots, edges = semantic similarity
2. Classify each node into a semantic zone
3. Traverse the zone graph to build the sequence: all BEGIN nodes → ESCALATION nodes → CLIMAX nodes
4. Within each zone, order by emotional arc (low → high intensity) not by film timestamp

**CineCut implementation approach:**
- Stage 1 LLM (text-only, subtitle input) outputs zone labels: `BEGIN_T` / `ESCALATION_T` / `CLIMAX_T`
- Stage 2 (existing LLaVA) assigns each scene to a zone via manifest field `semantic_zone`
- Assembly sorts clips by: `zone_order[zone] * 1000 + emotional_score` (not `timestamp`)
- Within CLIMAX zone, money shots (highest 8-signal scores) go last

**Complexity:** High — requires manifest schema change (add `semantic_zone` field), Stage 1 LLM integration, assembly rewrite

**Confidence:** HIGH — well-documented in both professional editing practice and 2025 academic literature

---

### Feature 2: BPM Grid / Beat Map Editing

**How professional editors do it:**
Editors drop markers on every beat of the music track in the NLE (Premiere, Resolve). Each clip START point is aligned to a beat marker. The "pulse" is the music; clips are cut to that pulse.

Standard workflow:
1. Analyze music track → extract BPM + beat timestamps array
2. Build a beat grid: `[0.0, 0.5, 1.0, 1.5, ...]` seconds (for 120 BPM)
3. Per act, target average clip length in beats (Act 1: 4-8 beats per clip; Act 3: 1-2 beats per clip)
4. Assign each clip an OUT point = next beat marker after minimum duration threshold

**BPM detection approach (Python):**
`librosa.beat.beat_track()` — dynamic programming beat tracker. Returns `(tempo, beat_frames)`. Convert frames to seconds with `librosa.frames_to_time(beat_frames, sr=sr)`. Handles variable-tempo tracks.

For music without strong beats (ambient/drone tracks for Horror/Drama vibes): fall back to fixed interval grid based on estimated BPM from `librosa.beat.tempo()`.

**Beat grid application:**
- Each act has an avg_cut_beats target (derived from existing Edit Profile avg_cut_length_sec + BPM)
- Clip durations are snapped: `clip_duration = round(clip_natural_duration / beat_interval) * beat_interval`
- Tolerance: ±1 beat (i.e., if a clip is 1.8 beats, round to 2 beats, not 1)

**Complexity:** Medium — librosa is a well-understood library; beat grid math is straightforward; the main work is integrating beat timestamps into the assembly pass

**Confidence:** HIGH — librosa 0.11.0 docs confirm `beat_track()` returns timestamps; widely used in editor tooling

---

### Feature 3: Dynamic Music Mixing (Auto-Ducking)

**How professional mixers do it:**
Music ducks (volume drops) when foreground audio (dialogue, VO, or high-emotion scene audio) is present. Sidechain compression is the standard technique: the foreground audio signal triggers gain reduction on the music bus.

**Standard parameters (from production sources):**
- Duck amount: **-12 dB** (default; subtle); **-18 dB** (voice clarity in noisy scenes)
- Attack time: **50–150ms** (fast enough to catch dialogue onset; slow enough not to pump)
- Release time: **200–500ms** (gradual enough to not feel like a jump)
- Threshold: **-20 dB** (music starts ducking when foreground signal exceeds this)
- Ratio: **3:1 to 6:1**

**CineCut implementation via FFmpeg:**
FFmpeg `sidechaincompress` filter supports sidechain ducking:
```
ffmpeg -i music.wav -i foreground.wav \
  -filter_complex "[1:a]asplit=2[sc][mix]; \
  [0:a][sc]sidechaincompress=threshold=0.02:ratio=4:attack=100:release=300[compressed]; \
  [compressed][mix]amix=inputs=2[out]" \
  -map "[out]" output.wav
```

**Vibe-based ducking profiles:**
- Action/Thriller: light ducking (-12 dB) — music dominates
- Drama/Romance: heavy ducking (-18 dB) — dialogue intelligibility critical
- Horror: asymmetric — duck during silence segments; swell on climax

**Music swells on visual peaks:**
Money shots (highest 8-signal score) trigger a music swell by NOT ducking — the music runs at full level during the highest-intensity clip. This creates the "big moment" feel.

**Complexity:** Medium — FFmpeg sidechaincompress is well-supported; the complexity is determining WHEN to duck (requires manifest-driven decision: clips with `dialogue=True` trigger duck)

**Confidence:** MEDIUM-HIGH — ducking parameters from multiple production sources; FFmpeg sidechaincompress filter exists but CUDA 11.4 audio compatibility should be verified in implementation

---

### Feature 4: Silence / Breathing Room

**How professional editors use it:**
Silence is an active editorial choice — not absence of content. The "stopdown" technique (Derek Lieu, professional game trailer editor) cuts music AND sound design for 1–6 seconds before a major impact. The silence makes the subsequent hit feel 2–3× louder by contrast.

**Placement rules:**
- **Act 2 → Act 3 boundary**: 3–5s silence before the CLIMAX montage. This is the most impactful placement.
- **After inciting incident** (optional, vibe-dependent): 1–2s pause after the "world-changing" moment. Used in Drama/Thriller vibes.
- **NEVER during Act 3 CLIMAX montage**: The rapid-cut montage must not be broken by silence.

**Duration guidance:**
- Minimum: 1.5s (shorter reads as a glitch, not intention)
- Standard: 3–4s (one full breath; feels deliberate)
- Maximum: 5s (beyond this, audience attention drifts)

**Silence segment implementation:**
A silence segment is a lavfi black video + silent audio clip:
```
ffmpeg -f lavfi -i color=c=black:s=1920x1080:r=24 \
       -f lavfi -i anullsrc=r=48000:cl=stereo \
       -t 3.5 silence_segment.mp4
```
This is identical to the existing `title_card` lavfi implementation in v1.

**Complexity:** Low — silence segments use the same lavfi pattern as existing title_card/button clips; placement logic requires act boundary detection (already in 3-act assembly)

**Confidence:** HIGH — "stopdown" technique well-documented by professional trailer editors; duration range (3–5s) confirmed across multiple sources

---

### Feature 5: SFX Transitions (Synthesized)

**What professional sound designers use:**
Trailers use the category "cinematic whoosh/swoosh" — a fast-moving, wide-bandwidth sound that bridges two cuts. The key insight from professional trailer audio: sub-bass is pushed hard, reverb tails stretch for seconds, and intensity varies with the cut type.

**Whoosh taxonomy:**
| Cut Type | SFX Character | Frequency Focus | Duration |
|----------|--------------|-----------------|----------|
| Hard cut (CLIMAX montage) | Sharp, fast, high-freq | 2kHz–8kHz sweep | 0.3–0.5s |
| Title card hit | Bass impact + mid sweep | 200Hz–4kHz | 0.5–0.8s |
| Act boundary transition | Broad, dramatic | Full-spectrum sweep + reverb tail | 0.8–1.5s |
| Dissolve (slower cut) | Soft, low-to-mid | 300Hz–2kHz | 0.6–1.0s |

**FFmpeg synthesis approach:**
Whoosh = frequency-swept sine (chirp) + phaser + reverb tail. FFmpeg `aevalsrc` can generate a chirp:
```bash
# High-freq hard-cut whoosh (~0.4s, 800Hz → 6kHz sweep)
ffmpeg -f lavfi \
  -i "aevalsrc=sin(2*PI*(800+5200*t/0.4)*t):s=44100:d=0.4" \
  -af "phaser=in_gain=0.4:out_gain=0.74,aecho=0.8:0.88:60:0.4" \
  whoosh_hard.wav
```
The chirp frequency ramps from 800Hz to 6kHz over 0.4 seconds, with phaser for motion and aecho for tail.

**Intensity mapping:**
- `beat_type == "Climax"` → sharp hard-cut whoosh
- `beat_type == "Money Shot"` → bass impact variant
- `transition_style == "dissolve"` → soft mid-sweep
- Act boundary cut → dramatic full-spectrum variant

**Anti-pattern:** Do NOT use the same whoosh on every cut — frequency variety prevents mud. Fast high-freq cuts, broader mid-freq for slower transitions.

**Complexity:** Medium — chirp synthesis is achievable in FFmpeg; the main work is parameterizing intensity per beat type and building a small synthesizer function that generates 4 whoosh variants ahead of time

**Confidence:** MEDIUM — FFmpeg `aevalsrc` chirp synthesis confirmed; phaser/aecho filters available; specific parameter tuning will require iteration at implementation time

---

### Feature 6: Hero Character VO Narration

**What professional trailers do:**
Modern trailers (post-2010) increasingly use protagonist IN-CHARACTER dialogue rather than an external "in a world" narrator. This is the "voice of the film" approach — the protagonist's actual voice, extracted from the film, creates authenticity.

**Placement:**
- Act 1 (BEGINNING): 1 line — establishes character voice, stakes, or world
- Act 2 (ESCALATION): 1–2 lines — deepens conflict or reveals character motivation
- Act 3 (CLIMAX): NO VO — the CLIMAX montage is pure visual/music/SFX; VO would dilute impact

**Duration limits:**
- Maximum: 3 lines total across the full trailer
- Per-line duration: ≤ 8 seconds (audiences won't follow long dialogue passages in a trailer)
- Natural audio pause before/after each line: 0.3–0.5s silence head/tail

**Audio treatment:**
- Normalize to -16 LUFS (slightly hotter than music bed, which sits at -18 to -20 LUFS during VO)
- Low-shelf boost: +2–3 dB at 200Hz (warmth; removes tinniness of extracted audio)
- High-pass filter: 80Hz roll-off (removes rumble from film audio)
- Light room reverb: 15–20ms pre-delay, 0.8–1.2s decay (adds "cinematic space" without sounding processed)
- No pitch shifting — preserve authentic voice

**Extraction approach:**
1. Protagonist detection: count dialogue lines per named character in SRT/ASS file (most lines = protagonist; works because SRT speaker tags or ASS dialogue actor field contain character names)
2. Select 3 highest-impact dialogue timestamps from protagonist (selection criteria: lines where the scene's beat_type is Inciting Incident or Rising Action AND line length ≥ 6 words)
3. Extract audio: `ffmpeg -i source.mkv -ss [start] -t [duration] -vn -acodec pcm_s16le vo_line.wav`
4. Apply EQ/reverb treatment via FFmpeg `equalizer` + `aecho` filters

**Protagonist detection heuristic (SRT files without speaker tags):**
SRT files rarely have speaker tags. For SRT format, the protagonist detection falls back to the two-stage LLM: Stage 1 structural analysis outputs `protagonist_name` as part of its zone-tagging pass (the LLM identifies who the story is about from subtitle text). This name is then used to search for matching dialogue lines.

**Complexity:** High — protagonist detection requires LLM cooperation; audio extraction is straightforward FFmpeg; the EQ treatment is medium complexity; the hardest part is selecting the RIGHT 3 lines (emotional impact scoring)

**Confidence:** MEDIUM — VO placement rules from professional trailer analysis; audio treatment parameters from film mixing standards; protagonist detection via LLM is novel but consistent with Stage 1 pipeline design

---

### Feature 7: Two-Stage LLM Pipeline

**What it solves:**
v1 uses a single LLaVA pass for all scene analysis. This conflates structural narrative understanding (what is this story about? what are the zones?) with visual scene analysis (what is in this frame?). Separating them:
1. Reduces hallucination — text-only Stage 1 doesn't confuse visual content with narrative arc
2. Speeds up Stage 1 — no image loading; pure text is fast
3. Allows Stage 2 to receive zone context, improving beat classification accuracy

**Stage 1: Structural Analysis (text-only)**
- Input: Full subtitle text (or first 30% for long films)
- Model: Text-only LLaVA inference via llama-server (same endpoint, no image attachment)
- Output JSON:
  ```json
  {
    "protagonist_name": "Sarah",
    "zone_boundaries": {
      "BEGIN_T": {"start_pct": 0, "end_pct": 28},
      "ESCALATION_T": {"start_pct": 28, "end_pct": 72},
      "CLIMAX_T": {"start_pct": 72, "end_pct": 100}
    },
    "theme": "survival thriller",
    "inciting_incident_timestamp": "00:14:32"
  }
  ```

**Stage 2: Scene Matching (existing LLaVA vision)**
- Input: Keyframe images + zone context from Stage 1
- Each scene analysis prompt includes: "This scene is from the [ESCALATION] zone of a [survival thriller]. Classify..."
- Output: same beat classification as v1, but zone-aware

**Implementation note:**
llama-server text-only mode = send the `/completion` endpoint with the subtitle text as prompt, omitting the `image_data` field. This is already supported by the v1 `requests`-based client.

**Complexity:** High — requires new Stage 1 prompt engineering, output schema validation (Pydantic), and integration into the existing pipeline stage ordering

**Confidence:** HIGH — llama-server supports text-only completion; the two-stage pattern matches TRAILDREAMS 2025 research; JSON output from LLaVA is established in v1

---

### Feature 8: SceneDescription Persistence

**What it solves:**
v1 re-runs full LLaVA inference (30–60 min) on every crash resume. Persistence means the pipeline can resume from the last-completed scene.

**Implementation:**
- Cache file: `.cinecut_cache/{source_hash}_{vibe}.scenes.json`
- Key: `f"{source_file_sha256[:12]}_{start_ms}_{end_ms}"`
- Value: full `SceneDescription` Pydantic model serialized to JSON
- Write: atomic (tempfile + os.replace, same pattern as existing atomic checkpoint)
- Read: on Stage 4 start, load cache; skip inference for any key that exists; only run inference for missing keys
- Invalidation: cache is keyed to source file hash — any change to source file invalidates automatically

**Complexity:** Low — straightforward file I/O with atomic writes; Pydantic `.model_dump_json()` handles serialization; the existing atomic checkpoint pattern can be reused directly

**Confidence:** HIGH — standard cache-aside pattern; no novel technology required

---

## Feature Dependencies on v1

| v2 Feature | Requires from v1 |
|------------|-----------------|
| Non-linear ordering | Beat classifier output (`beat_type`), 3-act assembly ordering hooks |
| BPM grid | Edit Profiles (avg_cut_length_sec per act), FFmpeg audio extraction |
| Dynamic ducking | FFmpeg audio pipeline, LUFS normalization (existing) |
| Silence segments | lavfi black+null clip generation (same as title_card/button) |
| SFX transitions | FFmpeg lavfi filter chain (existing), beat_type field in manifest |
| Hero VO | Subtitle timestamps, FFmpeg audio extraction, Stage 1 LLM output (protagonist_name) |
| Two-stage LLM | llama-server HTTP client (existing), Pydantic manifest schema |
| SceneDescription persistence | Stage 4 inference loop, Pydantic SceneDescription model |

---

## MVP Recommendation for v2.0

**Must ship (breaks the milestone promise if missing):**
1. SceneDescription persistence — immediate pain relief; no dependencies on other v2 work; do this first
2. Two-stage LLM pipeline + Zone tagging — all non-linear ordering depends on this
3. Non-linear scene ordering — the core narrative claim of v2.0
4. Music bed (vibe-matched) — silence is worse than imperfect music

**Ship second (differentiators that require core to be stable):**
5. BPM grid / beat map — requires music bed to exist
6. Dynamic ducking — requires music bed to exist
7. Silence segments — requires 3-act boundary detection (comes from zone tagging)
8. SFX transitions — can be added to the FFmpeg conform pass independently

**Ship last (high complexity, standalone):**
9. Hero VO narration — depends on Stage 1 protagonist detection; EQ tuning is iterative

**Defer to v2.1 or later:**
- VO line quality scoring (beyond simple line-count heuristic)
- Per-scene SFX intensity calibration (can start with fixed intensity tiers)
- Music archive management (auto-download on first use) — v2.0 can use a manually provided music directory

---

## Sources

- TRAILDREAMS (2025): https://www.ojcmt.net/download/trailer-reimagined-an-innovative-llm-driven-expressive-automated-movie-summary-framework-traildreams-16669.pdf [HIGH confidence — peer-reviewed 2025 research on LLM-driven trailer generation]
- Derek Lieu — Trailer Sound Design: https://www.derek-lieu.com/blog/2022/1/17/secrets-to-trailer-sound-design [HIGH confidence — professional trailer editor]
- Derek Lieu — Three-Act Structure: https://derek-lieu.medium.com/the-matrix-and-movie-trailer-3-act-structure-b06a68e01214 [HIGH confidence]
- Rareform Audio — Trailer Drop vs Stopdown: https://www.rareformaudio.com/blog/trailer-music-drop-vs-stopdown [MEDIUM confidence — specialized audio production source]
- Nathan Fields Music — Three-Act Trailer Music: https://www.nathanfieldsmusic.com/blog/three-act-structure-trailer-music [MEDIUM confidence]
- librosa 0.11.0 beat_track docs: https://librosa.org/doc/main/generated/librosa.beat.beat_track.html [HIGH confidence — official docs]
- Adobe Audition Auto-Ducking: https://blog.adobe.com/en/publish/2017/11/02/audition-deep-dive-auto-ducking-music [MEDIUM confidence — parameter references]
- iZotope — Audio Ducking: https://www.izotope.com/en/learn/what-is-audio-ducking [MEDIUM confidence]
- Pixflow — Cinematic Whoosh SFX: https://pixflow.net/blog/cinematic-whoosh-sound-effects/ [MEDIUM confidence — industry practice reference]
- Automatic Character Type Identification from Film Dialogs (ResearchGate): https://www.researchgate.net/publication/314447117_Automatic_Identification_of_Character_Types_from_Film_Dialogs [MEDIUM confidence — academic]
- Epikton — Trailer Pacing 2025: https://epikton.net/a-quick-guide-to-pacing-in-trailers/ [MEDIUM confidence]
- Film Editing Pro — Trailers, Teasers & Promos: https://www.filmeditingpro.com/trailers-teasers-promos-lengths-formats-tips/ [MEDIUM confidence]
