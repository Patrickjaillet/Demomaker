"""
particle_system.py  —  Phase 9.2 : Particules GPU
==================================================

Implémentation via **Transform Feedback** OpenGL 3.3 :
  - Mise à jour des particules sur GPU (pas de readback CPU)
  - Rendu en GL_POINTS avec vertex shader dédié
  - Forces audio réactives : iBass → gravité, iKick → explosion
  - Trails (traînées) via accumulation de frames

Architecture
------------

    ParticleEmitter
    ├── _vbo_a / _vbo_b         Double-buffer Transform Feedback
    ├── _vao_update             VAO pour la passe Update (TF)
    ├── _vao_render             VAO pour la passe Render
    ├── update(t, au)           Passe TF : met à jour positions/vitesses
    └── render(fbo, t, au)      Passe Render : dessine les points

    ParticleSystem
    ├── emitters: dict[str, ParticleEmitter]
    ├── set_scene(scene_name, scene_cfg)
    ├── update(t, audio_uniforms)
    └── render(fbo, t, audio_uniforms)

Configuration project.json
---------------------------
    {
      "base_name": "aurora",
      "start": 10.0,
      "duration": 10.0,
      "particles": {
        "emitter": "default",
        "count": 50000,
        "emit_rate": 2000,
        "lifetime": 3.0,
        "start_pos": [0.0, 0.0, 0.0],
        "spread": 1.0,
        "gravity": [0.0, -0.3, 0.0],
        "audio_gravity": true,
        "audio_burst": true,
        "color_start": [1.0, 0.4, 0.1, 1.0],
        "color_end":   [0.2, 0.0, 0.5, 0.0],
        "size_start": 4.0,
        "size_end": 0.5,
        "trail_alpha": 0.0
      }
    }

Shaders GLSL requis
-------------------
    shaders/particles_update.vert   Passe Transform Feedback
    shaders/particles_render.vert   Rendu des points
    shaders/particles_render.frag   Couleur/alpha des particules

Uniforms injectés dans les shaders
-----------------------------------
Passe update :
    iTime, iDeltaTime, iKick, iBass, iMid, iEnergy
    uGravity (vec3), uSpread (float), uEmitRate (float)
    uLifetime (float), uAudioGravity (bool), uAudioBurst (bool)

Passe render :
    iResolution, iTime, iCamMatrix (si CameraSystem connecté)
    uColorStart, uColorEnd (vec4), uSizeStart, uSizeEnd (float)
"""

from __future__ import annotations

import os
import math
from typing import Optional, Callable

import numpy as np
import moderngl


# ─────────────────────────────────────────────────────────────────────────────
#  Shaders internes (fallback si fichiers absents)
# ─────────────────────────────────────────────────────────────────────────────

_UPDATE_VERT = """
#version 330
#extension GL_ARB_transform_feedback : enable

layout(location = 0) in vec3  in_pos;
layout(location = 1) in vec3  in_vel;
layout(location = 2) in float in_life;
layout(location = 3) in float in_age;
layout(location = 4) in float in_seed;

out vec3  out_pos;
out vec3  out_vel;
out float out_life;
out float out_age;
out float out_seed;

uniform float iDeltaTime;
uniform float iTime;
uniform float iKick;
uniform float iBass;
uniform float iEnergy;
uniform vec3  uGravity;
uniform float uSpread;
uniform float uLifetime;
uniform bool  uAudioGravity;
uniform bool  uAudioBurst;

// Pseudo-RNG depuis seed
float rand(float s){ return fract(sin(s * 127.1 + iTime * 0.01) * 43758.5453); }

void main() {
    float age  = in_age + iDeltaTime;
    float life = in_life;

    if (age > life || life < 0.0) {
        // Réémettre
        float s  = in_seed + iTime * 0.001;
        float a  = rand(s)         * 6.2831;
        float e  = rand(s + 1.3)   * 0.5 + 0.5;
        float sp = uSpread;
        if (uAudioBurst) sp *= 1.0 + iKick * 3.0;
        out_pos  = vec3(cos(a)*e*sp, rand(s+2.7)*sp*0.5, sin(a)*e*sp);
        out_vel  = vec3(cos(a)*e*0.5, rand(s+3.1)*1.5+0.5, sin(a)*e*0.5);
        out_life = uLifetime * (0.7 + rand(s+4.2)*0.6);
        out_age  = 0.0;
        out_seed = rand(s + 5.9) * 1000.0;
    } else {
        vec3 g = uGravity;
        if (uAudioGravity) g *= 1.0 + iBass * 2.0;
        out_pos  = in_pos  + in_vel * iDeltaTime;
        out_vel  = in_vel  + g * iDeltaTime;
        out_life = in_life;
        out_age  = age;
        out_seed = in_seed;
    }
}
"""

