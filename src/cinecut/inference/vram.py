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


def _check_vram_free_mib_raw() -> int:
    """Query free VRAM without raising VramError. Returns 0 on any failure."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        return int(result.stdout.strip().splitlines()[0])
    except Exception:
        return 0


def wait_for_vram(
    min_free_mib: int = VRAM_MINIMUM_MIB,
    poll_interval_s: float = 2.0,
    timeout_s: float = 60.0,
) -> None:
    """Poll nvidia-smi until at least min_free_mib MiB is free.

    Called between LlavaEngine exit and TextEngine entry to wait for VRAM
    release after llama-server process termination (OS reclaims pages async).
    Raises VramError if VRAM does not free within timeout_s.
    """
    import time
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        free_mib = _check_vram_free_mib_raw()
        if free_mib >= min_free_mib:
            return
        time.sleep(poll_interval_s)
    raise VramError(
        f"VRAM did not reach {min_free_mib} MiB free within {timeout_s}s after model swap"
    )
