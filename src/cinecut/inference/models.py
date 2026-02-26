"""SceneDescription dataclass and Pydantic TypeAdapter for LLaVA inference output validation."""
from dataclasses import dataclass

from pydantic import TypeAdapter


@dataclass
class SceneDescription:
    """Structured description of a scene keyframe returned by LLaVA inference."""

    visual_content: str
    mood: str
    action: str
    setting: str


# JSON schema for llama-server json_schema field (constrained generation).
SCENE_DESCRIPTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "visual_content": {"type": "string"},
        "mood": {"type": "string"},
        "action": {"type": "string"},
        "setting": {"type": "string"},
    },
    "required": ["visual_content", "mood", "action", "setting"],
    "additionalProperties": False,
}

# Pydantic TypeAdapter for runtime validation of LLaVA response dicts.
_adapter: TypeAdapter[SceneDescription] = TypeAdapter(SceneDescription)


def validate_scene_description(data: dict) -> SceneDescription:
    """Validate a dict against the SceneDescription schema and return a dataclass instance.

    Raises pydantic.ValidationError if the data does not conform.
    """
    return _adapter.validate_python(data)
