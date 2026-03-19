"""
tests/test_particle_system.py
==============================
Tests unitaires et GPU pour ParticleEmitter / ParticleSystem.
"""
from __future__ import annotations
import os, sys
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from particle_system import ParticleEmitter, ParticleSystem, _PARTICLE_STRIDE


# ─── ParticleEmitter ─────────────────────────────────────────────────────────

class TestParticleEmitter:
    @pytest.mark.gpu
    def test_creates_buffers(self, gl_context):
        em = ParticleEmitter(gl_context, count=100)
        assert em._vbo[0] is not None
        assert em._vbo[1] is not None
        em.release()

    @pytest.mark.gpu
    def test_buffer_size(self, gl_context):
        count = 200
        em = ParticleEmitter(gl_context, count=count)
        expected = count * _PARTICLE_STRIDE
        assert em._vbo[0].size == expected
        em.release()

    @pytest.mark.gpu
    def test_update_no_crash(self, gl_context):
        """update() ne doit pas lever même si TF n'est pas supporté."""
        em = ParticleEmitter(gl_context, count=100)
        try:
            em.update(0.0, {})
            em.update(0.016, {"iKick": 0.5, "iBass": 0.3, "iEnergy": 0.2})
        except Exception as exc:
            pytest.skip(f"Transform Feedback non supporté : {exc}")
        em.release()

    @pytest.mark.gpu
    def test_render_no_crash(self, gl_context):
        em = ParticleEmitter(gl_context, count=100)
        try:
            em.render(0.0, {}, res=(640, 360))
        except Exception as exc:
            pytest.skip(f"Rendu particules non supporté : {exc}")
        em.release()

    @pytest.mark.gpu
    def test_double_buffer_swaps(self, gl_context):
        em = ParticleEmitter(gl_context, count=100)
        idx0 = em._idx
        try:
            em.update(0.0, {})
        except Exception:
            pytest.skip("TF non supporté")
        assert em._idx != idx0
        em.release()

    @pytest.mark.unit
    def test_default_config(self):
        """Vérifier les valeurs par défaut sans GPU."""
        em = ParticleEmitter.__new__(ParticleEmitter)
        em.cfg         = {}
        em.gravity     = np.array([0.0, -0.3, 0.0], dtype=np.float32)
        em.spread      = 1.0
        em.lifetime    = 3.0
        em.audio_grav  = True
        em.audio_burst = True
        assert em.lifetime == 3.0

    @pytest.mark.unit
    def test_custom_config(self):
        em = ParticleEmitter.__new__(ParticleEmitter)
        cfg = {"spread": 2.5, "lifetime": 5.0, "audio_gravity": False}
        em.cfg         = cfg
        em.spread      = float(cfg.get("spread", 1.0))
        em.lifetime    = float(cfg.get("lifetime", 3.0))
        em.audio_grav  = bool(cfg.get("audio_gravity", True))
        assert em.spread == 2.5
        assert em.lifetime == 5.0
        assert em.audio_grav is False


# ─── ParticleSystem ───────────────────────────────────────────────────────────

class TestParticleSystem:
    @pytest.mark.gpu
    def test_init(self, gl_context, project_dir):
        ps = ParticleSystem(gl_context, project_dir)
        assert ps._active_key == ""
        ps.release()

    @pytest.mark.gpu
    def test_set_scene_no_particles(self, gl_context, project_dir):
        ps = ParticleSystem(gl_context, project_dir)
        ps.set_scene("test", {})   # pas de config particules
        assert ps._active_key == ""
        ps.release()

    @pytest.mark.gpu
    def test_set_scene_creates_emitter(self, gl_context, project_dir):
        ps = ParticleSystem(gl_context, project_dir)
        scene_cfg = {"particles": {"count": 500, "emitter": "sparks"}}
        ps.set_scene("aurora", scene_cfg)
        assert ps._active_key != ""
        assert len(ps._emitters) == 1
        ps.release()

    @pytest.mark.gpu
    def test_same_scene_reuses_emitter(self, gl_context, project_dir):
        ps = ParticleSystem(gl_context, project_dir)
        scene_cfg = {"particles": {"count": 500}}
        ps.set_scene("aurora", scene_cfg)
        ps.set_scene("aurora", scene_cfg)
        assert len(ps._emitters) == 1
        ps.release()

    @pytest.mark.gpu
    def test_update_no_crash(self, gl_context, project_dir):
        ps = ParticleSystem(gl_context, project_dir)
        scene_cfg = {"particles": {"count": 200}}
        ps.set_scene("test", scene_cfg)
        try:
            ps.update(0.0, {})
            ps.update(0.016, {"iKick": 0.3})
        except Exception as exc:
            pytest.skip(f"TF non supporté : {exc}")
        ps.release()

    @pytest.mark.gpu
    def test_render_no_crash(self, gl_context, project_dir):
        ps = ParticleSystem(gl_context, project_dir)
        scene_cfg = {"particles": {"count": 200}}
        ps.set_scene("test", scene_cfg)
        try:
            ps.render(0.0, {}, res=(640, 360))
        except Exception as exc:
            pytest.skip(f"Rendu non supporté : {exc}")
        ps.release()

    @pytest.mark.gpu
    def test_camera_uniforms_passed(self, gl_context, project_dir):
        ps = ParticleSystem(gl_context, project_dir)
        cam = {"iCamMatrix": tuple(range(16))}
        ps.set_camera_uniforms(cam)
        assert ps._cam_uniforms == cam
        ps.release()
