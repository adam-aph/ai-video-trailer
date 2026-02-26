"""VRAM pre-flight check for LLaVA inference engine."""
import subprocess

from cinecut.errors import VramError

# Minimum free VRAM required for LLaVA 1.5-7B Q4 + 2048-token context.
VRAM_MINIMUM_MIB: int = 6144  # 6 GB


def check_vram_free_mib() -> int:
    """Query free VRAM via nvidia-smi and return the value in MiB.

    Also raises VramError if the free VRAM is below VRAM_MINIMUM_MIB.

    Raises:
        VramError: if nvidia-smi cannot be run, output cannot be parsed,
                   or free VRAM is below VRAM_MINIMUM_MIB.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        free_mib = int(result.stdout.strip().splitlines()[0])
    except subprocess.CalledProcessError as exc:
        raise VramError(f"nvidia-smi failed: {exc}") from exc
    except ValueError as exc:
        raise VramError(f"nvidia-smi output could not be parsed as integer: {exc}") from exc
    except IndexError as exc:
        raise VramError(f"nvidia-smi returned empty output") from exc

    if free_mib < VRAM_MINIMUM_MIB:
        raise VramError(
            f"Only {free_mib} MiB free VRAM, need at least {VRAM_MINIMUM_MIB} MiB"
        )

    return free_mib


def assert_vram_available() -> None:
    """Assert that sufficient VRAM is available for LLaVA inference.

    Calls check_vram_free_mib() which raises VramError if free VRAM is below
    VRAM_MINIMUM_MIB.
    """
    check_vram_free_mib()
