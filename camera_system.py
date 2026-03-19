"""
camera_system.py  —  Phase 9.1 : Système de Caméra 3D
======================================================

Expose aux shaders GLSL :
  iCamMatrix   mat4   Matrice view-projection inverse (world-ray casting)
  iCamPos      vec3   Position monde de la caméra
  iCamDir      vec3   Direction de regard normalisée
  iCamUp       vec3   Vecteur up de la caméra
  iCamFov      float  Champ de vision vertical en degrés
  iCamNear     float  Plan near (défaut 0.01)
  iCamFar      float  Plan far  (défaut 1000.0)
  iCamProgress float  Progression [0,1] sur la trajectoire courante

Trajectoires
------------
Une trajectoire est une liste de CameraKeyframe :
    time   float    temps absolu en secondes
    pos    vec3     position
    target vec3     point visé
    fov    float    champ de vision (°)
    roll   float    rotation autour de l'axe de visée (°)

Interpolation : catmull-rom sur pos/target, lerp sur fov/roll.

Configuration project.json
---------------------------
Chaque scène de la timeline peut porter un champ optionnel ``camera`` :

    {
      "base_name": "wormhole",
      "start": 50.0,
      "duration": 10.0,
      "camera": {
        "trajectory": "wormhole_cam",
        "fov": 75.0,
        "near": 0.01,
        "far": 500.0
      }
    }

Les trajectoires sont définies dans ``project.json → cameras`` :

    "cameras": {
      "wormhole_cam": [
        {"time": 0.0, "pos": [0,0,-5], "target": [0,0,0], "fov": 75, "roll": 0},
        {"time": 5.0, "pos": [0,2,-3], "target": [0,0,1], "fov": 80, "roll": 10},
        {"time": 10.0,"pos": [0,0, 0], "target": [0,0,5], "fov": 70, "roll": 0}
      ]
    }

Import Blender
--------------
La méthode ``CameraSystem.import_blender_json(path)`` accepte un fichier JSON
exporté par le script Blender fourni (``blender_export_camera.py``).
Format : liste de frames ``{"frame": N, "pos": [x,y,z], "rot_euler": [rx,ry,rz], "fov": f}``

Usage
-----
    cam = CameraSystem()
    cam.load_from_project(project_data)           # charge les trajectoires
    cam.set_scene("wormhole", scene_cfg, t_scene_start)
    uniforms = cam.update(t)                      # appel chaque frame
    cam.bind(prog)                                # injecte dans un shader
"""

from __future__ import annotations

import math
import json
import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
#  Types de données
# ─────────────────────────────────────────────────────────────────────────────

Vec3 = np.ndarray   # shape (3,), float32


def _v3(x: float, y: float, z: float) -> Vec3:
    return np.array([x, y, z], dtype=np.float32)


@dataclass
class CameraKeyframe:
    """Un keyframe de trajectoire caméra."""
    time:   float
    pos:    Vec3
    target: Vec3
    fov:    float = 60.0
    roll:   float = 0.0     # degrés

    def __post_init__(self):
        self.pos    = np.asarray(self.pos,    dtype=np.float32)
        self.target = np.asarray(self.target, dtype=np.float32)


# ─────────────────────────────────────────────────────────────────────────────
#  Mathématiques de caméra
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(v: Vec3) -> Vec3:
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def _look_at(pos: Vec3, target: Vec3, up: Vec3) -> np.ndarray:
    """Construit une matrice View (4×4 float32) depuis pos/target/up."""
    f = _normalize(target - pos)           # forward
    r = _normalize(np.cross(f, up))        # right
    u = np.cross(r, f)                     # up corrigé

    m = np.eye(4, dtype=np.float32)
    m[0, :3] = r
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3]  = -np.dot(r, pos)
    m[1, 3]  = -np.dot(u, pos)
    m[2, 3]  =  np.dot(f, pos)
    return m


