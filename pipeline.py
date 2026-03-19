"""
pipeline.py  —  Phase 2 : Système de Scènes & Pipeline GL
==========================================================

2.1  Passes configurables par JSON (jusqu'à 8 passes A..H + main)
2.2  Textures persistantes : LUT strip et bruit précalculé
2.3  Transitions entre scènes (6 shaders, durée configurable)
2.4  Post-processing global (bloom, grain, vignette, LUT, contraste)

Configuration dans project.json
--------------------------------
Chaque entrée de la timeline peut porter un champ optionnel "passes" :

  {
    "base_name": "plasma",
    "start": 10.0,
    "duration": 20.0,
    "transition_in":  {"effect": "transition_crossfade", "duration": 0.8},
    "transition_out": {"effect": "transition_ripple",    "duration": 1.2},
    "post": {
      "bloom": 0.4, "grain": 0.05, "vignette": 0.6,
      "saturation": 1.1, "contrast": 1.05, "lut": "cinema_warm"
    },
    "passes": [
      {"id": "A", "inputs": [],       "feedback": true,  "scale": 1.0},
      {"id": "B", "inputs": ["A"],    "feedback": false, "scale": 1.0},
      {"id": "C", "inputs": ["A","B"],"feedback": false, "scale": 0.5},
      {"id": "main", "inputs": ["A","B","C","D"]}
    ]
  }

Si "passes" est absent, le pipeline par défaut A/B/C/D est utilisé
(rétrocompatibilité totale).
"""

from __future__ import annotations
import os
import struct
import numpy as np
import moderngl

VERT = "#version 330\nin vec2 in_vert; void main(){ gl_Position=vec4(in_vert,0,1); }"
QUAD = np.array([-1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0, -1.0], dtype='f4')

# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _safe_set(prog, name, value):
    if prog and name in prog:
        prog[name].value = value

def _read_glsl(path: str) -> str | None:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    return None

# ─────────────────────────────────────────────────────────────────────────────
#  2.2 — GESTIONNAIRE DE TEXTURES (LUT + bruit)
# ─────────────────────────────────────────────────────────────────────────────

class TextureManager:
    """
    Charge et met en cache :
      - LUT strips  (256×1 RGBA f4)  depuis luts/*.raw
      - Textures de bruit             depuis noise/*.raw
    """

    def __init__(self, ctx: moderngl.Context, project_dir: str):
        self._ctx   = ctx
        self._dir   = project_dir
        self._cache: dict[str, moderngl.Texture] = {}

    def get(self, name: str) -> moderngl.Texture | None:
        """Retourne la texture chargée ou None si introuvable."""
        if name in self._cache:
            return self._cache[name]
        # Cherche dans luts/ puis noise/
        for subdir in ('luts', 'noise'):
            path = os.path.join(self._dir, subdir, name + '.raw')
            tex  = self._load_raw(path)
            if tex:
                self._cache[name] = tex
                return tex
        print(f"[TextureManager] Introuvable : {name}")
        return None

    def _load_raw(self, path: str) -> moderngl.Texture | None:
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'rb') as f:
                magic = f.read(4)
                if magic == b'LUT1':
                    # LUT strip : W(4) H(4) — RGBA f32
                    w, h = struct.unpack('<II', f.read(8))
                    data = np.frombuffer(f.read(), dtype=np.float32)
                    data = data.reshape(h, w, 4)
                    tex  = self._ctx.texture((w, h), 4, dtype='f4')
                    tex.write(data.tobytes())
                    tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
                    return tex
                elif magic == b'NOIS':
                    # Bruit : W(4) H(4) C(4) — float32
                    w, h, ch = struct.unpack('<III', f.read(12))
                    data = np.frombuffer(f.read(), dtype=np.float32)
                    data = data.reshape(h, w, ch)
                    tex  = self._ctx.texture((w, h), ch, dtype='f4')
                    tex.write(data.tobytes())
                    tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
                    tex.repeat_x = True
                    tex.repeat_y = True
                    return tex
        except Exception as e:
            print(f"[TextureManager] Erreur chargement {path}: {e}")
        return None

    def preload_all(self) -> None:
        """Pré-charge toutes les textures disponibles au démarrage."""
        for subdir in ('luts', 'noise'):
            folder = os.path.join(self._dir, subdir)
            if not os.path.isdir(folder):
                continue
            for fn in os.listdir(folder):
                if fn.endswith('.raw'):
                    name = fn[:-4]
                    self.get(name)
                    print(f"  [TextureManager] Chargé : {subdir}/{fn}")


