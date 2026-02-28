# Domain Pitfalls

**Domain:** AI-driven video trailer generation with local LLM inference — v2.0 Structural & Sensory Overhaul
**Project:** CineCut AI
**Researched:** 2026-02-28 (v2.0 addendum; v1.0 pitfalls retained below)
**Confidence:** MEDIUM-HIGH for FFmpeg audio/LLM pitfalls (well-documented failure modes verified by WebSearch); MEDIUM for BPM/music API pitfalls (partially verified); LOW for some edge cases (training data only)

---

## v2.0 Pitfalls — New Feature Integration

These pitfalls are specific to adding the eight v2.0 features to the existing CUDA 11.4 / llama-server / FFmpeg pipeline.
They are ordered by severity. Each includes the phase most likely to address it.

---

## Critical Pitfalls (v2.0)

Mistakes that cause corrupted output, pipeline rewrites, or subtle quality failures that are hard to diagnose post-hoc.

---

### Pitfall V2-1: llama-server Model Swap — CUDA Memory Not Released Between Sessions

**What goes wrong:** v2.0 introduces a two-stage LLM pipeline: a text-only structural analysis model (lightweight LLaMA, no mmproj) runs first to classify scenes into BEGIN_T/ESCALATION_T/CLIMAX_T zones, then the LLaVA visual model (with mmproj) runs second for per-frame description. Each uses a different llama-server invocation. The trap: terminating the first llama-server process does not guarantee immediate CUDA memory release on CUDA 11.4 / Kepler. The CUDA context can linger for several seconds after `process.terminate()` / `process.wait()`. If the second llama-server starts too quickly, it collides with the lingering VRAM allocation and either crashes on startup or silently fails to load all layers onto GPU (falling back to CPU-only, 10-100x slower).

**Why it happens:** The Linux kernel CUDA driver does not guarantee synchronous VRAM release on process exit for CUDA 11.4 / Kepler. Newer CUDA versions (12.x) improved deallocation speed, but CUDA 11.4 on Kepler is known to have slower teardown. A `process.wait()` returning 0 means the process exited, not that VRAM is free. `nvidia-smi` showing 0MB used is the only reliable signal that VRAM has been returned.

**Consequences:**
- Second llama-server fails to load model layers onto GPU (loads to CPU instead with no error message)
- Text-stage structural analysis takes 50-200x longer than expected (no error, just slowness)
- Inference produces structurally correct JSON but the scene-zone matching is based on degraded CPU-quality inference

**Warning signs:**
- Second llama-server startup completes unusually fast (under 5 seconds — model loaded entirely to CPU)
- `nvidia-smi` shows near-zero GPU utilization during the text-only inference stage
- Text-stage inference that should take ~2s per scene takes 30-90s per scene
- `nvidia-smi` after first server stop shows residual VRAM usage >50MB

**Prevention:**
1. After terminating the first llama-server, poll `nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits` until reported VRAM usage drops below a threshold (e.g. 500MB) or a timeout (15 seconds) is reached. Only then start the second server.
2. Add a hard sleep of at least 3 seconds between server stop and server start as a minimum baseline even if polling is not used.
3. Log which stage each llama-server invocation is serving. If the startup health check passes in under 3 seconds for a model that normally takes 8-15 seconds, emit a warning: "Model may not have loaded to GPU — startup was suspiciously fast."
4. Design the GPU_LOCK logic so that it covers the inter-stage gap: the lock should be held from first server `__enter__` through second server `__enter__`, with only the model swap in between.
5. Verify GPU load after startup by calling `nvidia-smi` and comparing reported VRAM against the expected model size. If VRAM used is below 80% of expected model size, abort with a clear error rather than silently proceeding with CPU inference.

**Detection:** Log `nvidia-smi` VRAM stats at: before first server start, after first server stop, before second server start, after second server health check. Any anomaly in these four readings should surface the issue immediately.

**Phase:** Phase 1 of v2.0 (Two-Stage LLM Pipeline). This is a day-one design constraint — the inter-stage swap logic must be built correctly from the start.

---

### Pitfall V2-2: FFmpeg Complex Filtergraph Audio Mixing — Ordering, Sync, and Loudnorm Interference

**What goes wrong:** The v2.0 output trailer has four simultaneous audio layers: (1) film audio from extracted clips, (2) music bed from royalty-free archive, (3) synthesized transition SFX, and (4) protagonist VO segments. Mixing these in FFmpeg with `amix` or a complex `-filter_complex` filtergraph introduces several failure modes that are easy to get wrong and extremely hard to debug once they interact.

**Sub-failures:**

**(a) amix normalizes input volumes, destroying the intended mix:**
FFmpeg's `amix` filter defaults to `normalize=1`, which divides each input by the number of inputs. With 4 inputs, every track is multiplied by 0.25. This obliterates the carefully tuned ducking ratios (e.g. music at -18dB under VO). The result sounds thin and quiet, with no apparent ducking relationship between tracks.

**(b) loudnorm applied to the mixed output destroys dynamic ducking:**
If a per-vibe LUFS normalization pass (`loudnorm`) is applied to the final mixed output rather than to individual stems before mixing, the loudnorm algorithm treats the ducking as content to be normalized away. A quiet segment (music ducked under VO) gets boosted; a loud segment (music at full level) gets reduced. The result sounds tonally flat — the dynamic intent of ducking is erased.

