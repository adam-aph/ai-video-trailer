# Feature Landscape

**Domain:** AI-driven video trailer generation from feature films
**Researched:** 2026-02-26
**Confidence:** MEDIUM (training data only -- WebSearch unavailable during this session; domain knowledge sourced from film editing literature and trailer production conventions in training corpus)

---

## Table Stakes

Features users expect. Missing = product feels incomplete or produces unusable output.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Three-act trailer structure | Every professional trailer follows Setup / Escalation / Climax+Title. Without it, output feels like a random clip reel. | High | See "Standard 2-Minute Trailer Structure" below |
| Subtitle-driven narrative extraction | SRT/ASS is the densest narrative signal. Without parsing dialogue for story beats, clip selection is blind. | Medium | Keyword scoring + sentence-level sentiment |
| Keyframe visual analysis | Dialogue alone misses action sequences, landscapes, visual reveals. Vision model fills the gap. | High | LLaVA via llama-cli per project constraints |
| Genre-aware edit pacing | A horror trailer cut at action-movie pace feels wrong. Per-genre timing profiles are fundamental. | Medium | See 18 Edit Profiles below |
| JSON manifest output | The manifest IS the product -- it is the machine-readable edit decision list. Without it, no human override, no debugging, no iterability. | Medium | See TRAILER_MANIFEST.json Schema below |
| Frame-accurate seeking | Off-by-one-second cuts destroy continuity and feel amateur. Must use FFmpeg `-ss` before `-i` pattern. | Low | Well-documented FFmpeg technique |
| Audio level normalization | Clips from different scenes have wildly different levels. Uneven audio = amateur output. | Low | LUFS-based per-vibe targeting via FFmpeg loudnorm |
| High-res conform from original source | Analysis on proxy, render on original. Output must match source quality or the tool is pointless. | Medium | Core three-tier pipeline architecture |
| Transition handling | Hard cuts alone feel like a rough assembly. Minimum viable set: hard cut, crossfade, fade-to-black, dip-to-black. | Low | FFmpeg filter graph |
| Title card / end slate timing | Trailer without a title card is not a trailer. Standard placement: movie title at ~1:45-1:55 of a 2:00 trailer. | Low | Template-based text overlay |
| Vibe selection via CLI flag | Core UX promise -- `--vibe horror` must Just Work | Low | Enum validation, clear error on invalid vibe |
| SRT + ASS subtitle format support | Both formats are standard in the media ecosystem | Low | pysubs2 handles both natively |
| Progress indication | Pipeline runs minutes to hours. User needs feedback or they will kill the process. | Low | Rich progress bars on FFmpeg and inference |
| Actionable error messages | FFmpeg and llama-cli failures are cryptic. Must translate to human-readable guidance. | Medium | Catch subprocess errors, provide fix suggestions |

## Differentiators

Features that set this tool apart from naive "random interesting clips" approaches.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Narrative beat detection (7 beat types) | Produces trailers with actual story arcs, not random impressive clips. This is what separates a trailer from a highlight reel. | High | See "Narrative Beat Framework" below |
| 18 genre-specific vibe edit profiles | Not just pacing -- color grading (LUT), audio treatment, transition style, and structural emphasis all shift per genre. | High | See detailed profiles below |
| Money shot quality scoring | AI identifies the most visually striking frames using motion, contrast, composition, and narrative weight signals. | High | Multi-signal scoring system |
| Subtitle emotional keyword extraction | Maps dialogue to emotional arcs: threat words, romantic language, comedic beats, revelation phrases. | Medium | Keyword dictionaries + sentiment scoring |
| `--review` manifest editing workflow | Human-in-the-loop without breaking the pipeline. Edit JSON, re-run conform. Professional editors will demand this. | Low | Already in project spec |
| LUT-based color grading per vibe | Teal-orange for action, desaturated for war, warm for romance. Visual coherence across clips from different scenes. | Medium | .cube files applied via FFmpeg lut3d |
| Audio ducking for dialogue clips | When a clip contains dialogue, music should duck. When it is visual-only, music stays full. | Medium | FFmpeg sidechain or loudnorm filter |
| Pacing curve within trailer | Not constant pace -- trailers accelerate. Act 1 is slow, Act 3 is rapid-fire before the resolve. | Medium | Cut duration as function of position in timeline |
| Hybrid keyframe strategy | Subtitle-midpoint + scene-change + interval fallback catches both dialogue and visual spectacle | Medium | Three extraction strategies composed |
| Beat reasoning in manifest | Each clip documents WHY it was selected. Enables meaningful human review rather than guesswork. | Low | `beat_reasoning` field per clip |

## Anti-Features

Features to explicitly NOT build in v1. Each has a clear reason.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Music generation or selection | Enormous scope creep. Music licensing is a legal minefield. AI music generation is a separate domain entirely. | Accept user-provided music track via optional flag. Default: use source audio from selected clips. |
| Voiceover / narration generation | TTS quality for trailer narration ("In a world...") requires specialized models and sounds terrible when wrong. | Extract compelling dialogue from the film via subtitle timestamps instead. |
| Real-time preview | Requires video player integration, timeline UI, massive engineering effort. Contradicts CLI-first design. K6000 cannot render + infer simultaneously. | Manifest-based workflow: generate JSON, optionally review, render once. |
| Subtitle generation / STT | Out of scope per PROJECT.md. User always provides subtitles. Adding STT adds huge complexity and a failure mode. | Require SRT/ASS input. Error clearly if missing. |
| Multi-language subtitle support | Subtitle parsing in non-Latin scripts, sentiment analysis in other languages -- each multiplies complexity. | Support English subtitles in v1. Document as future extension point. |
| Automatic poster/thumbnail generation | Different domain (still image composition). Distracts from core trailer generation. | Out of scope entirely. |
| Social media format variants (vertical, square) | Aspect ratio reframing requires subject detection and smart cropping -- a separate hard problem. | Output at source aspect ratio only. |
| Custom transition effects (wipes, glitch, star-wipes) | Beyond the 4 core transitions, each new effect is diminishing returns with high implementation cost. Tacky if done poorly. | Stick to: hard cut, crossfade, fade-to-black, dip-to-white. Genre profiles select from these. |
| Scene-level dialogue re-ordering | Rearranging dialogue out of film order risks narrative incoherence and is extremely hard to validate automatically. | Preserve chronological order within each act. Allow out-of-order only for money shots in Act 3 montage. |
| Web/GUI interface | Scope creep. CLI is the product per constraints. | Rich terminal output with progress bars and color. |
| Cloud inference fallback | Local-only is a hard constraint per PROJECT.md. | Document hardware requirements clearly. |
| Custom model training/fine-tuning | Massive scope. LLaVA off-the-shelf via llama-cli is the approach. | Prompt engineering over model modification. |

---

## Standard 2-Minute Trailer Structure

Based on professional trailer editing conventions. This three-act structure is the dominant format for theatrical trailers and has been stable for 20+ years.

### The Three-Act Trailer Framework

**Total runtime target: 1:50 - 2:10**