_RENDER_VERT = """
#version 330
layout(location = 0) in vec3  in_pos;
layout(location = 2) in float in_life;
layout(location = 3) in float in_age;

uniform mat4  iCamMatrix;
uniform vec3  iCamPos;
uniform float iCamFov;
uniform vec2  iResolution;
uniform float uSizeStart;
uniform float uSizeEnd;

out float v_t;

void main() {
    v_t = clamp(in_age / max(in_life, 0.001), 0.0, 1.0);
    vec4 pos = iCamMatrix * vec4(in_pos, 1.0);
    gl_Position = pos;
    float dist = length(in_pos - iCamPos);
    float sz = mix(uSizeStart, uSizeEnd, v_t);
    gl_PointSize = max(1.0, sz * 500.0 / max(dist, 0.1));
}
"""

_RENDER_FRAG = """
#version 330
in float v_t;
uniform vec4 uColorStart;
uniform vec4 uColorEnd;
out vec4 fragColor;
void main() {
    vec2 uv   = gl_PointCoord * 2.0 - 1.0;
    float d   = dot(uv, uv);
    if (d > 1.0) discard;
    float soft = 1.0 - smoothstep(0.5, 1.0, d);
    vec4  col  = mix(uColorStart, uColorEnd, v_t);
    fragColor  = vec4(col.rgb, col.a * soft);
}
"""

# Varyings capturés par Transform Feedback (doit correspondre aux out du vert)
_TF_VARYINGS = ["out_pos", "out_vel", "out_life", "out_age", "out_seed"]

# Taille en bytes d'une particule : 3+3+1+1+1 floats = 9 × 4 = 36 bytes
_PARTICLE_STRIDE = 9 * 4


# ─────────────────────────────────────────────────────────────────────────────
#  ParticleEmitter
# ─────────────────────────────────────────────────────────────────────────────