**(c) Timestamp misalignment between mixed audio and video:**
When the music bed is a separate audio file (not extracted from the source film), it starts at PTS=0. The film clips, after extraction and PTS reset, also start at PTS=0. After concatenation, the music bed must be re-timed to match the assembled trailer duration. If the music bed is mixed before concatenation (at the individual clip level), the timestamps are relative to each clip, not the trailer. If it is mixed after concatenation, the assembled video timestamps must be reset before mixing. Getting this ordering wrong produces a trailer where the music bed is in sync for the first clip only, then drifts.

**(d) Sample rate mismatch between sources causes filter rejection:**
The film audio, music bed (downloaded MP3/OGG from API), and SoX-synthesized SFX may have different sample rates (44100Hz, 48000Hz, 22050Hz). FFmpeg's `amix` filter rejects inputs with mismatched sample rates — it silently drops the mismatched stream or emits an "invalid sample rate" error. The final output plays without the missing stream and no clear error is surfaced in the log unless stderr is explicitly captured and checked.

**Prevention:**
1. Apply loudnorm to each stem independently before mixing (not to the final mix). Use individual clip LUFS normalization as already implemented in `extract_and_grade_clip()`. The music bed gets its own single-pass normalization to a fixed reference level (e.g. -23 LUFS) before being fed into the mixer. SFX stems at -18 LUFS. Film VO at -14 LUFS. Then mix using volume ratios, not loudnorm.
2. Always use `amix` with `normalize=0` (or use explicit `volume` filters before `amix`):
   ```
   -filter_complex "[0:a]volume=1.0[film];[1:a]volume=0.15[music];[2:a]volume=0.8[vo];[film][music][vo]amix=inputs=3:normalize=0"
   ```
3. Resample all audio stems to 48000Hz before entering any mixing filtergraph. Add `-ar 48000` to every stem extraction and music download conversion step. Never assume input sample rate — always verify with `ffprobe -show_entries stream=sample_rate`.
4. Mix audio only after final video concatenation. The music bed is applied in a single pass over the assembled trailer, not per-clip. This ensures music timeline alignment and avoids the per-clip timestamp problem.
5. Sidechain ducking for VO segments: use `sidechaincompress` or manual `volume` envelope filters keyed to VO timestamp windows rather than automatic ducking filters (which require precise threshold tuning and behave inconsistently with short VO segments).
6. Build a dedicated audio mixing function that accepts a list of (stem_path, level_db, start_time_s) tuples and generates the filtergraph programmatically. This prevents ad-hoc filtergraph construction that is easy to get wrong.

**Detection:**
- After mixing, verify all expected streams are present with `ffprobe -show_streams`.
- Compare audio stream duration against video stream duration — should be within 20ms.
- Spot-check: play the first 10 seconds of the mixed output and verify music bed is audible below VO.

**Phase:** Phase 2 of v2.0 (Audio Architecture). The mixing strategy must be locked before any audio stem generation work begins.

---

### Pitfall V2-3: Non-Linear Scene Reordering — Audio Bleed and Dialogue Continuity Breaks

**What goes wrong:** v2.0 reorders clips by semantic zone (BEGIN_T, ESCALATION_T, CLIMAX_T) rather than film chronology. A clip from minute 90 of the film may be placed before a clip from minute 15. This introduces three distinct failure modes:

**(a) Hard-cut audio bleed between reordered clips:**
When a clip is extracted from the film, FFmpeg extracts the film's complete audio track for that segment — including background score, ambient sound, and dialogue. If the next clip in the reordered sequence comes from a completely different scene, the audio environments collide at the cut point. For example: a quiet emotional scene (low ambient noise) cut to an action scene (gunfire audio) with no transition will sound jarring even with a hard cut, because the audio has no ramp. This is expected as an editorial choice, but the additional problem is audio from the tail of clip N bleeds into the head of clip N+1 if they share any acoustic space in the original film (e.g., both in the same room, separated by 40 minutes of film time).

**(b) Dialogue lines that depend on prior context sound incoherent:**
Selecting a scene where a character says "I told you this would happen" for the BEGIN_T zone makes no sense without the context of what was told. The structural analysis model is responsible for filtering these out, but if the zone-matching logic selects clips primarily by beat type without checking dialogue self-containedness, the final trailer contains non-sequitur dialogue lines that confuse viewers.

**(c) Subtitle alignment lost after reordering:**
If any downstream step tries to render subtitles or dialogue excerpts in the final trailer based on original SRT timestamps, those timestamps are now wrong. The dialogue from minute 90 appears at the trailer's second 10. Systems that naively copy subtitle timestamps into the manifest without adjusting for reorder position will either display nothing or display text at the wrong time.

**Prevention:**
1. Always extract clips with `-avoid_negative_ts make_zero` and reset PTS on both video and audio (`setpts=PTS-STARTPTS`, `asetpts=PTS-STARTPTS`) so each clip's audio starts at t=0, preventing bleed from original timeline position.
2. Add a 0.1-second audio fade-out at the end of every extracted clip and a 0.1-second audio fade-in at the start. This costs nothing perceptually on hard cuts but prevents any continuity clicks or bleed artifacts: `-af "afade=t=in:d=0.1,afade=t=out:st={duration-0.1}:d=0.1"`.
3. The zone-matching algorithm must filter out clips whose dialogue text contains pronouns that reference prior context without antecedent ("it", "that", "he told me"). Simple heuristic: flag dialogue excerpts shorter than 4 words or beginning with a pronoun as "context-dependent" and deprioritize them for BEGIN_T placement.
4. Subtitle timestamps in the manifest's `dialogue_excerpt` field are for human review only. Never attempt to render them as burned-in subtitles in the assembled trailer — the timestamps have no relationship to the reordered timeline.
5. When reordering, verify that no two adjacent clips in the output sequence come from within 30 seconds of each other in the source film. Adjacent clips from the same scene will create false continuity that viewers will notice as awkward (same shot, different angle, jarring cut).