| Section | Timing | Duration | Purpose | Content |
|---------|--------|----------|---------|---------|
| **Cold Open / Hook** | 0:00 - 0:08 | ~8s | Grab attention immediately | 1-2 striking shots. Often the single most visually arresting moment OR a quiet character moment that establishes tone. |
| **Studio Cards** | 0:08 - 0:12 | ~4s | Branding (optional for this tool) | Studio/production logos. Can overlap with audio from cold open. CineCut can skip this or insert a black gap. |
| **Act 1: Setup** | 0:12 - 0:40 | ~28s | Establish world, protagonist, stakes | 4-6 clips. Slower pacing (3-5s per cut). Introduce setting, main character, normal world. Key dialogue that establishes premise. |
| **Beat Drop / Transition** | 0:40 - 0:45 | ~5s | Punctuate shift in tone | Often a music sting, a smash cut to black, or a provocative line of dialogue. Signals "things are about to change." |
| **Act 2: Escalation** | 0:45 - 1:20 | ~35s | Raise stakes, show conflict | 8-12 clips. Medium pacing (2-3.5s per cut). Antagonist reveal, complications, relationships tested, action sequences begin. Music builds. |
| **Breath / False Resolution** | 1:20 - 1:25 | ~5s | Brief pause before final push | Often a quiet emotional beat, a character moment, or a line of dialogue that reframes everything. Dip to black common. |
| **Act 3: Climax Montage** | 1:25 - 1:45 | ~20s | Maximum intensity | 10-20 clips. Rapid-fire pacing (0.5-1.5s per cut). Money shots, action peaks, emotional climaxes. Music at peak intensity. |
| **Title Card** | 1:45 - 1:52 | ~7s | Movie title reveal | Clean title card. Often with a final music sting. |
| **Button / Stinger** | 1:52 - 2:00 | ~8s | Final memorable moment | One last clip -- often humor, a final reveal, or a tension beat. Leaves audience wanting more. |

### Cut Count by Section

| Section | Typical Cut Count | Avg Cut Duration |
|---------|-------------------|-----------------|
| Cold Open | 1-2 | 3-5s |
| Act 1: Setup | 4-6 | 3-5s |
| Act 2: Escalation | 8-12 | 2-3.5s |
| Act 3: Climax Montage | 10-20 | 0.5-1.5s |
| Button | 1-2 | 2-4s |
| **Total** | **24-42 clips** | **Varies by position** |

---

## Narrative Beat Framework

### Validated Framework: Expanding Beyond Inciting Incident / Climax / Money Shots

The three-category framework from PROJECT.md (Inciting Incident, Climax Beats, Money Shots) is a correct starting point but needs expansion for robust trailer generation. Professional trailer editors work with a richer vocabulary. The original three map cleanly to Act 1 (Inciting Incident), Act 3 (Climax), and Cold Open + Act 3 (Money Shots), but Act 2 -- the longest section -- has no beat type assigned.

### Recommended Beat Categories (7 types)

| Beat Type | What It Is | Where It Appears in Trailer | Detection Method |
|-----------|------------|----------------------------|-----------------|
| **World Establishment** | Shots that convey setting, time period, social context | Act 1 (first 2-3 clips) | Vision: wide/establishing shots, low motion, high scene diversity. Subtitles: expository dialogue, place names, time references. |
| **Character Introduction** | First clear shots of protagonist, showing personality/situation | Act 1 | Vision: face detection, medium shots, sustained screen time for one person. Subtitles: character name mentions, self-referential dialogue. |
| **Inciting Incident** | The event that disrupts the status quo and launches the story | Act 1 / Act 2 boundary | Subtitles: shift from neutral to urgent/threatening language. Vision: sudden change in lighting, location, or motion pattern vs. preceding scenes. |
| **Escalation Beats** | Complications, rising stakes, conflict intensification | Act 2 | Subtitles: conflict language, questions, confrontation. Vision: close-ups, fast motion, multiple characters in frame. |
| **Relationship Beats** | Emotional connections -- romance, friendship, betrayal, loyalty | Act 2 (scattered) | Subtitles: emotional keywords (love, trust, betray, together). Vision: two-shots, close-ups, low motion (intimate framing). |
| **Climax Peaks** | Maximum intensity moments -- action peaks, emotional breaking points, revelations | Act 3 | Subtitles: exclamations, short urgent lines, silence (action without dialogue). Vision: high motion vectors, dramatic lighting contrast, rapid camera movement. |
| **Money Shots** | The single most visually spectacular or emotionally devastating moments | Cold Open + Act 3 | Multi-signal: highest combined score across visual spectacle + narrative weight + uniqueness. See Money Shot Scoring below. |

### Why This Framework Over the Original Three

The original three categories map well to the three-act trailer structure but lack granularity for Act 2 (the longest section at ~35 seconds). Without Escalation Beats and Relationship Beats, the middle of the trailer becomes a gap the algorithm cannot fill intelligently. World Establishment and Character Introduction are also distinct from the Inciting Incident -- they are setup, not disruption.

**Recommendation:** Keep the original three as primary categories. Add Escalation Beats, Relationship Beats, World Establishment, and Character Introduction as secondary categories. The AI should tag every candidate clip with one or more beat types, then the trailer assembly algorithm selects clips to fill the structural template.

---

## Money Shot Quality Scoring

A "money shot" is the single most visually impressive or emotionally devastating moment in the film. The AI needs a multi-signal scoring system to identify these because no single signal is sufficient -- an explosion with no narrative context is just noise, and a powerful line of dialogue in a static medium shot may not be visually compelling enough for the cold open.

### Scoring Signals

| Signal | Weight | Detection Method | What It Captures |
|--------|--------|-----------------|-----------------|
| **Motion magnitude** | 0.20 | Frame-diff magnitude between consecutive proxy frames (mean absolute pixel difference) | Explosions, fights, chases, dramatic gestures |
| **Visual contrast** | 0.15 | Histogram spread / standard deviation of luminance channel | Dramatic lighting, silhouettes, fire/darkness juxtaposition |
| **Color saturation peaks** | 0.10 | Average saturation in HSV space relative to film mean | Vibrant moments: sunsets, explosions, neon, blood |
| **Scene uniqueness** | 0.15 | How visually different this keyframe is from the film's average frame (cosine distance of LLaVA embedding or simpler pixel histogram distance) | Unusual locations, VFX sequences, dream sequences |
| **Face presence + emotion** | 0.10 | LLaVA description mentioning faces, expressions, close-ups | Close-up emotional performances, villain reveals |
| **Subtitle emotional weight** | 0.15 | Keyword matching against emotional dictionaries (see below) | Lines like "I love you," "They're all dead," "Run!" that carry narrative weight |
| **Subtitle silence** | 0.05 | No subtitle overlap for 3+ seconds during high visual activity | Pure visual spectacle -- the film lets the image speak |
| **Temporal position** | 0.10 | Where in the film timeline (weighted toward final third, 0.6-1.0 normalized position) | Climactic moments tend to occur in the final 30% of runtime |

**Total weight: 1.00**

### Emotional Keyword Dictionaries

For subtitle emotional weight scoring. Each keyword hit adds to the emotional weight score for that subtitle segment.

