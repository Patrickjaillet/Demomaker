"""
tests/test_project_config.py
============================
Tests de validation de la structure ``project.json`` (Phase 8 — sans JSON Schema formel).

Couverture
----------
- Champs obligatoires présents
- Types corrects (config.RES = list[int, int], durée = float…)
- Timeline cohérente (pas de gap négatif, durée > 0)
- Champs facultatifs validés quand présents
- load_project() lève FileNotFoundError si absent
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers de validation
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_CONFIG_KEYS = {
    "RES", "MUSIC_FILE", "MUSIC_DURATION",
}

REQUIRED_SCENE_KEYS = {"base_name", "start", "duration"}


def _validate_project(data: dict) -> list[str]:
    """
    Retourne la liste des erreurs de validation trouvées dans ``data``.
    Liste vide → projet valide.
    """
    errors = []

    # ── config ──────────────────────────────────────────────────────────────
    if "config" not in data:
        errors.append("Champ 'config' manquant")
        return errors  # impossible de continuer

    cfg = data["config"]
    for key in REQUIRED_CONFIG_KEYS:
        if key not in cfg:
            errors.append(f"config.{key} manquant")

    res = cfg.get("RES")
    if not (isinstance(res, (list, tuple)) and len(res) == 2
            and all(isinstance(v, int) and v > 0 for v in res)):
        errors.append("config.RES doit être [width: int, height: int] avec width/height > 0")

    dur = cfg.get("MUSIC_DURATION")
    if dur is not None and not isinstance(dur, (int, float)):
        errors.append("config.MUSIC_DURATION doit être un nombre")

    smoothing = cfg.get("AUDIO_SMOOTHING")
    if smoothing is not None and not (0.0 <= smoothing <= 1.0):
        errors.append("config.AUDIO_SMOOTHING doit être dans [0, 1]")

    # ── timeline ─────────────────────────────────────────────────────────────
    if "timeline" not in data:
        errors.append("Champ 'timeline' manquant")
    else:
        for i, sc in enumerate(data["timeline"]):
            for key in REQUIRED_SCENE_KEYS:
                if key not in sc:
                    errors.append(f"timeline[{i}].{key} manquant")
            dur_sc = sc.get("duration", 0)
            if dur_sc <= 0:
                errors.append(f"timeline[{i}].duration doit être > 0 (valeur={dur_sc})")
            start_sc = sc.get("start", -1)
            if start_sc < 0:
                errors.append(f"timeline[{i}].start doit être >= 0")

    # ── overlays ─────────────────────────────────────────────────────────────
    if "overlays" not in data:
        errors.append("Champ 'overlays' manquant")

    return errors


# ─────────────────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectValidation:
    @pytest.mark.unit
    def test_minimal_project_valid(self, minimal_project):
        errors = _validate_project(minimal_project)
        assert errors == [], f"Erreurs inattendues : {errors}"

    @pytest.mark.unit
    def test_missing_config(self):
        errors = _validate_project({"timeline": [], "overlays": []})
        assert any("config" in e for e in errors)

    @pytest.mark.unit
    def test_missing_timeline(self, minimal_project):
        data = {k: v for k, v in minimal_project.items() if k != "timeline"}
        errors = _validate_project(data)
        assert any("timeline" in e for e in errors)

    @pytest.mark.unit
    def test_invalid_res_string(self, minimal_project):
        data = dict(minimal_project)
        data["config"] = dict(data["config"])
        data["config"]["RES"] = "1920x1080"  # type incorrect
        errors = _validate_project(data)
        assert any("RES" in e for e in errors)

    @pytest.mark.unit
    def test_invalid_res_zero(self, minimal_project):
        data = dict(minimal_project)
        data["config"] = dict(data["config"])
        data["config"]["RES"] = [0, 1080]
        errors = _validate_project(data)
        assert any("RES" in e for e in errors)

    @pytest.mark.unit
    def test_negative_duration(self, minimal_project):
        data  = dict(minimal_project)
        tl    = [dict(sc) for sc in data["timeline"]]
        tl[0] = dict(tl[0])
        tl[0]["duration"] = -1.0
        data["timeline"] = tl
        errors = _validate_project(data)
        assert any("duration" in e for e in errors)

    @pytest.mark.unit
    def test_negative_start(self, minimal_project):
        data = dict(minimal_project)
        tl   = [dict(sc) for sc in data["timeline"]]
        tl[0] = dict(tl[0])
        tl[0]["start"] = -0.5
        data["timeline"] = tl
        errors = _validate_project(data)
        assert any("start" in e for e in errors)

    @pytest.mark.unit
    def test_smoothing_out_of_range(self, minimal_project):
        data = dict(minimal_project)
        data["config"] = dict(data["config"])
        data["config"]["AUDIO_SMOOTHING"] = 1.5
        errors = _validate_project(data)
        assert any("AUDIO_SMOOTHING" in e for e in errors)


class TestLoadProject:
    @pytest.mark.unit
    def test_load_existing(self, project_dir):
        from system import load_project
        path = os.path.join(project_dir, "project.json")
        data = load_project(path)
        assert "config" in data
        assert "timeline" in data

    @pytest.mark.unit
    def test_load_missing_raises(self, tmp_path):
        from system import load_project
        with pytest.raises(FileNotFoundError):
            load_project(str(tmp_path / "nonexistent.json"))

    @pytest.mark.unit
    def test_load_malformed_json(self, tmp_path):
        from system import load_project
        bad = tmp_path / "bad.json"
        bad.write_text("{ invalid json }", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_project(str(bad))