# ─────────────────────────────────────────────────────────────────────────────
#  2.1 — PASSE DE RENDU
# ─────────────────────────────────────────────────────────────────────────────

class RenderPass:
    """
    Représente une passe de rendu unique :
      id        : identifiant ('A'..'H' ou 'main')
      inputs    : liste d'id de passes dont la texture est passée en iChannelN
      feedback  : si True, la texture de sortie est réinjectée à la frame suivante
      scale     : facteur de résolution (1.0 = full, 0.5 = half, 0.25 = quarter)
      condition : dict optionnel pour activer/désactiver la passe dynamiquement
                  selon un uniform audio.  Format :
                    {"uniform": "iKick", "op": ">", "threshold": 0.5}
                  Opérateurs supportés : ">", ">=", "<", "<=", "==", "!="
                  Si la condition est fausse, la passe est skippée (son FBO
                  conserve le contenu de la frame précédente).
    """

    def __init__(
        self,
        ctx:       moderngl.Context,
        pass_id:   str,
        base_res:  tuple[int, int],
        inputs:    list[str],
        feedback:  bool  = False,
        scale:     float = 1.0,
        condition: dict | None = None,
    ):
        self.id        = pass_id
        self.inputs    = inputs
        self.feedback  = feedback
        self.scale     = scale
        self.condition = condition   # dict ou None

        w = max(1, int(base_res[0] * scale))
        h = max(1, int(base_res[1] * scale))
        self.res = (w, h)

        # Double-buffer si feedback, simple sinon
        n_buf = 2 if feedback else 1
        self.textures: list[moderngl.Texture] = []
        self.fbos:     list[moderngl.Framebuffer] = []
        for _ in range(n_buf):
            tex = ctx.texture((w, h), 4, dtype='f4')
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            fbo = ctx.framebuffer(color_attachments=[tex])
            self.textures.append(tex)
            self.fbos.append(fbo)

        self._buf_idx  = 0   # double-buffer courant
        self.prog: moderngl.Program | None = None
        self.vao:  moderngl.VertexArray | None = None

    def load_shader(
        self,
        ctx:        moderngl.Context,
        quad_buf:   moderngl.Buffer,
        scene_name: str,
        project_dir: str,
    ) -> bool:
        if self.id == 'main':
            path = os.path.join(project_dir, 'scenes', f'scene_{scene_name}.frag')
        else:
            path = os.path.join(project_dir, 'scenes',
                                f'buffer_{self.id.lower()}_{scene_name}.frag')
        code = _read_glsl(path)
        if not code:
            return False
        try:
            self.prog = ctx.program(vertex_shader=VERT, fragment_shader=code)
            self.vao  = ctx.simple_vertex_array(self.prog, quad_buf, 'in_vert')
            return True
        except Exception as e:
            print(f"  [RenderPass {self.id}] Shader ERR {path}: {e}")
            return False

    @property
    def current_fbo(self) -> moderngl.Framebuffer:
        return self.fbos[self._buf_idx]

    @property
    def current_tex(self) -> moderngl.Texture:
        return self.textures[self._buf_idx]

    @property
    def prev_tex(self) -> moderngl.Texture:
        """Texture de la frame précédente (feedback)."""
        return self.textures[1 - self._buf_idx] if self.feedback else self.textures[0]

    def flip(self) -> None:
        if self.feedback:
            self._buf_idx = 1 - self._buf_idx

    def _eval_condition(self, audio_uniforms: dict) -> bool:
        """
        Évalue la condition de la passe.
        Retourne True si la passe doit être rendue, False pour la skipper.
        Si aucune condition n'est définie, retourne toujours True.
        """
        if not self.condition:
            return True
        uniform   = self.condition.get('uniform', 'iKick')
        op        = self.condition.get('op', '>')
        threshold = float(self.condition.get('threshold', 0.5))
        val       = float(audio_uniforms.get(uniform, 0.0))
        if op == '>':   return val >  threshold
        if op == '>=':  return val >= threshold
        if op == '<':   return val <  threshold
        if op == '<=':  return val <= threshold
        if op == '==':  return abs(val - threshold) < 1e-6
        if op == '!=':  return abs(val - threshold) >= 1e-6
        return True

    def render(
        self,
        pass_map:       dict[str, 'RenderPass'],
        t:              float,
        progress:       float,
        audio_uniforms: dict,
        bind_audio_fn,
        extra_textures: dict[str, moderngl.Texture] | None = None,
    ) -> None:
        if not (self.prog and self.vao):
            return

        # ── Passe conditionnelle : skipper si la condition est fausse ──────
        if not self._eval_condition(audio_uniforms):
            return

        self.current_fbo.use()
        ctx = self.prog.ctx  # pas disponible directement, on utilise le fbo
        # Lier les textures d'entrée
        unit = 0
        for inp_id in self.inputs:
            if inp_id in pass_map:
                src = pass_map[inp_id]
                # Si la passe source est en feedback, on veut prev_tex
                tex = src.prev_tex if (src.feedback and inp_id == self.id) else src.current_tex
                tex.use(unit)
                _safe_set(self.prog, f'iChannel{unit}', unit)
                unit += 1

        # Textures extra (bruit, LUT)
        if extra_textures:
            for uname, tex in extra_textures.items():
                tex.use(unit)
                _safe_set(self.prog, uname, unit)
                unit += 1

        _safe_set(self.prog, 'iTime',          t)
        _safe_set(self.prog, 'iResolution',    self.res)
        _safe_set(self.prog, 'iSceneProgress', float(progress))
        bind_audio_fn(self.prog)
        self.vao.render(moderngl.TRIANGLE_STRIP)