**Detection:** After reordering, log the source timestamps of consecutive clip pairs. Flag any pair where `|clip[i].source_start_s - clip[i+1].source_start_s| < 30.0` as a potential false-continuity problem.

**Phase:** Phase 2 of v2.0 (Non-Linear Ordering and Zone Matching). Prevention must be designed into the ordering algorithm from the start.

---

### Pitfall V2-4: BPM Detection Failures — Silence, Edge Cases, and Octave Errors

**What goes wrong:** v2.0 uses BPM detection on downloaded royalty-free music to drive the edit rhythm grid. BPM detection fails or produces wrong values in several well-documented cases:

**(a) Silence at track boundaries produces 0 BPM:**
`librosa.beat.beat_track()` returns 0.0 BPM and an empty beat array when no onset strength is detectable — including when the track starts or ends with a long silence (common in downloaded music with fade-out endings). The beat grid is empty. Any downstream code that divides by BPM or tries to calculate beat intervals from an empty array crashes with a ZeroDivisionError or IndexError.

**(b) Octave errors (half-tempo / double-tempo):**
Librosa's `beat_track` is known to return half or double the true tempo for tracks with strong backbeats or syncopated rhythms. A 140 BPM electronic track may return 70 BPM (half-tempo). A 90 BPM hip-hop track may return 180 BPM (double-tempo). The resulting edit grid places cuts at 2x or 0.5x the intended frequency, which sounds either frantic or sluggish.

**(c) Unusual time signatures (3/4, 5/4, 7/8):**
Librosa assumes 4/4 time by default. In 3/4 time (waltz), the beat-tracking algorithm places phantom beats at non-existent positions, producing an irregular beat grid that doesn't align with musical accents. Documentary-style music and some classical film scores commonly use 3/4 or compound meters.

**(d) Variable tempo throughout the track:**
Downloaded royalty-free tracks may have tempo ramps (build-up sections) or explicit tempo changes mid-track. Running a global BPM analysis returns an average that is wrong for every section of the track.

**Consequences:**
- ZeroDivisionError or crash at the beat grid construction step
- Edit cuts land between beats instead of on beats, destroying the rhythm-sync effect
- Variable-BPM tracks have random-feeling cuts despite BPM-sync being active

**Prevention:**
1. Always guard against 0 BPM: after calling `beat_track`, check if the returned tempo is 0 or the beat array is empty. Fall back to a vibe-default BPM (e.g. Action: 140, Drama: 80, Horror: 65) rather than crashing.
2. Clamp detected BPM to a plausible range per vibe (e.g. 60-180 BPM). If detected value is outside range, attempt octave correction: if tempo > vibe_max, halve it; if tempo < vibe_min, double it.
3. Prefer `librosa.feature.tempo()` with a prior distribution over `librosa.beat.beat_track()` for tempo detection when onset strength is weak. The prior can be tuned to the vibe's expected BPM range.
4. For edit rhythm purposes, use beat positions (not just BPM) to define the grid. `librosa.beat.beat_track()` returns both tempo and beat frames. Use the beat frame positions directly for cut point candidates rather than reconstructing from BPM alone.
5. If the detected beat array has fewer than 8 beats in the first 30 seconds of a track, classify the track as "non-beat-tracked" and fall back to measure-level cuts at (60 / bpm * 4) intervals (quarter-note bars), which is more robust than individual beat tracking.
6. Set `trim=False` in `beat_track()` to prevent silence-trimming behavior that can drop the last (or first) beats and shift the entire grid.

**Detection:** Log detected BPM and beat count for every downloaded track. Flag tracks with detected BPM outside the range [60, 200] or beat count under 10 as requiring fallback handling.

**Phase:** Phase 3 of v2.0 (BPM Grid / Beat Map). All edge cases must be handled before the beat map is used to drive cut timing.

---

### Pitfall V2-5: Music API Unreliability — Downtime, OAuth Expiry, Track Unavailability, and Caching

**What goes wrong:** The music bed feature downloads a royalty-free track from an external API (e.g. Freesound) on first use per vibe. Several failure modes exist that, if not handled gracefully, make the entire pipeline fail for any vibe that has not yet downloaded its music track:

**(a) API downtime during first run:**
The Freesound API (or any external music source) may be unavailable. An unhandled `requests.ConnectionError` or timeout propagates up and crashes the pipeline mid-run, after inference has already completed and expensive work has been done.

**(b) OAuth2 token expiry (Freesound requires OAuth2 for full-quality downloads):**
Freesound's OAuth2 access tokens expire after 24 hours. The refresh token must be stored and used to obtain a new access token. If the stored token is stale and no refresh logic is implemented, all download attempts fail with HTTP 401 Unauthorized. This is a silent failure for users who ran the tool yesterday and now re-run it on a new film.

