import json
import tempfile
from pathlib import Path
import pytest
from cinecut.manifest.schema import TrailerManifest, ClipEntry, VALID_VIBES
from cinecut.manifest.loader import load_manifest
from cinecut.manifest.vibes import VIBE_PROFILES, VibeProfile
from cinecut.errors import ManifestError

FIXTURE = Path(__file__).parent / "fixtures" / "sample_manifest.json"


class TestValidManifest:
    def test_load_fixture(self):
        data = json.loads(FIXTURE.read_text())
        data["source_file"] = "/fake/path.mkv"
        m = TrailerManifest.model_validate(data)
        assert m.vibe == "action"
        assert len(m.clips) == 3

    def test_vibe_normalization(self):
        m = TrailerManifest.model_validate({
            "source_file": "/f.mkv", "vibe": "Action",
            "clips": [{"source_start_s": 0.0, "source_end_s": 5.0, "beat_type": "breath", "act": "act1"}]
        })
        assert m.vibe == "action"

    def test_scifi_alias(self):
        """'scifi' without hyphen should normalize to 'sci-fi'"""
        m = TrailerManifest.model_validate({
            "source_file": "/f.mkv", "vibe": "scifi",
            "clips": [{"source_start_s": 0.0, "source_end_s": 5.0, "beat_type": "breath", "act": "act1"}]
        })
        assert m.vibe == "sci-fi"

    def test_valid_vibes_count(self):
        assert len(VALID_VIBES) == 18

    def test_load_from_file(self, tmp_path):
        data = json.loads(FIXTURE.read_text())
        data["source_file"] = "/fake/path.mkv"
        p = tmp_path / "manifest.json"
        p.write_text(json.dumps(data))
        m = load_manifest(p)
        assert isinstance(m, TrailerManifest)


class TestInvalidManifest:
    def test_missing_source_file(self):
        with pytest.raises(Exception):  # pydantic ValidationError or ManifestError
            TrailerManifest.model_validate({"vibe": "action", "clips": []})

    def test_end_before_start(self):
        with pytest.raises(Exception):
            TrailerManifest.model_validate({
                "source_file": "/f.mkv", "vibe": "action",
                "clips": [{"source_start_s": 5.0, "source_end_s": 3.0, "beat_type": "breath", "act": "act1"}]
            })

    def test_invalid_vibe(self):
        with pytest.raises(Exception):
            TrailerManifest.model_validate({
                "source_file": "/f.mkv", "vibe": "nonexistent_vibe",
                "clips": [{"source_start_s": 0.0, "source_end_s": 5.0, "beat_type": "breath", "act": "act1"}]
            })

    def test_invalid_json_raises_manifest_error(self, tmp_path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("not json at all {{{")
        with pytest.raises(ManifestError):
            load_manifest(bad_json)

    def test_empty_clips_rejected(self):
        with pytest.raises(Exception):
            TrailerManifest.model_validate({"source_file": "/f.mkv", "vibe": "action", "clips": []})


class TestVibeProfiles:
    def test_all_18_profiles_present(self):
        assert len(VIBE_PROFILES) == 18

    def test_keys_match_valid_vibes(self):
        assert set(VIBE_PROFILES.keys()) == VALID_VIBES

    def test_all_profiles_are_vibe_profile_instances(self):
        for name, p in VIBE_PROFILES.items():
            assert isinstance(p, VibeProfile), f"{name} is not VibeProfile"

    def test_profile_name_matches_key(self):
        for name, p in VIBE_PROFILES.items():
            assert p.name == name

    @pytest.mark.parametrize("vibe,expected_lufs", [
        ("action", -14.0), ("horror", -20.0), ("documentary", -20.0),
        ("drama", -18.0), ("thriller", -16.0),
    ])
    def test_lufs_targets(self, vibe, expected_lufs):
        assert VIBE_PROFILES[vibe].lufs_target == expected_lufs

    def test_action_color_params(self):
        a = VIBE_PROFILES["action"]
        assert a.temp_shift == -0.05
        assert a.saturation == 1.15
        assert a.contrast == 1.20
        assert a.act3_avg_cut_s == 1.2

    def test_lut_filenames_are_cube_files(self):
        for name, p in VIBE_PROFILES.items():
            assert p.lut_filename.endswith(".cube"), f"{name} lut_filename missing .cube"