def _perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    """Matrice Projection perspective (4×4 float32, convention OpenGL)."""
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def _roll_matrix(roll_deg: float, forward: Vec3) -> np.ndarray:
    """Rotation autour de l'axe forward de ``roll_deg`` degrés (4×4)."""
    rad = math.radians(roll_deg)
    c, s = math.cos(rad), math.sin(rad)
    f = _normalize(forward)
    x, y, z = float(f[0]), float(f[1]), float(f[2])
    # Rodrigues
    m = np.array([
        [c + x*x*(1-c),   x*y*(1-c) - z*s, x*z*(1-c) + y*s, 0],
        [y*x*(1-c) + z*s, c + y*y*(1-c),   y*z*(1-c) - x*s, 0],
        [z*x*(1-c) - y*s, z*y*(1-c) + x*s, c + z*z*(1-c),   0],
        [0, 0, 0, 1],
    ], dtype=np.float32)
    return m


def _catmull_rom(p0: Vec3, p1: Vec3, p2: Vec3, p3: Vec3, t: float) -> Vec3:
    """Interpolation Catmull-Rom entre p1 et p2 (t ∈ [0,1])."""
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        2 * p1
        + (-p0 + p2) * t
        + (2*p0 - 5*p1 + 4*p2 - p3) * t2
        + (-p0 + 3*p1 - 3*p2 + p3) * t3
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Trajectoire
# ─────────────────────────────────────────────────────────────────────────────

class CameraTrajectory:
    """
    Liste de ``CameraKeyframe`` avec interpolation Catmull-Rom.

    La durée totale correspond au temps du dernier keyframe moins le premier.
    """

    def __init__(self, keyframes: list[CameraKeyframe]):
        self.keyframes = sorted(keyframes, key=lambda k: k.time)

    @property
    def duration(self) -> float:
        if len(self.keyframes) < 2:
            return 0.0
        return self.keyframes[-1].time - self.keyframes[0].time

    def evaluate(self, t: float) -> CameraKeyframe:
        """
        Retourne un ``CameraKeyframe`` interpolé au temps absolu ``t``.
        Clampé aux extrêmes si hors plage.
        """
        kfs = self.keyframes
        if not kfs:
            return CameraKeyframe(t, _v3(0, 0, -5), _v3(0, 0, 0))
        if len(kfs) == 1 or t <= kfs[0].time:
            return kfs[0]
        if t >= kfs[-1].time:
            return kfs[-1]

        # Trouver le segment [i, i+1]
        i = 0
        for j in range(len(kfs) - 1):
            if kfs[j].time <= t < kfs[j + 1].time:
                i = j
                break

        t0 = kfs[i].time
        t1 = kfs[i + 1].time
        alpha = (t - t0) / max(t1 - t0, 1e-9)

        # Indices voisins pour Catmull-Rom
        i0 = max(0, i - 1)
        i1 = i
        i2 = i + 1
        i3 = min(len(kfs) - 1, i + 2)

        pos    = _catmull_rom(kfs[i0].pos,    kfs[i1].pos,    kfs[i2].pos,    kfs[i3].pos,    alpha)
        target = _catmull_rom(kfs[i0].target, kfs[i1].target, kfs[i2].target, kfs[i3].target, alpha)
        fov    = kfs[i1].fov  + (kfs[i2].fov  - kfs[i1].fov)  * alpha
        roll   = kfs[i1].roll + (kfs[i2].roll - kfs[i1].roll) * alpha

        return CameraKeyframe(t, pos, target, fov, roll)

    @classmethod
    def from_list(cls, data: list[dict]) -> "CameraTrajectory":
        """Construit depuis une liste de dicts (format project.json)."""
        kfs = []
        for d in data:
            kfs.append(CameraKeyframe(
                time   = float(d.get("time", 0.0)),
                pos    = d.get("pos",    [0.0, 0.0, -5.0]),
                target = d.get("target", [0.0, 0.0,  0.0]),
                fov    = float(d.get("fov",  60.0)),
                roll   = float(d.get("roll",  0.0)),
            ))
        return cls(kfs)

    @classmethod
    def import_blender_json(cls, path: str, fps: float = 24.0) -> "CameraTrajectory":
        """
        Importe une trajectoire depuis un JSON exporté par Blender.

        Format attendu (généré par ``blender_export_camera.py``) :
            [
              {"frame": 1,  "pos": [x,y,z], "target": [tx,ty,tz], "fov": 60.0},
              {"frame": 25, "pos": [...], ...},
              ...
            ]
        Les frames sont converties en secondes via ``fps``.
        """
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        kfs = []
        for entry in data:
            frame = float(entry.get("frame", entry.get("time", 0)))
            # Accepte aussi "time" directement en secondes
            t = frame / fps if "frame" in entry else frame
            pos = entry.get("pos", entry.get("location", [0, 0, -5]))
            # Si rot_euler fourni, calcule target depuis pos + forward Euler ZYX
            if "rot_euler" in entry and "target" not in entry:
                rx, ry, rz = entry["rot_euler"]
                cx, cy, cz = math.cos(rx), math.cos(ry), math.cos(rz)
                sx, sy, sz = math.sin(rx), math.sin(ry), math.sin(rz)
                # Forward Blender → OpenGL (Y forward → -Z forward)
                fwd = np.array([
                    cy * sz,
                    sx * sy * sz + cx * cz,
                    -cx * sy * sz + sx * cz,
                ], dtype=np.float32)
                target = np.array(pos, dtype=np.float32) + fwd
            else:
                target = entry.get("target", [0, 0, 0])
            kfs.append(CameraKeyframe(
                time   = t,
                pos    = pos,
                target = target,
                fov    = float(entry.get("fov", 60.0)),
                roll   = float(entry.get("roll", 0.0)),
            ))
        return cls(kfs)

    def to_list(self) -> list[dict]:
        """Sérialise pour project.json."""
        return [
            {
                "time":   kf.time,
                "pos":    kf.pos.tolist(),
                "target": kf.target.tolist(),
                "fov":    kf.fov,
                "roll":   kf.roll,
            }
            for kf in self.keyframes
        ]


