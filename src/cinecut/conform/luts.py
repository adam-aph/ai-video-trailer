import numpy as np
from pathlib import Path

from cinecut.manifest.vibes import VIBE_PROFILES

LUT_SIZE = 33


def generate_cube_lut(
    title: str,
    size: int,
    temp_shift: float,
    saturation: float,
    contrast: float,
    brightness: float,
    output_path: Path,
) -> Path:
    """Generate a .cube LUT file using NumPy vectorized operations.

    CRITICAL loop order: R is FASTEST (innermost), B is SLOWEST (outermost).
    Array indexing: [ri, gi, bi] where ri is innermost, bi is outermost.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    vals = np.linspace(0.0, 1.0, size)
    r, g, b = np.meshgrid(vals, vals, vals, indexing="ij")

    # Saturation: pivot around luma
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    r_out = luma + saturation * (r - luma)
    g_out = luma + saturation * (g - luma)
    b_out = luma + saturation * (b - luma)

    # Contrast: pivot at 0.5
    r_out = (r_out - 0.5) * contrast + 0.5
    g_out = (g_out - 0.5) * contrast + 0.5
    b_out = (b_out - 0.5) * contrast + 0.5

    # Temperature shift (add to R, subtract from B)
    r_out = r_out + temp_shift
    b_out = b_out - temp_shift

    # Brightness (uniform offset)
    r_out = r_out + brightness
    g_out = g_out + brightness
    b_out = b_out + brightness

    # Clamp to [0, 1]
    r_out = np.clip(r_out, 0.0, 1.0)
    g_out = np.clip(g_out, 0.0, 1.0)
    b_out = np.clip(b_out, 0.0, 1.0)

    with open(output_path, "w") as f:
        f.write(f'TITLE "{title}"\n')
        f.write(f"LUT_3D_SIZE {size}\n")
        f.write("DOMAIN_MIN 0.0 0.0 0.0\n")
        f.write("DOMAIN_MAX 1.0 1.0 1.0\n")
        # CRITICAL: R fastest (innermost loop), B slowest (outermost loop)
        for bi in range(size):
            for gi in range(size):
                for ri in range(size):
                    f.write(
                        f"{r_out[ri, gi, bi]:.6f} "
                        f"{g_out[ri, gi, bi]:.6f} "
                        f"{b_out[ri, gi, bi]:.6f}\n"
                    )

    return output_path


def ensure_luts(vibe_name: str, lut_dir: Path) -> Path:
    """Return the .cube LUT file for the given vibe, generating it if not cached.

    Args:
        vibe_name: Canonical lowercase vibe name (e.g. "action", "sci-fi").
        lut_dir: Directory to store generated LUT files.

    Returns:
        Path to the .cube file.

    Raises:
        ValueError: If vibe_name is not a known vibe (programming error, not runtime).
    """
    if vibe_name not in VIBE_PROFILES:
        raise ValueError(
            f"Unknown vibe '{vibe_name}'. Available: {sorted(VIBE_PROFILES)}"
        )
    profile = VIBE_PROFILES[vibe_name]
    output_path = lut_dir / profile.lut_filename
    if output_path.exists():
        return output_path
    lut_dir.mkdir(parents=True, exist_ok=True)
    return generate_cube_lut(
        title=profile.lut_filename.replace(".cube", ""),
        size=LUT_SIZE,
        temp_shift=profile.temp_shift,
        saturation=profile.saturation,
        contrast=profile.contrast,
        brightness=profile.brightness,
        output_path=output_path,
    )
