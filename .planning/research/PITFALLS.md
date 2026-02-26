# Domain Pitfalls

**Domain:** AI-driven video trailer generation with local LLM inference
**Project:** CineCut AI
**Researched:** 2026-02-26
**Confidence:** MEDIUM (training data; WebSearch unavailable for verification)

---

## Critical Pitfalls

Mistakes that cause rewrites, corrupted output, or fundamental architecture problems.

---

### Pitfall 1: VRAM Contention Between llama-cli and FFmpeg Hardware Decoding

**What goes wrong:** llama-cli loads a LLaVA model that occupies 8-10GB of the 12GB VRAM budget. FFmpeg, when compiled with NVDEC/NVENC support (cuvid, h264_cuvid), silently allocates GPU memory for hardware decoding/encoding. The two processes compete for the same 12GB VRAM. The system appears to work on short clips but OOMs on 2-hour films because FFmpeg's GPU memory allocation grows with decode queue depth.

**Why it happens:** llama-cli and FFmpeg are independent processes with no shared memory manager. Neither knows the other exists. CUDA's default memory allocation strategy is greedy -- llama.cpp in particular will pre-allocate a large contiguous block at startup.

**Consequences:** CUDA out-of-memory errors mid-pipeline (after potentially hours of processing). Corrupted partial output. In worst cases, the NVIDIA driver crashes entirely, requiring a restart of both processes.

**Warning signs:**
- `nvidia-smi` shows >95% VRAM utilization during proxy creation
- Sporadic `CUDA error: out of memory` that only appear with longer films
- FFmpeg exits with signal 9 (killed) or cryptic "Unknown error"
- System becomes sluggish during pipeline execution

**Prevention:**
1. **Never run llama-cli and FFmpeg GPU operations concurrently.** Design the pipeline as strictly sequential: FFmpeg creates all proxies/keyframes first, then llama-cli runs inference, then FFmpeg does the conform. No overlap.
2. **Force FFmpeg to use CPU decoding for the analysis proxy.** Use `-hwaccel none` or simply omit hardware acceleration flags. At 420p, CPU decode is fast enough and avoids all VRAM contention.
3. **Reserve GPU exclusively for inference.** Only use FFmpeg NVENC for the final conform step (if at all), and only after llama-cli has fully exited and released VRAM.
4. **Add a VRAM check before inference.** Shell out to `nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits` and abort with a clear message if free VRAM is below the model's requirement.
5. **Set `CUDA_VISIBLE_DEVICES` per subprocess** if you need isolation, though with a single GPU this mainly prevents accidental multi-context allocation.

**Detection:** Monitor `nvidia-smi` output at each pipeline stage transition. Log VRAM usage before and after each major operation.

**Phase:** Must be addressed in Phase 1 (pipeline architecture). Getting this wrong means rewriting the entire orchestration layer.

---

### Pitfall 2: CUDA 11.4 / Kepler Architecture Compatibility Wall

**What goes wrong:** The Quadro K6000 uses the Kepler architecture (compute capability 3.5). NVIDIA dropped Kepler support in CUDA 12.0+. Many modern libraries (PyTorch 2.x, newer llama.cpp builds) require CUDA 12+ or assume compute capability 5.0+ (Maxwell). Attempting to use pre-built binaries or pip packages results in either silent failures, incorrect results, or startup crashes.

**Why it happens:** The ecosystem is moving toward newer GPU architectures. CUDA 11.4 is the last major CUDA version supporting Kepler. Pre-built wheels for llama-cpp-python, PyTorch, etc. are typically compiled for CUDA 12.x and sm_70+ (Volta). Even if they claim CUDA 11 support, they may not include sm_35 kernels.

**Consequences:**
- llama-cli binary may need to be compiled from source with `-DLLAMA_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=35`
- PyTorch (if used for any utility) must be pinned to <=2.0.x or <=2.1.x with the CUDA 11.8 wheel (which still includes sm_35)
- Random segfaults or "no kernel image" errors at runtime that are extremely hard to diagnose
- Performance will be significantly lower than benchmarks suggest (benchmarks are typically for Ampere/Ada GPUs)

**Warning signs:**
- `CUDA error: no kernel image is available for execution on the device`
- llama-cli compiles but produces garbage output (wrong CUDA arch)
- `torch.cuda.is_available()` returns True but operations fail
- Performance is 10-100x worse than expected benchmarks