| Category | Example Keywords | Genre Relevance |
|----------|-----------------|-----------------|
| **Threat** | kill, die, dead, destroy, end, war, attack, hunt, weapon, fight, blood | Action, Thriller, Horror, War, Crime |
| **Romance** | love, heart, together, forever, kiss, miss, need, beautiful, feel | Romance, Drama, Family |
| **Comedy** | Detected primarily via LLaVA tone analysis rather than keywords (comedy is tonal, not lexical) | Comedy, Animation, Family |
| **Mystery** | truth, secret, hidden, who, why, suspect, evidence, clue, reveal, lies | Mystery, Crime, Thriller |
| **Wonder** | beautiful, incredible, impossible, magic, believe, amazing, dream, world | Fantasy, Sci-Fi, Adventure, Animation |
| **Loss** | gone, dead, lost, never, goodbye, remember, alone, without, miss | Drama, War, History |
| **Urgency** | now, run, go, hurry, time, fast, before, quick, move, get out | Action, Thriller, Horror |

### Scoring Implementation Note

The weights above are starting points. They should be tunable per genre via the edit profile. For example, Horror should weight "subtitle silence" higher (dread relies on quiet), while Comedy should weight "subtitle emotional weight" higher (jokes are in the dialogue). The edit profiles below include a `beat_emphasis` list that should influence weight distribution.

---

## 18 Genre Vibe Edit Profiles

Each profile specifies concrete parameters for the trailer assembly algorithm. These are opinionated starting points based on genre conventions. The `--review` workflow lets humans override any value in the manifest.

### Profile Parameter Definitions

| Parameter | Unit | Description |
|-----------|------|-------------|
| `avg_cut_duration_act1` | seconds | Average clip length in Act 1 (Setup) |
| `avg_cut_duration_act2` | seconds | Average clip length in Act 2 (Escalation) |
| `avg_cut_duration_act3` | seconds | Average clip length in Act 3 (Climax Montage) |
| `total_clip_count` | range | Target number of clips in the full trailer |
| `primary_transition` | enum | Most-used transition type |
| `secondary_transition` | enum | Transition used at act boundaries or emphasis points |
| `music_energy_curve` | description | How music intensity should change across the trailer |
| `audio_lufs_target` | dB LUFS | Integrated loudness target for the final mix |
| `dialogue_ratio` | 0.0-1.0 | Target proportion of clips containing dialogue vs. visual-only |
| `lut_color_temp` | description | Color grading direction for .cube LUT design |
| `lut_contrast` | low/medium/high | Contrast boost level |
| `lut_saturation` | low/medium/high/boosted | Saturation adjustment |
| `cold_open_style` | description | What kind of clip opens the trailer |
| `button_style` | description | What kind of clip ends the trailer (post-title stinger) |
| `beat_emphasis` | list | Which narrative beat types are prioritized for clip selection |
| `pacing_curve` | description | How pacing changes through the trailer |

### Transition Enum Values

- `hard_cut` -- Instantaneous cut. The professional default.
- `crossfade` -- Gradual blend between clips. Suggests time passing or emotional connection.
- `fade_to_black` -- Clip fades to black before next clip appears. Creates separation, gravity.
- `dip_to_black` -- Brief black between clips (faster than fade). Creates rhythm.
- `dip_to_white` -- Brief white flash between clips. Suggests magic, energy, transcendence.
- `smash_cut` -- Hard cut but specifically from quiet to loud or slow to fast. Comedic or horror timing device.

---

### 1. Action

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 3.0s |
| `avg_cut_duration_act2` | 2.0s |
| `avg_cut_duration_act3` | 0.8s |
| `total_clip_count` | 35-42 |
| `primary_transition` | hard_cut |
| `secondary_transition` | dip_to_black |
| `music_energy_curve` | Starts medium energy. Steady build through Act 2. Drops at 1:20 for breath beat. Explodes to maximum for Act 3 montage. |
| `audio_lufs_target` | -14 LUFS |
| `dialogue_ratio` | 0.30 |
| `lut_color_temp` | Teal-orange: teal shadows, warm orange highlights. The modern action standard (Michael Bay, Marvel). |
| `lut_contrast` | high |
| `lut_saturation` | boosted |
| `cold_open_style` | Single explosive money shot -- explosion, crash, or action peak. Maximum visual impact in 4-6 seconds. |
| `button_style` | One-liner quip from hero OR final action beat with a sting. |
| `beat_emphasis` | [money_shots, climax_peaks, escalation_beats] |
| `pacing_curve` | Aggressive acceleration. Act 3 should feel like a machine gun of cuts. Widest gap between Act 1 pace (3.0s) and Act 3 pace (0.8s). |

### 2. Adventure

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 4.0s |
| `avg_cut_duration_act2` | 2.5s |
| `avg_cut_duration_act3` | 1.2s |
| `total_clip_count` | 28-35 |
| `primary_transition` | hard_cut |
| `secondary_transition` | crossfade |
| `music_energy_curve` | Opens with wonder and awe. Builds to excitement through Act 2. Grand orchestral crescendo at Act 3. |
| `audio_lufs_target` | -14 LUFS |
| `dialogue_ratio` | 0.40 |
| `lut_color_temp` | Warm golden tones, vivid blues for sky/water. Rich and inviting -- the world should look like a place you want to visit. |
| `lut_contrast` | medium |
| `lut_saturation` | boosted |
| `cold_open_style` | Sweeping landscape or establishing shot of exotic location. Let the world sell itself. |
| `button_style` | Humorous character moment or one final awe-inspiring visual. |
| `beat_emphasis` | [world_establishment, money_shots, escalation_beats] |
| `pacing_curve` | Leisurely Act 1 (let the world breathe). Moderate build. Fast but not frantic Act 3. |

### 3. Animation

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 3.5s |
| `avg_cut_duration_act2` | 2.5s |
| `avg_cut_duration_act3` | 1.0s |
| `total_clip_count` | 30-38 |
| `primary_transition` | hard_cut |
| `secondary_transition` | crossfade |
| `music_energy_curve` | Playful and dynamic. Energy matches emotional beats rather than strictly building. Big crescendo for Act 3. |
| `audio_lufs_target` | -14 LUFS |
| `dialogue_ratio` | 0.45 |
| `lut_color_temp` | Preserve original color palette. Animated films are already precisely color-designed. Minimal grading -- at most a slight contrast bump. |
| `lut_contrast` | low |
| `lut_saturation` | medium (preserve source) |
| `cold_open_style` | Visually striking establishing shot of the animated world OR a gag/joke moment. |
| `button_style` | Comedy beat or heartwarming moment. Animation trailers almost always end on warmth or humor. |
| `beat_emphasis` | [character_introduction, relationship_beats, money_shots] |
| `pacing_curve` | Varied -- matches emotional beats rather than strict acceleration. Allows comedic timing pauses (comedy needs silence to land). |