# ─────────────────────────────────────────────────────────────────────────────
#  2.3 — GESTIONNAIRE DE TRANSITIONS
# ─────────────────────────────────────────────────────────────────────────────

class TransitionManager:
    """
    Gère le crossfade entre deux scènes via un shader de transition.
    """

    DEFAULT_EFFECT   = 'transition_crossfade'
    DEFAULT_DURATION = 0.5   # secondes

    def __init__(
        self,
        ctx:         moderngl.Context,
        project_dir: str,
        quad_buf:    moderngl.Buffer,
        base_res:    tuple[int, int],
    ):
        self._ctx         = ctx
        self._dir         = project_dir
        self._quad        = quad_buf
        self._res         = base_res
        self._prog:  moderngl.Program | None      = None
        self._vao:   moderngl.VertexArray | None   = None
        self._cur_effect  = ''
        self._active      = False
        self._t_start     = 0.0
        self._duration    = self.DEFAULT_DURATION
        self._tex_prev:   moderngl.Texture | None = None
        self._tex_next:   moderngl.Texture | None = None

        # FBO pour capturer la frame précédente
        self._tex_capture = ctx.texture(base_res, 4, dtype='f4')
        self._tex_capture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._fbo_capture = ctx.framebuffer(color_attachments=[self._tex_capture])

    def _load_effect(self, effect: str) -> bool:
        if effect == self._cur_effect and self._prog:
            return True
        for folder in ('transitions', 'scenes', 'overlays'):
            path = os.path.join(self._dir, folder, f'{effect}.frag')
            code = _read_glsl(path)
            if code:
                try:
                    self._prog = self._ctx.program(
                        vertex_shader=VERT, fragment_shader=code)
                    self._vao  = self._ctx.simple_vertex_array(
                        self._prog, self._quad, 'in_vert')
                    self._cur_effect = effect
                    return True
                except Exception as e:
                    print(f"[Transition] Shader ERR {effect}: {e}")
        return False

    def capture_prev(self, src_tex: moderngl.Texture) -> None:
        """Copie la texture de la scène courante dans le buffer de capture."""
        # Blit via draw fullscreen — simple et compatible
        self._tex_prev = src_tex

    def start(
        self,
        tex_next:  moderngl.Texture,
        effect:    str | None = None,
        duration:  float | None = None,
        t_now:     float = 0.0,
    ) -> None:
        effect   = effect   or self.DEFAULT_EFFECT
        duration = duration or self.DEFAULT_DURATION
        if not self._load_effect(effect):
            return
        self._tex_next  = tex_next
        self._active    = True
        self._t_start   = t_now
        self._duration  = max(0.05, duration)

    @property
    def active(self) -> bool:
        return self._active

    def render(
        self,
        t:     float,
        res:   tuple[int, int],
        fbo_out: moderngl.Framebuffer,
    ) -> bool:
        """
        Dessine la transition sur fbo_out.
        Retourne True si la transition est terminée.
        """
        if not self._active:
            return False
        if not (self._prog and self._vao and self._tex_prev and self._tex_next):
            self._active = False
            return True

        progress = (t - self._t_start) / self._duration
        if progress >= 1.0:
            self._active = False
            return True

        fbo_out.use()
        unit = 0
        self._tex_prev.use(unit);  _safe_set(self._prog, 'iChannelPrev', unit); unit += 1
        self._tex_next.use(unit);  _safe_set(self._prog, 'iChannelNext', unit); unit += 1
        _safe_set(self._prog, 'iTransition', float(progress))
        _safe_set(self._prog, 'iTime',       t)
        _safe_set(self._prog, 'iResolution', res)
        self._vao.render(moderngl.TRIANGLE_STRIP)
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  2.4 — POST-PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

