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

    @model_validator(mode="after")
    def end_after_start(self) -> "ClipEntry":
        if self.source_end_s <= self.source_start_s:
            raise ValueError(
                f"source_end_s ({self.source_end_s}) must be > source_start_s ({self.source_start_s})"
            )
        return self


class TrailerManifest(BaseModel):
    schema_version: str = "2.0"   # bumped; keep as str (not Literal) for backward compat
    source_file: str
    vibe: str
    clips: list[ClipEntry] = Field(min_length=1)
    structural_anchors: Optional[StructuralAnchors] = None  # Phase 7 — absent in v1.0 manifests

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
