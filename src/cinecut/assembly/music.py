"""Jamendo API v3 music fetch with permanent per-vibe cache for Phase 9 music bed (MUSC-01, MUSC-02, MUSC-03)."""

import logging
import os

import requests
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_logger = logging.getLogger("cinecut")

JAMENDO_TRACKS_URL = "https://api.jamendo.com/v3.0/tracks/"

VIBE_TO_JAMENDO_TAG: dict[str, str] = {
    "action": "action",
    "adventure": "adventure",
    "animation": "pop",
    "comedy": "pop",
    "crime": "darkambient",
    "documentary": "documentary",
    "drama": "dramatic",
    "family": "pop",
    "fantasy": "epic",
    "history": "classical",
    "horror": "darkambient",
    "music": "pop",
    "mystery": "darkambient",
    "romance": "romantic",
    "sci-fi": "electronic",
    "thriller": "dramatic",
    "war": "epic",
    "western": "acoustic",
}


@dataclass
class MusicBed:
    """Music track selected by Phase 9. local_path points to ~/.cinecut/music/{vibe}.mp3."""

    track_id: str
    track_name: str
    artist_name: str
    license_ccurl: str
    local_path: str  # Absolute path to the cached MP3 file
    bpm: Optional[float] = None  # Filled by Plan 03 after generate_beat_grid() runs


def get_music_cache_dir() -> Path:
    """Return ~/.cinecut/music/, creating it if it does not exist."""
    cache_dir = Path.home() / ".cinecut" / "music"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def fetch_music_for_vibe(vibe: str) -> Optional[MusicBed]:
    """Fetch or return cached CC-licensed music track for the given vibe.

    MUSC-02: Returns cached MusicBed immediately if ~/.cinecut/music/{vibe}.mp3 exists (no API call).
    MUSC-01: On cache miss, calls Jamendo API v3 tracks endpoint and downloads the first track
             with audiodownload_allowed=True.
    MUSC-03: Any exception (network error, missing client_id, no results, download failure) is
             caught — logs a warning and returns None. Pipeline continues without music.

    Requires: JAMENDO_CLIENT_ID env var set to a valid Jamendo developer client_id.
    """
    try:
        cache_dir = get_music_cache_dir()
        cached_path = cache_dir / f"{vibe}.mp3"

        # MUSC-02: Cache hit — return immediately without API call
        if cached_path.exists():
            return MusicBed(
                track_id="cached",
                track_name=f"{vibe} (cached)",
                artist_name="unknown",
                license_ccurl="",
                local_path=str(cached_path),
            )

        # MUSC-01: Cache miss — check env var before calling API
        client_id = os.environ.get("JAMENDO_CLIENT_ID", "")
        if not client_id:
            raise ValueError("JAMENDO_CLIENT_ID env var not set — register at developer.jamendo.com")

        tag = VIBE_TO_JAMENDO_TAG.get(vibe, "pop")
        params = {
            "client_id": client_id,
            "format": "json",
            "limit": "10",
            "tags": tag,
            "order": "popularity_total",
            "audioformat": "mp32",
            "include": "musicinfo",
        }
        resp = requests.get(JAMENDO_TRACKS_URL, params=params, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        tracks = data.get("results", [])
        if not tracks:
            raise ValueError(f"Jamendo returned 0 tracks for tag '{tag}'")

        # PITFALL 3: filter for audiodownload_allowed=True (since April 2022, False returns 404)
        downloadable = [t for t in tracks if t.get("audiodownload_allowed", False)]
        if not downloadable:
            raise ValueError(f"No downloadable tracks in Jamendo results for tag '{tag}'")
        selected = downloadable[0]

        download_url = selected.get("audiodownload", "")
        if not download_url:
            raise ValueError("Selected track has no audiodownload URL")

        # PITFALL 7: atomic download — write to .tmp then rename to prevent partial-file corruption
        tmp_path = cache_dir / f"{vibe}.mp3.tmp"
        try:
            with requests.get(download_url, stream=True, timeout=60) as dl:
                dl.raise_for_status()
                with open(tmp_path, "wb") as f:
                    for chunk in dl.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            tmp_path.rename(cached_path)  # atomic on same filesystem
        except Exception:
            tmp_path.unlink(missing_ok=True)  # clean up partial file
            raise

        return MusicBed(
            track_id=str(selected.get("id", "unknown")),
            track_name=selected.get("name", "unknown"),
            artist_name=selected.get("artist_name", "unknown"),
            license_ccurl=selected.get("license_ccurl", ""),
            local_path=str(cached_path),
        )

    except Exception as exc:
        _logger.warning(
            "Music bed unavailable for vibe '%s': %s — trailer will be produced without music",
            vibe,
            exc,
        )
        return None