# ─────────────────────────────────────────────────────────────────────────────
#  CameraSystem — gestionnaire principal
# ─────────────────────────────────────────────────────────────────────────────

class CameraSystem:
    """
    Gestionnaire de caméra 3D pour le moteur MEGADEMO.

    Responsabilités
    ---------------
    - Stocker les trajectoires nommées (depuis project.json ou import Blender)
    - Sélectionner la trajectoire active pour une scène
    - Calculer chaque frame la matrice ``iCamMatrix`` (View-Projection inverse)
      et les uniforms caméra dérivés
    - Injecter tous les uniforms dans un programme GLSL

    Uniforms injectés
    -----------------
    iCamMatrix   mat4    VP⁻¹ pour ray-casting (fragment shader)
    iCamPos      vec3    Position monde
    iCamDir      vec3    Direction regard normalisée
    iCamUp       vec3    Vecteur up
    iCamFov      float   FOV vertical (degrés)
    iCamNear     float   Plan near
    iCamFar      float   Plan far
    iCamProgress float   [0,1] sur la trajectoire courante
    """

    DEFAULT_FOV  = 60.0
    DEFAULT_NEAR = 0.01
    DEFAULT_FAR  = 1000.0
    DEFAULT_UP   = _v3(0.0, 1.0, 0.0)

    def __init__(self, aspect_ratio: float = 16.0 / 9.0):
        self.aspect = aspect_ratio
        self._trajectories: dict[str, CameraTrajectory] = {}
        self._active_traj:  Optional[CameraTrajectory]  = None
        self._scene_start:  float = 0.0
        self._scene_dur:    float = 0.0
        self._scene_cfg:    dict  = {}

        # État courant (mis à jour par update())
        self._pos     = _v3(0.0, 0.0, -5.0)
        self._target  = _v3(0.0, 0.0,  0.0)
        self._up      = _v3(0.0, 1.0,  0.0)
        self._fov     = self.DEFAULT_FOV
        self._near    = self.DEFAULT_NEAR
        self._far     = self.DEFAULT_FAR
        self._roll    = 0.0
        self._progress = 0.0
        self._cam_matrix = np.eye(4, dtype=np.float32)

        # Caméra libre (override manuel)
        self._free_mode  = False
        self._free_pos   = _v3(0.0, 0.0, -5.0)
        self._free_target= _v3(0.0, 0.0,  0.0)
        self._free_fov   = self.DEFAULT_FOV

    # ── Chargement ────────────────────────────────────────────────────────────

    def load_from_project(self, project_data: dict) -> None:
        """
        Charge toutes les trajectoires depuis ``project_data["cameras"]``.
        Format: ``{"cameras": {"traj_name": [{time, pos, target, fov, roll}, ...]}}``
        """
        cameras = project_data.get("cameras", {})
        for name, kf_list in cameras.items():
            self._trajectories[name] = CameraTrajectory.from_list(kf_list)
        if cameras:
            print(f"CAMERA: {len(cameras)} trajectoire(s) chargée(s)")

    def add_trajectory(self, name: str, traj: CameraTrajectory) -> None:
        """Enregistre une trajectoire nommée."""
        self._trajectories[name] = traj

    def import_blender(self, name: str, path: str, fps: float = 24.0) -> bool:
        """Importe et enregistre une trajectoire depuis un JSON Blender."""
        try:
            traj = CameraTrajectory.import_blender_json(path, fps)
            self._trajectories[name] = traj
            print(f"CAMERA: Importé '{name}' depuis {path} ({len(traj.keyframes)} kf)")
            return True
        except Exception as exc:
            print(f"CAMERA: Import Blender ERR '{path}': {exc}")
            return False

    # ── Changement de scène ───────────────────────────────────────────────────

    def set_scene(self, scene_name: str, scene_cfg: dict, t_scene_start: float) -> None:
        """
        Configure la caméra pour une nouvelle scène.

        Paramètres
        ----------
        scene_name      : nom de la scène (non utilisé ici, pour extension future)
        scene_cfg       : dict de la scène (peut contenir un champ ``"camera"``)
        t_scene_start   : temps absolu de début de la scène
        """
        self._scene_start = t_scene_start
        self._scene_dur   = float(scene_cfg.get("duration", 0.0))
        self._scene_cfg   = scene_cfg.get("camera", {})
        self._free_mode   = False

        cam_cfg = self._scene_cfg
        self._near = float(cam_cfg.get("near", self.DEFAULT_NEAR))
        self._far  = float(cam_cfg.get("far",  self.DEFAULT_FAR))

        traj_name = cam_cfg.get("trajectory", "")
        if traj_name and traj_name in self._trajectories:
            self._active_traj = self._trajectories[traj_name]
            print(f"CAMERA: Trajectoire '{traj_name}' activée ({len(self._active_traj.keyframes)} kf)")
        else:
            self._active_traj = None
            # Position/target statiques optionnelles
            if "pos" in cam_cfg:
                self._pos    = np.array(cam_cfg["pos"],    dtype=np.float32)
            if "target" in cam_cfg:
                self._target = np.array(cam_cfg["target"], dtype=np.float32)
            self._fov  = float(cam_cfg.get("fov",  self.DEFAULT_FOV))

    # ── Mode libre (viewport interactif) ─────────────────────────────────────

    def set_free(self, pos: Vec3, target: Vec3, fov: float = 60.0) -> None:
        """Active le mode libre (viewport interactif ou debug)."""
        self._free_mode   = True
        self._free_pos    = np.asarray(pos,    dtype=np.float32)
        self._free_target = np.asarray(target, dtype=np.float32)
        self._free_fov    = fov

    # ── Mise à jour par frame ─────────────────────────────────────────────────

    def update(self, t: float) -> dict:
        """
        Calcule et retourne un dict de tous les uniforms caméra pour le temps ``t``.

        Retourne
        --------
        dict contenant :
            iCamMatrix, iCamPos, iCamDir, iCamUp,
            iCamFov, iCamNear, iCamFar, iCamProgress
        """
        if self._free_mode:
            pos    = self._free_pos
            target = self._free_target
            fov    = self._free_fov
            roll   = 0.0
            self._progress = 0.0
        elif self._active_traj is not None:
            # Temps relatif dans la trajectoire
            t_rel = t - self._scene_start
            kf = self._active_traj.evaluate(t_rel)
            pos    = kf.pos
            target = kf.target
            fov    = kf.fov
            roll   = kf.roll
            dur = max(self._active_traj.duration, 1e-6)
            self._progress = min(1.0, max(0.0, t_rel / dur))
        else:
            pos    = self._pos
            target = self._target
            fov    = self._fov
            roll   = self._roll
            self._progress = 0.0

        self._pos    = pos
        self._target = target
        self._fov    = fov
        self._roll   = roll

        # Up avec roll
        fwd = _normalize(target - pos)
        if abs(roll) > 1e-4:
            rm  = _roll_matrix(roll, fwd)
            up  = (_normalize(np.cross(np.cross(fwd, self.DEFAULT_UP), fwd)))
            up4 = np.array([*up, 0.0], dtype=np.float32)
            up  = (rm @ up4)[:3]
        else:
            up = _normalize(np.cross(np.cross(fwd, self.DEFAULT_UP), fwd))
        self._up = up

        # Matrices
        view = _look_at(pos, target, up)
        proj = _perspective(fov, self.aspect, self._near, self._far)
        vp   = proj @ view

        # Inverse VP pour le ray-casting dans les fragment shaders
        try:
            vp_inv = np.linalg.inv(vp).astype(np.float32)
        except np.linalg.LinAlgError:
            vp_inv = np.eye(4, dtype=np.float32)
        self._cam_matrix = vp_inv

        return {
            "iCamMatrix":   tuple(vp_inv.T.flatten().tolist()),  # column-major
            "iCamPos":      tuple(pos.tolist()),
            "iCamDir":      tuple(fwd.tolist()),
            "iCamUp":       tuple(up.tolist()),
            "iCamFov":      float(fov),
            "iCamNear":     float(self._near),
            "iCamFar":      float(self._far),
            "iCamProgress": float(self._progress),
        }

    # ── Injection GLSL ────────────────────────────────────────────────────────

    def bind(self, prog) -> None:
        """
        Injecte tous les uniforms caméra dans le programme ``prog``.
        Appeler après ``update()``.
        """
        if prog is None:
            return
        unis = self.update.__doc__  # juste pour la doc; on utilise l'état courant
        uniforms = {
            "iCamMatrix":   tuple(self._cam_matrix.T.flatten().tolist()),
            "iCamPos":      tuple(self._pos.tolist()),
            "iCamDir":      tuple(_normalize(self._target - self._pos).tolist()),
            "iCamUp":       tuple(self._up.tolist()),
            "iCamFov":      float(self._fov),
            "iCamNear":     float(self._near),
            "iCamFar":      float(self._far),
            "iCamProgress": float(self._progress),
        }
        for name, value in uniforms.items():
            if name in prog:
                try:
                    prog[name].value = value
                except Exception:
                    pass

    # ── Persistance ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Sérialise toutes les trajectoires pour project.json."""
        return {
            name: traj.to_list()
            for name, traj in self._trajectories.items()
        }

    # ── Accès état ───────────────────────────────────────────────────────────

    @property
    def position(self) -> Vec3:
        return self._pos.copy()

    @property
    def direction(self) -> Vec3:
        return _normalize(self._target - self._pos)

    @property
    def trajectory_names(self) -> list[str]:
        return list(self._trajectories.keys())
