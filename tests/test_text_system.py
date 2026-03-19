"""
tests/test_text_system.py
==========================
Tests unitaires pour TextAtlas, KaraokeTrack, TextSystem.
"""
from __future__ import annotations
import os, sys, math
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from text_system import (
    TextAtlas, KaraokeTrack, TextRenderer, TextSystem,
)


# ─── KaraokeTrack ────────────────────────────────────────────────────────────

class TestKaraokeTrack:
    @pytest.mark.unit
    def test_word_count_matches(self):
        k = KaraokeTrack(["HELLO", "WORLD"], [1.0, 2.0])
        colors = k.get_word_colors(0.5)
        assert len(colors) == 2

    @pytest.mark.unit
    def test_active_word_brighter(self):
        k = KaraokeTrack(
            ["A", "B"],
            [1.0, 2.0],
            color_off=(0.5, 0.5, 0.5, 1.0),
            color_on=(1.0, 1.0, 1.0, 1.0),
            duration_ms=500,
        )
        colors = k.get_word_colors(1.1)   # "A" est actif
        # Le premier mot doit avoir une luminosité > celui de la couleur off
        assert colors[0][0] > 0.5

    @pytest.mark.unit
    def test_inactive_word_dim(self):
        k = KaraokeTrack(["A", "B"], [1.0, 2.0], duration_ms=200)
        colors = k.get_word_colors(0.0)   # avant tout onset
        assert colors[0] == k.color_off

    @pytest.mark.unit
    def test_from_dict(self):
        d = {
            "words": ["HI", "THERE"],
            "timecodes": [0.0, 1.0],
            "color_off": "#888888",
            "color_on":  "#ffffff",
            "duration_ms": 300,
        }
        k = KaraokeTrack.from_dict(d)
        assert k.words == ["HI", "THERE"]
        assert abs(k.duration - 0.3) < 1e-6

    @pytest.mark.unit
    def test_mismatch_raises(self):
        with pytest.raises(AssertionError):
            KaraokeTrack(["A", "B", "C"], [1.0, 2.0])

    @pytest.mark.unit
    def test_colors_are_tuples(self):
        k = KaraokeTrack(["X"], [0.0])
        colors = k.get_word_colors(0.5)
        assert isinstance(colors[0], tuple)
        assert len(colors[0]) == 4

    @pytest.mark.unit
    def test_after_duration_back_to_off(self):
        k = KaraokeTrack(["A"], [1.0], duration_ms=200)
        colors = k.get_word_colors(5.0)   # bien après la durée
        assert colors[0] == k.color_off


# ─── TextAtlas ───────────────────────────────────────────────────────────────

class TestTextAtlas:
    @pytest.mark.unit
    def test_build_without_pil_graceful(self):
        """Sans Pillow, build() doit retourner False sans lever."""
        import text_system as ts
        orig = ts._HAS_PIL
        ts._HAS_PIL = False
        atlas = TextAtlas(size=32)
        result = atlas.build()
        ts._HAS_PIL = orig
        assert result is False

    @pytest.mark.unit
    def test_build_with_pil(self):
        pil = pytest.importorskip("PIL.Image")
        atlas = TextAtlas(size=32, sdf=False, atlas_size=512)
        ok = atlas.build()
        assert ok is True
        assert len(atlas.glyphs) > 0

    @pytest.mark.unit
    def test_image_shape(self):
        pytest.importorskip("PIL.Image")
        atlas = TextAtlas(size=32, sdf=False, atlas_size=256)
        atlas.build()
        assert atlas.image is not None
        assert atlas.image.shape == (256, 256)

    @pytest.mark.unit
    def test_glyphs_have_uv(self):
        pytest.importorskip("PIL.Image")
        atlas = TextAtlas(size=32, sdf=False, atlas_size=512)
        atlas.build()
        for ch, g in atlas.glyphs.items():
            assert "u0" in g and "v0" in g
            assert 0.0 <= g["u0"] <= g["u1"] <= 1.0

    @pytest.mark.unit
    def test_measure(self):
        pytest.importorskip("PIL.Image")
        atlas = TextAtlas(size=32, sdf=False, atlas_size=512)
        atlas.build()
        w, h = atlas.measure("HELLO")
        assert w > 0 and h > 0

    @pytest.mark.unit
    def test_sdf_image_range(self):
        pytest.importorskip("PIL.Image")
        atlas = TextAtlas(size=32, sdf=True, atlas_size=256)
        atlas.build()
        assert atlas.image is not None
        assert atlas.image.min() >= 0.0
        assert atlas.image.max() <= 1.0


# ─── TextSystem ──────────────────────────────────────────────────────────────

class TestTextSystem:
    @pytest.mark.unit
    def test_no_text_config_inactive(self, project_dir, minimal_project):
        """Sans champ 'text' dans la scène, TextSystem doit rester silencieux."""
        ts = TextSystem.__new__(TextSystem)
        ts._active = False
        ts._renderers = {}
        ts._scene_cfg = {}
        # render() avec _active=False ne doit pas lever
        ts.render(0.0, {})

    @pytest.mark.gpu
    def test_set_scene_creates_renderer(self, gl_context, project_dir):
        pytest.importorskip("PIL.Image")
        ts = TextSystem(gl_context, project_dir, res=(640, 360))
        scene_cfg = {
            "text": {
                "mode": "plain",
                "size": 32,
                "lines": [{"text": "TEST", "y": 0.5}],
            }
        }
        ts.set_scene("test_scene", scene_cfg)
        assert ts._active is True
        assert len(ts._renderers) > 0
        ts.release()

    @pytest.mark.gpu
    def test_render_no_crash(self, gl_context, project_dir):
        pytest.importorskip("PIL.Image")
        ts = TextSystem(gl_context, project_dir, res=(640, 360))
        scene_cfg = {"text": {"mode": "plain", "size": 32,
                               "lines": [{"text": "HI", "y": 0.5}]}}
        ts.set_scene("scene", scene_cfg)
        ts.render(1.0, {"iKick": 0.5})
        ts.release()