### 4. Comedy

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 3.5s |
| `avg_cut_duration_act2` | 3.0s |
| `avg_cut_duration_act3` | 1.5s |
| `total_clip_count` | 25-32 |
| `primary_transition` | hard_cut |
| `secondary_transition` | smash_cut |
| `music_energy_curve` | Light and upbeat. Drops to near-silence for dialogue beats (jokes need quiet to land). Builds for Act 3 joke montage. |
| `audio_lufs_target` | -14 LUFS |
| `dialogue_ratio` | 0.60 |
| `lut_color_temp` | Warm, bright, slightly overexposed feel. Comedies look sunny and inviting. |
| `lut_contrast` | low |
| `lut_saturation` | medium |
| `cold_open_style` | Setup-punchline joke or absurd visual gag. Comedy trailers must establish tone in the first 8 seconds. |
| `button_style` | Best joke in the film (the "button gag"). This is the most important clip in a comedy trailer. |
| `beat_emphasis` | [character_introduction, relationship_beats, escalation_beats] |
| `pacing_curve` | Slower overall -- comedy needs breathing room for timing. Clips run longer to let jokes land. Act 3 montage is rapid-fire jokes. |

### 5. Crime

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 3.5s |
| `avg_cut_duration_act2` | 2.5s |
| `avg_cut_duration_act3` | 1.0s |
| `total_clip_count` | 30-38 |
| `primary_transition` | hard_cut |
| `secondary_transition` | dip_to_black |
| `music_energy_curve` | Tense and driving from the start. Percussion-heavy. Builds pressure steadily without relief. |
| `audio_lufs_target` | -16 LUFS |
| `dialogue_ratio` | 0.50 |
| `lut_color_temp` | Cool desaturated. Think David Fincher: muted greens and blues, sickly fluorescent undertone. |
| `lut_contrast` | high |
| `lut_saturation` | low |
| `cold_open_style` | Mysterious or provocative dialogue line over dark visuals. "Nobody gets away clean." |
| `button_style` | Revelation moment or confrontation one-liner. |
| `beat_emphasis` | [inciting_incident, escalation_beats, climax_peaks] |
| `pacing_curve` | Steady tension build. No playful moments, no relief. Act 3 is rapid but controlled -- precision, not chaos. |

### 6. Documentary

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 5.0s |
| `avg_cut_duration_act2` | 3.5s |
| `avg_cut_duration_act3` | 2.0s |
| `total_clip_count` | 20-28 |
| `primary_transition` | crossfade |
| `secondary_transition` | fade_to_black |
| `music_energy_curve` | Somber or reflective start. Emotional build through Act 2. Powerful crescendo for Act 3 that resolves with weight. |
| `audio_lufs_target` | -16 LUFS |
| `dialogue_ratio` | 0.70 |
| `lut_color_temp` | Naturalistic -- respect source material. Slight warm shift for human subjects. Do not over-stylize reality. |
| `lut_contrast` | medium |
| `lut_saturation` | medium |
| `cold_open_style` | Provocative interview quote or striking real-world image. Documentary trailers lead with "why should you care?" |
| `button_style` | Emotional statement from subject or striking statistic/text card. |
| `beat_emphasis` | [character_introduction, inciting_incident, climax_peaks] |
| `pacing_curve` | Slow and deliberate throughout. Even Act 3 does not go rapid-fire -- let emotional weight land. Documentary trailers have the most consistent pacing. |

### 7. Drama

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 4.0s |
| `avg_cut_duration_act2` | 3.0s |
| `avg_cut_duration_act3` | 1.5s |
| `total_clip_count` | 25-33 |
| `primary_transition` | crossfade |
| `secondary_transition` | fade_to_black |
| `music_energy_curve` | Quiet emotional start (solo piano or strings). Swelling through Act 2. Powerful emotional peak at Act 3 that may resolve quietly. |
| `audio_lufs_target` | -16 LUFS |
| `dialogue_ratio` | 0.55 |
| `lut_color_temp` | Warm amber tones, slightly desaturated. Human and grounded, not flashy. |
| `lut_contrast` | medium |
| `lut_saturation` | low-medium |
| `cold_open_style` | Quiet character moment -- a look, a gesture, a whispered line. Drama trailers establish intimacy first. |
| `button_style` | Emotional gut-punch line or silent meaningful look. Drama buttons are quiet, not loud. |
| `beat_emphasis` | [relationship_beats, character_introduction, climax_peaks] |
| `pacing_curve` | Slow build throughout. Act 3 accelerates but stays emotionally grounded, not frenetic. |

### 8. Family

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 3.5s |
| `avg_cut_duration_act2` | 2.5s |
| `avg_cut_duration_act3` | 1.2s |
| `total_clip_count` | 28-35 |
| `primary_transition` | crossfade |
| `secondary_transition` | hard_cut |
| `music_energy_curve` | Uplifting and warm. Builds to joyful peak. Brief emotional dip (the "heart" moment). Resolves warmly. |
| `audio_lufs_target` | -14 LUFS |
| `dialogue_ratio` | 0.50 |
| `lut_color_temp` | Bright, warm, high-key lighting preserved. Family films look safe and inviting. |
| `lut_contrast` | low |
| `lut_saturation` | medium-high |
| `cold_open_style` | Charming character moment or visual wonder. Immediately signal "this is for everyone." |
| `button_style` | Heartwarming moment or gentle comedy beat. Never threatening or ambiguous. |
| `beat_emphasis` | [character_introduction, relationship_beats, world_establishment] |
| `pacing_curve` | Gentle and inviting. Moderate acceleration in Act 3 but never aggressive. |

### 9. Fantasy

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 4.0s |
| `avg_cut_duration_act2` | 2.5s |
| `avg_cut_duration_act3` | 1.0s |
| `total_clip_count` | 30-38 |
| `primary_transition` | crossfade |
| `secondary_transition` | dip_to_white |
| `music_energy_curve` | Ethereal/mysterious opening. Building grandeur through Act 2. Epic orchestral peak at Act 3. |
| `audio_lufs_target` | -14 LUFS |
| `dialogue_ratio` | 0.35 |
| `lut_color_temp` | Rich and saturated -- deep greens, golds, mystical blues. The world should feel magical and otherworldly. |
| `lut_contrast` | high |
| `lut_saturation` | boosted |
| `cold_open_style` | Sweeping world-building shot or magical visual. Fantasy sells on world first, character second. |
| `button_style` | Magical reveal or epic battle moment. |
| `beat_emphasis` | [world_establishment, money_shots, climax_peaks] |
| `pacing_curve` | Let the world breathe in Act 1. Steadily build. Explosive Act 3 montage. |

### 10. History

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 4.5s |
| `avg_cut_duration_act2` | 3.0s |
| `avg_cut_duration_act3` | 1.5s |
| `total_clip_count` | 25-33 |
| `primary_transition` | crossfade |
| `secondary_transition` | fade_to_black |
| `music_energy_curve` | Stately and building. Period-appropriate gravitas. Powerful crescendo that does not cheapen the subject. |
| `audio_lufs_target` | -16 LUFS |
| `dialogue_ratio` | 0.50 |
| `lut_color_temp` | Muted warm -- sepia influence, amber shadows. Period-appropriate feel without going full sepia-tone. |
| `lut_contrast` | medium |
| `lut_saturation` | low |
| `cold_open_style` | Text card with historical context OR sweeping period establishing shot. History trailers often set the stakes with text. |
| `button_style` | Powerful historical statement or emotional character moment. |
| `beat_emphasis` | [world_establishment, inciting_incident, climax_peaks] |
| `pacing_curve` | Deliberate and dignified. Act 3 builds intensity but respects gravitas. |