**Prevention:**
1. **Compile llama.cpp from source** with explicit `CMAKE_CUDA_ARCHITECTURES=35`. Do NOT use pre-built releases.
2. **Pin CUDA toolkit to 11.4.** Do not install CUDA 12 even if prompted. Use `nvcc --version` to verify.
3. **If using any Python CUDA libraries,** pin to versions with known CUDA 11.4 / sm_35 support. Document exact version pins.
4. **Test inference early** with a simple llama-cli prompt before building any pipeline. Verify output quality, not just "it runs."
5. **Accept performance constraints.** Kepler lacks tensor cores and has lower memory bandwidth. Budget 5-15 seconds per keyframe for LLaVA inference. Design the pipeline for patience, not speed.

**Detection:** Run `nvidia-smi` to confirm driver 470.x is loaded. Run `nvcc --version` to confirm CUDA 11.4. Test llama-cli with `--verbose` flag to see CUDA backend initialization.

**Phase:** Must be validated in Phase 0 (environment setup) before any other work begins. If llama-cli cannot run LLaVA on this GPU, the entire project concept needs revision.

---

### Pitfall 3: Subprocess Management of llama-cli -- Silent Failures and Zombie Processes

**What goes wrong:** llama-cli is invoked via `subprocess.Popen` or `subprocess.run`. Over the course of analyzing hundreds of keyframes from a 2-hour film, several failure modes emerge: (a) llama-cli hangs on certain inputs and never returns, (b) llama-cli crashes but the parent Python process doesn't detect it, (c) zombie processes accumulate when the parent doesn't properly wait, (d) stderr output is lost, making failures undiagnosable.

**Why it happens:** Subprocess-based integration lacks the error propagation of in-process function calls. llama-cli writes to stdout/stderr in unpredictable ways. Some LLaVA prompts cause the model to enter a generation loop that never hits an EOS token. CUDA errors in the child process may corrupt the GPU state without the parent knowing.

**Consequences:**
- Pipeline appears to hang for hours (actually one llama-cli invocation is stuck)
- Accumulated zombie processes consume PID space and potentially hold VRAM allocations
- Missing or truncated scene descriptions that silently degrade trailer quality
- GPU left in a bad state after a crash, requiring manual cleanup

**Warning signs:**
- Single keyframe analysis taking >60 seconds (should be 5-15s on Kepler)
- `ps aux | grep llama` shows multiple llama-cli processes
- `nvidia-smi` shows VRAM allocated but no active compute
- Incomplete JSON in llama-cli output (truncated mid-token)

**Prevention:**
1. **Always use `subprocess.run()` with `timeout` parameter.** Set a generous but firm timeout (e.g., 120 seconds per keyframe). Catch `subprocess.TimeoutExpired`, kill the process, and log the failure.
2. **Capture both stdout and stderr.** Use `capture_output=True` and log stderr on any non-zero exit code.
3. **Validate output before proceeding.** llama-cli output should be parseable (check for valid JSON or expected structure). If output is garbage, retry once then skip with a logged warning.
4. **Implement a process cleanup wrapper:**
   ```python
   def run_llama(args, timeout=120):
       try:
           result = subprocess.run(
               args, capture_output=True, text=True, timeout=timeout
           )
           if result.returncode != 0:
               logger.error(f"llama-cli failed: {result.stderr}")
               return None
           return result.stdout
       except subprocess.TimeoutExpired:
           logger.warning("llama-cli timed out, skipping frame")
           return None
   ```
5. **Never use `subprocess.Popen` without explicit `.wait()` or context manager.** If you need streaming output, use `Popen` with a background thread reading stdout, but always ensure cleanup in a `finally` block.
6. **Add a `--max-tokens` flag** to every llama-cli invocation to prevent runaway generation.

**Detection:** Log wall-clock time per inference call. Alert if any single call exceeds 2x the median time. Monitor process count.

**Phase:** Phase 2 (inference integration). Must be designed correctly from the start -- retrofitting timeout/retry logic is painful.

---

### Pitfall 4: Timecode Drift Between Analysis Proxy and Source File

**What goes wrong:** The 420p analysis proxy is created via FFmpeg transcode. Keyframes are extracted from this proxy and analyzed by LLaVA. The TRAILER_MANIFEST.json records timecodes based on the proxy. When the final conform step seeks into the original high-resolution source using these timecodes, the actual frame is wrong -- sometimes by milliseconds (visible as a jump cut), sometimes by seconds (completely wrong shot).

