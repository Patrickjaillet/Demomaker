"""
system.py  —  Moteur de rendu principal
Phase 9 : Fonctionnalités Créatives Avancées

Ajouts Phase 9
--------------
- ``CameraSystem``   — trajectoires 3D, ``iCamMatrix``, import Blender
- ``ParticleSystem`` — particules GPU Transform Feedback, forces audio
- ``TextSystem``     — atlas SDF, scroll, karaoke synchronisé

Les trois systèmes se connectent sur la boucle de rendu après
``ScenePipeline.render()``.  Ils sont tous optionnels : si la scène
ne configure pas de caméra / particules / texte, ils sont silencieux.
"""

import pygame
import moderngl
import time
import numpy as np
import soundfile as sf
import os
import json

from audio_analysis import AudioAnalyzer
from param_system import ParamSystem, parse_shader_params
from pipeline import (
    ScenePipeline, TransitionManager, PostProcessor,
    TextureManager, DEFAULT_PASSES, _safe_set, QUAD, VERT, _read_glsl
)
from base_renderer import BaseRenderer

# Phase 9 — nouveaux systèmes
from camera_system   import CameraSystem
from particle_system import ParticleSystem
from text_system     import TextSystem

PROJECT_FILE = "project.json"


def load_project(path=PROJECT_FILE):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Fichier projet introuvable : '{path}'\n"
            "Lance demomaker_gui.py pour en créer un.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_scene_at_time(timeline, t):
    for scene in timeline:
        if scene["start"] <= t < (scene["start"] + scene["duration"]):
            return scene
    return None


def get_overlay_at_time(overlays, t):
    for ov in overlays:
        if ov["start"] <= t < (ov["start"] + ov["duration"]):
            return ov
    return None