class ParticleEmitter:
    """
    Émetteur de particules GPU utilisant Transform Feedback.

    Paramètres
    ----------
    ctx           : moderngl.Context
    count         : nombre maximum de particules
    cfg           : dict de configuration (depuis project.json)
    shader_dir    : dossier contenant les shaders (fallback = intégrés)
    """

    def __init__(
        self,
        ctx:        moderngl.Context,
        count:      int = 50_000,
        cfg:        dict | None = None,
        shader_dir: str = "",
    ):
        self.ctx     = ctx
        self.count   = max(1, count)
        self.cfg     = cfg or {}
        self._t_prev = -1.0
        self._active = True

        # Config
        self.gravity     = np.array(self.cfg.get("gravity", [0.0, -0.3, 0.0]), dtype=np.float32)
        self.spread      = float(self.cfg.get("spread",     1.0))
        self.lifetime    = float(self.cfg.get("lifetime",   3.0))
        self.audio_grav  = bool( self.cfg.get("audio_gravity", True))
        self.audio_burst = bool( self.cfg.get("audio_burst",   True))
        self.color_start = tuple(self.cfg.get("color_start", [1.0, 0.4, 0.1, 1.0]))
        self.color_end   = tuple(self.cfg.get("color_end",   [0.2, 0.0, 0.5, 0.0]))
        self.size_start  = float(self.cfg.get("size_start",  4.0))
        self.size_end    = float(self.cfg.get("size_end",    0.5))

        self._build_buffers()
        self._build_shaders(shader_dir)

    # ── Initialisation buffers ────────────────────────────────────────────────

    def _build_buffers(self) -> None:
        """Crée les deux VBO pour le double-buffer Transform Feedback."""
        # Données initiales : particules "mortes" (life=-1)
        rng  = np.random.default_rng(42)
        data = np.zeros((self.count, 9), dtype=np.float32)
        # pos (3), vel (3), life (1), age (1), seed (1)
        data[:, 6] = -1.0        # life = -1 → sera réémis immédiatement
        data[:, 8] = rng.random(self.count).astype(np.float32) * 1000.0  # seed
        raw = data.tobytes()
        flags = moderngl.DYNAMIC_DRAW
        self._vbo = [
            self.ctx.buffer(data=raw, dynamic=True),
            self.ctx.buffer(data=raw, dynamic=True),
        ]
        self._idx = 0   # buffer courant en lecture

    def _build_shaders(self, shader_dir: str) -> None:
        """Compile les programmes Update et Render."""
        def _read(name):
            path = os.path.join(shader_dir, name)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fh:
                    return fh.read()
            return None

        # ── Programme Update (Transform Feedback) ────────────────────────────
        upd_code = _read("particles_update.vert") or _UPDATE_VERT
        try:
            self._prog_update = self.ctx.program(
                vertex_shader   = upd_code,
                varyings        = _TF_VARYINGS,
            )
        except Exception as exc:
            print(f"PARTICLES: ERR shader update: {exc}")
            self._prog_update = None

        # ── Programme Render ─────────────────────────────────────────────────
        rnd_vert = _read("particles_render.vert") or _RENDER_VERT
        rnd_frag = _read("particles_render.frag") or _RENDER_FRAG
        try:
            self._prog_render = self.ctx.program(
                vertex_shader   = rnd_vert,
                fragment_shader = rnd_frag,
            )
        except Exception as exc:
            print(f"PARTICLES: ERR shader render: {exc}")
            self._prog_render = None

        self._build_vaos()

    def _build_vaos(self) -> None:
        """Reconstruit les VAO pour les deux passes."""
        if not self._prog_update or not self._prog_render:
            self._vao_update = [None, None]
            self._vao_render = [None, None]
            return

        stride = _PARTICLE_STRIDE
        fmt    = "3f 3f f f f"   # pos vel life age seed
        attrs  = ["in_pos", "in_vel", "in_life", "in_age", "in_seed"]

        self._vao_update = []
        self._vao_render = []
        for vbo in self._vbo:
            try:
                vau = self.ctx.vertex_array(
                    self._prog_update, [(vbo, fmt, *attrs)])
                var = self.ctx.vertex_array(
                    self._prog_render, [(vbo, fmt, *attrs)])
                self._vao_update.append(vau)
                self._vao_render.append(var)
            except Exception as exc:
                print(f"PARTICLES: ERR VAO: {exc}")
                self._vao_update.append(None)
                self._vao_render.append(None)

    # ── Helpers uniforms ──────────────────────────────────────────────────────

    @staticmethod
    def _set(prog, name, value):
        if prog and name in prog:
            try:
                prog[name].value = value
            except Exception:
                pass

    # ── Passe Update (Transform Feedback) ────────────────────────────────────

    def update(self, t: float, audio_uniforms: dict) -> None:
        """Exécute la passe Transform Feedback pour mettre à jour les particules."""
        if not self._active:
            return
        if not self._prog_update:
            return

        dt = min(t - self._t_prev, 0.1) if self._t_prev >= 0 else 0.016
        self._t_prev = t

        src = self._idx
        dst = 1 - self._idx

        vao = self._vao_update[src]
        if vao is None:
            return

        p = self._prog_update
        self._set(p, "iDeltaTime",   float(dt))
        self._set(p, "iTime",        float(t))
        self._set(p, "iKick",        float(audio_uniforms.get("iKick",   0.0)))
        self._set(p, "iBass",        float(audio_uniforms.get("iBass",   0.0)))
        self._set(p, "iEnergy",      float(audio_uniforms.get("iEnergy", 0.0)))
        self._set(p, "uGravity",     tuple(self.gravity.tolist()))
        self._set(p, "uSpread",      float(self.spread))
        self._set(p, "uLifetime",    float(self.lifetime))
        self._set(p, "uAudioGravity",bool(self.audio_grav))
        self._set(p, "uAudioBurst",  bool(self.audio_burst))

        # Transform Feedback : lire de src, écrire dans dst
        try:
            self.ctx.transform(
                vao,
                self._vbo[dst],
                moderngl.POINTS,
                vertices = self.count,
            )
        except Exception as exc:
            print(f"PARTICLES: ERR transform: {exc}")

        self._idx = dst  # swap

    # ── Passe Render ──────────────────────────────────────────────────────────

    def render(
        self,
        t:              float,
        audio_uniforms: dict,
        cam_uniforms:   dict | None = None,
        res:            tuple = (1920, 1080),
    ) -> None:
        """Dessine les particules avec GL_POINTS."""
        if not self._active or not self._prog_render:
            return
        vao = self._vao_render[self._idx]
        if vao is None:
            return

        p = self._prog_render
        self._set(p, "iTime",       float(t))
        self._set(p, "iResolution", res)
        self._set(p, "uColorStart", self.color_start)
        self._set(p, "uColorEnd",   self.color_end)
        self._set(p, "uSizeStart",  float(self.size_start))
        self._set(p, "uSizeEnd",    float(self.size_end))

        # Uniforms caméra (si CameraSystem connecté)
        if cam_uniforms:
            for k, v in cam_uniforms.items():
                self._set(p, k, v)

        try:
            self.ctx.enable(moderngl.BLEND)
            self.ctx.enable(moderngl.PROGRAM_POINT_SIZE)
            self.ctx.blend_equation = moderngl.FUNC_ADD
            self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)  # additif
            vao.render(moderngl.POINTS, vertices=self.count)
            self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
        except Exception as exc:
            print(f"PARTICLES: ERR render: {exc}")

    # ── Nettoyage ─────────────────────────────────────────────────────────────

    def release(self) -> None:
        for vao_list in (self._vao_update, self._vao_render):
            for v in vao_list:
                if v:
                    try: v.release()
                    except Exception: pass
        for vbo in self._vbo:
            if vbo:
                try: vbo.release()
                except Exception: pass
        for prog in (self._prog_update, self._prog_render):
            if prog:
                try: prog.release()
                except Exception: pass