**Why it happens:** Multiple causes:
- **Variable frame rate (VFR) source files:** Many MKV files from consumer cameras or streaming rips have variable frame rates. FFmpeg normalizes to constant frame rate (CFR) during proxy creation, shifting frame timing.
- **Seek precision:** FFmpeg's `-ss` before `-i` does keyframe-based seeking. The nearest keyframe in the proxy may be at a different offset than in the source due to different GOP structures.
- **Transcoding timestamp rounding:** FFmpeg's timestamp handling can introduce sub-frame rounding errors that accumulate over a 2-hour file.
- **Container timestamp differences:** MKV, AVI, and MP4 use different internal timestamp precision (MKV uses nanoseconds, MP4 uses a timescale).

**Consequences:**
- Trailer clips start/end on wrong frames -- visible as flash frames or missing the intended moment
- Audio/video desynchronization in the final output
- The `--review` workflow becomes unreliable (what the user approved in the manifest is not what they get)
- Worst case: the entire trailer is 1-2 seconds off throughout, making it look amateurish

**Warning signs:**
- First/last frame of clips shows a clearly different shot than expected
- Audio from one scene plays over video from an adjacent scene
- `--review` mode output doesn't match final conform output
- Film has VFR (check with `ffprobe -v error -select_streams v -show_entries stream=r_frame_rate,avg_frame_rate`)

**Prevention:**
1. **Force CFR during proxy creation** with `-vsync cfr` or `-r 24` (matching source FPS). Verify the proxy frame count matches expected `duration * fps`.
2. **Use PTS-based timecodes, not frame numbers.** Store timecodes in the manifest as seconds with millisecond precision (e.g., `"start_time": 3723.456`), not frame indices.
3. **For the final conform, use `-ss` before `-i` for fast seeking, but add `-noaccurate_seek` awareness.** Test both `-ss` before and after `-i` for your specific source format. `-ss` after `-i` is slower but frame-accurate.
4. **Validate timecodes with a spot-check step.** After manifest generation, extract 3-5 thumbnails from the SOURCE at manifest timecodes and compare them against the proxy frames that were analyzed. Flag discrepancies.
5. **Normalize VFR to CFR at ingest.** If `r_frame_rate != avg_frame_rate`, warn the user and force CFR conversion as the first pipeline step.
6. **Store the proxy's exact frame rate and timescale in the manifest metadata** so the conform step can compensate.

**Detection:** Compare `ffprobe` frame counts between proxy and source. Any mismatch >1 frame per minute of content indicates a drift problem.

**Phase:** Phase 1 (proxy pipeline design) and Phase 4 (conform step). The proxy creation decisions in Phase 1 directly determine whether Phase 4 can be frame-accurate.

---

### Pitfall 5: FFmpeg Command Construction Injection and Escaping Failures

**What goes wrong:** FFmpeg commands are built by string concatenation or f-strings using user-provided filenames, timecodes, and filter expressions. Special characters in filenames (spaces, quotes, brackets, unicode) break the command. Worse, if subtitle files or LUT paths contain shell metacharacters, they can cause shell injection when passed through `subprocess.run(shell=True)`.

