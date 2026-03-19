"""
tests/test_camera_system.py
============================
Tests unitaires pour CameraSystem / CameraTrajectory / CameraKeyframe.
"""
from __future__ import annotations
import os, sys, json, math
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from camera_system import (
    CameraSystem, CameraTrajectory, CameraKeyframe,
    _normalize, _look_at, _perspective, _catmull_rom, _v3,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _simple_traj():
    return CameraTrajectory([
        CameraKeyframe(0.0,  _v3(0, 0, -5), _v3(0, 0, 0), fov=60),
        CameraKeyframe(5.0,  _v3(3, 2, -3), _v3(0, 1, 0), fov=70),
        CameraKeyframe(10.0, _v3(0, 0,  0), _v3(0, 0, 5), fov=65),
    ])


# ─── Tests mathématiques ──────────────────────────────────────────────────────

class TestMath:
    @pytest.mark.unit
    def test_normalize_unit_vector(self):
        v = _normalize(_v3(3, 0, 4))
        assert abs(np.linalg.norm(v) - 1.0) < 1e-6

    @pytest.mark.unit
    def test_normalize_zero_no_crash(self):
        v = _normalize(_v3(0, 0, 0))
        assert v is not None

    @pytest.mark.unit
    def test_look_at_shape(self):
        m = _look_at(_v3(0, 0, -5), _v3(0, 0, 0), _v3(0, 1, 0))
        assert m.shape == (4, 4)

    @pytest.mark.unit
    def test_look_at_orthonormal(self):
        m = _look_at(_v3(1, 2, -3), _v3(0, 0, 0), _v3(0, 1, 0))
        # Les 3 premières lignes doivent être orthonormales
        for i in range(3):
            assert abs(np.linalg.norm(m[i, :3]) - 1.0) < 1e-5

    @pytest.mark.unit
    def test_perspective_shape(self):
        m = _perspective(60, 16/9, 0.01, 1000)
        assert m.shape == (4, 4)

    @pytest.mark.unit
    def test_catmull_rom_endpoints(self):
        p0 = _v3(0, 0, 0); p1 = _v3(1, 0, 0)
        p2 = _v3(2, 0, 0); p3 = _v3(3, 0, 0)
        r0 = _catmull_rom(p0, p1, p2, p3, 0.0)
        r1 = _catmull_rom(p0, p1, p2, p3, 1.0)
        assert abs(r0[0] - 1.0) < 1e-5
        assert abs(r1[0] - 2.0) < 1e-5


# ─── CameraTrajectory ─────────────────────────────────────────────────────────

class TestCameraTrajectory:
    @pytest.mark.unit
    def test_duration(self):
        t = _simple_traj()
        assert abs(t.duration - 10.0) < 1e-6

    @pytest.mark.unit
    def test_evaluate_at_start(self):
        t = _simple_traj()
        kf = t.evaluate(0.0)
        assert abs(kf.pos[2] - (-5.0)) < 1e-4

    @pytest.mark.unit
    def test_evaluate_at_end(self):
        t = _simple_traj()
        kf = t.evaluate(10.0)
        assert abs(kf.pos[2] - 0.0) < 1e-4

    @pytest.mark.unit
    def test_evaluate_clamps_below(self):
        t = _simple_traj()
        kf = t.evaluate(-1.0)
        assert kf is not None

    @pytest.mark.unit
    def test_evaluate_clamps_above(self):
        t = _simple_traj()
        kf = t.evaluate(99.0)
        assert kf is not None

    @pytest.mark.unit
    def test_evaluate_mid_interpolated(self):
        t = _simple_traj()
        kf = t.evaluate(5.0)
        # À t=5, on doit être au keyframe 1
        assert abs(kf.pos[0] - 3.0) < 0.5

    @pytest.mark.unit
    def test_from_list(self):
        data = [
            {"time": 0.0, "pos": [0,0,-5], "target": [0,0,0], "fov": 60, "roll": 0},
            {"time": 3.0, "pos": [1,0,-3], "target": [0,0,1], "fov": 65, "roll": 5},
        ]
        traj = CameraTrajectory.from_list(data)
        assert len(traj.keyframes) == 2
        assert abs(traj.keyframes[0].fov - 60) < 1e-6

    @pytest.mark.unit
    def test_to_list_roundtrip(self):
        t = _simple_traj()
        d = t.to_list()
        t2 = CameraTrajectory.from_list(d)
        assert len(t2.keyframes) == len(t.keyframes)
        for kf1, kf2 in zip(t.keyframes, t2.keyframes):
            assert abs(kf1.time - kf2.time) < 1e-5

    @pytest.mark.unit
    def test_single_keyframe(self):
        t = CameraTrajectory([CameraKeyframe(0.0, _v3(0,0,-5), _v3(0,0,0))])
        kf = t.evaluate(5.0)
        assert kf is not None

    @pytest.mark.unit
    def test_blender_json_import(self, tmp_path):
        data = [
            {"frame": 1,  "pos": [0,0,-5], "target": [0,0,0], "fov": 60},
            {"frame": 25, "pos": [1,0,-3], "target": [0,0,1], "fov": 70},
        ]
        p = tmp_path / "cam.json"
        p.write_text(json.dumps(data))
        traj = CameraTrajectory.import_blender_json(str(p), fps=24.0)
        assert len(traj.keyframes) == 2
        assert abs(traj.keyframes[0].time - 1/24) < 1e-4

    @pytest.mark.unit
    def test_blender_rot_euler(self, tmp_path):
        """Import avec rot_euler doit calculer un target."""
        data = [{"frame": 1, "pos": [0,0,0], "rot_euler": [0,0,0], "fov": 60}]
        p = tmp_path / "cam_euler.json"
        p.write_text(json.dumps(data))
        traj = CameraTrajectory.import_blender_json(str(p), fps=24.0)
        kf = traj.keyframes[0]
        # Le target doit être différent de pos
        assert not np.allclose(kf.pos, kf.target)


# ─── CameraSystem ─────────────────────────────────────────────────────────────

class TestCameraSystem:
    @pytest.mark.unit
    def test_init(self):
        cs = CameraSystem(aspect_ratio=16/9)
        assert cs.aspect == pytest.approx(16/9, rel=1e-4)

    @pytest.mark.unit
    def test_load_from_project(self):
        cs = CameraSystem()
        project = {"cameras": {
            "main": [
                {"time": 0.0, "pos": [0,0,-5], "target": [0,0,0], "fov": 60, "roll": 0},
                {"time": 5.0, "pos": [2,0,-3], "target": [0,0,1], "fov": 70, "roll": 0},
            ]
        }}
        cs.load_from_project(project)
        assert "main" in cs.trajectory_names

    @pytest.mark.unit
    def test_update_returns_dict(self):
        cs = CameraSystem()
        result = cs.update(0.0)
        assert "iCamMatrix" in result
        assert "iCamPos"    in result
        assert "iCamDir"    in result
        assert "iCamFov"    in result
        assert "iCamProgress" in result

    @pytest.mark.unit
    def test_cam_matrix_is_tuple_of_16(self):
        cs = CameraSystem()
        result = cs.update(0.0)
        assert len(result["iCamMatrix"]) == 16

    @pytest.mark.unit
    def test_set_free_mode(self):
        cs = CameraSystem()
        cs.set_free(_v3(1, 2, 3), _v3(0, 0, 0), fov=45.0)
        result = cs.update(0.0)
        assert abs(result["iCamFov"] - 45.0) < 1e-4
        # En mode libre, progress = 0
        assert result["iCamProgress"] == 0.0

    @pytest.mark.unit
    def test_set_scene_with_trajectory(self):
        cs = CameraSystem()
        cs.add_trajectory("fly", _simple_traj())
        scene_cfg = {"base_name": "test", "start": 0.0, "duration": 10.0,
                     "camera": {"trajectory": "fly", "fov": 60}}
        cs.set_scene("test", scene_cfg, t_scene_start=0.0)
        result = cs.update(5.0)
        # La progression doit être ~0.5
        assert 0.3 < result["iCamProgress"] < 0.7

    @pytest.mark.unit
    def test_to_dict_roundtrip(self):
        cs = CameraSystem()
        cs.add_trajectory("test_traj", _simple_traj())
        d = cs.to_dict()
        assert "test_traj" in d
        assert len(d["test_traj"]) == 3

    @pytest.mark.unit
    def test_import_blender_bad_path(self):
        cs = CameraSystem()
        ok = cs.import_blender("cam", "/nonexistent/path.json")
        assert ok is False

    @pytest.mark.unit
    def test_position_property(self):
        cs = CameraSystem()
        cs.set_free(_v3(1, 2, 3), _v3(0, 0, 0))
        cs.update(0.0)
        pos = cs.position
        assert abs(pos[0] - 1.0) < 1e-5

    @pytest.mark.unit
    def test_direction_normalized(self):
        cs = CameraSystem()
        cs.set_free(_v3(0, 0, -5), _v3(0, 0, 0))
        cs.update(0.0)
        d = cs.direction
        assert abs(np.linalg.norm(d) - 1.0) < 1e-5