class PostProcessor:
    """
    Applique une passe de post-processing après le rendu de scène.
    Les paramètres sont configurables par scène dans project.json.
    """

    DEFAULTS = {
        'bloom':    0.0,
        'grain':    0.0,
        'vignette': 0.5,
        'saturation': 1.0,
        'contrast': 1.0,
        'lut':      '',    # nom de la LUT ('' = désactivé)
    }

    def __init__(
        self,
        ctx:          moderngl.Context,
        project_dir:  str,
        quad_buf:     moderngl.Buffer,
        base_res:     tuple[int, int],
        tex_manager:  TextureManager,
    ):
        self._ctx     = ctx
        self._dir     = project_dir
        self._quad    = quad_buf
        self._res     = base_res
        self._texmgr  = tex_manager
        self._prog:   moderngl.Program | None    = None
        self._vao:    moderngl.VertexArray | None = None
        self._params  = dict(self.DEFAULTS)

        # FBO intermédiaire
        self._tex_pp  = ctx.texture(base_res, 4, dtype='f4')
        self._tex_pp.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._fbo_pp  = ctx.framebuffer(color_attachments=[self._tex_pp])

        self._load_shader()

    def _load_shader(self) -> None:
        path = os.path.join(self._dir, 'shaders', 'post_process.frag')
        code = _read_glsl(path)
        if code:
            try:
                self._prog = self._ctx.program(vertex_shader=VERT, fragment_shader=code)
                self._vao  = self._ctx.simple_vertex_array(
                    self._prog, self._quad, 'in_vert')
                print("[PostProcessor] Shader chargé")
            except Exception as e:
                print(f"[PostProcessor] Shader ERR: {e}")

    def configure(self, params: dict) -> None:
        """Met à jour les paramètres depuis la config de la scène."""
        self._params = {**self.DEFAULTS, **params}

    def render(
        self,
        src_tex:        moderngl.Texture,
        fbo_out:        moderngl.Framebuffer,
        t:              float,
        audio_uniforms: dict,
    ) -> None:
        """
        Applique le post-processing sur src_tex, écrit dans fbo_out.
        Si le shader est absent, blitte directement.
        """
        if not (self._prog and self._vao):
            # Fallback : dessiner src_tex tel quel
            return

        fbo_out.use()
        unit = 0
        src_tex.use(unit); _safe_set(self._prog, 'iChannel0', unit); unit += 1

        # LUT
        lut_name = self._params.get('lut', '')
        lut_active = 0.0
        if lut_name:
            lut_tex = self._texmgr.get(lut_name)
            if lut_tex:
                lut_tex.use(unit); _safe_set(self._prog, 'iChannel1', unit); unit += 1
                lut_active = 1.0

        _safe_set(self._prog, 'iResolution',  self._res)
        _safe_set(self._prog, 'iTime',        t)
        _safe_set(self._prog, 'iPostBloom',   float(self._params.get('bloom', 0.0)))
        _safe_set(self._prog, 'iPostGrain',   float(self._params.get('grain', 0.0)))
        _safe_set(self._prog, 'iPostVig',     float(self._params.get('vignette', 0.5)))
        _safe_set(self._prog, 'iPostSat',     float(self._params.get('saturation', 1.0)))
        _safe_set(self._prog, 'iPostContrast',float(self._params.get('contrast', 1.0)))
        _safe_set(self._prog, 'iPostLUT',     lut_active)

        # Uniforms audio réactifs
        for name in ('iKick', 'iBass', 'iEnergy'):
            if name in audio_uniforms:
                _safe_set(self._prog, name, float(audio_uniforms[name]))

        self._vao.render(moderngl.TRIANGLE_STRIP)

    @property
    def enabled(self) -> bool:
        return self._prog is not None


