"""
tests/test_base_renderer.py
===========================
Tests unitaires et d'intégration pour ``BaseRenderer``.

Couverture
----------
- _safe_set          (unit)
- _read_glsl         (unit)
- _write_png_raw     (unit)
- _scene_at          (unit)
- _overlay_at        (unit)
- init_gl_base       (gpu)
- _make_prog         (gpu)
- _get_prog          (gpu — cache)
- _load_texture      (gpu)
- _get_cached_texture(gpu)
- _load_overlay_shader(gpu)
- _bind_audio_uniforms(gpu)
- release_base       (gpu)
- resolution property(unit)
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import pytest

# Ajoute le dossier racine au path
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from base_renderer import BaseRenderer, EMPTY_AUDIO_UNIFORMS


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_br(project_dir, minimal_project):
    """Crée un BaseRenderer non initialisé (sans contexte GL)."""
    return BaseRenderer(
        project_dir = project_dir,
        cfg         = minimal_project["config"],
        timeline    = minimal_project["timeline"],
        overlays    = minimal_project["overlays"],
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Tests unitaires purs (pas de GPU)
# ─────────────────────────────────────────────────────────────────────────────

class TestSafeSet:
    """_safe_set ne lève aucune exception en cas de prog None ou nom absent."""

    @pytest.mark.unit
    def test_none_prog_no_crash(self):
        BaseRenderer._safe_set(None, "iTime", 1.0)

    @pytest.mark.unit
    def test_missing_uniform_no_crash(self, base_renderer):
        # On utilise un prog réel mais on demande un uniform inexistant
        prog, _ = base_renderer._make_prog(
            "#version 330\nout vec4 c;\nvoid main(){c=vec4(0.0);}")
        assert prog is not None
        BaseRenderer._safe_set(prog, "iDoesNotExist", 42.0)  # ne doit pas lever

    @pytest.mark.unit
    def test_assigns_value(self, base_renderer):
        frag = "#version 330\nuniform float iTime;\nout vec4 c;\nvoid main(){c=vec4(iTime);}"
        prog, _ = base_renderer._make_prog(frag)
        assert prog is not None
        BaseRenderer._safe_set(prog, "iTime", 3.14)
        assert abs(prog["iTime"].value - 3.14) < 1e-5


class TestReadGlsl:
    @pytest.mark.unit
    def test_returns_none_for_missing(self, tmp_path):
        result = BaseRenderer._read_glsl(str(tmp_path / "nonexistent.frag"))
        assert result is None

    @pytest.mark.unit
    def test_reads_content(self, tmp_path):
        p = tmp_path / "shader.frag"
        p.write_text("void main(){}", encoding="utf-8")
        assert BaseRenderer._read_glsl(str(p)) == "void main(){}"

    @pytest.mark.unit
    def test_none_path(self):
        assert BaseRenderer._read_glsl(None) is None


class TestWritePngRaw:
    @pytest.mark.unit
    def test_creates_valid_png(self, tmp_path):
        path = str(tmp_path / "out.png")
        arr  = np.zeros((8, 8, 3), dtype=np.uint8)
        arr[0, 0] = [255, 0, 0]
        BaseRenderer._write_png_raw(path, arr)
        assert os.path.exists(path)
        # Signature PNG
        with open(path, "rb") as fh:
            assert fh.read(8) == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.unit
    def test_rgba_png(self, tmp_path):
        path = str(tmp_path / "rgba.png")
        arr  = np.full((4, 4, 4), 128, dtype=np.uint8)
        BaseRenderer._write_png_raw(path, arr)
        assert os.path.exists(path)

    @pytest.mark.unit
    def test_can_read_back_with_pil(self, tmp_path):
        pil = pytest.importorskip("PIL.Image")
        path = str(tmp_path / "check.png")
        arr  = np.full((16, 16, 3), [0, 128, 255], dtype=np.uint8)
        BaseRenderer._write_png_raw(path, arr)
        img = pil.open(path)
        assert img.size == (16, 16)


class TestTimelineLookup:
    @pytest.mark.unit
    def test_scene_at_start(self, project_dir, minimal_project):
        br = _make_br(project_dir, minimal_project)
        sc = br._scene_at(0.0)
        assert sc is not None
        assert sc["base_name"] == "scene_a"

    @pytest.mark.unit
    def test_scene_at_second_entry(self, project_dir, minimal_project):
        br = _make_br(project_dir, minimal_project)
        sc = br._scene_at(7.5)
        assert sc is not None
        assert sc["base_name"] == "scene_b"

    @pytest.mark.unit
    def test_scene_at_boundary(self, project_dir, minimal_project):
        br = _make_br(project_dir, minimal_project)
        # t=5.0 : exactement le début de scene_b (fin de scene_a exclue)
        sc = br._scene_at(5.0)
        assert sc["base_name"] == "scene_b"

    @pytest.mark.unit
    def test_scene_at_past_end(self, project_dir, minimal_project):
        br = _make_br(project_dir, minimal_project)
        assert br._scene_at(999.0) is None

    @pytest.mark.unit
    def test_overlay_at_no_overlays(self, project_dir, minimal_project):
        br = _make_br(project_dir, minimal_project)
        assert br._overlay_at(1.0) is None

    @pytest.mark.unit
    def test_overlay_at_found(self, project_dir, minimal_project):
        project = dict(minimal_project)
        project["overlays"] = [{"start": 2.0, "duration": 3.0, "effect": "scroll"}]
        br = BaseRenderer(
            project_dir = project_dir,
            cfg         = project["config"],
            timeline    = project["timeline"],
            overlays    = project["overlays"],
        )
        assert br._overlay_at(4.0)["effect"] == "scroll"
        assert br._overlay_at(5.1) is None


class TestResolutionProperty:
    @pytest.mark.unit
    def test_resolution(self, project_dir, minimal_project):
        br = _make_br(project_dir, minimal_project)
        assert br.resolution == (640, 360)


# ─────────────────────────────────────────────────────────────────────────────
#  Tests GPU
# ─────────────────────────────────────────────────────────────────────────────

class TestInitGlBase:
    @pytest.mark.gpu
    def test_quad_buffer_created(self, base_renderer):
        assert base_renderer._quad_buf is not None

    @pytest.mark.gpu
    def test_ctx_assigned(self, base_renderer, gl_context):
        assert base_renderer.ctx is gl_context


class TestMakeProg:
    @pytest.mark.gpu
    def test_valid_shader(self, base_renderer):
        frag = "#version 330\nout vec4 c;\nvoid main(){c=vec4(1.0);}"
        prog, vao = base_renderer._make_prog(frag)
        assert prog is not None
        assert vao is not None

    @pytest.mark.gpu
    def test_none_code_returns_none(self, base_renderer):
        prog, vao = base_renderer._make_prog(None)
        assert prog is None
        assert vao is None

    @pytest.mark.gpu
    def test_invalid_shader_returns_none(self, base_renderer):
        prog, vao = base_renderer._make_prog("THIS IS NOT GLSL {{{")
        assert prog is None

    @pytest.mark.gpu
    def test_cache_hit(self, base_renderer):
        frag = "#version 330\nout vec4 c;\nvoid main(){c=vec4(0.5);}"
        key  = "test_cache_key"
        p1, _ = base_renderer._get_prog(key, frag)
        p2, _ = base_renderer._get_prog(key, frag)
        assert p1 is p2  # même objet


class TestLoadTexture:
    @pytest.mark.gpu
    def test_loads_png(self, base_renderer, small_png):
        tex = base_renderer._load_texture(small_png)
        assert tex is not None
        assert tex.width == 16
        assert tex.height == 16

    @pytest.mark.gpu
    def test_missing_file_returns_none(self, base_renderer, tmp_path):
        tex = base_renderer._load_texture(str(tmp_path / "ghost.png"))
        assert tex is None

    @pytest.mark.gpu
    def test_cached_texture(self, base_renderer, small_png, project_dir):
        # Copier l'image dans le projet pour que le chemin relatif fonctionne
        import shutil
        dest = os.path.join(project_dir, "images", "small.png")
        shutil.copy(small_png, dest)
        t1 = base_renderer._get_cached_texture("images/small.png")
        t2 = base_renderer._get_cached_texture("images/small.png")
        assert t1 is t2


class TestOverlayShader:
    @pytest.mark.gpu
    def test_load_existing_overlay(self, base_renderer):
        base_renderer._load_overlay_shader("test_overlay")
        assert base_renderer._prog_overlay is not None
        assert base_renderer._vao_overlay is not None

    @pytest.mark.gpu
    def test_load_missing_overlay(self, base_renderer):
        base_renderer._load_overlay_shader("nonexistent_fx_xyz")
        assert base_renderer._prog_overlay is None

    @pytest.mark.gpu
    def test_no_reload_when_same(self, base_renderer):
        base_renderer._load_overlay_shader("test_overlay")
        prog1 = base_renderer._prog_overlay
        base_renderer._load_overlay_shader("test_overlay")
        prog2 = base_renderer._prog_overlay
        assert prog1 is prog2


class TestBindAudioUniforms:
    @pytest.mark.gpu
    def test_injects_known_uniforms(self, base_renderer):
        frag = (
            "#version 330\n"
            "uniform float iKick;\n"
            "uniform float iBPM;\n"
            "out vec4 c;\n"
            "void main(){c=vec4(iKick, iBPM/200.0, 0.0, 1.0);}\n"
        )
        prog, _ = base_renderer._make_prog(frag)
        assert prog is not None
        au = dict(EMPTY_AUDIO_UNIFORMS)
        au["iKick"] = 0.75
        au["iBPM"]  = 140.0
        base_renderer._bind_audio_uniforms(prog, au)
        assert abs(prog["iKick"].value - 0.75) < 1e-5
        assert abs(prog["iBPM"].value  - 140.0) < 1e-5

    @pytest.mark.gpu
    def test_none_prog_no_crash(self, base_renderer):
        base_renderer._bind_audio_uniforms(None, EMPTY_AUDIO_UNIFORMS)


class TestReleaseBase:
    @pytest.mark.gpu
    def test_release_clears_caches(self, gl_context_per_test, project_dir, minimal_project):
        from base_renderer import BaseRenderer
        br = BaseRenderer(
            project_dir = project_dir,
            cfg         = minimal_project["config"],
            timeline    = minimal_project["timeline"],
            overlays    = minimal_project["overlays"],
        )
        br.init_gl_base(gl_context_per_test)
        # Crée des ressources
        br._make_prog("#version 330\nout vec4 c;\nvoid main(){c=vec4(0.0);}")
        br.release_base()
        assert len(br._tex_cache) == 0
        assert len(br._prog_cache) == 0
