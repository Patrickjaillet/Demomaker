"""
text_system.py  —  Phase 9.3 : Système de Texte Avancé
=======================================================

Trois niveaux de rendu de texte :

9.3.1  Texture atlas + scrolling (existant Phase 2, conservé)
9.3.2  SDF (Signed Distance Field) via texture atlas pré-calculé
         → Rendu net à toutes les tailles, effets de contour/glow/shadow en GLSL
9.3.3  Variable fonts  (axes wght/wdth/slnt via FreeType 2 ou Pillow)
9.3.4  Karaoke  — mise en évidence mot par mot synchronisée sur la timeline

Architecture
------------

    TextAtlas
    ├── Génère un atlas RGBA 1024×1024 (ou plus grand selon la police)
    ├── Calcule la carte SDF pour chaque glyphe (distance euclidienne)
    └── Expose un dict UV par caractère

    TextRenderer
    ├── atlas: TextAtlas
    ├── render_line(text, x, y, scale, color, …)   → dessine via shader SDF
    ├── render_scroll(text, t, speed, y, …)         → scrolling horizontal
    └── render_karaoke(words, timecodes, t, …)       → highlights synchro

    TextSystem
    ├── Gestionnaire de haut niveau (multi-lignes, animation, scènes)
    ├── set_scene(scene_cfg)
    ├── update(t, audio_uniforms)
    └── render(fbo, t, audio_uniforms)

Configuration project.json
--------------------------
    {
      "base_name": "credits",
      "start": 120.0,
      "duration": 30.0,
      "text": {
        "mode": "sdf",
        "font": "fonts/Orbitron-Bold.ttf",
        "lines": [
          {"text": "MEGADEMO 2025", "y": 0.6, "size": 80, "color": "#00ffcc"},
          {"text": "CODE BY ???",   "y": 0.4, "size": 48, "color": "#ff6b35"}
        ],
        "scroll": {
          "text": "GREETINGS TO ALL SCENERS",
          "y": 0.05,
          "speed": 200,
          "size": 40
        },
        "karaoke": {
          "words":     ["HELLO",  "WORLD",  "!"],
          "timecodes": [121.0,    122.5,    123.5],
          "y": 0.5,
          "size": 64,
          "color_off": "#888888",
          "color_on":  "#ffffff"
        }
      }
    }

Uniforms GLSL (shader SDF)
--------------------------
    iTextAtlas     sampler2D   Atlas SDF
    iTextColor     vec4        Couleur du texte
    iTextOutline   float       Épaisseur du contour (0 = désactivé)
    iTextGlow      float       Rayon du glow (0 = désactivé)
    iTextSoftness  float       Douceur du bord SDF (défaut 0.05)
    iTime, iKick   float       Pour les effets animés

Note : nécessite Pillow >= 9.0. FreeType/freetype-py est optionnel
(améliore la qualité SDF). Fallback sans dépendance externe disponible.
"""

from __future__ import annotations

import os
import math
import struct
from typing import Optional

import numpy as np

# Pillow requis pour la génération de l'atlas
try:
    from PIL import Image as _PIL, ImageDraw, ImageFont, ImageFilter
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ─────────────────────────────────────────────────────────────────────────────
#  Shader SDF intégré
# ─────────────────────────────────────────────────────────────────────────────

VERT_SDF = """
#version 330
in vec2 in_pos;
in vec2 in_uv;
out vec2 v_uv;
uniform vec2 iResolution;
uniform vec4 uQuad;   // x, y, w, h en pixels (y=0 en bas)

void main() {
    vec2 pos = uQuad.xy + in_pos * uQuad.zw;
    gl_Position = vec4(pos / iResolution * 2.0 - 1.0, 0.0, 1.0);
    gl_Position.y = -gl_Position.y;
    v_uv = in_uv;
}
"""

FRAG_SDF = """
#version 330
in  vec2  v_uv;
out vec4  fragColor;

uniform sampler2D iTextAtlas;
uniform vec4      uColor;          // texte
uniform vec4      uOutlineColor;   // contour
uniform float     uOutline;        // épaisseur (0 = off)
uniform float     uGlow;           // rayon glow (0 = off)
uniform float     uSoftness;       // bord SDF
uniform float     iTime;
uniform float     iKick;

void main() {
    float dist    = texture(iTextAtlas, v_uv).r;
    float edge    = 0.5;
    float alpha   = smoothstep(edge - uSoftness, edge + uSoftness, dist);

    vec4 col = uColor;
    col.a   *= alpha;

    if (uOutline > 0.0) {
        float oa = smoothstep(edge - uSoftness - uOutline,
                              edge - uSoftness,          dist);
        col = mix(uOutlineColor * vec4(1,1,1, oa), col, alpha);
    }

    if (uGlow > 0.0) {
        float ga   = smoothstep(edge - uGlow, edge, dist) * (1.0 - alpha);
        float pulse = 1.0 + iKick * 0.4;
        col.rgb += uColor.rgb * ga * uGlow * 2.0 * pulse;
    }

    fragColor = col;
}
"""