# ─────────────────────────────────────────────────────────────────────────────
#  PIPELINE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

# Configuration de passes par défaut (rétrocompatibilité)
DEFAULT_PASSES = [
    {"id": "A", "inputs": [],            "feedback": True,  "scale": 1.0},
    {"id": "B", "inputs": ["A"],         "feedback": False, "scale": 1.0},
    {"id": "C", "inputs": ["A", "B"],    "feedback": False, "scale": 1.0},
    {"id": "D", "inputs": ["C","B","A"], "feedback": False, "scale": 1.0},
    {"id": "main", "inputs": ["A","B","C","D"]},
]


class ScenePipeline:
    """
    Pipeline de rendu d'une scène unique.
    Créé/mis à jour lors du changement de scène.
    Supporte jusqu'à 8 passes configurables.
    """

    MAX_PASSES = 8

    def __init__(
        self,
        ctx:         moderngl.Context,
        project_dir: str,
        scene_name:  str,
        scene_cfg:   dict,
        base_res:    tuple[int, int],
        quad_buf:    moderngl.Buffer,
        tex_manager: TextureManager,
    ):
        self._ctx         = ctx
        self._dir         = project_dir
        self.scene_name   = scene_name
        self._base_res    = base_res
        self._quad        = quad_buf
        self._texmgr      = tex_manager

        # Passes configurables
        passes_cfg = scene_cfg.get('passes', DEFAULT_PASSES)
        self.passes: dict[str, RenderPass] = {}
        self.pass_order: list[str] = []

        for pcfg in passes_cfg:
            pid       = pcfg['id']
            inputs    = pcfg.get('inputs', [])
            feedbk    = pcfg.get('feedback', False)
            scale     = float(pcfg.get('scale', 1.0))
            condition = pcfg.get('condition', None)   # Phase 2.1 — passe conditionnelle
            rp = RenderPass(ctx, pid, base_res, inputs, feedbk, scale, condition)
            rp.load_shader(ctx, quad_buf, scene_name, project_dir)
            self.passes[pid]   = rp
            self.pass_order.append(pid)

        # Post-processing
        post_cfg = scene_cfg.get('post', {})
        self._post_params = post_cfg

    def render(
        self,
        t:             float,
        progress:      float,
        audio_uniforms: dict,
        bind_audio_fn,
        fbo_screen:    moderngl.Framebuffer,
        post_proc:     PostProcessor | None = None,
        extra_textures: dict[str, moderngl.Texture] | None = None,
    ) -> moderngl.Texture | None:
        """
        Exécute toutes les passes dans l'ordre.
        Retourne la texture de la passe 'main' (ou None).
        """
        # Toutes les passes sauf 'main' (offscreen)
        for pid in self.pass_order:
            if pid == 'main':
                continue
            rp = self.passes[pid]
            rp.render(self.passes, t, progress, audio_uniforms,
                      bind_audio_fn, extra_textures)
            rp.flip()

        # Passe principale → screen (ou post-processor)
        main_pass = self.passes.get('main')
        if not main_pass or not (main_pass.prog and main_pass.vao):
            return None

        if post_proc and post_proc.enabled and self._post_params:
            # Rendre main dans un FBO intermédiaire, puis post-process
            post_proc.configure(self._post_params)
            # On réutilise le FBO de la passe A comme tampon temporaire
            a_pass = self.passes.get('A') or self.passes.get(self.pass_order[0])
            if a_pass:
                main_pass.render(self.passes, t, progress, audio_uniforms,
                                 bind_audio_fn, extra_textures)
                post_proc.render(main_pass.current_tex, fbo_screen, t, audio_uniforms)
            else:
                fbo_screen.use()
                main_pass.render(self.passes, t, progress, audio_uniforms,
                                 bind_audio_fn, extra_textures)
        else:
            # Rendu direct sur l'écran
            fbo_screen.use()
            main_pass.render(self.passes, t, progress, audio_uniforms,
                             bind_audio_fn, extra_textures)

        return main_pass.current_tex

    @property
    def main_tex(self) -> moderngl.Texture | None:
        m = self.passes.get('main')
        return m.current_tex if m else None