### 11. Horror

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 4.5s |
| `avg_cut_duration_act2` | 3.0s |
| `avg_cut_duration_act3` | 0.6s |
| `total_clip_count` | 30-40 |
| `primary_transition` | hard_cut |
| `secondary_transition` | smash_cut |
| `music_energy_curve` | Quiet/creepy start with ambient drones. Tension builds with silence as a weapon. Sudden stings for scares. Chaotic peak at Act 3. |
| `audio_lufs_target` | -18 LUFS (quieter baseline creates greater dynamic range for scare stings) |
| `dialogue_ratio` | 0.35 |
| `lut_color_temp` | Cold blue-green, deep shadows, crushed blacks. The darkness is a character. |
| `lut_contrast` | high |
| `lut_saturation` | low |
| `cold_open_style` | Deceptively calm establishing shot -- "everything seems normal" setup. The quiet before the terror. |
| `button_style` | Jump scare or deeply unsettling final image. Horror buttons are designed to make you flinch. |
| `beat_emphasis` | [world_establishment, inciting_incident, money_shots] |
| `pacing_curve` | Deliberately slow Act 1 (build dread). Act 2 alternates slow tension with sudden jarring cuts. Act 3 is extremely rapid-fire, near-strobe cutting. Horror trailers have the widest pacing variance of any genre. |

### 12. Music

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 3.5s |
| `avg_cut_duration_act2` | 2.5s |
| `avg_cut_duration_act3` | 1.5s |
| `total_clip_count` | 28-35 |
| `primary_transition` | crossfade |
| `secondary_transition` | hard_cut |
| `music_energy_curve` | Driven by diegetic music from the film itself. Build from intimate rehearsal/origin to performance peak. The source audio IS the trailer music. |
| `audio_lufs_target` | -14 LUFS |
| `dialogue_ratio` | 0.40 |
| `lut_color_temp` | Vibrant and warm -- concert lighting, stage colors preserved. Do not mute the visual energy of performance. |
| `lut_contrast` | medium |
| `lut_saturation` | boosted |
| `cold_open_style` | Intimate musical moment (practicing alone) or crowd/venue establishing shot. |
| `button_style` | Peak performance moment or emotional musical climax. |
| `beat_emphasis` | [character_introduction, relationship_beats, climax_peaks] |
| `pacing_curve` | Rhythm-driven -- cuts should feel musical rather than strictly accelerating. Performance clips can run longer than average. |

### 13. Mystery

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 4.0s |
| `avg_cut_duration_act2` | 2.5s |
| `avg_cut_duration_act3` | 1.0s |
| `total_clip_count` | 28-35 |
| `primary_transition` | hard_cut |
| `secondary_transition` | dip_to_black |
| `music_energy_curve` | Mysterious and restrained start. Growing unease through Act 2. Revelation-driven crescendo at Act 3. |
| `audio_lufs_target` | -16 LUFS |
| `dialogue_ratio` | 0.55 |
| `lut_color_temp` | Cool neutral tones, shadows emphasized. Film noir influence -- pools of light in darkness. |
| `lut_contrast` | high |
| `lut_saturation` | low |
| `cold_open_style` | A question posed in dialogue ("Who did this?") or an enigmatic visual (a clue, a body, a locked door). |
| `button_style` | Plot twist hint or unanswered question that hooks curiosity. Mystery buttons tease, they do not resolve. |
| `beat_emphasis` | [inciting_incident, escalation_beats, climax_peaks] |
| `pacing_curve` | Measured and controlled. Act 3 is fast but precise -- not chaotic. Mystery is about precision, not frenzy. |

### 14. Romance

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 4.0s |
| `avg_cut_duration_act2` | 3.0s |
| `avg_cut_duration_act3` | 1.5s |
| `total_clip_count` | 24-30 |
| `primary_transition` | crossfade |
| `secondary_transition` | fade_to_black |
| `music_energy_curve` | Gentle and warm start. Emotional swelling through Act 2. Bittersweet or triumphant peak depending on the film's tone. |
| `audio_lufs_target` | -16 LUFS |
| `dialogue_ratio` | 0.60 |
| `lut_color_temp` | Warm golden hour -- soft amber, gentle highlight bloom, romantic warmth throughout. |
| `lut_contrast` | low |
| `lut_saturation` | medium |
| `cold_open_style` | Meet-cute moment or beautiful establishing shot of romantic location. |
| `button_style` | The kiss, the declaration, or a bittersweet look. Romance buttons are the emotional payoff. |
| `beat_emphasis` | [character_introduction, relationship_beats, climax_peaks] |
| `pacing_curve` | Slow and gentle throughout. Even Act 3 stays emotionally measured. Romance trailers rarely go rapid-fire -- the fastest cuts are still 1.5s. |

### 15. Sci-Fi

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 4.0s |
| `avg_cut_duration_act2` | 2.5s |
| `avg_cut_duration_act3` | 0.8s |
| `total_clip_count` | 32-40 |
| `primary_transition` | hard_cut |
| `secondary_transition` | dip_to_white |
| `music_energy_curve` | Atmospheric/electronic start. Building tension through Act 2 with synth layers. Massive orchestral+synth peak at Act 3. |
| `audio_lufs_target` | -14 LUFS |
| `dialogue_ratio` | 0.35 |
| `lut_color_temp` | Cool blue-steel high-tech feel. Occasional warm contrast for human moments (cool environment, warm faces). |
| `lut_contrast` | high |
| `lut_saturation` | medium |
| `cold_open_style` | Striking visual of technology, space, or altered world. Sci-fi sells on spectacle and concept. |
| `button_style` | Mind-bending visual or provocative concept line. "What if everything you knew was wrong?" |
| `beat_emphasis` | [world_establishment, money_shots, inciting_incident] |
| `pacing_curve` | Let the world breathe in Act 1. Build tension in Act 2. Explosive Act 3 with VFX-heavy money shots front and center. |

### 16. Thriller

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 3.5s |
| `avg_cut_duration_act2` | 2.0s |
| `avg_cut_duration_act3` | 0.8s |
| `total_clip_count` | 32-40 |
| `primary_transition` | hard_cut |
| `secondary_transition` | dip_to_black |
| `music_energy_curve` | Ticking tension from the first frame. Relentless build with no relief. Frenetic peak at Act 3. |
| `audio_lufs_target` | -16 LUFS |
| `dialogue_ratio` | 0.45 |
| `lut_color_temp` | Desaturated with cold blue undertones. Oppressive and claustrophobic feel. |
| `lut_contrast` | high |
| `lut_saturation` | low |
| `cold_open_style` | Tension-establishing moment -- a phone call, a discovery, a threat stated plainly. |
| `button_style` | Final twist tease or threat escalation. Thriller buttons make you feel unsafe. |
| `beat_emphasis` | [inciting_incident, escalation_beats, climax_peaks] |
| `pacing_curve` | Starts tense and never lets up. Steady acceleration throughout. Act 3 is relentless. Thriller pacing is the most linear of all genres. |