**Why it happens:** FFmpeg's command-line syntax is complex. Filter graphs use their own escaping rules (colons, backslashes, semicolons have special meaning). Developers often test with clean filenames and never encounter the issue until a user provides `Movie (2024) [1080p].mkv` or `C'est la Vie.srt`.

**Consequences:**
- Pipeline crashes on filenames with spaces or special characters (most common user complaint)
- Shell injection vulnerability if `shell=True` is used
- LUT filter application fails silently when .cube file path contains spaces
- Subtitle burn-in fails on ASS files with backslashes in style definitions

**Warning signs:**
- Works perfectly with test files, fails on first real user input
- FFmpeg errors mentioning "No such file or directory" despite the file existing
- Filter graph parsing errors (`Invalid filtergraph`)

**Prevention:**
1. **Never use `shell=True` with subprocess.** Always pass arguments as a list:
   ```python
   subprocess.run(["ffmpeg", "-i", input_path, ...])  # CORRECT
   subprocess.run(f"ffmpeg -i {input_path} ...", shell=True)  # WRONG
   ```
2. **For FFmpeg filter graphs,** use FFmpeg's escaping rules. Colons in paths must be escaped as `\\:`. Use a helper function:
   ```python
   def ffmpeg_escape_path(path: str) -> str:
       return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
   ```
3. **Validate all filenames at CLI entry.** Reject or warn about filenames that will cause FFmpeg issues, or copy to a sanitized temp path.
4. **Test with adversarial filenames** during development: spaces, parentheses, brackets, quotes, unicode characters, very long paths.

**Detection:** Unit test the FFmpeg command builder with a suite of pathological filenames.

**Phase:** Phase 1 (FFmpeg wrapper design). Must be correct from the start -- every subsequent phase depends on reliable FFmpeg execution.

---

## Moderate Pitfalls

---

### Pitfall 6: Keyframe Extraction Disk Space Exhaustion

**What goes wrong:** Extracting keyframes from a 2-hour film at even 1 frame per second produces 7,200 PNG images. At 420p, each PNG is ~200-500KB. Total: 1.5-3.5GB of temporary images per film. If the pipeline doesn't clean up after itself, or if it crashes mid-extraction, these files accumulate. Running the tool on multiple films fills the disk.

**Why it happens:** The naive approach (`ffmpeg -vf fps=1 frame_%05d.png`) writes all frames first, then processes them. Developers forget to add cleanup. Crash-recovery paths skip cleanup. Users run the tool repeatedly during testing.

**Consequences:**
- Disk full errors mid-pipeline (FFmpeg writes a truncated image, LLaVA analyzes garbage)
- `/tmp` fills up, affecting the entire system
- Slow filesystem performance as directories accumulate thousands of small files
- Filename collisions if multiple runs target the same output directory

**Warning signs:**
- Disk usage growing by several GB per run
- Slow file listing in the temp directory
- `OSError: [Errno 28] No space left on device`

**Prevention:**
1. **Use Python's `tempfile.mkdtemp()` for each run.** This guarantees unique directories and enables easy cleanup.
2. **Process keyframes in a streaming fashion** -- extract one (or a small batch), analyze with LLaVA, delete the image, then extract the next. Never materialize all 7,200 frames simultaneously.
3. **Register cleanup with `atexit`** and in signal handlers (SIGINT, SIGTERM) so interrupted runs still clean up.
4. **Don't extract every frame.** Extract only I-frames (keyframes) with `-vf "select=eq(pict_type,I)"` or use scene detection (`-vf "select=gt(scene,0.3)"`) to reduce frame count by 10-50x.
5. **Use JPEG instead of PNG** for analysis frames. LLaVA doesn't need lossless input. JPEG at quality 80 is ~5x smaller.
6. **Check available disk space before extraction** and warn if below a threshold (e.g., 10GB free).

**Detection:** Log total disk usage of temp directories. Alert if >5GB per run.

**Phase:** Phase 2 (keyframe extraction). Design the extraction strategy before writing the inference loop.

---

### Pitfall 7: Subtitle Parsing Edge Cases -- Encoding, Overlapping Cues, Malformed Files

**What goes wrong:** Real-world SRT/ASS files are messy. Common issues: (a) encoding is not UTF-8 (Latin-1, Windows-1252, Chinese GB2312), (b) SRT files have overlapping timestamp ranges, (c) ASS files use non-standard formatting tags that break parsers, (d) timestamps are malformed (missing milliseconds, reversed start/end), (e) HTML tags in SRT text (`<i>`, `<b>`), (f) BOM (byte order mark) at file start.

**Why it happens:** Subtitle files come from many sources: fan communities, professional subtitling houses, DVD/Blu-ray rips, streaming downloads. There is no enforcement of standards. The SRT "format" is not formally specified at all -- it's a de facto standard with many dialects.

**Consequences:**
- Narrative analysis misses or misinterprets dialogue
- Crash on encoding errors (`UnicodeDecodeError`)
- Overlapping cues cause duplicate text, inflating the importance of repeated dialogue
- Missing timestamps mean the system can't map dialogue to video timecodes
- ASS style overrides parsed as literal text (e.g., `{\an8}` appearing in narrative analysis)

**Warning signs:**
- `UnicodeDecodeError` on first run with a real subtitle file
- Parsed dialogue contains formatting artifacts (`<i>`, `{\an8}`, `{\\pos(320,50)}`)
- Timeline has gaps or overlaps when visualized
- Subtitle text is empty after parsing (encoding mismatch produced empty strings)

**Prevention:**
1. **Use `chardet` or `charset_normalizer` for encoding detection.** Try UTF-8 first, fall back to detected encoding, and always decode to UTF-8 internally.
2. **Use `pysubs2` for parsing,** not a hand-rolled parser. It handles both SRT and ASS, strips formatting tags, and normalizes timestamps. It is well-maintained and handles most edge cases.
3. **Strip all formatting tags** after parsing. For SRT: remove HTML tags. For ASS: remove override blocks (`{\\...}`).
4. **Handle overlapping cues** by merging overlapping entries or taking the longer one. Don't duplicate text.
5. **Validate after parsing:** Check that at least 80% of cues have non-empty text and valid timestamps. If not, warn the user that the subtitle file may be corrupt.
6. **Handle BOM explicitly:** Open files with `encoding='utf-8-sig'` as the first attempt (this strips BOM automatically).

**Detection:** Log subtitle parse statistics: total cues, empty cues, encoding detected, overlap count.

**Phase:** Phase 1 (input processing). Subtitle parsing is upstream of everything -- bad parsing corrupts all downstream analysis.

---

### Pitfall 8: LLaVA Prompt Engineering -- Hallucination, Context Overflow, and Inconsistent Output Format

**What goes wrong:** LLaVA is asked to describe a keyframe image for narrative analysis. Failure modes: (a) the model hallucinates details not present in the image (especially for dark/blurry frames), (b) the prompt + image tokens exceed the context window, causing truncated or incoherent output, (c) the output format varies between invocations (sometimes JSON, sometimes prose, sometimes bullet points) despite instructions, (d) the model describes the frame literally ("a dark rectangle") instead of narratively.

**Why it happens:** Vision-language models are not deterministic. Dark or ambiguous frames provide weak visual signal. The context window of smaller LLaVA variants (7B) is typically 2048-4096 tokens. Image tokens consume a large portion (~576 tokens for a 336x336 image with CLIP-ViT-L). If you also pass subtitle context + previous frame descriptions, you easily overflow. Format compliance is inherently unreliable with smaller models.

**Consequences:**
- Scene descriptions don't match actual content -- trailer selects wrong moments
- Context overflow causes model to ignore instructions (format, content focus)
- Inconsistent output format breaks downstream JSON parsing
- Dark/action scenes (exactly the ones most important for trailers) get the worst descriptions

**Warning signs:**
- LLaVA output varies wildly in structure between frames
- JSON parsing failures on llama-cli output
- Scene descriptions mention objects/people not in the frame
- Output length varies from 10 to 500+ tokens unpredictably

**Prevention:**
1. **Keep prompts minimal.** Do not try to cram subtitle context + instructions + format requirements into one prompt. The image tokens already consume a large chunk. A good prompt is 100-200 tokens max.
2. **Use a fixed output schema** with explicit delimiters, not JSON. JSON is unreliable from small models. Use a simple template:
   ```
   SCENE_TYPE: [action/dialogue/establishing/transition]
   MOOD: [one word]
   DESCRIPTION: [one sentence]
   INTENSITY: [1-5]
   ```
3. **Pre-filter frames before sending to LLaVA.** Calculate average brightness and contrast. Skip frames that are nearly black (common during fades). Skip frames that are nearly identical to the previous frame (static shots).
4. **Set temperature to 0 (or as low as llama-cli allows)** for deterministic output. Use `--temp 0` flag.
5. **Set `--max-tokens` to a reasonable limit** (150-200 tokens). This prevents runaway generation and keeps output focused.
6. **Post-process output with simple regex/string matching.** Don't rely on the model always following the format. Parse what you can, use defaults for what you can't.
7. **Separate vision analysis from narrative analysis.** LLaVA describes the image. A separate text-based pass (using subtitle data only, no image) handles narrative structure. Don't ask LLaVA to do both.

**Detection:** Log output token count per frame. Flag frames where output parsing fails. Track hallucination rate by spot-checking a sample of descriptions against actual frames.

**Phase:** Phase 2 (inference pipeline). Prompt engineering is iterative -- budget time for experimentation.

---

### Pitfall 9: Audio/Video Sync Drift in the Conform Step

**What goes wrong:** The final trailer is assembled by concatenating clips extracted from the source file. Each clip is independently extracted with FFmpeg. When concatenated, audio drifts out of sync -- sometimes by a few frames, sometimes by entire seconds. The drift accumulates with each clip.

**Why it happens:** Multiple causes compound:
- **Audio frame boundaries don't align with video frames.** AAC audio has 1024-sample frames (~23ms at 48kHz). If a video clip starts at a frame boundary that doesn't align with an AAC frame boundary, FFmpeg pads or truncates the audio, introducing a small offset.
- **Variable audio sample rate in source.** Some MKV files have audio streams with slightly irregular sample timing.
- **Concatenation without re-encoding.** Using the `concat` demuxer on clips with different GOP structures or audio frame alignments causes cumulative drift.
- **Using `-c copy` for the final output.** Stream copy skips re-encoding but cannot fix timestamp irregularities.

**Consequences:**
- Dialogue doesn't match lip movement (noticeable at >2 frames / ~80ms of drift)
- Sound effects and music hits land on wrong visuals
- Professional-looking trailer ruined by amateur sync issues

**Warning signs:**
- Audio feels "slightly off" in the last third of the trailer
- `ffprobe` shows different durations for audio and video streams in individual clips
- Concatenated output has brief audio glitches at cut points

**Prevention:**
1. **Re-encode both audio and video in the final conform step.** Do NOT use `-c copy`. The quality cost of re-encoding is negligible compared to sync issues.
2. **Extract clips with PTS-based timestamps.** Use `-af asetpts=PTS-STARTPTS` and `-vf setpts=PTS-STARTPTS` to reset timestamps per clip.
3. **Use the `concat` filter (not the concat demuxer)** for joining clips. The filter re-encodes and handles timestamp normalization. The demuxer does stream copy and inherits all source timing problems:
   ```
   ffmpeg -i clip1.mp4 -i clip2.mp4 -filter_complex "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1" output.mp4
   ```
4. **Normalize audio sample rate** during clip extraction with `-ar 48000`.
5. **Add a sync verification step** after assembly: extract audio and video durations from the final output and compare. They should match within 1 frame duration.

**Detection:** Compare audio and video stream durations in the final output with `ffprobe -show_entries stream=duration`. Difference should be <20ms.

**Phase:** Phase 4 (conform/assembly). This is the last step but must be designed alongside clip extraction in Phase 2-3.

---

### Pitfall 10: LUT Application Color Space Mismatches

**What goes wrong:** A .cube LUT file is designed for a specific input color space (typically Rec.709 or log). When applied to video in a different color space, the output looks wrong -- crushed blacks, blown highlights, weird color casts. The trailer looks "filtered" rather than "graded."

**Why it happens:** .cube LUT files are simple 3D lookup tables -- they have no metadata about expected input/output color spaces. If a LUT expects log-encoded input (common for cinematic LUTs) but receives Rec.709 gamma-encoded input, the transform produces incorrect results. Additionally, FFmpeg's `lut3d` filter doesn't perform any color space conversion -- it applies the LUT directly to whatever pixel values it receives.

**Consequences:**
- Trailer looks worse than the source material
- Different source files produce wildly different results with the same LUT
- Users blame the tool when the issue is LUT/color space mismatch
- Dark scenes become completely unreadable

**Warning signs:**
- Output looks excessively dark or contrasty
- Colors look "wrong" -- oversaturated or desaturated in unexpected ways
- Same LUT looks different on different source files
- Highlights clip to pure white abruptly

**Prevention:**
1. **Design LUTs for Rec.709 input.** Most consumer/prosumer video is Rec.709. Don't use LOG-input LUTs unless you add a linearization step.
2. **Create/source LUTs specifically for this project.** Don't rely on random free LUTs from the internet -- they assume specific workflows (e.g., Blackmagic Film -> Rec.709). Create .cube files that transform Rec.709 to a stylized Rec.709 output.
3. **Apply LUTs after all other processing** (scaling, deinterlacing, etc.) but before final encoding.
4. **Use a conservative LUT intensity.** Apply the LUT at reduced strength by blending:
   ```
   -vf "split[a][b];[b]lut3d=file=vibe.cube[c];[a][c]blend=all_opacity=0.6"
   ```
   This ensures the LUT enhances rather than overwhelms the source material.
5. **Test each LUT against at least 3 different source materials** (bright scene, dark scene, skin tones) before shipping.
6. **Include a `--no-lut` flag** so users can bypass color grading if it causes issues.

**Detection:** Visual QA. There is no automated way to detect "looks wrong." Provide sample frame previews during `--review` mode.

**Phase:** Phase 3 (vibe profiles / LUT integration). LUTs should be one of the last features added because they're purely aesthetic.

---

### Pitfall 11: JSON Manifest Schema Evolution and Integrity

**What goes wrong:** The TRAILER_MANIFEST.json is the critical intermediary artifact. As the project evolves, the schema changes (new fields, renamed fields, changed types). Old manifests become incompatible with new code. Additionally, manifests can be corrupted by: (a) partial writes if the process crashes mid-generation, (b) manual edits (via `--review`) introducing typos or invalid values, (c) floating point precision loss in timecodes.

**Why it happens:** JSON manifests are easy to create but hard to validate. The schema exists only implicitly in the code. Manual editing (a core feature of `--review`) means the system must tolerate human-introduced errors.

**Consequences:**
- Conform step crashes on invalid manifest (after hours of inference work are already done)
- Timecode precision loss (JSON floating point) causes frame-level inaccuracy
- Schema changes break the `--review` workflow (user edits a manifest, schema changes, old edit is invalid)
- Invalid manual edits produce cryptic FFmpeg errors rather than clear validation messages

**Warning signs:**
- `KeyError` or `TypeError` during conform step
- Timecodes in output manifest differ slightly from inference calculations
- Users report `--review` edits "not taking effect"

**Prevention:**
1. **Define a formal schema using Pydantic models.** Validate the manifest both after generation AND after `--review` editing:
   ```python
   class ClipEntry(BaseModel):
       start_time: float  # seconds, 3 decimal places
       end_time: float
       scene_type: Literal["action", "dialogue", "establishing", "transition"]
       intensity: int = Field(ge=1, le=5)
   ```
2. **Use `Decimal` or fixed-point representation for timecodes** in internal processing. Only convert to float at JSON serialization, with explicit rounding to 3 decimal places (millisecond precision).
3. **Write manifest atomically.** Write to a temp file, then `os.replace()` to the final path. This prevents partial writes.
4. **Include a schema version field** in the manifest. Validate version on load and provide migration or clear error messages for old versions.
5. **After `--review`, re-validate the manifest** before proceeding to conform. Show clear, specific error messages: "Clip 7: end_time (125.400) is before start_time (130.200)".
6. **Include a checksum or generation metadata** in the manifest so the system can detect if it was manually modified.

**Detection:** Validation at every manifest read boundary (after generation, after review, before conform).

**Phase:** Phase 2 (manifest design). The schema must be solid before building the inference loop or conform step.

---

## Minor Pitfalls

---

### Pitfall 12: CLI UX -- Progress Reporting for Long Operations

**What goes wrong:** Processing a 2-hour film can take 30-60+ minutes (proxy creation + hundreds of inference calls + conform). The CLI shows no progress indication. Users think it's hung, kill the process, and restart -- wasting all completed work.

**Why it happens:** Developers test with short clips. They know the pipeline is working. Real users don't. A silent CLI processing for 45 minutes is indistinguishable from a hung process.

**Prevention:**
1. **Show progress bars** for each pipeline phase (proxy creation, keyframe extraction, inference, conform). Use `tqdm` or `rich.progress`.
2. **Print ETA estimates** based on completed/remaining work.
3. **Log to a file simultaneously.** If something goes wrong, the user has a log to report.
4. **Support `Ctrl+C` gracefully.** Catch SIGINT, clean up temp files, report what was completed.
5. **Consider checkpoint/resume.** Save inference results incrementally so a crashed run can resume from where it left off.

**Phase:** Phase 1 (CLI skeleton). Bolting on progress reporting later requires threading it through every function.

---

### Pitfall 13: FFmpeg Version Incompatibilities

**What goes wrong:** Different FFmpeg versions have different filter syntax, codec support, and default behaviors. A command that works on FFmpeg 5.x may fail on FFmpeg 4.x or behave differently on FFmpeg 6.x. The `lut3d` filter, `scene` detection, and concat filter syntax have all changed between major versions.

**Why it happens:** FFmpeg is often installed via system package managers (which may be outdated) or built from source (which may be bleeding edge). There is no universal "current version."

**Prevention:**
1. **Detect FFmpeg version at startup.** Parse `ffmpeg -version` output and warn if below a minimum (e.g., 4.4+).
2. **Test all FFmpeg commands against the minimum supported version.** Don't use features from unreleased or very recent FFmpeg.
3. **Document the minimum FFmpeg version** in the project README and validate it in the CLI entrypoint.

**Phase:** Phase 1 (environment validation).

---

### Pitfall 14: Memory Leaks in Long-Running Python Pipeline

**What goes wrong:** Processing a 2-hour film means the Python process runs for 30-60+ minutes. If frame data (images, decoded video buffers) is not properly released, memory usage grows linearly with film length. On a system already constrained by VRAM, running out of system RAM causes swap thrashing and extreme slowdown.

**Why it happens:** Python's garbage collector handles most cases, but large numpy arrays (if used for image processing), byte buffers from subprocess stdout, and accumulated log strings can leak. Particularly dangerous: storing all keyframe analysis results in a growing list when they should be written to disk incrementally.

**Prevention:**
1. **Process frames in a streaming fashion.** Don't load all frames or all analysis results into memory simultaneously.
2. **Write intermediate results to disk** (or append to the manifest) as they are produced.
3. **Explicitly `del` large buffers** after use, especially subprocess output.
4. **Monitor RSS during development** with `resource.getrusage()`. Flag if memory growth exceeds 100MB over baseline.

**Phase:** Phase 2 (inference pipeline design).

---

### Pitfall 15: Scene Detection Threshold Sensitivity

**What goes wrong:** FFmpeg's `select=gt(scene,T)` filter is used to find scene changes for keyframe extraction. The threshold `T` dramatically affects results: too low (0.1) produces thousands of frames including every camera wobble; too high (0.5) misses subtle cuts and entire scenes. The optimal threshold varies by film -- action movies have rapid cuts, dialogue scenes have slow dissolves.

**Why it happens:** Scene detection is based on inter-frame pixel difference. There's no universal threshold. Fast action, lens flares, and lighting changes trigger false positives. Slow dissolves and match cuts are false negatives.

**Prevention:**
1. **Use a moderate default threshold** (0.3) but make it configurable via CLI flag (`--scene-threshold`).
2. **Apply a two-pass approach:** First pass with a low threshold to find candidates, second pass to cluster and de-duplicate frames within a time window (e.g., keep at most 1 frame per 2-second window).
3. **Combine scene detection with I-frame extraction.** I-frames naturally occur at scene boundaries in well-encoded video.
4. **Report the number of extracted keyframes** to the user so they can adjust the threshold if needed.
5. **Set a maximum keyframe count** (e.g., 500) to prevent runaway extraction.

**Phase:** Phase 2 (keyframe extraction). Requires experimentation with real film content.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Environment Setup | CUDA 11.4 / Kepler compatibility (Pitfall 2) | Compile llama.cpp from source with sm_35. Validate before any other work. |
| Proxy Pipeline | Timecode drift (Pitfall 4) | Force CFR, use PTS-based timecodes, validate proxy-source alignment |
| Proxy Pipeline | FFmpeg escaping (Pitfall 5) | Never use shell=True. Build command as list. Test with pathological filenames. |
| Proxy Pipeline | FFmpeg version (Pitfall 13) | Detect version at startup, document minimum version |
| Keyframe Extraction | Disk space (Pitfall 6) | Streaming extraction, temp directories, cleanup handlers |
| Keyframe Extraction | Scene detection sensitivity (Pitfall 15) | Configurable threshold, two-pass approach, frame cap |
| Inference Pipeline | VRAM contention (Pitfall 1) | Sequential pipeline, CPU FFmpeg decode, GPU-only for inference |
| Inference Pipeline | Subprocess management (Pitfall 3) | Timeouts, output validation, zombie cleanup |
| Inference Pipeline | Prompt engineering (Pitfall 8) | Minimal prompts, fixed output schema, pre-filter dark frames |
| Inference Pipeline | Memory leaks (Pitfall 14) | Streaming processing, incremental disk writes |
| Manifest Design | Schema integrity (Pitfall 11) | Pydantic validation, atomic writes, schema versioning |
| Vibe / LUT Integration | Color space mismatch (Pitfall 10) | Rec.709-input LUTs, blend intensity, `--no-lut` escape hatch |
| Conform / Assembly | A/V sync drift (Pitfall 9) | Re-encode everything, concat filter (not demuxer), normalized sample rates |
| CLI UX | Silent long operations (Pitfall 12) | Progress bars from Phase 1, Ctrl+C handling, checkpoint/resume |

---

## Sources

- Training data knowledge of FFmpeg, CUDA, llama.cpp, LLaVA, Python subprocess management (MEDIUM confidence -- WebSearch was unavailable for verification)
- CUDA 11.4 Kepler deprecation is well-documented in NVIDIA release notes
- FFmpeg filter graph escaping rules from FFmpeg documentation
- LLaVA architecture details (image token count, context windows) from published papers
- pysubs2 library known to handle SRT/ASS edge cases from community usage
- A/V sync issues with concat demuxer vs filter are extensively documented in FFmpeg wiki and trac

**Confidence note:** All findings in this document are based on training data up to early 2025. WebSearch was unavailable to verify against the latest library versions or community discussions. Recommendations should be validated against current documentation, especially for llama.cpp CUDA 11.4 support status which may have changed.