**(c) Rate limiting:**
Freesound enforces 60 requests/minute and 2000 requests/day. A batch run generating trailers for multiple films in a row, each for different vibes, can exhaust the daily quota. The API returns HTTP 429 with no automatic retry. Unhandled, this looks identical to a generic network error.

**(d) Track unavailability:**
A specific track ID hardcoded for a vibe may be removed by its uploader, DMCA-d, or made private after the initial track selection was made. The download returns HTTP 404. If the track selection logic is hardcoded to a specific Freesound ID rather than a search query, the entire vibe breaks permanently when that track disappears.

**(e) Downloaded file format mismatch:**
Freesound hosts sounds in their original format (MP3, OGG, FLAC, WAV — whatever the uploader provided). The downloaded file may not be the expected format. Code that assumes `.mp3` and tries to open a `.flac` file will fail.

**Prevention:**
1. Cache music tracks to a permanent per-vibe location (e.g. `~/.cinecut/music/<vibe>.<ext>`). On second run, use the cached track without any API call. Never download the same vibe track twice.
2. Make music a "best-effort" feature: if download fails for any reason (network error, 401, 404, 429), log a warning and continue the pipeline without a music bed rather than aborting. The trailer is still valid without music.
3. Use a search query approach rather than hardcoded track IDs: query `"vibe_name cinematic music"` and download the first result that matches format requirements. This is resilient to individual track deletion.
4. Store OAuth2 tokens (access + refresh) in a config file (`~/.cinecut/config.json`). On each API call, check token expiry and auto-refresh before the call. Wrap all API calls in a decorator that handles 401 by refreshing once and retrying once.
5. Handle HTTP 429 explicitly: parse the `Retry-After` header (if present) and either wait the specified seconds (for short waits < 60s) or skip and use cached/fallback track.
6. After download, verify the file with `ffprobe -show_format` before caching. If ffprobe fails, discard and retry. Convert to a canonical format (48000Hz mono or stereo WAV) immediately after download so downstream code always receives a known format.

**Detection:** Log every API call with status code and response time. Log cache hit/miss status. Any 4xx or 5xx response should be user-visible as a warning, not a silent failure.

**Phase:** Phase 3 of v2.0 (Music Bed / Royalty-Free Archive). The caching and graceful-degradation strategy must be built before any API integration is deployed.

---

### Pitfall V2-6: Protagonist VO Extraction — Background Music Bleed, Codec Edge Cases, and Duration Clipping

**What goes wrong:** VO extraction pulls a protagonist dialogue segment from the film's audio track at subtitle-defined timestamps and uses it as a VO layer in the trailer. Several things can go wrong:

**(a) Background music and ambient sound are extracted alongside the dialogue:**
FFmpeg extracts the complete audio mix at the given timestamp — it has no way to isolate the voice from the background score. A dramatic scene where the protagonist speaks over a swelling orchestral track produces a VO clip that is 40-60% music. When this is mixed into the trailer's music bed, the film's original score bleeds into the new music bed, creating a cacophonous double-score effect. This is not fixable in FFmpeg alone — source separation would require a neural network (out of scope for local-only).

**(b) Very short segments (< 1s) cause loudnorm to fail:**
The existing v1.0 code already uses a fallback for segments < 3s (single-pass with volume=0dB instead of two-pass loudnorm). For VO segments that are < 0.5s (individual short utterances common in action dialogue), even single-pass loudnorm produces artifacts. Short AAC frames have boundary issues at segment edges.

**(c) AAC stream copy with `-ss` before `-i` produces incorrect start offset:**
Using `-ss <start> -i <source> -t <dur> -c:a copy -vn` for audio-only extraction with stream copy has a known FFmpeg behavior: when `-ss` is placed before `-i` (input seeking), the seeking lands on the nearest keyframe before the timestamp. With AAC at 1024 samples per frame (~21ms at 48kHz), this can shift the actual audio start by up to 21ms. For very short VO segments (under 1s), a 21ms offset is noticeable. Using `-c:a aac` (re-encode) instead of `-c:a copy` with output seeking (`-ss` after `-i`) eliminates this but is slower.

**(d) Codec mismatch when the source file has AC3, DTS, or EAC3 audio:**
Many MKV rips have AC3 or DTS 5.1 audio. Stream-copying these to a separate audio file intended for mixing requires the container to support the codec (e.g. AC3 in an MKV or MP4 with appropriate container support). If the output format is `.wav` or `.aac`, stream copy fails. If re-encoding is used, the channel layout must be explicitly downmixed to stereo (`-ac 2`) or the audio has 6 channels that most FFmpeg filter chain assumptions break on.

