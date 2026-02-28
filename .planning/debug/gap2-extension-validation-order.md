---
status: diagnosed
trigger: "Extension validation can't be confirmed — Typer exists=True fires before extension check"
created: 2026-02-26T00:00:00Z
updated: 2026-02-26T00:00:00Z
---

## Current Focus

hypothesis: Typer's exists=True validation runs at argument-parsing time (before main() body executes), so when the file does not exist the extension check at cli.py:76 is never reached
test: ran cinecut with a nonexistent .pdf path vs an existing .pdf path; observed which error message appeared in each case
expecting: confirmed
next_action: DIAGNOSED - no further action needed

## Symptoms

expected: `cinecut movie.pdf ...` shows "unsupported file type" error panel (our Rich panel from cli.py:77-83)
actual: when the .pdf file does not exist on disk, shows Typer's built-in "File does not exist" error instead of our extension panel
errors: "Invalid value for 'VIDEO': File '/tmp/nonexistent.pdf' does not exist."
reproduction: `cinecut /tmp/nonexistent.pdf --subtitle /tmp/dummy.srt --vibe action` (where nonexistent.pdf is not on disk)
started: always — structural ordering issue in how Typer validates Path arguments

## Eliminated

- hypothesis: extension check is missing entirely (was only planned, never implemented)
  evidence: extension check IS implemented at cli.py:76-83; confirmed by live test showing the Rich error panel when a .pdf file EXISTS on disk
  timestamp: 2026-02-26T00:00:00Z

## Evidence

- timestamp: 2026-02-26T00:00:00Z
  checked: src/cinecut/cli.py lines 42-83
  found: VIDEO argument declared with `exists=True` (line 47); extension check is at lines 76-83 inside main() function body
  implication: Typer/Click validates `exists=True` during argument parsing, before main() is called at all; the extension check at line 76 can only run if the file passes the existence check first

- timestamp: 2026-02-26T00:00:00Z
  checked: live execution — existing .pdf file
  found: `touch /tmp/test_dummy.pdf && cinecut /tmp/test_dummy.pdf ...` → Rich error panel: "Unsupported video format: .pdf / Supported formats: .avi, .mkv, .mp4"
  implication: extension check works correctly when the file exists; the check IS implemented and functional

- timestamp: 2026-02-26T00:00:00Z
  checked: live execution — nonexistent .pdf file (VIDEO positional arg)
  found: output is Typer's plain Click error box: "Invalid value for 'VIDEO': File '/tmp/nonexistent.pdf' does not exist." — NOT our Rich panel
  implication: Typer's exists=True fires at parse time and raises BadParameter before main() body is entered; our extension check at line 76 is unreachable in this code path

- timestamp: 2026-02-26T00:00:00Z
  checked: live execution — nonexistent .pdf file (--subtitle option, wrong VIDEO but valid path)
  found: when video path exists but subtitle does not, same Click error box appears: "File '/tmp/nonexistent.pdf' does not exist." for subtitle
  implication: same problem applies to both VIDEO and --subtitle arguments; both use exists=True

- timestamp: 2026-02-26T00:00:00Z
  checked: Typer source / help() output for typer.Argument
  found: exists=True delegates to Click's Path type validation which runs convert() at parse time; there is no hook to intercept or reorder it
  implication: the only way to run our extension check first is to remove exists=True and implement existence checking manually inside main()

## Resolution

root_cause: The VIDEO (and --subtitle) Typer arguments use `exists=True` (cli.py:47 and cli.py:59). Typer delegates this to Click's Path type, which validates file existence during argument parsing — before main() is ever called. The custom extension check lives at cli.py:76-83, inside the function body. When the user passes a file with a wrong extension that also does not exist on disk, Click's existence check fires first with a plain error box, and our extension check is never reached. When the file DOES exist (even with a wrong extension), main() is called and our Rich error panel is shown correctly.

fix direction: Remove `exists=True` from the VIDEO and subtitle Typer argument declarations (cli.py:47 and cli.py:59). Add manual existence checks inside main(), after the extension checks, using Path.exists(). This reorders validation to: (1) extension check with our Rich panel, (2) existence check with our Rich panel. Both checks then produce consistent Rich error panels.

  File: src/cinecut/cli.py
  Line 47: remove `exists=True,` from the VIDEO Argument
  Line 59: remove `exists=True,` from the subtitle Option
  After line 83 (after extension checks): add manual `if not video.exists(): ... raise typer.Exit(1)`
  After line 92 (after subtitle extension check): add manual `if not subtitle.exists(): ... raise typer.Exit(1)`

verification: not applied (diagnosis-only mode)
files_changed: []
