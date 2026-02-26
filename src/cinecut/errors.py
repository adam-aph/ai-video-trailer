from pathlib import Path


class CineCutError(Exception):
    """Base class for all CineCut errors."""


class ProxyCreationError(CineCutError):
    def __init__(self, source: Path, detail: str) -> None:
        super().__init__(
            f"Failed to create analysis proxy from '{source.name}'.\n"
            f"  Cause: {detail}\n"
            f"  Check: Is FFmpeg installed and in PATH? Is '{source.name}' a valid MKV/AVI/MP4 file?\n"
            f"  Tip: Run `ffprobe '{source}' -v quiet -show_streams` to verify the file is readable."
        )
        self.source = source
        self.detail = detail


class KeyframeExtractionError(CineCutError):
    def __init__(self, timestamp_s: float, detail: str) -> None:
        super().__init__(
            f"Failed to extract keyframe at {timestamp_s:.2f}s.\n"
            f"  Cause: {detail}\n"
            f"  Check: Does the proxy file exist and is it a valid video?"
        )
        self.timestamp_s = timestamp_s
        self.detail = detail


class SubtitleParseError(CineCutError):
    def __init__(self, path: Path, detail: str) -> None:
        super().__init__(
            f"Cannot parse subtitle file '{path.name}'.\n"
            f"  Cause: {detail}\n"
            f"  Check: Is the file valid SRT or ASS format?\n"
            f"  Tip: Try re-saving the file as UTF-8 in a text editor."
        )
        self.path = path
        self.detail = detail


class ProxyValidationError(CineCutError):
    def __init__(self, proxy_path: Path, detail: str) -> None:
        super().__init__(
            f"Proxy file '{proxy_path.name}' failed post-creation validation.\n"
            f"  Cause: {detail}\n"
            f"  Check: Was there sufficient disk space during encoding? Is the source file complete?"
        )
        self.proxy_path = proxy_path
        self.detail = detail