**Prevention:**
1. Accept that VO extraction includes background audio. This is an inherent limitation of single-channel extraction from a mixed audio track. Compensate by setting VO volume conservatively low in the mix (-6dB relative to music bed) and positioning VO segments only during music bed lulls or explicitly ducked sections. Do not try to isolate voice — it is out of scope.
2. For all VO segments, regardless of duration, always re-encode to AAC 48000Hz stereo using `-c:a aac -ar 48000 -ac 2`. Never use stream copy for VO extraction. The consistency guarantees downstream mixing will always work.
3. Use output seeking for VO extraction (place `-ss` after `-i`): this is slower but frame-accurate. VO segments are typically 1-8 seconds — output seeking overhead is 1-5 seconds of decode, which is acceptable for accuracy.
4. Enforce a minimum VO segment duration of 0.8s. If the subtitle event spans less than 0.8s, expand symmetrically (0.2s padding on each side) before extraction. Never extract sub-0.5s VO segments.
5. Explicitly downmix multi-channel sources: always add `-af "pan=stereo|c0=c0+c2+0.7*c4|c1=c1+c3+0.7*c5"` for 5.1 → stereo downmix, or simply `-ac 2` for generic downmix.
6. After extraction, verify with `ffprobe -show_entries stream=duration,channels,sample_rate` that the extracted file matches expectations. A 0-duration file or 0-channel file should trigger a warning and skip that VO segment.

**Detection:** Log every VO extraction with: source timestamp, duration, channels detected in source, and whether re-encode or copy was used. Flag anything under 0.5s or with channels != 2 after extraction.

**Phase:** Phase 3 of v2.0 (Protagonist VO Extraction).

---

## Moderate Pitfalls (v2.0)

---

### Pitfall V2-7: SceneDescription Persistence — Stale Cache and Schema Migration

**What goes wrong:** v2.0 adds SceneDescription persistence so that resume after crash skips re-running LLaVA inference. The persistence is implemented as a JSON file alongside the manifest. Two failure modes are particularly insidious because they produce wrong output silently:

**(a) Stale cache when source file changes:**
The user re-runs the pipeline on the same output path but with a different source file (updated cut of the film, replaced MKV). The work directory hash is based on source path, not source content. If the source file path is the same but the mtime has changed, the cached SceneDescriptions describe the old film and are applied to the new film's keyframes. Zone matching produces structurally plausible but factually wrong assignments (scenes are mapped to wrong zones based on descriptions from a different version of the film).

**(b) Schema evolution corrupts old caches:**
During v2.0 development, the SceneDescription schema will evolve. A cache written with the initial schema (fields: `visual_content`, `mood`, `action`, `setting`) becomes incompatible when a new field is added (`zone_classification: str`) or a field is renamed. Pydantic will raise a `ValidationError` on load, crashing the pipeline. Or worse: if the new field is `Optional`, Pydantic succeeds but the zone_classification is `None` for all cached entries, producing empty zone assignments that default to `BEGIN_T` and defeat the entire two-stage pipeline.

**Prevention:**
1. Cache key must include content hash, not just path. Use: `hash(source_path + str(source_stat.st_mtime) + str(source_stat.st_size))`. If either mtime or size changes, the cache is invalid and must be regenerated. This is the same atomic-checkpoint pattern already in v1.0 (`checkpoint.py`).
2. SceneDescription cache file must include a `schema_version` field (e.g. `"v2.1"`). On load, compare against the current schema version constant in `inference/models.py`. If versions differ, log a warning and force full re-inference rather than loading stale data.
3. Use Pydantic `model_validate()` in strict mode on cache load — any validation failure (missing field, wrong type) should trigger cache invalidation and re-inference, not a crash or silent default.
4. Define a clear migration policy: cache schema version mismatches always trigger full re-inference. Do not attempt to migrate old cache entries — inference cost is the lesser evil compared to silent wrong output.
5. Cache file must be written atomically using `os.replace()` from a temp file, same as the manifest, to prevent partial writes that look like valid JSON but are corrupted mid-write.
6. Include in the cache file: the source file path, the source file mtime, the source file size, the schema version, and the total number of frames described. On load, verify all five fields before trusting the cache.

**Detection:** On every pipeline run, log whether SceneDescription cache was loaded (hit) or regenerated (miss) and why. Log the cache key values used for the match.

**Phase:** Phase 1 of v2.0 (SceneDescription Persistence). Must be implemented before any zone-matching work begins, because the two-stage pipeline depends on reliable cached scene descriptions.

---

### Pitfall V2-8: SFX Synthesis — Sample Rate Mismatch, Duration Mismatch, and Pipe Deadlock

**What goes wrong:** Transition SFX are synthesized via FFmpeg's `lavfi` source filters (sine, noise) or piped through SoX. Three failure modes:

**(a) Sample rate mismatch between synthesized SFX and film audio:**
FFmpeg's `lavfi` generates audio at a default sample rate that may differ from the film's audio sample rate. The `sine` source generates at 44100Hz by default. If the rest of the pipeline uses 48000Hz, the SFX sounds slightly off-pitch when mixed (44100 interpreted as 48000 plays at 108.84% speed). The pitch shift is ~0.73 semitones — subtle but audible.