class Engine(BaseRenderer):
    """
    Moteur de rendu temps-réel Phase 9.

    Nouvelles propriétés
    --------------------
    camera_system   : CameraSystem
    particle_system : ParticleSystem
    text_system     : TextSystem
    """

    def __init__(self):
        project     = load_project()
        cfg         = project["config"]
        project_dir = os.path.dirname(os.path.abspath(PROJECT_FILE))

        super().__init__(
            project_dir = project_dir,
            cfg         = cfg,
            timeline    = project["timeline"],
            overlays    = project["overlays"],
        )

        self._init_pygame()
        self.ctx = moderngl.create_context()
        self.init_gl_base(self.ctx)

        self.audio_data  = None
        self.stereo_data = None
        self.sr          = 44100
        self.setup_audio(cfg.get("MUSIC_FILE", ""))
        self._init_resources()
        self._init_audio_analyzer()
        self._init_pipeline_systems()
        self._init_phase9_systems(project)       # ← Phase 9

        self.start_time           = time.perf_counter()
        self.current_scene_name   = None
        self.current_overlay_name = None
        self._scene_pipeline:  ScenePipeline | None = None
        self._prev_pipeline:   ScenePipeline | None = None

        self._inter_scene_tex:  moderngl.Texture | None = None
        self._inter_scene_fbo:  moderngl.Framebuffer | None = None

        self.audio_uniforms = dict(
            iKick=0.0, iBass=0.0, iMid=0.0, iHigh=0.0,
            iBassPeak=0.0, iMidPeak=0.0, iHighPeak=0.0,
            iBassRMS=0.0, iMidRMS=0.0, iHighRMS=0.0,
            iBeat=0.0, iBPM=120.0,
            iBar=0.0, iBeat4=0.0, iSixteenth=0.0,
            iEnergy=0.0, iDrop=0.0,
            iStereoWidth=0.0, iCue=0.0, iSection=0.0,
        )
        self.kick = 0.0

        self.param_system = ParamSystem()

        if self.textures_intro:
            self.intro_time = cfg.get("INTRO_TIME", 0.0)
        else:
            self.intro_time = 0.0
            print("MOTEUR: Aucune texture d'intro — timeline démarre à t=0")

    # ── Init ─────────────────────────────────────────────────────────────────

    def _res(self):
        return tuple(self.cfg["RES"])

    def _init_pygame(self):
        pygame.init()
        pygame.display.set_mode(self._res(), pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE)
        pygame.display.set_caption(self.cfg.get("WINDOW_TITLE", "MEGADEMO"))

    def _init_pipeline_systems(self):
        self._texmgr = TextureManager(self.ctx, self.project_dir)
        self._texmgr.preload_all()

        self._transition = TransitionManager(
            self.ctx, self.project_dir, self._quad_buf, self._res())

        self._post = PostProcessor(
            self.ctx, self.project_dir, self._quad_buf, self._res(), self._texmgr)

        self._noise_textures: dict = {}
        for name in ('blue_noise', 'worley_noise', 'white_noise'):
            tex = self._texmgr.get(name)
            if tex:
                self._noise_textures[f'i{name.title().replace("_","")}'] = tex
        print(f"PIPELINE: {len(self._noise_textures)} textures de bruit disponibles")

        res = self._res()
        self._inter_scene_tex = self.ctx.texture(res, 4, dtype='f4')
        self._inter_scene_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._inter_scene_fbo = self.ctx.framebuffer(
            color_attachments=[self._inter_scene_tex])
        self._inter_scene_fbo.use()
        self.ctx.clear(0.0, 0.0, 0.0, 1.0)
        print("PIPELINE: FBO feedback inter-scènes initialisé")

    # ── Phase 9 — Init des 3 nouveaux systèmes ────────────────────────────────

    def _init_phase9_systems(self, project: dict) -> None:
        """Initialise CameraSystem, ParticleSystem, TextSystem."""
        res = self._res()
        aspect = res[0] / max(res[1], 1)

        # Caméra
        self.camera_system = CameraSystem(aspect_ratio=aspect)
        self.camera_system.load_from_project(project)
        self._cam_uniforms: dict = {}

        # Particules
        self.particle_system = ParticleSystem(self.ctx, self.project_dir)

        # Texte
        self.text_system = TextSystem(self.ctx, self.project_dir, res)

        print("PHASE9: CameraSystem, ParticleSystem, TextSystem initialisés")

    def _init_resources(self):
        scroll_text = self.cfg.get("SCROLL_TEXT", "")
        self.scroll_tex = self.create_text_texture(scroll_text, "fonts/fabric-shapes.ttf", 80)
        self.textures_intro = {}
        for name in ["logo", "presents", "album"]:
            for folder in ("images", "img"):
                path = os.path.join(folder, f"{name}.png")
                tex  = self._load_texture(path)
                if tex:
                    self.textures_intro[name] = tex
                    print(f"INTRO: Texture '{name}' ← '{path}'")
                    break
        self._load_intro_shader()

    # ── Textures ──────────────────────────────────────────────────────────────

    def create_text_texture(self, text, font_path, size, color=(255, 255, 255)):
        try:
            font = pygame.font.Font(font_path, size)
        except Exception:
            font = pygame.font.SysFont("Arial", size)
        surf = font.render(" " * 10 + text + " " * 10, True, color).convert_alpha()
        data = pygame.image.tostring(surf, "RGBA", True)
        tex  = self.ctx.texture(surf.get_size(), 4, data)
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        return tex

    def _load_intro_shader(self):
        code = _read_glsl("shaders/intro.frag")
        if code:
            try:
                self.intro_prog = self.ctx.program(vertex_shader=VERT, fragment_shader=code)
                self.intro_vao  = self.ctx.simple_vertex_array(
                    self.intro_prog, self._quad_buf, 'in_vert')
                print("INTRO: Shader chargé")
            except Exception as e:
                print(f"INTRO ERR: {e}")

    def load_overlay_shader(self, effect_name):
        self._load_overlay_shader(effect_name)
        self.prog_overlay = self._prog_overlay
        self.vao_overlay  = self._vao_overlay

    # ── Audio ─────────────────────────────────────────────────────────────────

    def setup_audio(self, path):
        if not path or not os.path.exists(path):
            print(f"AUDIO: '{path}' introuvable.")
            return
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
        except Exception as e:
            print(f"AUDIO mixer ERR: {e}")
        try:
            data, self.sr = sf.read(path)
            if data.ndim > 1:
                self.stereo_data = data.astype(np.float32)
                self.audio_data  = data.mean(axis=1).astype(np.float32)
            else:
                self.stereo_data = None
                self.audio_data  = data.astype(np.float32)
            print(f"AUDIO: '{path}' — {len(self.audio_data)} samples @ {self.sr} Hz")
        except Exception as e:
            print(f"AUDIO read ERR: {e}")

    def _init_audio_analyzer(self):
        if self.audio_data is not None:
            self.analyzer = AudioAnalyzer(
                ctx            = self.ctx,
                audio_data     = self.audio_data,
                stereo_data    = self.stereo_data,
                sr             = self.sr,
                smoothing      = self.cfg.get("AUDIO_SMOOTHING", 0.85),
                kick_sens      = self.cfg.get("KICK_SENS", 1.5),
                bass_gain      = self.cfg.get("BASS_GAIN", 1.0),
                mid_gain       = self.cfg.get("MID_GAIN", 1.0),
                high_gain      = self.cfg.get("HIGH_GAIN", 1.0),
                beat_threshold = self.cfg.get("BEAT_THRESHOLD", 0.4),
                latency_ms     = self.cfg.get("LATENCY_MS", 0.0),
                cue_points     = self.cfg.get("CUE_POINTS", []),
            )
            print(f"AUDIO: Analyseur Phase 1 — FFT={self.analyzer.fft_size}")
        else:
            self.analyzer = None

    def _update_audio(self, t):
        if self.analyzer is not None:
            self.audio_uniforms = self.analyzer.update(t)
            self.kick = self.audio_uniforms["iKick"]

    def _on_bind_audio_extra(self, prog, uniforms, scene_name, t):
        if self.analyzer is not None:
            self.analyzer.bind_textures(prog, start_unit=8)
        if scene_name and t is not None:
            bpm = uniforms.get('iBPM', 120.0)
            self.param_system.inject(prog, scene_name, t, uniforms, bpm)
        # Phase 9 — injecter les uniforms caméra
        if self._cam_uniforms:
            for name, value in self._cam_uniforms.items():
                self._safe_set(prog, name, value)

    def safe_set(self, prog, name, value):
        self._safe_set(prog, name, value)

    # ── Chargement de scène (Phase 9 : active les 3 nouveaux systèmes) ────────

    def _load_scene(self, sc: dict, t: float) -> ScenePipeline:
        name = sc["base_name"]
        pipeline = ScenePipeline(
            ctx         = self.ctx,
            project_dir = self.project_dir,
            scene_name  = name,
            scene_cfg   = sc,
            base_res    = self._res(),
            quad_buf    = self._quad_buf,
            tex_manager = self._texmgr,
        )
        print(f"MOTEUR: Scène [{name}] — {len(pipeline.passes)} passes "
              f"| post={'oui' if sc.get('post') else 'non'}")

        # Params
        shader_path = os.path.join(self.project_dir, "scenes", f"scene_{name}.frag")
        params = self.param_system.parse_shader(shader_path)
        if params:
            self.param_system.register_scene(name, params)
            auto_data = self.cfg.get("automation", {})
            if name in auto_data:
                self.param_system.from_dict({name: auto_data[name]})
            print(f"  → {len(params)} @params: {[p.name for p in params]}")

        # ── Phase 9 — activer caméra / particules / texte ────────────────────
        self.camera_system.set_scene(name, sc, t)
        self.particle_system.set_scene(name, sc)
        self.text_system.set_scene(name, sc)

        return pipeline

    # ── Boucle principale ─────────────────────────────────────────────────────

    def run(self):
        clock = pygame.time.Clock()
        res   = self._res()

        print(f"MOTEUR: Démarrage — {len(self.timeline)} scènes — "
              f"durée={self.cfg.get('MUSIC_DURATION', 0)}s")

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: return

            t = time.perf_counter() - self.start_time
            if t >= self.cfg.get("MUSIC_DURATION", 9999): break

            self._update_audio(t)

            # ── Phase 9 : mise à jour caméra ─────────────────────────────────
            self._cam_uniforms = self.camera_system.update(t)
            self.particle_system.set_camera_uniforms(self._cam_uniforms)

            self.ctx.screen.use()
            self.ctx.clear(0.0, 0.0, 0.0)

            if t < self.intro_time:
                self._render_intro(t, res)
            else:
                self._render_timeline(t, res)

            pygame.display.flip()
            clock.tick(60)

    # ── Rendu ─────────────────────────────────────────────────────────────────

    def _render_intro(self, t, res):
        logo_dur = self.cfg.get("LOGO_DURATION", 0.0)
        pres_dur = self.cfg.get("PRESENTS_DURATION", 0.0)
        if t < logo_dur:                    key, lt = "logo",     t
        elif t < logo_dur + pres_dur:       key, lt = "presents", t - logo_dur
        else:                               key, lt = "album",    t - logo_dur - pres_dur
        tex = self.textures_intro.get(key)
        if tex and hasattr(self, 'intro_vao') and hasattr(self, 'intro_prog'):
            tex.use(0)
            p = self.intro_prog
            _safe_set(p, 'iChannel0',   0)
            _safe_set(p, 'iTime',       lt)
            _safe_set(p, 'iResolution', res)
            self._bind_audio_uniforms(p, self.audio_uniforms)
            self.intro_vao.render(moderngl.TRIANGLE_STRIP)

    def _render_timeline(self, t, res):
        sc = get_scene_at_time(self.timeline, t)

        if sc and sc["base_name"] != self.current_scene_name:
            if self._scene_pipeline and self._scene_pipeline.main_tex \
                    and self._inter_scene_fbo:
                src = self._scene_pipeline.main_tex
                self._inter_scene_fbo.use()
                try:
                    src.use(0)
                    p = getattr(self._post, '_prog', None)
                    v = getattr(self._post, '_vao', None)
                    if p and v and 'iChannel0' in p:
                        _safe_set(p, 'iChannel0', 0)
                        _safe_set(p, 'iPostBloom', 0.0); _safe_set(p, 'iPostGrain', 0.0)
                        _safe_set(p, 'iPostVig', 0.0);   _safe_set(p, 'iPostSat', 1.0)
                        _safe_set(p, 'iPostContrast', 1.0); _safe_set(p, 'iPostLUT', 0.0)
                        _safe_set(p, 'iResolution', self._res()); _safe_set(p, 'iTime', 0.0)
                        v.render(moderngl.TRIANGLE_STRIP)
                except Exception:
                    pass
                self._noise_textures['iPrevScene'] = self._inter_scene_tex

            if self._scene_pipeline and self._scene_pipeline.main_tex:
                self._transition.capture_prev(self._scene_pipeline.main_tex)

            self._prev_pipeline   = self._scene_pipeline
            self._scene_pipeline  = self._load_scene(sc, t)
            self.current_scene_name = sc["base_name"]

            tr_cfg = sc.get("transition_in", {})
            if tr_cfg and self._prev_pipeline:
                self._transition.start(
                    tex_next = self._scene_pipeline.main_tex,
                    effect   = tr_cfg.get("effect"),
                    duration = tr_cfg.get("duration"),
                    t_now    = t,
                )

        if sc is None or self._scene_pipeline is None:
            return

        progress = (t - sc["start"]) / max(sc["duration"], 1e-6)

        # ── Phase 9 : update particules ───────────────────────────────────────
        self.particle_system.update(t, self.audio_uniforms)

        # Pipeline GL (scène)
        self._scene_pipeline.render(
            t              = t,
            progress       = progress,
            audio_uniforms = self.audio_uniforms,
            bind_audio_fn  = lambda prog, scene_name=None: self._bind_audio_uniforms(
                prog, self.audio_uniforms, scene_name, t),
            fbo_screen     = self.ctx.screen,
            post_proc      = self._post if sc.get('post') else None,
            extra_textures = self._noise_textures,
        )

        # Transition
        if self._transition.active:
            done = self._transition.render(t, res, self.ctx.screen)
            if done:
                self._prev_pipeline = None

        # ── Phase 9 : rendu particules ────────────────────────────────────────
        self.particle_system.render(t, self.audio_uniforms, res)

        # ── Phase 9 : rendu texte ─────────────────────────────────────────────
        self.text_system.render(t, self.audio_uniforms)

        # Overlay
        self._render_overlay(t, res)

    def _render_overlay(self, t, res):
        ov = get_overlay_at_time(self.overlays, t)
        if not ov:
            self.current_overlay_name = None
            return
        ov_id = ov.get("name", "") + ov.get("effect", "")
        if ov_id != self.current_overlay_name:
            self.current_overlay_name = ov_id
            self.load_overlay_shader(ov["effect"])
        tex = self.scroll_tex if ov.get("file") == "SCROLL_INTERNAL" \
              else self._get_cached_texture(ov.get("file", ""))
        if tex and self._prog_overlay and self._vao_overlay:
            self.ctx.enable(moderngl.BLEND)
            tex.use(0)
            p = self._prog_overlay
            _safe_set(p, 'iChannel0',   0)
            _safe_set(p, 'iTime',       t)
            _safe_set(p, 'iResolution', res)
            _safe_set(p, 'iLocalTime',  t - ov["start"])
            _safe_set(p, 'iDuration',   ov["duration"])
            self._bind_audio_uniforms(p, self.audio_uniforms)
            self._vao_overlay.render(moderngl.TRIANGLE_STRIP)


if __name__ == "__main__":
    Engine().run()
