"""
viewport.py — Viewport OpenGL 800×450 intégré dans la GUI PySide6.

Points techniques importants :
- QOpenGLWidget utilise un FBO interne Qt (pas FBO 0).
  On capture son ID via ctypes/glGetIntegerv dans paintGL et on utilise
  ctx.detect_framebuffer() pour que moderngl rende dessus correctement.
- Pipeline multipass identique à system.py : passes A/B/C/D + scène + overlay.
- Les overlays sont cherchés dans overlays/ puis scenes/ (rétrocompat).
"""

import os
import sys
import ctypes
import numpy as np

from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtGui import QSurfaceFormat

import moderngl

# ── Vertex shader partagé ────────────────────────────────────────────────────
VERT = "#version 330\nin vec2 in_vert; void main(){ gl_Position=vec4(in_vert,0,1); }"

# ── Quad plein écran ─────────────────────────────────────────────────────────
QUAD = np.array([-1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0, -1.0], dtype="f4")

# ── Fond animé quand aucune scène n'est active ───────────────────────────────
FRAG_EMPTY = """
#version 330
uniform vec2  iResolution;
uniform float iTime;
out vec4 fragColor;
void main(){
    vec2 uv = gl_FragCoord.xy / iResolution;
    float gx = step(0.97, mod(uv.x * 40.0, 1.0));
    float gy = step(0.97, mod(uv.y * 22.5, 1.0));
    float grid = max(gx, gy);
    vec3 col = mix(vec3(0.04, 0.05, 0.08), vec3(0.08, 0.14, 0.22), grid * 0.5);
    float pulse = sin(iTime * 0.7) * 0.5 + 0.5;
    col += vec3(0.0, 0.25, 0.5) * 0.05 * pulse;
    // croix centrale
    vec2 c = abs(uv - 0.5);
    float cross_ = max(step(0.498, 1.0-c.x)*step(c.y, 0.003),
                       step(0.498, 1.0-c.y)*step(c.x, 0.003));
    col = mix(col, vec3(0.0, 0.5, 0.8), cross_ * 0.4);
    fragColor = vec4(col, 1.0);
}
"""

# Shader de rendu d'image : affiche iChannel0 centré/letterboxé avec fade in/out
FRAG_IMAGE = """
#version 330
uniform sampler2D iChannel0;  // image texture
uniform vec2  iResolution;    // viewport size
uniform vec2  iTexSize;       // texture original size
uniform float iLocalTime;     // temps depuis le début du bloc
uniform float iDuration;      // durée totale du bloc
uniform float iKick;
out vec4 fragColor;

void main(){
    vec2 uv = gl_FragCoord.xy / iResolution;
    vec2 screen_ar = iResolution / iResolution.y;
    vec2 tex_ar    = iTexSize    / iTexSize.y;

    // Letterbox / pillarbox : garder les proportions de l'image
    vec2 scale = tex_ar / screen_ar;
    // Fit: shrink to fit inside
    float fit = min(1.0 / scale.x, 1.0 / scale.y);
    scale *= fit;

    // Centrer
    vec2 tuv = (uv - 0.5) / scale + 0.5;

    // Hors image = transparent
    if(tuv.x < 0.0 || tuv.x > 1.0 || tuv.y < 0.0 || tuv.y > 1.0){
        fragColor = vec4(0.0);
        return;
    }

    vec4 tex = texture(iChannel0, tuv);

    // Fade in/out sur 5% de la durée
    float fade_in  = smoothstep(0.0, iDuration * 0.05, iLocalTime);
    float fade_out = smoothstep(iDuration, iDuration * 0.95, iLocalTime);
    float alpha    = tex.a * fade_in * fade_out;

    // Léger glow sur kick
    float glow = 1.0 + iKick * 0.15;

    fragColor = vec4(tex.rgb * glow, alpha);
}
"""