# ─────────────────────────────────────────────────────────────────────────────
#  ParticleSystem — gestionnaire global
# ─────────────────────────────────────────────────────────────────────────────

class ParticleSystem:
    """
    Gestionnaire de particules pour le moteur MEGADEMO.

    Crée et gère les ``ParticleEmitter`` par scène.
    S'intègre dans la boucle de rendu après ``ScenePipeline.render()``.
    """

    def __init__(self, ctx: moderngl.Context, project_dir: str = ""):
        self.ctx         = ctx
        self.shader_dir  = os.path.join(project_dir, "shaders")
        self._emitters:  dict[str, ParticleEmitter] = {}
        self._active_key: str = ""
        self._cam_uniforms: dict = {}

    # ── Connexion à la caméra ─────────────────────────────────────────────────

    def set_camera_uniforms(self, cam_uniforms: dict) -> None:
        """Met à jour les uniforms caméra injectés dans le shader render."""
        self._cam_uniforms = cam_uniforms

    # ── Changement de scène ───────────────────────────────────────────────────

    def set_scene(self, scene_name: str, scene_cfg: dict) -> None:
        """
        Active l'émetteur pour la scène courante.
        Crée l'émetteur s'il n'existe pas encore.
        """
        pcfg = scene_cfg.get("particles")
        if not pcfg:
            self._active_key = ""
            return

        key = f"{scene_name}:{pcfg.get('emitter', 'default')}"
        if key not in self._emitters:
            count = int(pcfg.get("count", 50_000))
            self._emitters[key] = ParticleEmitter(
                ctx        = self.ctx,
                count      = count,
                cfg        = pcfg,
                shader_dir = self.shader_dir,
            )
            print(f"PARTICLES: Émetteur '{key}' créé ({count} particules)")
        self._active_key = key

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, t: float, audio_uniforms: dict) -> None:
        """Passe Transform Feedback pour l'émetteur actif."""
        em = self._emitters.get(self._active_key)
        if em:
            em.update(t, audio_uniforms)

    # ── Render ────────────────────────────────────────────────────────────────

    def render(
        self,
        t:              float,
        audio_uniforms: dict,
        res:            tuple = (1920, 1080),
    ) -> None:
        """Dessine les particules de l'émetteur actif sur le FBO courant."""
        em = self._emitters.get(self._active_key)
        if em:
            em.render(t, audio_uniforms, self._cam_uniforms, res)

    # ── Nettoyage ─────────────────────────────────────────────────────────────

    def release(self) -> None:
        for em in self._emitters.values():
            em.release()
        self._emitters.clear()