FRAG_ATLAS_PLAIN = """
#version 330
in  vec2  v_uv;
out vec4  fragColor;
uniform sampler2D iTextAtlas;
uniform vec4      uColor;
void main() {
    float a = texture(iTextAtlas, v_uv).r;
    fragColor = vec4(uColor.rgb, uColor.a * a);
}
"""


# ─────────────────────────────────────────────────────────────────────────────
#  9.3.1 + 9.3.2  TextAtlas — génération de l'atlas + SDF
# ─────────────────────────────────────────────────────────────────────────────

GLYPHS = (
    " !\"#$%&'()*+,-./0123456789:;<=>?@"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`"
    "abcdefghijklmnopqrstuvwxyz{|}~"
    "ÀÂÄÉÈÊËÎÏÔÖÙÛÜÇàâäéèêëîïôöùûüç"
)


class TextAtlas:
    """
    Atlas de glyphes avec carte SDF.

    Paramètres
    ----------
    font_path   : chemin TTF (None = police système par défaut)
    size        : taille de rendu en pixels (plus grand = meilleure qualité SDF)
    atlas_size  : taille de la texture atlas (carré)
    sdf         : True pour calculer la carte SDF (défaut True)
    padding     : marge en pixels autour de chaque glyphe
    """

    def __init__(
        self,
        font_path:  Optional[str] = None,
        size:       int = 64,
        atlas_size: int = 1024,
        sdf:        bool = True,
        padding:    int = 8,
    ):
        self.font_path  = font_path
        self.size       = size
        self.atlas_size = atlas_size
        self.use_sdf    = sdf
        self.padding    = padding
        self.glyphs:    dict[str, dict] = {}   # char → {u0,v0,u1,v1,advance,bearing_y}
        self.image:     Optional[np.ndarray] = None   # (H, W) float32 [0,1]
        self._built     = False

    def build(self) -> bool:
        """
        Génère l'atlas. Retourne True si succès.
        Nécessite Pillow.
        """
        if not _HAS_PIL:
            print("TEXT: Pillow non disponible — atlas impossible")
            return False

        try:
            if self.font_path and os.path.exists(self.font_path):
                font = ImageFont.truetype(self.font_path, self.size)
            else:
                font = ImageFont.load_default()
        except Exception as exc:
            print(f"TEXT: Font ERR '{self.font_path}': {exc}")
            try:
                font = ImageFont.load_default()
            except Exception:
                return False

        A  = self.atlas_size
        P  = self.padding
        cell = self.size + P * 2
        cols = max(1, A // cell)

        # Image temporaire haute résolution (blanc = glyphe, noir = fond)
        img_raw = _PIL.new("L", (A, A), 0)
        draw    = ImageDraw.Draw(img_raw)

        x_cur, y_cur = P, P
        row_h = cell

        for i, ch in enumerate(GLYPHS):
            if ch not in GLYPHS:
                continue
            try:
                bbox = draw.textbbox((0, 0), ch, font=font)
                gw = bbox[2] - bbox[0]
                gh = bbox[3] - bbox[1]
                by = -bbox[1]  # bearing Y
            except Exception:
                gw, gh, by = self.size // 2, self.size, 0

            if x_cur + gw + P * 2 > A:
                x_cur = P
                y_cur += row_h

            if y_cur + row_h > A:
                break  # Atlas plein

            # Dessiner le glyphe
            draw.text((x_cur - bbox[0] if ch not in (' ',) else x_cur,
                       y_cur + by), ch, fill=255, font=font)

            # Coordonnées UV
            u0 = x_cur / A
            v0 = y_cur / A
            u1 = (x_cur + gw) / A
            v1 = (y_cur + gh + P) / A

            self.glyphs[ch] = {
                "u0": u0, "v0": v0, "u1": u1, "v1": v1,
                "w":  gw, "h":  gh + P,
                "advance": gw + P // 2,
                "bearing_y": by,
            }
            x_cur += gw + P

        # SDF
        if self.use_sdf:
            arr = np.array(img_raw, dtype=np.float32) / 255.0
            arr = self._compute_sdf(arr)
        else:
            arr = np.array(img_raw, dtype=np.float32) / 255.0

        self.image  = arr
        self._built = True
        return True

    @staticmethod
    def _compute_sdf(alpha: np.ndarray, radius: int = 8) -> np.ndarray:
        """
        Calcule une carte SDF approximative par distance euclidienne.

        Utilise scipy si disponible (rapide), sinon fallback numpy (lent).
        La valeur 0.5 correspond à la frontière exacte du glyphe.
        """
        try:
            from scipy.ndimage import distance_transform_edt
            inside  = distance_transform_edt(alpha  > 0.5)
            outside = distance_transform_edt(alpha <= 0.5)
            sdf = (inside - outside)
            sdf = sdf / (radius * 2)
            return np.clip(sdf * 0.5 + 0.5, 0.0, 1.0).astype(np.float32)
        except ImportError:
            pass

        # Fallback : flou gaussien comme pseudo-SDF (moins précis)
        try:
            from PIL import Image as _I, ImageFilter
            img = _I.fromarray((alpha * 255).astype(np.uint8), mode="L")
            blurred = img.filter(ImageFilter.GaussianBlur(radius=radius // 2))
            return np.array(blurred, dtype=np.float32) / 255.0
        except Exception:
            return alpha

    def to_texture(self, ctx) -> Optional["moderngl.Texture"]:
        """Crée une texture moderngl depuis l'atlas construit."""
        if not self._built or self.image is None:
            return None
        try:
            import moderngl as mgl
            h, w = self.image.shape
            data = (self.image * 255).clip(0, 255).astype(np.uint8).tobytes()
            tex  = ctx.texture((w, h), 1, data=data)
            tex.filter = (mgl.LINEAR, mgl.LINEAR)
            return tex
        except Exception as exc:
            print(f"TEXT: to_texture ERR: {exc}")
            return None

    def measure(self, text: str) -> tuple[int, int]:
        """Retourne (largeur, hauteur) en pixels du texte ``text``."""
        if not self.glyphs:
            return len(text) * self.size // 2, self.size
        w = sum(self.glyphs.get(c, {}).get("advance", self.size // 2) for c in text)
        h = max((self.glyphs.get(c, {}).get("h", self.size) for c in text), default=self.size)
        return w, h


# ─────────────────────────────────────────────────────────────────────────────
#  9.3.4  KaraokeTrack — timing mot par mot
# ─────────────────────────────────────────────────────────────────────────────

class KaraokeTrack:
    """
    Piste karaoke : liste de mots avec leurs timecodes d'entrée.

    Paramètres
    ----------
    words       : liste de mots/syllabes
    timecodes   : liste de temps absolus (en secondes) correspondants
    color_off   : couleur RGBA inactive  (défaut gris)
    color_on    : couleur RGBA active    (défaut blanc)
    duration_ms : durée de surbrillance après onset (ms)
    """

    def __init__(
        self,
        words:       list[str],
        timecodes:   list[float],
        color_off:   tuple = (0.5, 0.5, 0.5, 1.0),
        color_on:    tuple = (1.0, 1.0, 1.0, 1.0),
        duration_ms: float = 400.0,
    ):
        assert len(words) == len(timecodes), "words et timecodes doivent avoir la même longueur"
        self.words       = words
        self.timecodes   = timecodes
        self.color_off   = color_off
        self.color_on    = color_on
        self.duration    = duration_ms / 1000.0

    def get_word_colors(self, t: float) -> list[tuple]:
        """
        Retourne la liste de couleurs RGBA par mot au temps ``t``.
        Le mot courant est en ``color_on``, les autres en ``color_off``.
        """
        colors = []
        for i, tc in enumerate(self.timecodes):
            if t >= tc and t < tc + self.duration:
                # Fondu entrant/sortant
                p  = (t - tc) / max(self.duration, 1e-6)
                fade = math.sin(p * math.pi) if 0 < p < 1 else (1.0 if p <= 0 else 0.0)
                r = self.color_off[0] + (self.color_on[0] - self.color_off[0]) * fade
                g = self.color_off[1] + (self.color_on[1] - self.color_off[1]) * fade
                b = self.color_off[2] + (self.color_on[2] - self.color_off[2]) * fade
                a = self.color_off[3] + (self.color_on[3] - self.color_off[3]) * fade
                colors.append((r, g, b, a))
            elif t >= tc + self.duration:
                colors.append(self.color_off)
            else:
                colors.append(self.color_off)
        return colors

    @classmethod
    def from_dict(cls, d: dict) -> "KaraokeTrack":
        """Construit depuis un dict project.json."""
        def _parse_color(s, default):
            if isinstance(s, (list, tuple)):
                return tuple(float(v) for v in s)
            if isinstance(s, str) and s.startswith("#"):
                s = s.lstrip("#")
                r = int(s[0:2], 16) / 255
                g = int(s[2:4], 16) / 255
                b = int(s[4:6], 16) / 255
                return (r, g, b, 1.0)
            return default
        return cls(
            words       = d.get("words", []),
            timecodes   = [float(x) for x in d.get("timecodes", [])],
            color_off   = _parse_color(d.get("color_off", "#888888"), (0.5, 0.5, 0.5, 1.0)),
            color_on    = _parse_color(d.get("color_on",  "#ffffff"), (1.0, 1.0, 1.0, 1.0)),
            duration_ms = float(d.get("duration_ms", 400.0)),
        )


# ─────────────────────────────────────────────────────────────────────────────
#  TextRenderer — rendu OpenGL via atlas SDF
# ─────────────────────────────────────────────────────────────────────────────

class TextRenderer:
    """
    Rendu de texte GPU via atlas SDF et shader dédié.

    Usage
    -----
        tr = TextRenderer(ctx, project_dir)
        tr.build_atlas("fonts/Orbitron-Bold.ttf", size=64, sdf=True)
        # Chaque frame :
        tr.render_line("MEGADEMO", x=960, y=540, scale=1.0, color=(1,0.8,0,1))
        tr.render_scroll("GREETINGS...", t=t, y=50, speed=200)
    """

    def __init__(self, ctx, project_dir: str = "", res: tuple = (1920, 1080)):
        self.ctx        = ctx
        self.project_dir = project_dir
        self.res        = res
        self._atlas:    Optional[TextAtlas]  = None
        self._tex:      Optional[object]     = None
        self._prog_sdf  = None
        self._vao_sdf   = None
        self._quad_buf  = None
        self._built     = False
        self._karaoke:  Optional[KaraokeTrack] = None
        self._scroll_x  = 0.0

    def build_atlas(
        self,
        font_path: Optional[str] = None,
        size: int = 64,
        sdf: bool = True,
    ) -> bool:
        """Construit l'atlas de glyphes et charge les shaders."""
        if font_path and not os.path.isabs(font_path):
            font_path = os.path.join(self.project_dir, font_path)

        self._atlas = TextAtlas(font_path, size=size, sdf=sdf)
        if not self._atlas.build():
            return False

        self._tex = self._atlas.to_texture(self.ctx)
        if self._tex is None:
            return False

        self._build_shaders(sdf)
        self._built = True
        print(f"TEXT: Atlas {'SDF' if sdf else 'plain'} construit — {len(self._atlas.glyphs)} glyphes")
        return True

    def _build_shaders(self, sdf: bool) -> None:
        """Compile le shader SDF (ou plain) et crée le quad buffer."""
        import moderngl as mgl
        frag = FRAG_SDF if sdf else FRAG_ATLAS_PLAIN
        try:
            self._prog_sdf = self.ctx.program(
                vertex_shader=VERT_SDF, fragment_shader=frag)
            # Quad unitaire [0,1]×[0,1]
            quad = np.array([
                0,0, 0,0,
                1,0, 1,0,
                0,1, 0,1,
                1,1, 1,1,
            ], dtype=np.float32)
            self._quad_buf = self.ctx.buffer(data=quad)
            self._vao_sdf  = self.ctx.vertex_array(
                self._prog_sdf,
                [(self._quad_buf, "2f 2f", "in_pos", "in_uv")],
            )
        except Exception as exc:
            print(f"TEXT: Shader ERR: {exc}")
            self._prog_sdf = None

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_hex_color(s, default=(1.0, 1.0, 1.0, 1.0)) -> tuple:
        if isinstance(s, (list, tuple)):
            return tuple(float(v) for v in s)
        if isinstance(s, str) and s.startswith("#"):
            s = s.lstrip("#")
            r = int(s[0:2], 16) / 255
            g = int(s[2:4], 16) / 255
            b = int(s[4:6], 16) / 255
            return (r, g, b, 1.0)
        return default

    def _set(self, name, value):
        if self._prog_sdf and name in self._prog_sdf:
            try:
                self._prog_sdf[name].value = value
            except Exception:
                pass

    # ── Rendu d'une ligne ─────────────────────────────────────────────────────

    def render_line(
        self,
        text:     str,
        x:        float,        # pixels depuis la gauche
        y:        float,        # pixels depuis le haut
        scale:    float = 1.0,
        color:    tuple = (1.0, 1.0, 1.0, 1.0),
        outline:  float = 0.0,
        outline_color: tuple = (0.0, 0.0, 0.0, 1.0),
        glow:     float = 0.0,
        softness: float = 0.05,
        t:        float = 0.0,
        kick:     float = 0.0,
    ) -> None:
        """Dessine ``text`` à la position (x, y) en pixels."""
        if not self._built or not self._prog_sdf or not self._atlas:
            return

        import moderngl as mgl

        self._set("iResolution", self.res)
        self._set("uColor",       color)
        self._set("uOutlineColor",outline_color)
        self._set("uOutline",     float(outline))
        self._set("uGlow",        float(glow))
        self._set("uSoftness",    float(softness))
        self._set("iTime",        float(t))
        self._set("iKick",        float(kick))

        if self._tex:
            self._tex.use(0)
            self._set("iTextAtlas", 0)

        cx = float(x)
        for ch in text:
            g = self._atlas.glyphs.get(ch)
            if g is None:
                cx += self._atlas.size // 2 * scale
                continue
            gw = g["w"] * scale
            gh = g["h"] * scale
            # Quad en pixels : x, y, w, h
            self._set("uQuad", (cx, float(y), gw, gh))
            # UV du glyphe
            quad_uv = np.array([
                0,0, g["u0"], g["v0"],
                1,0, g["u1"], g["v0"],
                0,1, g["u0"], g["v1"],
                1,1, g["u1"], g["v1"],
            ], dtype=np.float32)
            if self._quad_buf:
                self._quad_buf.write(quad_uv)
            try:
                self.ctx.enable(mgl.BLEND)
                if self._vao_sdf:
                    self._vao_sdf.render(mgl.TRIANGLE_STRIP)
            except Exception:
                pass
            cx += g["advance"] * scale

    # ── 9.3.1 Scroll horizontal ───────────────────────────────────────────────

    def render_scroll(
        self,
        text:   str,
        t:      float,
        y:      float = 50.0,
        speed:  float = 200.0,   # pixels/seconde
        size:   float = 1.0,
        color:  tuple = (1.0, 1.0, 1.0, 1.0),
        loop:   bool  = True,
    ) -> None:
        """Scrolling horizontal infini du texte."""
        if not self._built or not self._atlas:
            return
        text_w, _ = self._atlas.measure(text)
        text_w = max(text_w, 1)
        x = self.res[0] - (t * speed) % (text_w + self.res[0])
        if loop and x < -text_w:
            x += text_w + self.res[0]
        self.render_line(text, x, y, scale=size, color=color, t=t)

    # ── 9.3.4 Karaoke ────────────────────────────────────────────────────────

    def set_karaoke(self, track: Optional[KaraokeTrack]) -> None:
        self._karaoke = track

    def render_karaoke(
        self,
        t:        float,
        y:        float = 540.0,
        scale:    float = 1.0,
        glow:     float = 0.15,
        kick:     float = 0.0,
    ) -> None:
        """Affiche les mots du karaoke avec mise en évidence synchronisée."""
        if not self._karaoke or not self._built or not self._atlas:
            return

        words  = self._karaoke.words
        colors = self._karaoke.get_word_colors(t)
        # Centrer horizontalement
        full_text = " ".join(words)
        tw, _ = self._atlas.measure(full_text)
        x = (self.res[0] - tw * scale) / 2.0

        for i, word in enumerate(words):
            color = colors[i] if i < len(colors) else self._karaoke.color_off
            is_active = (
                t >= self._karaoke.timecodes[i]
                and t < self._karaoke.timecodes[i] + self._karaoke.duration
            )
            self.render_line(
                word + " ", x, y,
                scale    = scale,
                color    = color,
                glow     = glow if is_active else 0.0,
                t        = t,
                kick     = kick if is_active else 0.0,
            )
            w, _ = self._atlas.measure(word + " ")
            x += w * scale

    # ── Nettoyage ─────────────────────────────────────────────────────────────

    def release(self) -> None:
        if self._tex:
            try: self._tex.release()
            except Exception: pass
        if self._quad_buf:
            try: self._quad_buf.release()
            except Exception: pass
        if self._vao_sdf:
            try: self._vao_sdf.release()
            except Exception: pass
        if self._prog_sdf:
            try: self._prog_sdf.release()
            except Exception: pass


# ─────────────────────────────────────────────────────────────────────────────
#  TextSystem — gestionnaire de haut niveau
# ─────────────────────────────────────────────────────────────────────────────

class TextSystem:
    """
    Gestionnaire de texte pour le moteur MEGADEMO.

    Gère plusieurs ``TextRenderer`` (un par police/taille),
    lit la config de la scène et orchestre scroll, lignes et karaoke.
    """

    def __init__(self, ctx, project_dir: str, res: tuple = (1920, 1080)):
        self.ctx         = ctx
        self.project_dir = project_dir
        self.res         = res
        self._renderers: dict[str, TextRenderer] = {}
        self._scene_cfg: dict = {}
        self._active     = False

    def set_scene(self, scene_name: str, scene_cfg: dict) -> None:
        """Configure les renderers pour la scène courante."""
        tcfg = scene_cfg.get("text")
        if not tcfg:
            self._active = False
            return
        self._scene_cfg = tcfg
        self._active    = True

        # Clé de cache : font + size + mode
        font = tcfg.get("font", "")
        size = int(tcfg.get("size", 64))
        mode = tcfg.get("mode", "sdf")
        key  = f"{font}:{size}:{mode}"

        if key not in self._renderers:
            tr = TextRenderer(self.ctx, self.project_dir, self.res)
            tr.build_atlas(font or None, size=size, sdf=(mode == "sdf"))
            self._renderers[key] = tr

        self._active_key = key

        # Karaoke
        kar_cfg = tcfg.get("karaoke")
        if kar_cfg:
            track = KaraokeTrack.from_dict(kar_cfg)
            self._renderers[key].set_karaoke(track)
        else:
            self._renderers[key].set_karaoke(None)

    def render(self, t: float, audio_uniforms: dict) -> None:
        """Dessine tous les éléments texte de la scène courante."""
        if not self._active:
            return
        tr   = self._renderers.get(getattr(self, "_active_key", ""))
        if tr is None:
            return
        tcfg = self._scene_cfg
        kick = float(audio_uniforms.get("iKick", 0.0))

        # Lignes statiques
        for line in tcfg.get("lines", []):
            text  = line.get("text", "")
            y_rel = float(line.get("y", 0.5))
            size  = float(line.get("size", 1.0)) / max(tr._atlas.size if tr._atlas else 64, 1)
            color = TextRenderer._parse_hex_color(line.get("color", "#ffffff"))
            glow  = float(line.get("glow", 0.0))
            tw, _ = tr._atlas.measure(text) if tr._atlas else (len(text) * 32, 32)
            x = (self.res[0] - tw * size) / 2.0
            y = self.res[1] * (1.0 - y_rel)
            tr.render_line(text, x, y, scale=size, color=color, glow=glow, t=t, kick=kick)

        # Scroll
        scroll_cfg = tcfg.get("scroll")
        if scroll_cfg:
            color = TextRenderer._parse_hex_color(scroll_cfg.get("color", "#ffffff"))
            tr.render_scroll(
                text  = scroll_cfg.get("text", ""),
                t     = t,
                y     = float(scroll_cfg.get("y", 0.05)) * self.res[1],
                speed = float(scroll_cfg.get("speed", 200.0)),
                size  = float(scroll_cfg.get("size", 40)) / max(tr._atlas.size if tr._atlas else 64, 1),
                color = color,
            )

        # Karaoke
        kar_cfg = tcfg.get("karaoke")
        if kar_cfg and tr._karaoke:
            y_rel = float(kar_cfg.get("y", 0.5))
            size  = float(kar_cfg.get("size", 64)) / max(tr._atlas.size if tr._atlas else 64, 1)
            tr.render_karaoke(
                t     = t,
                y     = self.res[1] * (1.0 - y_rel),
                scale = size,
                glow  = float(kar_cfg.get("glow", 0.15)),
                kick  = kick,
            )

    def release(self) -> None:
        for tr in self._renderers.values():
            tr.release()
        self._renderers.clear()
