from pathlib import Path

from pydantic import ValidationError

from cinecut.errors import ManifestError
from cinecut.manifest.schema import TrailerManifest


def load_manifest(path: Path) -> TrailerManifest:
    """Load and validate TRAILER_MANIFEST.json. Raises ManifestError on failure."""
    try:
        return TrailerManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except ValidationError as e:
        field_errors = "; ".join(
            f"{' -> '.join(str(x) for x in err['loc'])}: {err['msg']}"
            for err in e.errors()
        )
        raise ManifestError(path, f"Schema validation failed: {field_errors}") from e
    except (OSError, UnicodeDecodeError) as e:
        raise ManifestError(path, str(e)) from e