**(b) Synthesized SFX duration does not match the transition it covers:**
A transition SFX synthesized for a 0.5s crossfade is not automatically trimmed to 0.5s. If the synthesis command produces a 1.0s audio file (common with FFmpeg's lavfi + `-t` flag edge cases), the SFX extends into the next clip's audio. For fade-to-black transitions, a whoosh SFX that is 0.3s too long makes the next clip's first line of dialogue sound like it begins mid-effect.

**(c) SoX pipe deadlock when FFmpeg writes to stdout and SoX reads from stdin without a proper pipe:**
If synthesis involves piping FFmpeg output into SoX for processing (e.g. adding reverb to a synthesized tone), the standard deadlock scenario applies: if both processes write to an unbuffered pipe simultaneously and the pipe buffer fills, both processes block. This only happens with larger audio files but is silent — the pipeline hangs indefinitely with no error.

**Prevention:**
1. Always explicitly specify `-ar 48000` on every `lavfi` source synthesis command. Never rely on FFmpeg's default sample rate for generated audio. Canonical rule: all audio in this pipeline is 48000Hz stereo AAC.
2. Use `-t <exact_duration>` in the FFmpeg synthesis command to match the transition duration precisely. Verify the output duration with `ffprobe` after generation — if it differs from target by more than 50ms, regenerate or trim.
3. If SoX is used for post-processing, avoid pipes. Write FFmpeg output to a temp file, then run SoX as a separate process reading from the temp file. This eliminates pipe deadlock at the cost of one extra disk write per SFX (negligible for <10s files).
4. For SFX synthesis, prefer FFmpeg-native lavfi over SoX integration. FFmpeg can synthesize sine tones, filtered noise, and AM-modulated tones entirely within a single process invocation. SoX adds a dependency and pipe complexity for marginal benefit on short synthesis tasks.

**Example FFmpeg-only SFX synthesis (whoosh transition):**
```
ffmpeg -y -f lavfi -i "sine=frequency=200:duration=0.5,afade=t=in:d=0.1,afade=t=out:st=0.4:d=0.1" \
  -ar 48000 -ac 2 -c:a aac transition_whoosh.aac
```

**Detection:** After every SFX synthesis, run `ffprobe -show_entries stream=duration,sample_rate,channels` on the output and assert: duration within 50ms of target, sample_rate == 48000, channels == 2.

**Phase:** Phase 3 of v2.0 (Transition SFX). The audio format contract (48000Hz, stereo, AAC) must be enforced at synthesis time, not at mix time.

---

### Pitfall V2-9: Two-Stage LLM Context Budget — Text Model Overload and Zone Classification Instability

**What goes wrong:** The text-only structural analysis model receives the full subtitle corpus (potentially 1,000-3,000 subtitle events from a 2-hour film) to classify scenes into structural zones. Two failure modes:

**(a) Context window overflow:**
A 2-hour film typically generates 1,800-2,400 subtitle lines. At roughly 15 tokens per subtitle line (timestamp + text), that is 27,000-36,000 tokens. Most lightweight LLaMA models (1B-3B parameters) have a context window of 2,048-8,192 tokens. The full subtitle corpus does not fit. The model silently truncates its input context, meaning the latter half of the film (Acts 2 and 3) is never analyzed. The zone classification assigns nearly all content to BEGIN_T because the model only sees the beginning.

**(b) Zone classification is sensitive to prompt framing:**
The text-only model must produce structured zone labels (BEGIN_T, ESCALATION_T, CLIMAX_T). Small changes in prompt wording (e.g. "classify" vs "categorize", "zones" vs "sections") produce dramatically different outputs from small models. A model that works correctly with one prompt may produce all-ESCALATION_T classifications if the prompt is slightly rephrased during a refactor.

**Prevention:**
1. Never send the full subtitle corpus to the text model in a single call. Chunk the subtitle corpus into segments of 50-100 events (representing roughly 5-10 minutes of film). Call the model once per chunk, receiving zone labels per chunk. This keeps each call well within 2K-4K tokens.
2. Use a fixed, regression-tested prompt template stored as a constant in `inference/structural.py`. Any change to the prompt must be explicitly reviewed and tested against a known-good output. Do not allow prompt construction to vary based on runtime state.
3. Validate zone label output: the model should return one of exactly three strings per scene chunk. If the output contains anything else, retry once with temperature lowered to 0. If the retry also fails, assign the default zone for the film position (beginning 33% → BEGIN_T, middle 33% → ESCALATION_T, final 33% → CLIMAX_T) and log a warning.
4. Measure and document the context window of the specific model being used. Store this as a constant (`TEXT_MODEL_CONTEXT_TOKENS = 4096`). The chunking logic must compute chunk sizes from this constant, not from a hardcoded estimate.

**Detection:** Log the number of tokens in each call payload (approximated as `len(text.split()) * 1.3`). Flag any call where estimated token count exceeds 80% of the model's context window.

**Phase:** Phase 1 of v2.0 (Two-Stage LLM Pipeline).

---

### Pitfall V2-10: Silence Segments as Deliberate Editorial Tool — Duration Precision and A/V Sync Gap

**What goes wrong:** v2.0 adds deliberate silence segments (black video, no audio) as editorial breathing room. These are generated with FFmpeg lavfi (`color=c=black:duration=X`). Two failure modes:

**(a) Fractional duration causes A/V desync in concatenation:**
A silence segment specified as `duration=1.5` may be generated with a fractional-frame duration (e.g. 1.5008s for 24fps) due to PTS rounding. When concatenated with clips re-encoded at exactly 1.5s using `-t 1.5`, the silence segment is slightly longer. Over multiple silence segments, this accumulates into visible A/V sync drift (video finishes before audio or vice versa).

**(b) Silence segment treated as a clip in audio mixing causes timing offset:**
If the music bed mixing step counts silence segments as regular clips and tries to apply audio extraction to them (they have no audio stream), `ffprobe` returns no audio stream duration, causing a division by zero or index error in the music timing calculation.

**Prevention:**
1. Always round silence duration to the nearest frame boundary before generating: `silence_duration_s = round(target_duration_s * fps) / fps`. For 24fps content, 1.5s becomes `round(1.5 * 24) / 24 = 36/24 = 1.5` exactly. Prevents fractional-frame accumulation.
2. Silence segments must be generated with explicit frame rate matching the source: `-r <fps>` in the lavfi command.
3. Tag silence segments in the manifest with a `is_silence: bool` field. The music bed mixing step must skip silence segments during any per-clip audio calculations and simply continue the music bed timeline through them (they contribute duration but no audio source).
4. Generate silence segments with an explicit silent audio stream included (`-f lavfi -i "anullsrc=r=48000:cl=stereo" -t X`) so every segment has both video and audio streams. This makes the concatenation step treat them uniformly without special-casing.

**Phase:** Phase 2 of v2.0 (Silence/Breathing Room). Address in the same phase as BPM grid — silence segments interact directly with the beat grid timing.

---

## Minor Pitfalls (v2.0)

---

### Pitfall V2-11: BPM Grid and Non-Linear Ordering Interaction — Semantic Zones Override Rhythm

**What goes wrong:** The BPM edit grid distributes cuts on beat positions. The non-linear ordering algorithm distributes clips by semantic zone. When both systems run, they can conflict: the semantic ordering wants to place a 3.5s clip (fits 3 beats at 120BPM) at a position where the beat grid demands 2-beat slots (2s). The clip is either padded with silence (disrupts the beat feel) or trimmed (cuts off dialogue). Neither outcome is ideal, but the worse failure is the pipeline choosing silently rather than surfacing the conflict.

**Prevention:** Design the zone ordering pass to run first, producing a clip sequence. Then the BPM grid pass trims or pads clips to fit beat slots, constrained by a minimum intelligibility duration (no clip under 0.8s, no trim that cuts spoken dialogue mid-word). Log all trims/pads so the human review step can see them.

**Phase:** Phase 2 of v2.0 (BPM Grid + Ordering).

---

### Pitfall V2-12: Music Bed Track Looping — Hard Loop Boundary Artifacts

**What goes wrong:** A downloaded royalty-free track may be shorter than the assembled trailer (common — many royalty-free tracks are 60-90 seconds; trailers are ~120 seconds). Naively looping the track with FFmpeg's `aloop` filter produces an audible click at the loop boundary when the track does not loop seamlessly (different amplitude at end vs. start).

**Prevention:** Use crossfade loop: fade the end of track iteration 1 into the start of track iteration 2 using `acrossfade=d=2.0` in the filter graph. Alternatively, select tracks from the archive that are long enough for the target trailer duration (flag tracks under 90 seconds as requiring loop handling).

**Phase:** Phase 3 of v2.0 (Music Bed).

---

### Pitfall V2-13: lut_path Escaping Breaks when SFX and Music File Paths Enter the Same Filter Graph

**What goes wrong:** v1.0 has a known-safe FFmpeg command construction approach for LUT paths. v2.0 adds music bed paths and SFX paths into filter graph arguments. Paths with spaces or special characters in these new arguments re-introduce the escaping problem for the audio filter graph specifically. The existing `ffmpeg_escape_path()` helper (if it exists) may not be applied to audio filter paths — it was likely only applied to LUT paths.

**Prevention:** Apply path escaping to every path that enters any FFmpeg filter graph argument, not just LUT paths. Consider storing all audio asset paths in temp directories with sanitized names (no spaces, no special characters) to eliminate the risk at the source.

**Phase:** Phase 2 of v2.0 (Audio Architecture). Audit the FFmpeg builder for audio filter path handling.

---

## Phase-Specific Warnings (v2.0)

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Two-Stage LLM Pipeline | CUDA memory lingering between model swap (V2-1) | Poll nvidia-smi after first server stop; minimum 3s gap before second start |
| Two-Stage LLM Pipeline | Text model context overflow (V2-9) | Chunk subtitle corpus into 50-100 event batches; never send full corpus in one call |
| SceneDescription Persistence | Stale cache from changed source file (V2-7) | Cache key must include mtime + size hash, not just path |
| SceneDescription Persistence | Schema migration corrupting old caches (V2-7) | schema_version field; version mismatch always triggers full re-inference |
| Non-Linear Ordering | Audio bleed between reordered clips (V2-3) | Per-clip PTS reset + 0.1s audio fades on every extracted segment |
| Non-Linear Ordering | Context-dependent dialogue selected for BEGIN_T (V2-3) | Filter pronoun-leading dialogue from zone assignments |
| BPM Grid | Zero BPM from silent tracks / empty beats array (V2-4) | Guard against 0.0 BPM; fallback to vibe-default BPM |
| BPM Grid | Octave errors (half/double tempo) (V2-4) | Clamp to vibe range; halve/double when outside bounds |
| BPM Grid vs Ordering | Zone ordering conflicts with beat slot duration (V2-11) | Ordering first, BPM trimming second; log all trims |
| Music Bed | API downtime / OAuth expiry / 429 rate limit (V2-5) | Cache tracks; graceful degradation to no-music on any API failure |
| Music Bed | Loop boundary click on short tracks (V2-12) | Crossfade loop with acrossfade; flag tracks < 90s |
| Audio Mixing | amix normalize=1 destroys ducking ratios (V2-2) | Always use normalize=0; apply volume filters before amix |
| Audio Mixing | loudnorm on mixed output destroys dynamic range (V2-2) | Normalize each stem independently before mixing |
| Audio Mixing | Sample rate mismatch across audio sources (V2-2) | Resample all audio to 48000Hz before any mixing filtergraph |
| Audio Mixing | Music + SFX paths not escaped in filter graph (V2-13) | Extend path escaping helper to all filter graph arguments |
| VO Extraction | Background score bleeds into VO clip (V2-6) | Accept limitation; lower VO volume in mix; position during music lulls |
| VO Extraction | Short segment loudnorm artifacts (V2-6) | Always re-encode VO to AAC 48000Hz 2ch; minimum 0.8s duration |
| VO Extraction | AAC frame-boundary seek offset (V2-6) | Use output seeking (-ss after -i) for VO extraction |
| SFX Synthesis | Sample rate default 44100Hz from lavfi (V2-8) | Always specify -ar 48000 in every synthesis command |
| SFX Synthesis | Duration mismatch — SFX too long for transition (V2-8) | Use -t <exact_duration>; verify with ffprobe after generation |
| SFX Synthesis | SoX pipe deadlock (V2-8) | Write to temp file; never pipe FFmpeg → SoX |
| Silence Segments | Fractional frame duration accumulation (V2-10) | Round to nearest frame boundary before generating |
| Silence Segments | Missing audio stream causes mixer errors (V2-10) | Always generate silence segments with explicit anullsrc audio stream |

---

## Retained v1.0 Critical Pitfalls

The following pitfalls from v1.0 research remain valid and should be revisited in v2.0 context where noted.

### Pitfall 1: VRAM Contention Between llama-server and FFmpeg Hardware Decoding
(See v1.0 PITFALLS — fully resolved in v1.0 via GPU_LOCK. v2.0 note: the two-stage pipeline introduces a new model-swap window where both sequential llama-server invocations must still be covered by GPU_LOCK. Do not release GPU_LOCK between stages.)

### Pitfall 4: Timecode Drift Between Analysis Proxy and Source File
(See v1.0 PITFALLS — v2.0 note: non-linear ordering increases the number of `source_start_s` / `source_end_s` lookups against the source file. Any timecode drift that was marginal in v1.0 becomes more visible when clips from across the full 2-hour timeline are randomly combined.)

### Pitfall 9: Audio/Video Sync Drift in Conform Step
(See v1.0 PITFALLS — v2.0 note: the addition of music bed and SFX audio tracks increases the number of audio inputs to the mixing filtergraph. The existing `-ar 48000 -avoid_negative_ts make_zero` pattern from `conform/pipeline.py` must be extended to all new audio sources.)

### Pitfall 11: JSON Manifest Schema Evolution
(See v1.0 PITFALLS — v2.0 directly triggers this. The v2.0 manifest additions (zone classification, BPM grid, music track reference, silence segment flags) require a schema version bump from `"1.0"` to `"2.0"`. Any v1.0 manifests on disk will fail validation against the v2.0 schema. This is expected and correct — handle it with a clear error: "This manifest was created with CineCut v1.0 and requires re-generation for v2.0 features.")

---

## Sources

### Verified (WebSearch + official documentation)

- FFmpeg `amix` filter documentation — `normalize=0` default behavior, sample rate mismatch rejection: [FFmpeg Filters Documentation](https://ffmpeg.org/ffmpeg-filters.html)
- Librosa `beat_track` edge cases — 0 BPM on silence, `trim=False` behavior, octave errors: [librosa 0.11.0 beat_track docs](https://librosa.org/doc/main/generated/librosa.beat.beat_track.html)
- Freesound API rate limits (60 req/min, 2000 req/day, 429 response), OAuth2 token 24hr expiry, refresh token strategy: [Freesound APIv2 Overview](https://freesound.org/docs/api/overview.html), [Freesound Authentication](https://freesound.org/docs/api/authentication.html)
- llama-server runtime model switching not natively supported; workarounds via process restart: [llama.cpp Issue #13027](https://github.com/ggml-org/llama.cpp/issues/13027), [llama.cpp Model Management blog](https://huggingface.co/blog/ggml-org/model-management-in-llamacpp)
- Multimodal projector VRAM overhead (~1.9GB additional for mmproj): [llama.cpp multimodal docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
- SoX pipe streaming mode issues (size header absent in streaming, pipe buffer deadlock): [FFmpeg-user SoX resampler thread](https://ffmpeg-user.ffmpeg.narkive.com/N2TUbPVd/audio-resampler-sox-returns-different-result)
- FFmpeg concat `setpts=PTS-STARTPTS` / `asetpts=PTS-STARTPTS` requirement for mixed-source concatenation: [FFmpeg FilteringGuide](https://trac.ffmpeg.org/wiki/FilteringGuide)
- AAC frame boundary (~21ms) seeking offset with stream copy and input seeking: [FFmpeg documentation on -ss and -accurate_seek](https://www.ffmpeg.org/ffmpeg.html)

### Training Data (MEDIUM confidence, not independently verified by WebSearch)

- CUDA 11.4 / Kepler slow VRAM deallocation timing after process exit
- llama.cpp context window sizes for 1B-3B text-only models
- AC3/DTS to stereo downmix FFmpeg filter syntax
- Film audio extraction background-score bleed characteristics

---

*Research completed: 2026-02-28*
*Covers v2.0 feature additions. v1.0 pitfalls retained for reference. v2.0 pitfalls are additive, not replacements.*