### 17. War

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 4.5s |
| `avg_cut_duration_act2` | 2.5s |
| `avg_cut_duration_act3` | 1.0s |
| `total_clip_count` | 28-36 |
| `primary_transition` | hard_cut |
| `secondary_transition` | fade_to_black |
| `music_energy_curve` | Somber and reverent start. Building martial intensity through Act 2. Powerful epic peak. Optional quiet resolve after title card. |
| `audio_lufs_target` | -16 LUFS |
| `dialogue_ratio` | 0.40 |
| `lut_color_temp` | Desaturated olive/brown. Muted palette inspired by Saving Private Ryan and Dunkirk. Color is a luxury war films deny themselves. |
| `lut_contrast` | high |
| `lut_saturation` | low |
| `cold_open_style` | Quiet human moment before chaos -- soldier writing a letter, calm before the storm, hands shaking. |
| `button_style` | Powerful statement about duty/sacrifice OR explosive battle moment. War trailers balance spectacle with gravity. |
| `beat_emphasis` | [character_introduction, inciting_incident, money_shots, climax_peaks] |
| `pacing_curve` | Slow reflective Act 1. Building Act 2. Intense but not frivolous Act 3. War trailers must never feel like they are enjoying the violence. |

### 18. Western

| Parameter | Value |
|-----------|-------|
| `avg_cut_duration_act1` | 4.5s |
| `avg_cut_duration_act2` | 3.0s |
| `avg_cut_duration_act3` | 1.2s |
| `total_clip_count` | 25-33 |
| `primary_transition` | hard_cut |
| `secondary_transition` | crossfade |
| `music_energy_curve` | Sparse and atmospheric start (lone guitar, wind, silence). Building tension. Climactic showdown peak. |
| `audio_lufs_target` | -16 LUFS |
| `dialogue_ratio` | 0.35 |
| `lut_color_temp` | Warm dusty amber, high-contrast sunlight, burnt orange shadows. The landscape is baked and harsh. |
| `lut_contrast` | high |
| `lut_saturation` | medium |
| `cold_open_style` | Sweeping frontier landscape OR lone figure silhouette against horizon. Westerns sell the emptiness. |
| `button_style` | Showdown moment -- the draw, the confrontation, or lone ride into sunset. |
| `beat_emphasis` | [world_establishment, character_introduction, climax_peaks] |
| `pacing_curve` | Deliberately slow and sparse. Westerns breathe. Even Act 3 has more restraint than action genres. The fastest cuts are still 1.2s. |

---

## TRAILER_MANIFEST.json Schema

This is the core output artifact of the AI pipeline and the interface between analysis and rendering. It must be human-readable (for `--review` mode), machine-parseable (for FFmpeg conform), and self-documenting (every clip explains why it was chosen).

```json
{
  "$schema": "trailer_manifest_v1",
  "version": "1.0.0",
  "generated_at": "2026-02-26T14:30:00Z",
  "generator_version": "cinecut-0.1.0",

  "source": {
    "video_file": "/path/to/film.mkv",
    "subtitle_file": "/path/to/film.srt",
    "subtitle_format": "srt",
    "duration_seconds": 7200.0,
    "resolution": "1920x1080",
    "fps": 23.976,
    "codec": "h264",
    "audio_channels": 2,
    "audio_sample_rate": 48000
  },

  "vibe": {
    "genre": "action",
    "edit_profile": {
      "avg_cut_duration_act1": 3.0,
      "avg_cut_duration_act2": 2.0,
      "avg_cut_duration_act3": 0.8,
      "total_clip_count_target": 38,
      "primary_transition": "hard_cut",
      "secondary_transition": "dip_to_black",
      "audio_lufs_target": -14,
      "dialogue_ratio_target": 0.30,
      "lut_file": "vibes/action.cube",
      "lut_intensity": 0.85
    }
  },

  "trailer_structure": {
    "target_duration_seconds": 120.0,
    "sections": [
      {
        "name": "cold_open",
        "start_time": 0.0,
        "end_time": 8.0,
        "purpose": "hook",
        "clip_count_target": 1,
        "transition_out": "dip_to_black"
      },
      {
        "name": "act1_setup",
        "start_time": 12.0,
        "end_time": 40.0,
        "purpose": "establish_world_and_character",
        "clip_count_target": 5,
        "transition_out": "dip_to_black"
      },
      {
        "name": "beat_drop",
        "start_time": 40.0,
        "end_time": 45.0,
        "purpose": "tone_shift",
        "clip_count_target": 1,
        "transition_out": "hard_cut"
      },
      {
        "name": "act2_escalation",
        "start_time": 45.0,
        "end_time": 80.0,
        "purpose": "raise_stakes",
        "clip_count_target": 10,
        "transition_out": "fade_to_black"
      },
      {
        "name": "breath",
        "start_time": 80.0,
        "end_time": 85.0,
        "purpose": "pause_before_climax",
        "clip_count_target": 1,
        "transition_out": "dip_to_black"
      },
      {
        "name": "act3_climax",
        "start_time": 85.0,
        "end_time": 105.0,
        "purpose": "maximum_intensity",
        "clip_count_target": 16,
        "transition_out": "hard_cut"
      },
      {
        "name": "title_card",
        "start_time": 105.0,
        "end_time": 112.0,
        "purpose": "movie_title",
        "clip_count_target": 0,
        "transition_out": "fade_to_black"
      },
      {
        "name": "button",
        "start_time": 112.0,
        "end_time": 120.0,
        "purpose": "final_hook",
        "clip_count_target": 1,
        "transition_out": "fade_to_black"
      }
    ]
  },

  "clips": [
    {
      "id": "clip_001",
      "section": "cold_open",
      "order": 1,

      "source_in": 5834.250,
      "source_out": 5838.750,
      "duration": 4.5,

      "beat_type": "money_shot",
      "beat_score": 0.92,
      "beat_reasoning": "High motion magnitude explosion sequence with dramatic lighting contrast. Top-scoring clip by composite money shot metric.",

      "visual_analysis": {
        "motion_magnitude": 0.85,
        "contrast_score": 0.78,
        "saturation_score": 0.65,
        "scene_uniqueness": 0.72,
        "face_present": false,
        "llava_description": "Massive explosion engulfs a bridge as vehicles are thrown into the air. Orange fireballs against dark smoke. Wide establishing shot with high dynamic range."
      },

      "subtitle_analysis": {
        "has_dialogue": false,
        "subtitle_text": null,
        "emotional_category": null,
        "emotional_weight": 0.0
      },

      "audio_treatment": {
        "use_source_audio": true,
        "dialogue_ducking": false,
        "fade_in_ms": 0,
        "fade_out_ms": 200,
        "volume_adjustment_db": 0.0
      },

      "transition_in": "none",
      "transition_out": "dip_to_black",
      "transition_duration_ms": 500,

      "lut_override": null,
      "speed_factor": 1.0,

      "human_override": false,
      "human_notes": null
    },
    {
      "id": "clip_002",
      "section": "act1_setup",
      "order": 2,

      "source_in": 180.500,
      "source_out": 185.000,
      "duration": 4.5,

      "beat_type": "world_establishment",
      "beat_score": 0.71,
      "beat_reasoning": "Wide establishing shot of city at dawn. Low motion, high scene uniqueness. Sets the world for the audience.",

      "visual_analysis": {
        "motion_magnitude": 0.12,
        "contrast_score": 0.65,
        "saturation_score": 0.55,
        "scene_uniqueness": 0.80,
        "face_present": false,
        "llava_description": "Aerial view of a sprawling city at dawn. Golden light catches skyscraper windows. Fog rolls through lower streets."
      },

      "subtitle_analysis": {
        "has_dialogue": false,
        "subtitle_text": null,
        "emotional_category": null,
        "emotional_weight": 0.0
      },

      "audio_treatment": {
        "use_source_audio": true,
        "dialogue_ducking": false,
        "fade_in_ms": 500,
        "fade_out_ms": 0,
        "volume_adjustment_db": -3.0
      },

      "transition_in": "fade_to_black",
      "transition_out": "crossfade",
      "transition_duration_ms": 750,

      "lut_override": null,
      "speed_factor": 1.0,

      "human_override": false,
      "human_notes": null
    }
  ],

  "title_card": {
    "text": "FILM TITLE",
    "font": "default",
    "font_size": 72,
    "font_color": "#FFFFFF",
    "duration_seconds": 7.0,
    "background": "black",
    "fade_in_ms": 500,
    "fade_out_ms": 500,
    "position": "center"
  },

  "audio_master": {
    "music_track": null,
    "music_volume_db": -6.0,
    "dialogue_boost_db": 3.0,
    "lufs_target": -14,
    "limiter_ceiling_db": -1.0,
    "crossfade_between_clips_ms": 50
  },

  "render_settings": {
    "output_file": "trailer_output.mp4",
    "resolution": "source",
    "codec": "libx264",
    "preset": "slow",
    "crf": 18,
    "audio_codec": "aac",
    "audio_bitrate": "192k",
    "pixel_format": "yuv420p"
  },

  "metadata": {
    "total_clips": 35,
    "total_duration_seconds": 119.5,
    "dialogue_clip_count": 11,
    "visual_only_clip_count": 24,
    "avg_beat_score": 0.68,
    "min_beat_score": 0.42,
    "max_beat_score": 0.92,
    "film_coverage_percent": 2.8,
    "chronological_order_preserved": true,
    "sections_with_clips": ["cold_open", "act1_setup", "beat_drop", "act2_escalation", "breath", "act3_climax", "button"],
    "beat_type_distribution": {
      "money_shot": 4,
      "world_establishment": 3,
      "character_introduction": 3,
      "inciting_incident": 2,
      "escalation_beats": 10,
      "relationship_beats": 5,
      "climax_peaks": 8
    }
  }
}
```

