import tempfile
from pathlib import Path
import pytest
from cinecut.conform.luts import generate_cube_lut, ensure_luts, LUT_SIZE


class TestGenerateCubeLut:
    def test_identity_lut_format(self, tmp_path):
        p = generate_cube_lut("identity", 2, 0.0, 1.0, 1.0, 0.0, tmp_path / "id.cube")
        lines = p.read_text().splitlines()
        assert lines[0] == 'TITLE "identity"'
        assert lines[1] == "LUT_3D_SIZE 2"
        assert lines[2] == "DOMAIN_MIN 0.0 0.0 0.0"
        assert lines[3] == "DOMAIN_MAX 1.0 1.0 1.0"

    def test_identity_r_fastest(self, tmp_path):
        """R must be the fastest-changing index (innermost loop) per .cube spec"""
        p = generate_cube_lut("identity", 2, 0.0, 1.0, 1.0, 0.0, tmp_path / "id.cube")
        data = [l for l in p.read_text().splitlines()[4:] if l.strip()]
        assert len(data) == 8  # 2^3
        # B=0,G=0,R=0 -> black
        assert data[0] == "0.000000 0.000000 0.000000"
        # B=0,G=0,R=1 -> red (R fastest)
        assert data[1] == "1.000000 0.000000 0.000000", f"Expected red at index 1, got: {data[1]}"
        # B=0,G=1,R=0 -> green
        assert data[2] == "0.000000 1.000000 0.000000"
        # B=1,G=0,R=0 -> blue (B slowest)
        assert data[4] == "0.000000 0.000000 1.000000"

    def test_lut_size_33(self, tmp_path):
        p = generate_cube_lut("test", LUT_SIZE, 0.0, 1.0, 1.0, 0.0, tmp_path / "t.cube")
        data = [l for l in p.read_text().splitlines()[4:] if l.strip()]
        assert len(data) == LUT_SIZE ** 3

    def test_ensure_luts_idempotent(self, tmp_path):
        p1 = ensure_luts("action", tmp_path)
        p2 = ensure_luts("action", tmp_path)
        assert p1 == p2
        assert p1.exists()

    def test_ensure_luts_creates_dir(self, tmp_path):
        lut_dir = tmp_path / "deep" / "luts"
        assert not lut_dir.exists()
        p = ensure_luts("drama", lut_dir)
        assert p.exists()

    def test_ensure_luts_unknown_vibe(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown vibe"):
            ensure_luts("nonexistent", tmp_path)