def _read_glsl(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return None


def _safe_set(prog, name, value):
    if prog and name in prog:
        prog[name].value = value



# ════════════════════════════════════════════════════════════════════════════
#  WIDGET OPENGL
# ════════════════════════════════════════════════════════════════════════════

class ViewportGL(QOpenGLWidget):
    """Widget OpenGL 800×450 — pipeline multipass moderngl."""

    VP_W = 800
    VP_H = 450

    def __init__(self, project_dir: str, parent=None):
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setDepthBufferSize(0)
        fmt.setStencilBufferSize(0)
        QSurfaceFormat.setDefaultFormat(fmt)

        super().__init__(parent)
        self.setFixedSize(self.VP_W, self.VP_H)

        self.project_dir = project_dir
        self._time      = 0.0
        self._kick      = 0.0
        self._audio_uniforms = {
            "iKick": 0.0, "iBass": 0.0, "iMid": 0.0,
            "iHigh": 0.0, "iBeat": 0.0, "iBPM": 120.0,
        }
        self._timeline  = []
        self._overlays  = []
        self._images    = []

        self._current_scene   = None
        self._current_overlay = None

        # Ressources GL
        self.ctx        = None
        self._ready     = False
        self._quad_buf  = None
        self._qt_fbo    = None   # FBO Qt capturé à la première frame

        # Programmes scène
        self._p_a = self._vao_a = None
        self._p_b = self._vao_b = None
        self._p_c = self._vao_c = None
        self._p_d = self._vao_d = None
        self._p_main = self._vao_main = None

        # Programme overlay
        self._p_ov  = self._vao_ov  = None

        # Programme image (rendu direct texture sur quad)
        self._p_img = self._vao_img = None

        # Programme fond vide
        self._p_empty = self._vao_empty = None

        # FBO / textures offscreen
        self._tex_a   = []
        self._fbo_a   = []
        self._fbo_idx = 0
        self._tex_b = self._fbo_b = None
        self._tex_c = self._fbo_c = None
        self._tex_d = self._fbo_d = None

        # Cache textures overlay
        self._tex_cache = {}

    # ── Taille ──────────────────────────────────────────────────────────────

    def sizeHint(self):        return QSize(self.VP_W, self.VP_H)
    def minimumSizeHint(self): return QSize(self.VP_W, self.VP_H)

    # ── API publique ─────────────────────────────────────────────────────────

    def set_time(self, t: float):
        self._time = max(0.0, t)
        self.update()

    def set_audio_uniforms(self, uniforms: dict):
        """Reçoit les uniforms audio calculés par le moteur (pour prévisualisation live)."""
        self._audio_uniforms = uniforms.copy()
        self._kick = uniforms.get("iKick", 0.0)

    def _bind_audio(self, prog):
        """Envoie tous les uniforms audio au programme GLSL."""
        if prog is None:
            return
        for name, val in self._audio_uniforms.items():
            if name in prog:
                prog[name].value = val

    def set_project(self, timeline: list, overlays: list, images: list = None):
        self._timeline        = timeline
        self._overlays        = overlays
        self._images          = images or []
        self._current_scene   = None
        self._current_overlay = None
        self.update()

    def reload(self):
        self._current_scene   = None
        self._current_overlay = None
        self._tex_cache.clear()
        self.update()

    # ── Init GL ──────────────────────────────────────────────────────────────

    def initializeGL(self):
        try:
            self.ctx = moderngl.create_context()
            self.ctx.enable(moderngl.BLEND)
            self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            self._quad_buf = self.ctx.buffer(data=QUAD)
            self._build_targets()
            self._build_empty_prog()
            self._build_image_prog()
            self._ready = True
        except Exception as e:
            print(f"[Viewport] initializeGL échoué : {e}")

    def resizeGL(self, w, h):
        pass  # taille fixe

    def _build_targets(self):
        res = (self.VP_W, self.VP_H)

        def _tex():
            t = self.ctx.texture(res, 4, dtype="f4")
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
            return t

        self._tex_a = [_tex(), _tex()]
        self._fbo_a = [self.ctx.framebuffer(color_attachments=[t])
                       for t in self._tex_a]
        self._fbo_idx = 0

        self._tex_b = _tex(); self._fbo_b = self.ctx.framebuffer(color_attachments=[self._tex_b])
        self._tex_c = _tex(); self._fbo_c = self.ctx.framebuffer(color_attachments=[self._tex_c])
        self._tex_d = _tex(); self._fbo_d = self.ctx.framebuffer(color_attachments=[self._tex_d])

    def _build_empty_prog(self):
        self._p_empty   = self.ctx.program(vertex_shader=VERT, fragment_shader=FRAG_EMPTY)
        self._vao_empty = self.ctx.simple_vertex_array(self._p_empty, self._quad_buf, "in_vert")

    def _build_image_prog(self):
        self._p_img   = self.ctx.program(vertex_shader=VERT, fragment_shader=FRAG_IMAGE)
        self._vao_img = self.ctx.simple_vertex_array(self._p_img, self._quad_buf, "in_vert")

    # ── Shaders ──────────────────────────────────────────────────────────────

    def _make_prog(self, code):
        if not code:
            return None, None
        try:
            prog = self.ctx.program(vertex_shader=VERT, fragment_shader=code)
            vao  = self.ctx.simple_vertex_array(prog, self._quad_buf, "in_vert")
            return prog, vao
        except Exception as e:
            print(f"[Viewport] Erreur compilation shader : {e}")
            return None, None

    def _load_scene(self, base_name: str):
        if base_name == self._current_scene:
            return
        print(f"[Viewport] Chargement scène : {base_name}")
        sd = os.path.join(self.project_dir, "scenes")
        
        # Libération explicite de l'ancienne VRAM
        for p in [self._p_a, self._p_b, self._p_c, self._p_d, self._p_main]:
            if p: p.release()
        for v in [self._vao_a, self._vao_b, self._vao_c, self._vao_d, self._vao_main]:
            if v: v.release()

        def _frag(prefix):
            if prefix == "scene":
                return _read_glsl(os.path.join(sd, f"scene_{base_name}.frag"))
            return _read_glsl(os.path.join(sd, f"{prefix}_{base_name}.frag"))

        self._p_a,    self._vao_a    = self._make_prog(_frag("buffer_a"))
        self._p_b,    self._vao_b    = self._make_prog(_frag("buffer_b"))
        self._p_c,    self._vao_c    = self._make_prog(_frag("buffer_c"))
        self._p_d,    self._vao_d    = self._make_prog(_frag("buffer_d"))
        self._p_main, self._vao_main = self._make_prog(_frag("scene"))
        self._current_scene = base_name

    def _load_overlay(self, effect_name: str):
        if effect_name == self._current_overlay:
            return
        # overlays/ en priorité, puis scenes/ pour rétrocompat
        code = None
        for folder in ("overlays", "scenes"):
            path = os.path.join(self.project_dir, folder, f"{effect_name}.frag")
            code = _read_glsl(path)
            if code:
                break
        self._p_ov, self._vao_ov = self._make_prog(code)
        self._current_overlay = effect_name

    def _get_texture(self, rel_path: str):
        if not rel_path:
            return None
        if rel_path in self._tex_cache:
            return self._tex_cache[rel_path]
        full = os.path.join(self.project_dir, rel_path)
        if not os.path.exists(full):
            return None
        try:
            from PIL import Image
            img  = Image.open(full).convert("RGBA")
            img  = img.transpose(Image.FLIP_TOP_BOTTOM)
            tex  = self.ctx.texture(img.size, 4, img.tobytes())
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._tex_cache[rel_path] = tex
            return tex
        except ImportError:
            print("[Viewport] Pillow non installé — images overlay désactivées. pip install Pillow")
        except Exception as e:
            print(f"[Viewport] Erreur chargement image '{rel_path}': {e}")
        return None

    # ── Helpers timeline ─────────────────────────────────────────────────────

    def _scene_at(self, t):
        for sc in self._timeline:
            s, d = sc["start"], sc["duration"]
            if s <= t < s + d:
                return sc
        return None

    def _overlay_at(self, t):
        for ov in self._overlays:
            s, d = ov["start"], ov["duration"]
            if s <= t < s + d:
                return ov
        return None

    def _image_at(self, t):
        for img in self._images:
            s, d = img["start"], img["duration"]
            if s <= t < s + d:
                return img
        return None

    # ── Rendu ────────────────────────────────────────────────────────────────

    def paintGL(self):
        if not self._ready:
            return

        # ── Capturer le FBO Qt (fait une seule fois) ──────────────────────
        if self._qt_fbo is None:
            qt_fbo_id = self.defaultFramebufferObject()
            try:
                self._qt_fbo = self.ctx.detect_framebuffer(qt_fbo_id)
            except Exception:
                # Fallback : utiliser ctx.screen (peut être FBO 0 selon le driver)
                self._qt_fbo = self.ctx.screen
            print(f"[Viewport] Qt FBO id = {qt_fbo_id}")

        t   = self._time
        res = (self.VP_W, self.VP_H)

        sc = self._scene_at(t)

        if sc is None:
            # Aucune scène → fond animé
            self._qt_fbo.use()
            self.ctx.viewport = (0, 0, *res)
            self.ctx.clear(0.04, 0.05, 0.08)
            _safe_set(self._p_empty, "iResolution", res)
            _safe_set(self._p_empty, "iTime",       t)
            self._vao_empty.render(moderngl.TRIANGLE_STRIP)
            return

        # ── Charger la scène si changement ───────────────────────────────
        self._load_scene(sc["base_name"])
        progress = (t - sc["start"]) / max(sc["duration"], 1e-6)

        # ── Passes offscreen ─────────────────────────────────────────────
        self._pass(self._p_a, self._vao_a,
                   self._fbo_a[self._fbo_idx],
                   [self._tex_a[1 - self._fbo_idx]],
                   t, progress, res)

        self._pass(self._p_b, self._vao_b,
                   self._fbo_b,
                   [self._tex_a[self._fbo_idx]],
                   t, progress, res)

        self._pass(self._p_c, self._vao_c,
                   self._fbo_c,
                   [self._tex_a[self._fbo_idx], self._tex_b],
                   t, progress, res)

        self._pass(self._p_d, self._vao_d,
                   self._fbo_d,
                   [self._tex_c, self._tex_b, self._tex_a[self._fbo_idx]],
                   t, progress, res)

        # ── Passe principale → FBO Qt ─────────────────────────────────────
        self._qt_fbo.use()
        self.ctx.viewport = (0, 0, *res)

        if self._p_main and self._vao_main:
            tex_main = self._tex_d if self._p_d else self._tex_a[self._fbo_idx]
            inputs = [tex_main, self._tex_b, self._tex_c, self._tex_d]
            for i, tex in enumerate(inputs):
                tex.use(i)
                _safe_set(self._p_main, f"iChannel{i}", i)
            _safe_set(self._p_main, "iTime",          t)
            _safe_set(self._p_main, "iResolution",    res)
            _safe_set(self._p_main, "iSceneProgress", float(progress))
            self._bind_audio(self._p_main)
            self._vao_main.render(moderngl.TRIANGLE_STRIP)
        else:
            # Pas de shader main → afficher buffer A directement
            self._qt_fbo.use()
            self.ctx.viewport = (0, 0, *res)
            self.ctx.clear(0.04, 0.05, 0.08)
            _safe_set(self._p_empty, "iResolution", res)
            _safe_set(self._p_empty, "iTime",       t)
            self._vao_empty.render(moderngl.TRIANGLE_STRIP)

        # ── Overlay ───────────────────────────────────────────────────────
        ov = self._overlay_at(t)
        if ov:
            self._render_overlay(ov, t, res)

        # ── Image track ───────────────────────────────────────────────────
        img = self._image_at(t)
        if img:
            self._render_image(img, t, res)

        self._fbo_idx = 1 - self._fbo_idx

    def _pass(self, prog, vao, fbo, inputs, t, progress, res):
        if not (prog and vao):
            return
        fbo.use()
        self.ctx.viewport = (0, 0, *res)
        for i, tex in enumerate(inputs):
            tex.use(i)
            _safe_set(prog, f"iChannel{i}", i)
        _safe_set(prog, "iTime",          t)
        _safe_set(prog, "iResolution",    res)
        _safe_set(prog, "iSceneProgress", float(progress))
        self._bind_audio(prog)
        vao.render(moderngl.TRIANGLE_STRIP)

    def _render_overlay(self, ov, t, res):
        self._load_overlay(ov.get("effect", ""))
        if not (self._p_ov and self._vao_ov):
            return
        self.ctx.enable(moderngl.BLEND)
        file_ = ov.get("file", "")
        if file_ and file_ != "SCROLL_INTERNAL":
            tex = self._get_texture(file_)
            if tex:
                tex.use(0)
                _safe_set(self._p_ov, "iChannel0", 0)
        _safe_set(self._p_ov, "iTime",      t)
        _safe_set(self._p_ov, "iResolution", res)
        self._bind_audio(self._p_ov)
        _safe_set(self._p_ov, "iLocalTime", t - ov["start"])
        _safe_set(self._p_ov, "iDuration",  ov["duration"])
        self._vao_ov.render(moderngl.TRIANGLE_STRIP)

    def _render_image(self, img, t, res):
        """Affiche une image de la piste IMAGE en overlay, centré avec letterbox."""
        if not (self._p_img and self._vao_img):
            return
        file_ = img.get("file", "")
        if not file_:
            return
        tex = self._get_texture(file_)
        if tex is None:
            return

        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        tex.use(0)
        _safe_set(self._p_img, "iChannel0",  0)
        _safe_set(self._p_img, "iResolution", res)
        _safe_set(self._p_img, "iTexSize",    (float(tex.width), float(tex.height)))
        _safe_set(self._p_img, "iLocalTime",  t - img["start"])
        _safe_set(self._p_img, "iDuration",   img["duration"])
        self._bind_audio(self._p_img)
        self._vao_img.render(moderngl.TRIANGLE_STRIP)

        # Si un effet shader est défini, l'appliquer par-dessus
        effect = img.get("effect", "")
        if effect:
            self._load_overlay(effect)
            if self._p_ov and self._vao_ov:
                tex.use(0)
                _safe_set(self._p_ov, "iChannel0",  0)
                _safe_set(self._p_ov, "iTime",       t)
                _safe_set(self._p_ov, "iResolution", res)
                self._bind_audio(self._p_ov)
                _safe_set(self._p_ov, "iLocalTime",  t - img["start"])
                _safe_set(self._p_ov, "iDuration",   img["duration"])
                self._vao_ov.render(moderngl.TRIANGLE_STRIP)


# ════════════════════════════════════════════════════════════════════════════
#  PANNEAU COMPLET  (viewport + header + footer)
# ════════════════════════════════════════════════════════════════════════════

class ViewportPanel(QWidget):
    """Conteneur du viewport GL avec barre de titre et barre de statut."""

    # Couleurs (dupliquées ici pour autonomie)
    _C_BG2    = "#161b22"
    _C_BG3    = "#21262d"
    _C_BORDER = "#30363d"
    _C_ACC    = "#00d4ff"
    _C_ACC2   = "#ff6b35"
    _C_ACC3   = "#39ff14"
    _C_ACC4   = "#c084fc"
    _C_TXTDIM = "#6e7681"
    _C_TXTHI  = "#f0f6fc"

    def __init__(self, project_dir: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{self._C_BG2};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(28)
        hdr.setStyleSheet(
            f"background:{self._C_BG3};"
            f"border-bottom:1px solid {self._C_BORDER};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 0, 8, 0)
        hl.setSpacing(6)

        lbl = QLabel("  ▣  VIEWPORT  800 × 450")
        lbl.setStyleSheet(
            f"color:{self._C_ACC};font:bold 8pt 'Courier New';"
            f"background:transparent;")
        hl.addWidget(lbl)
        hl.addStretch()

        self._scene_lbl = QLabel("no scene")
        self._scene_lbl.setStyleSheet(
            f"color:{self._C_TXTDIM};font:8pt 'Courier New';"
            f"background:transparent;")
        hl.addWidget(self._scene_lbl)

        hl.addWidget(self._vsep())

        btn = QPushButton("⟳ RELOAD")
        btn.setFixedHeight(20)
        btn.setStyleSheet(f"""
            QPushButton {{
                color:{self._C_ACC3};background:transparent;
                border:1px solid {self._C_ACC3};
                padding:1px 8px;font:bold 7pt 'Courier New';
            }}
            QPushButton:hover {{background:{self._C_BG2};}}
        """)
        btn.clicked.connect(self.reload)
        hl.addWidget(btn)
        lay.addWidget(hdr)

        # ── GL widget ─────────────────────────────────────────────────────
        self.gl = ViewportGL(project_dir, self)
        lay.addWidget(self.gl, 0, Qt.AlignCenter)

        # ── Footer ────────────────────────────────────────────────────────
        foot = QWidget()
        foot.setFixedHeight(22)
        foot.setStyleSheet(
            f"background:{self._C_BG3};"
            f"border-top:1px solid {self._C_BORDER};")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(8, 0, 8, 0)
        fl.setSpacing(12)

        self._time_lbl = QLabel("00:00.0")
        self._time_lbl.setStyleSheet(
            f"color:{self._C_ACC};font:bold 9pt 'Courier New';"
            f"background:transparent;")
        fl.addWidget(self._time_lbl)

        self._ov_lbl = QLabel("")
        self._ov_lbl.setStyleSheet(
            f"color:{self._C_ACC2};font:8pt 'Courier New';"
            f"background:transparent;")
        fl.addWidget(self._ov_lbl)

        fl.addStretch()

        info = QLabel("OpenGL 3.3  ·  ModernGL  ·  multipass")
        info.setStyleSheet(
            f"color:{self._C_TXTDIM};font:7pt 'Courier New';"
            f"background:transparent;")
        fl.addWidget(info)
        lay.addWidget(foot)

    def _vsep(self):
        f = QFrame(); f.setFrameShape(QFrame.VLine)
        f.setStyleSheet(f"color:{self._C_BORDER};"); return f

    # ── API publique ─────────────────────────────────────────────────────────

    def set_time(self, t: float):
        self.gl.set_time(t)

        # Mettre à jour header / footer
        m  = int(t) // 60
        s  = int(t) % 60
        ds = int((t * 10) % 10)
        self._time_lbl.setText(f"{m:02d}:{s:02d}.{ds}")

        sc = self.gl._scene_at(t)
        if sc:
            name = sc.get("name") or sc.get("base_name", "?")
            self._scene_lbl.setText(
                f"▶  {name}  [{sc['start']:.1f} → {sc['start']+sc['duration']:.1f}s]")
        else:
            self._scene_lbl.setText("no scene")

        ov = self.gl._overlay_at(t)
        self._ov_lbl.setText(f"OVL: {ov['name']}" if ov else "")

    def set_project(self, cfg: dict, timeline: list, overlays: list, images: list = None):
        self.gl.set_project(timeline, overlays, images or [])

    def set_project_dir(self, path: str):
        self.gl.project_dir = path
        self.reload()

    def reload(self):
        self.gl.reload()