### Schema Field Rationale

| Field Group | Why Included |
|-------------|-------------|
| `source` | Render pipeline needs exact source metadata for frame-accurate seeking and codec matching. Audio metadata needed for normalization. |
| `vibe.edit_profile` | All genre parameters in one place. Human can tweak any value before render in `--review` mode. |
| `trailer_structure.sections` | Defines the three-act template with timing. Clips are assigned to sections. Timing values are adjustable. |
| `clips[].source_in/out` | Frame-accurate timestamps for FFmpeg seeking. Seconds with millisecond precision for sub-frame accuracy. |
| `clips[].beat_type/score/reasoning` | Explains WHY this clip was selected. Critical for human review in `--review` mode. The reasoning string is the most important human-facing field. |
| `clips[].visual_analysis` | LLaVA output preserved. Allows human to understand what the AI "saw" without re-running inference. |
| `clips[].subtitle_analysis` | Shows what dialogue (if any) is in this clip and its emotional classification. |
| `clips[].audio_treatment` | Per-clip audio decisions: ducking, fades, volume adjustment, source audio toggle. |
| `clips[].transition_in/out` | Per-clip transition decisions. Human can override at the clip level for fine control. |
| `clips[].human_override/notes` | Explicitly marked when a human has modified this clip. Preserves provenance for debugging. |
| `title_card` | Movie title rendering parameters. Simple but necessary -- a trailer without a title is not a trailer. |
| `audio_master` | Global audio mix settings. Separate from per-clip treatment. Includes limiter to prevent clipping. |
| `render_settings` | FFmpeg output parameters. Reasonable quality defaults (CRF 18 is visually transparent), all human-overridable. |
| `metadata` | Summary statistics for quick validation. "Does this look right?" at a glance without reading every clip. Beat type distribution shows balance. |

---

## Feature Dependencies

```
Subtitle Parsing ──────────────┐
                               ├──> Narrative Beat Detection ──> Clip Selection
Keyframe Visual Analysis ──────┘                                      │
(LLaVA via llama-cli)                                                 │
                                                                      │
Genre Edit Profile Loading ───────────────────────────────────────────┤
                                                                      │
                                                                      v
                                                            TRAILER_MANIFEST.json
                                                                      │
                                              ┌───────────────────────┤
                                              │                       │
                                        [--review]              [auto mode]
                                              │                       │
                                        Human edits JSON              │
                                              │                       │
                                              └───────┬───────────────┘
                                                      │
                                                      v
                                              FFmpeg Conform Pipeline
                                                      │
                                              ┌───────┼───────┐
                                              │       │       │
                                         LUT Apply  Audio   Transitions
                                              │    Normalize    │
                                              └───────┼───────┘
                                                      │
                                                      v
                                                Final MP4 Output
```

### Critical Path Dependencies

