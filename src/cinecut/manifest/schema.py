from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Standalone frozenset — no import from vibes.py to avoid circular imports.
# vibes.py is also standalone and does NOT import from schema.py.
VALID_VIBES: frozenset[str] = frozenset({
    "action",
    "adventure",
    "animation",
    "comedy",
    "crime",
    "documentary",
    "drama",
    "family",
    "fantasy",
    "history",
    "horror",
    "music",
    "mystery",
    "romance",
    "sci-fi",
    "thriller",
    "war",
    "western",
})

# Alias map for common misspellings / format variations
_VIBE_ALIASES: dict[str, str] = {
    "scifi": "sci-fi",
    "sci_fi": "sci-fi",
}


class NarrativeZone(str, Enum):
    """Narrative zone assigned by sentence-transformers zone matching (STRC-02).

    str, Enum ensures Pydantic v2 serializes as plain string ("BEGINNING" not {"value":"BEGINNING"}).
    """
    BEGINNING = "BEGINNING"
    ESCALATION = "ESCALATION"
    CLIMAX = "CLIMAX"


class StructuralAnchors(BaseModel):
    """Narrative anchor timestamps extracted from subtitle corpus (Phase 7)."""
    begin_t: float = Field(ge=0.0, description="BEGIN narrative anchor timestamp (seconds)")
    escalation_t: float = Field(ge=0.0, description="ESCALATION narrative anchor timestamp (seconds)")
    climax_t: float = Field(ge=0.0, description="CLIMAX narrative anchor timestamp (seconds)")
    source: str = "llm"  # "llm" | "heuristic"


class ClipEntry(BaseModel):
    source_start_s: float = Field(ge=0.0)
    source_end_s: float = Field(ge=0.0)
    beat_type: Literal[
        "inciting_incident",
        "character_introduction",
        "escalation_beat",
        "relationship_beat",
        "money_shot",
        "climax_peak",
        "breath",
    ]
    act: Literal[
        "cold_open",
        "act1",
        "beat_drop",
        "act2",
        "breath",
        "act3",
        "title_card",
        "button",
    ]
    transition: Literal["hard_cut", "crossfade", "fade_to_black", "fade_to_white"] = "hard_cut"
    dialogue_excerpt: str = ""

    # Phase 4 additions (EDIT-01): analysis metadata
    reasoning: Optional[str] = None
    visual_analysis: Optional[str] = None
    subtitle_analysis: Optional[str] = None
    money_shot_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # Phase 8: zone-based ordering (STRC-02)
    narrative_zone: Optional[NarrativeZone] = None

    @model_validator(mode="after")
    def end_after_start(self) -> "ClipEntry":
        if self.source_end_s <= self.source_start_s:
            raise ValueError(
                f"source_end_s ({self.source_end_s}) must be > source_start_s ({self.source_start_s})"
            )
        return self


class BpmGrid(BaseModel):
    """BPM grid metadata stored in manifest (BPMG-01, BPMG-03)."""
    bpm: float = Field(gt=0.0, description="Resolved BPM after octave correction or vibe_default fallback")
    beat_count: int = Field(ge=0, description="Number of beat timestamps in the grid")
    source: str = Field(description="'librosa' if detected from audio; 'vibe_default' if fallback used")


class MusicBed(BaseModel):
    """Music track metadata stored in manifest (MUSC-01, MUSC-02)."""
    track_id: str
    track_name: str
    artist_name: str
    license_ccurl: str
    local_path: str     # Absolute path to ~/.cinecut/music/{vibe}.mp3
    bpm: Optional[float] = None   # Filled after BPM detection runs on the music file


class TrailerManifest(BaseModel):
    schema_version: str = "2.0"   # bumped; keep as str (not Literal) for backward compat
    source_file: str
    vibe: str
    clips: list[ClipEntry] = Field(min_length=1)
    structural_anchors: Optional[StructuralAnchors] = None  # Phase 7 — absent in v1.0 manifests
    bpm_grid: Optional[BpmGrid] = None      # None if BPM detection was skipped or unavailable
    music_bed: Optional[MusicBed] = None    # None if music unavailable (MUSC-03 graceful degradation)

    @field_validator("vibe", mode="before")
    @classmethod
    def normalize_vibe(cls, v: str) -> str:
        # Normalize: lowercase, replace spaces with hyphens
        normalized = v.lower().replace(" ", "-")
        # Apply alias mapping for known misspellings
        normalized = _VIBE_ALIASES.get(normalized, normalized)
        if normalized not in VALID_VIBES:
            raise ValueError(
                f"Unknown vibe '{v}'. Valid vibes: {sorted(VALID_VIBES)}"
            )
        return normalized