1. **Subtitle parsing** and **keyframe visual analysis** are independent and can run in parallel on the proxy
2. Both feed into **narrative beat detection** which requires both subtitle and visual signals
3. **Clip selection** requires beat detection output + genre edit profile parameters
4. **Manifest generation** requires clip selection output (this is the AI's deliverable)
5. **FFmpeg conform** requires the manifest (and optionally human edits from `--review`)
6. **LUT application**, **audio normalization**, and **transitions** are applied during the conform render pass

### Implication for Phase Structure

- **Phase 1** must deliver: subtitle parsing + basic FFmpeg conform pipeline (can generate a trailer from manually-authored manifest)
- **Phase 2** must deliver: keyframe extraction + LLaVA analysis + narrative beat detection
- **Phase 3** must deliver: genre edit profiles + clip selection algorithm + full manifest generation
- **Phase 4** must deliver: LUT creation/sourcing + audio treatment + polish features

---

## MVP Recommendation

### Must Ship (Phase 1 -- Pipeline Skeleton)

1. **SRT/ASS subtitle parsing** with basic keyword extraction -- the primary narrative signal, zero hardware cost
2. **FFmpeg conform pipeline** -- frame-accurate clip extraction from original source, concatenation, hard cut + crossfade transitions
3. **TRAILER_MANIFEST.json generation and consumption** -- even if initially hand-authored or minimally populated, the manifest-based workflow must work end-to-end
4. **Three-act trailer structural template** with configurable section timings
5. **`--review` flag** for manifest inspection before render
6. **Basic audio normalization** (single LUFS target, loudnorm filter)

### Must Ship (Phase 2 -- AI Brain)

7. **420p proxy creation** for analysis pipeline
8. **LLaVA keyframe analysis** via llama-cli on proxy frames
9. **Narrative beat detection** combining subtitle signals + LLaVA visual descriptions
10. **Money shot quality scoring** with the multi-signal system described above
11. **Clip selection algorithm** that fills the three-act template from detected beats

### Differentiator Ship (Phase 3 -- Genre Intelligence)

12. **All 18 genre vibe edit profiles** with the concrete parameters specified above
13. **Pacing curve implementation** (cut duration as function of timeline position per genre)
14. **Per-genre transition selection** logic
15. **Emotional keyword dictionaries** for all 7 categories

### Polish Ship (Phase 4 -- Production Quality)

16. **LUT sourcing/creation** for all 18 vibes (.cube files)
17. **Audio ducking** for dialogue clips
18. **Per-vibe LUFS targeting** (different loudness targets per genre)
19. **Title card rendering** with basic text overlay
20. **Button/stinger selection** logic (post-title clip -- the hardest creative decision to automate)

### Defer to v2+

- **Music track integration** -- accept user-provided track, sync cuts to beat grid
- **Multi-language subtitle support** -- requires per-language keyword dictionaries
- **Vertical/square format output** -- requires subject-aware reframing
- **Custom transition effects** beyond the core set
- **Scene-level dialogue re-ordering** for non-chronological trailers
- **A/B trailer generation** -- generate multiple trailer variants from same source

---

## Edit Profile Quick Reference Matrix

For implementation, a compact view of all 18 profiles' key differentiators:

| Genre | Act1 Cut | Act2 Cut | Act3 Cut | Clips | Dialogue | Primary Trans | Contrast | Saturation | LUFS |
|-------|----------|----------|----------|-------|----------|---------------|----------|------------|------|
| Action | 3.0s | 2.0s | 0.8s | 35-42 | 0.30 | hard_cut | high | boosted | -14 |
| Adventure | 4.0s | 2.5s | 1.2s | 28-35 | 0.40 | hard_cut | medium | boosted | -14 |
| Animation | 3.5s | 2.5s | 1.0s | 30-38 | 0.45 | hard_cut | low | medium | -14 |
| Comedy | 3.5s | 3.0s | 1.5s | 25-32 | 0.60 | hard_cut | low | medium | -14 |
| Crime | 3.5s | 2.5s | 1.0s | 30-38 | 0.50 | hard_cut | high | low | -16 |
| Documentary | 5.0s | 3.5s | 2.0s | 20-28 | 0.70 | crossfade | medium | medium | -16 |
| Drama | 4.0s | 3.0s | 1.5s | 25-33 | 0.55 | crossfade | medium | low-med | -16 |
| Family | 3.5s | 2.5s | 1.2s | 28-35 | 0.50 | crossfade | low | med-high | -14 |
| Fantasy | 4.0s | 2.5s | 1.0s | 30-38 | 0.35 | crossfade | high | boosted | -14 |
| History | 4.5s | 3.0s | 1.5s | 25-33 | 0.50 | crossfade | medium | low | -16 |
| Horror | 4.5s | 3.0s | 0.6s | 30-40 | 0.35 | hard_cut | high | low | -18 |
| Music | 3.5s | 2.5s | 1.5s | 28-35 | 0.40 | crossfade | medium | boosted | -14 |
| Mystery | 4.0s | 2.5s | 1.0s | 28-35 | 0.55 | hard_cut | high | low | -16 |
| Romance | 4.0s | 3.0s | 1.5s | 24-30 | 0.60 | crossfade | low | medium | -16 |
| Sci-Fi | 4.0s | 2.5s | 0.8s | 32-40 | 0.35 | hard_cut | high | medium | -14 |
| Thriller | 3.5s | 2.0s | 0.8s | 32-40 | 0.45 | hard_cut | high | low | -16 |
| War | 4.5s | 2.5s | 1.0s | 28-36 | 0.40 | hard_cut | high | low | -16 |
| Western | 4.5s | 3.0s | 1.2s | 25-33 | 0.35 | hard_cut | high | medium | -16 |

### Key Patterns Across Genres

- **Loud genres** (Action, Adventure, Animation, Comedy, Family, Fantasy, Music, Sci-Fi): -14 LUFS
- **Quiet/intense genres** (Crime, Documentary, Drama, History, Mystery, Romance, Thriller, War): -16 LUFS
- **Horror is unique**: -18 LUFS baseline to allow maximum dynamic range for scares
- **High dialogue** (Documentary 0.70, Comedy 0.60, Romance 0.60): story told through words
- **Low dialogue** (Action 0.30, Horror 0.35, Fantasy 0.35, Sci-Fi 0.35, Western 0.35): story told through images
- **Fastest Act 3** (Horror 0.6s, Action/Sci-Fi/Thriller 0.8s): maximum intensity genres
- **Slowest Act 3** (Documentary 2.0s, Comedy/Drama/Romance 1.5s): emotion over spectacle
- **Most clips** (Action 35-42): highest density of visual information
- **Fewest clips** (Documentary 20-28): let each shot breathe

---

## Sources and Confidence Notes

- **Professional trailer structure:** Based on widely documented three-act trailer format described in film editing literature (Walter Murch's "In the Blink of an Eye" approach applied to trailers), trailer editor interviews, and industry analysis in training corpus. The three-act structure, cold open/button framework, and ~2:00 runtime convention have been standard since the late 1990s. **Confidence: MEDIUM-HIGH.** The structure is well-established; specific timing values are approximations from aggregate analysis.

- **Genre color grading conventions:** Based on cinematography and color grading references in training data. Conventions like teal-orange for action, desaturated for war, and warm golden for romance are well-documented. **Confidence: MEDIUM.** LUT parameters will need tuning against actual .cube files during implementation.

- **Cut duration and pacing by genre:** Based on empirical analysis of trailer editing patterns discussed in film editing communities and academic analysis of trailer pacing. **Confidence: MEDIUM.** These are informed starting points, not ground truth. The `--review` workflow exists precisely because automated pacing needs human tuning.

- **TRAILER_MANIFEST.json schema:** Original design synthesized from project requirements, EDL/AAF interchange format conventions, and the specific needs of the FFmpeg conform pipeline. **Confidence: HIGH** for structure (it maps directly to required FFmpeg operations), **MEDIUM** for field completeness (additional fields may surface during implementation).

- **Narrative beat framework:** Synthesized from screenplay structure theory (Blake Snyder's Save the Cat, Syd Field's three-act structure, Joseph Campbell's monomyth) applied specifically to trailer editing. **Confidence: MEDIUM.** The categories are sound but detection methods are speculative until validated against real LLaVA output quality on the K6000.

- **Money shot scoring weights:** Original design. No single authoritative source exists for "how to computationally identify the best shot in a film." The weights are a reasonable starting point that should be treated as hyperparameters to be tuned empirically. **Confidence: LOW-MEDIUM.** The signals are correct; the weights are educated guesses.

**Note:** WebSearch was unavailable during this research session. All findings derive from training data. Claims about specific timing values, cut counts, and scoring weights should be treated as informed starting points requiring empirical validation, not ground truth.
