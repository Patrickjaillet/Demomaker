"""
export_engine.py — Phase 8 : Refactorisé pour hériter de BaseRenderer

Changements Phase 8
-------------------
- ``ExportEngine`` hérite de ``BaseRenderer``
- Suppression de la duplication de ``_safe_set``, ``_read_glsl``, ``_get_texture``,
  ``_write_png_raw``, ``_scene_at``, ``_overlay_at``
- ``_make_prog`` délègue à ``BaseRenderer._make_prog``
- ``_load_overlay`` délègue à ``BaseRenderer._load_overlay_shader``
- Initialisation GL via ``self.init_gl_base(self.ctx)``

Phases précédentes inchangées
------------------------------
Phase 1.3 : Mode offline AudioAnalyzer.precompute()
Phase 7.1 : Codec H.264 / H.265 / ProRes / VP9 / PNG_seq / EXR_seq
Phase 7.4 : Queue, rapport HTML, webhook

Usage (inchangé)
-----------------
    from export_engine import ExportEngine
    eng = ExportEngine(project_dir, project_data,
                       width=1920, height=1080, fps=60,
                       on_progress=lambda f, total: ...,
                       on_log=lambda msg: ...)
    eng.run(output_path)
"""

import os
import sys
import subprocess
import numpy as np

from base_renderer import BaseRenderer, VERT_SHADER as VERT

# ─────────────────────────────────────────────────────────────────────────────
#  Shaders internes (inchangés)
# ─────────────────────────────────────────────────────────────────────────────

FRAG_BLACK = """
#version 330
out vec4 fragColor;
void main(){ fragColor = vec4(0.0, 0.0, 0.0, 1.0); }
"""

FRAG_IMAGE = """
#version 330
uniform sampler2D iChannel0;
uniform vec2  iResolution;
uniform vec2  iTexSize;
uniform float iLocalTime;
uniform float iDuration;
uniform float iKick;
out vec4 fragColor;
void main(){
    vec2 uv = gl_FragCoord.xy / iResolution;
    vec2 screen_ar = iResolution / iResolution.y;
    vec2 tex_ar    = iTexSize    / iTexSize.y;
    vec2 scale = tex_ar / screen_ar;
    float fit = min(1.0 / scale.x, 1.0 / scale.y);
    scale *= fit;
    vec2 tuv = (uv - 0.5) / scale + 0.5;
    if(tuv.x < 0.0 || tuv.x > 1.0 || tuv.y < 0.0 || tuv.y > 1.0){
        fragColor = vec4(0.0); return;
    }
    vec4 tex = texture(iChannel0, tuv);
    float fade_in  = smoothstep(0.0, iDuration * 0.05, iLocalTime);
    float fade_out = smoothstep(iDuration, iDuration * 0.95, iLocalTime);
    float alpha    = tex.a * fade_in * fade_out;
    float glow = 1.0 + iKick * 0.15;
    fragColor = vec4(tex.rgb * glow, alpha);
}
"""


# ─────────────────────────────────────────────────────────────────────────────
#  ExportEngine
# ─────────────────────────────────────────────────────────────────────────────

class ExportEngine(BaseRenderer):
    """
    Moteur d'export headless.

    Hérite de ``BaseRenderer`` (Phase 8) pour partager la logique GPU avec
    ``Engine``.
    """

    def __init__(
        self,
        project_dir: str,
        project_data: dict,
        width: int = 1920,
        height: int = 1080,
        fps: int = 60,
        on_progress=None,
        on_log=None,
        codec: str = "h264",
        crf: int = 18,
    ):
        cfg      = project_data.get("config", {})
        timeline = project_data.get("timeline", [])
        overlays = project_data.get("overlays", [])
        images   = project_data.get("images", [])

        super().__init__(
            project_dir = project_dir,
            cfg         = cfg,
            timeline    = timeline,
            overlays    = overlays,
        )

        self.images   = images
        self.width    = width
        self.height   = height
        self.fps      = fps
        self.codec    = codec   # h264 | h265 | prores | vp9 | png_seq | exr_seq
        self.crf      = crf

        self.on_progress = on_progress or (lambda f, t: None)
        self._log        = on_log or (lambda m: print(m))

        self._cancelled   = False
        self._kick        = 0.0
        self._audio_data  = None
        self._stereo_data = None
        self._audio_sr    = 44100
        self._audio_frames = None
        self._offline_mode = False

        # Programmes shaders internes (initialisés dans run())
        self._p_black = self._vao_black = None
        self._p_img   = self._vao_img   = None
        self._p_a = self._vao_a = None
        self._p_b = self._vao_b = None
        self._p_c = self._vao_c = None
        self._p_d = self._vao_d = None
        self._p_main = self._vao_main = None
        self._current_scene = None
        self._scroll_tex    = None
        self._fbo_idx       = 0

    def cancel(self):
        """Demande l'arrêt propre de l'export en cours."""
        self._cancelled = True

    # ─────────────────────────────────────────────────────────────────────────
    #  Helpers timeline supplémentaires
    # ─────────────────────────────────────────────────────────────────────────

    def _image_at(self, t: float):
        for img in self.images:
            s, d = img["start"], img["duration"]
            if s <= t < s + d:
                return img
        return None

    # ─────────────────────────────────────────────────────────────────────────
    #  Audio offline (Phase 1.3)
    # ─────────────────────────────────────────────────────────────────────────

    def _load_audio(self):
        """
        Charge l'audio et précalcule l'analyse complète (mode offline).
        Remplit ``self._audio_frames`` : list[dict] indexé par frame.
        Si ``AudioAnalyzer`` n'est pas disponible, retombe sur l'analyse simplifiée.
        """
        music_rel = self.cfg.get("MUSIC_FILE", "")
        if not music_rel:
            return
        path = os.path.join(self.project_dir, music_rel)
        if not os.path.exists(path):
            self._log(f"⚠ Audio introuvable : {path}")
            return

        try:
            import soundfile as sf
            data, self._audio_sr = sf.read(path)
            if data.ndim > 1:
                self._stereo_data = data.astype(np.float32)
                self._audio_data  = data.mean(axis=1).astype(np.float32)
            else:
                self._stereo_data = None
                self._audio_data  = data.astype(np.float32)
            self._log(
                f"♪ Audio chargé : {len(self._audio_data)} samples @ {self._audio_sr} Hz "
                f"({'stéréo' if self._stereo_data is not None else 'mono'})")
        except Exception as e:
            self._log(f"⚠ Impossible de lire l'audio : {e}")
            return

        try:
            sys.path.insert(0, self.project_dir)
            from audio_analysis import AudioAnalyzer
            import moderngl as _mgl

            self._log("♪ Précalcul audio offline (AudioAnalyzer)…")
            _ctx = _mgl.create_standalone_context()
            _analyzer = AudioAnalyzer(
                ctx            = _ctx,
                audio_data     = self._audio_data,
                stereo_data    = self._stereo_data,
                sr             = self._audio_sr,
                smoothing      = self.cfg.get("AUDIO_SMOOTHING", 0.85),
                kick_sens      = self.cfg.get("KICK_SENS", 1.5),
                bass_gain      = self.cfg.get("BASS_GAIN", 1.0),
                mid_gain       = self.cfg.get("MID_GAIN", 1.0),
                high_gain      = self.cfg.get("HIGH_GAIN", 1.0),
                beat_threshold = self.cfg.get("BEAT_THRESHOLD", 0.4),
                latency_ms     = self.cfg.get("LATENCY_MS", 0.0),
                cue_points     = self.cfg.get("CUE_POINTS", []),
            )
            duration = float(self.cfg.get("MUSIC_DURATION", 240.0))
            self._audio_frames = _analyzer.precompute(duration, float(self.fps))
            _ctx.release()
            self._log(f"♪ Précalcul terminé : {len(self._audio_frames)} frames analysées")
            self._offline_mode = True
        except Exception as e:
            self._log(f"⚠ Mode offline indisponible ({e}) — retour à l'analyse simplifiée")
            self._audio_frames = None
            self._offline_mode = False

    def _get_audio_uniforms(self, frame_idx: int) -> dict:
        """
        Retourne le dict complet des uniforms audio pour la frame ``frame_idx``.

        Mode offline  : depuis le tableau précalculé (``self._audio_frames``).
        Mode simplifié: calcule uniquement ``iKick`` (rétrocompatibilité).
        """
        if self._offline_mode and self._audio_frames:
            idx = min(frame_idx, len(self._audio_frames) - 1)
            return self._audio_frames[idx]

        if self._audio_data is not None:
            t  = frame_idx / self.fps
            si = int(t * self._audio_sr)
            if si < len(self._audio_data) - 2048:
                sample = (np.mean(np.abs(self._audio_data[si:si + 2048]))
                          * self.cfg.get("KICK_SENS", 1.5) * 15.0)
                smooth = self.cfg.get("AUDIO_SMOOTHING", 0.85)
                self._kick = self._kick * smooth + sample * (1.0 - smooth)
        return {
            "iKick": float(self._kick), "iBass": 0.0, "iMid": 0.0, "iHigh": 0.0,
            "iBassPeak": 0.0, "iMidPeak": 0.0, "iHighPeak": 0.0,
            "iBassRMS": 0.0, "iMidRMS": 0.0, "iHighRMS": 0.0,
            "iBeat": 0.0, "iBPM": 120.0, "iBar": 0.0, "iBeat4": 0.0,
            "iSixteenth": 0.0, "iEnergy": 0.0, "iDrop": 0.0,
            "iStereoWidth": 0.0, "iCue": 0.0, "iSection": 0.0,
        }

    # ─────────────────────────────────────────────────────────────────────────
    #  Chargement de scène / overlay
    # ─────────────────────────────────────────────────────────────────────────

    def _load_scene(self, base_name: str):
        """Compile les shaders de la scène ``base_name`` si elle a changé."""
        if base_name == self._current_scene:
            return
        self._log(f"  Chargement scène : {base_name}")
        sd = os.path.join(self.project_dir, "scenes")

        def _frag(prefix):
            if prefix == "scene":
                return self._read_glsl(os.path.join(sd, f"scene_{base_name}.frag"))
            return self._read_glsl(os.path.join(sd, f"{prefix}_{base_name}.frag"))

        self._p_a,    self._vao_a    = self._make_prog(_frag("buffer_a"))
        self._p_b,    self._vao_b    = self._make_prog(_frag("buffer_b"))
        self._p_c,    self._vao_c    = self._make_prog(_frag("buffer_c"))
        self._p_d,    self._vao_d    = self._make_prog(_frag("buffer_d"))
        self._p_main, self._vao_main = self._make_prog(_frag("scene"))
        self._current_scene = base_name

    def _load_overlay(self, effect_name: str):
        """Délègue à ``BaseRenderer._load_overlay_shader``."""
        self._load_overlay_shader(effect_name)

    # ─────────────────────────────────────────────────────────────────────────
    #  Passes de rendu
    # ─────────────────────────────────────────────────────────────────────────

    def _pass(self, prog, vao, fbo, inputs, t, progress, res, au):
        import moderngl as _mgl
        if not (prog and vao):
            return
        fbo.use()
        self.ctx.viewport = (0, 0, *res)
        for i, tex in enumerate(inputs):
            tex.use(i)
            self._safe_set(prog, f"iChannel{i}", i)
        self._safe_set(prog, "iTime",          t)
        self._safe_set(prog, "iResolution",    res)
        self._safe_set(prog, "iSceneProgress", float(progress))
        for k, v in au.items():
            self._safe_set(prog, k, float(v))
        vao.render(_mgl.TRIANGLE_STRIP)

    def _render_overlay(self, ov, t, fbo_out):
        import moderngl as _mgl
        self._load_overlay(ov["effect"])
        res = (self.width, self.height)
        if ov.get("file") == "SCROLL_INTERNAL":
            tex = self._scroll_tex
        else:
            tex = self._get_cached_texture(ov.get("file", ""))
        if tex and self._prog_overlay and self._vao_overlay:
            fbo_out.use()
            self.ctx.viewport = (0, 0, *res)
            self.ctx.enable(_mgl.BLEND)
            tex.use(0)
            p = self._prog_overlay
            self._safe_set(p, "iChannel0",  0)
            self._safe_set(p, "iTime",       t)
            self._safe_set(p, "iKick",       float(self._kick))
            self._safe_set(p, "iResolution", res)
            self._safe_set(p, "iLocalTime",  t - ov["start"])
            self._safe_set(p, "iDuration",   ov["duration"])
            self._vao_overlay.render(_mgl.TRIANGLE_STRIP)
            self.ctx.disable(_mgl.BLEND)

    def _render_image(self, img, t, fbo_out):
        import moderngl as _mgl
        tex = self._get_cached_texture(img.get("file", ""))
        if tex and self._p_img and self._vao_img:
            res = (self.width, self.height)
            fbo_out.use()
            self.ctx.viewport = (0, 0, *res)
            self.ctx.enable(_mgl.BLEND)
            tex.use(0)
            p = self._p_img
            self._safe_set(p, "iChannel0",   0)
            self._safe_set(p, "iResolution",  res)
            self._safe_set(p, "iTexSize",     (float(tex.width), float(tex.height)))
            self._safe_set(p, "iLocalTime",   t - img["start"])
            self._safe_set(p, "iDuration",    img["duration"])
            self._safe_set(p, "iKick",        float(self._kick))
            self._vao_img.render(_mgl.TRIANGLE_STRIP)
            self.ctx.disable(_mgl.BLEND)

    # ─────────────────────────────────────────────────────────────────────────
    #  Scroll texture
    # ─────────────────────────────────────────────────────────────────────────

    def _make_scroll_tex(self):
        text = self.cfg.get("SCROLL_TEXT", "MEGADEMO")
        try:
            from PIL import Image as PILImage, ImageDraw, ImageFont
            import moderngl as _mgl
            font_path = os.path.join(self.project_dir, "fonts", "fabric-shapes.ttf")
            try:
                font = ImageFont.truetype(font_path, 80)
            except Exception:
                font = ImageFont.load_default()
            dummy = PILImage.new("RGBA", (1, 1))
            bbox  = ImageDraw.Draw(dummy).textbbox((0, 0), text, font=font)
            w, h  = bbox[2] - bbox[0] + 40, bbox[3] - bbox[1] + 20
            img   = PILImage.new("RGBA", (max(w, 1), max(h, 1)), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((20, 10), text, font=font, fill=(255, 255, 255, 255))
            img   = img.transpose(PILImage.FLIP_TOP_BOTTOM)
            tex   = self.ctx.texture(img.size, 4, img.tobytes())
            tex.filter = (_mgl.LINEAR, _mgl.LINEAR)
            return tex
        except Exception as e:
            self._log(f"⚠ Scroll texture : {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    #  Vérification ffmpeg
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def check_ffmpeg():
        """Retourne ``(True, version_str)`` ou ``(False, message_erreur)``."""
        try:
            r = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                line = r.stdout.splitlines()[0]
                return True, line
        except FileNotFoundError:
            return False, "ffmpeg introuvable dans le PATH."
        except Exception as e:
            return False, str(e)
        return False, "ffmpeg introuvable."

    # ─────────────────────────────────────────────────────────────────────────
    #  Séquence d'images (PNG / EXR)
    # ─────────────────────────────────────────────────────────────────────────

    def _run_sequence(self, output_dir: str, total_frames: int) -> bool:
        """Export en séquence d'images PNG ou EXR frame par frame."""
        import moderngl as _mgl

        ext = ".exr" if self.codec == "exr_seq" else ".png"
        self._log(f"▶ Séquence {self.codec.upper()} → {output_dir}  ({total_frames} frames)")
        os.makedirs(output_dir, exist_ok=True)

        try:
            ctx = _mgl.create_standalone_context()
        except Exception as e:
            self._log(f"✖ Contexte OpenGL impossible : {e}")
            return False

        res = (self.width, self.height)
        fbo_out = ctx.framebuffer(color_attachments=[ctx.texture(res, 4, dtype='f4')])

        quad_buf = ctx.buffer(data=__import__('numpy').array(
            [-1, 1, -1, -1, 1, 1, 1, -1], dtype='f4'))
        self.ctx       = ctx
        self._quad_buf = quad_buf
        self.init_gl_base(ctx)

        self._load_audio()
        self._current_scene   = None
        self._current_overlay_name = None

        def _tex4():
            t = ctx.texture(res, 4, dtype='f4')
            t.filter = (_mgl.LINEAR, _mgl.LINEAR)
            return t

        tex_a  = [_tex4(), _tex4()]
        fbo_a  = [ctx.framebuffer(color_attachments=[t]) for t in tex_a]
        tex_b  = _tex4(); fbo_b = ctx.framebuffer(color_attachments=[tex_b])
        tex_c  = _tex4(); fbo_c = ctx.framebuffer(color_attachments=[tex_c])
        tex_d  = _tex4(); fbo_d = ctx.framebuffer(color_attachments=[tex_d])
        fbo_idx = 0

        p_black, vao_black = self._make_prog(
            "#version 330\nout vec4 c;void main(){c=vec4(0,0,0,1);}")

        ctx.enable(_mgl.BLEND)
        ctx.blend_func = _mgl.SRC_ALPHA, _mgl.ONE_MINUS_SRC_ALPHA

        try:
            for frame_idx in range(total_frames):
                if self._cancelled:
                    self._log("⚠ Séquence annulée.")
                    return False

                t  = frame_idx / self.fps
                au = self._get_audio_uniforms(frame_idx)
                sc = self._scene_at(t)

                if sc:
                    self._load_scene(sc["base_name"])
                    progress = (t - sc["start"]) / max(sc["duration"], 1e-6)
                    self._pass(self._p_a, self._vao_a, fbo_a[fbo_idx],
                               [tex_a[1 - fbo_idx]], t, progress, res, au)
                    self._pass(self._p_b, self._vao_b, fbo_b,
                               [tex_a[fbo_idx]], t, progress, res, au)
                    self._pass(self._p_c, self._vao_c, fbo_c,
                               [tex_a[fbo_idx], tex_b], t, progress, res, au)
                    self._pass(self._p_d, self._vao_d, fbo_d,
                               [tex_c, tex_b, tex_a[fbo_idx]], t, progress, res, au)

                    fbo_out.use()
                    ctx.viewport = (0, 0, *res)
                    ctx.disable(_mgl.BLEND)
                    if self._p_main and self._vao_main:
                        for i, tx in enumerate([tex_d, tex_b, tex_c, tex_d]):
                            tx.use(i)
                            self._safe_set(self._p_main, f'iChannel{i}', i)
                        self._safe_set(self._p_main, 'iTime',          t)
                        self._safe_set(self._p_main, 'iResolution',    res)
                        self._safe_set(self._p_main, 'iSceneProgress', float(progress))
                        for k, v in au.items():
                            self._safe_set(self._p_main, k, float(v))
                        self._vao_main.render(_mgl.TRIANGLE_STRIP)
                    elif p_black:
                        vao_black.render(_mgl.TRIANGLE_STRIP)
                    ctx.enable(_mgl.BLEND)
                else:
                    fbo_out.use()
                    ctx.viewport = (0, 0, *res)
                    ctx.disable(_mgl.BLEND)
                    if p_black:
                        vao_black.render(_mgl.TRIANGLE_STRIP)
                    ctx.enable(_mgl.BLEND)

                fbo_idx = 1 - fbo_idx

                filename = os.path.join(output_dir, f"frame_{frame_idx:05d}{ext}")
                if ext == ".png":
                    raw = fbo_out.read(components=3, alignment=1)
                    arr = __import__('numpy').frombuffer(raw, dtype='uint8').reshape(
                        self.height, self.width, 3)
                    arr = __import__('numpy').flipud(arr)
                    try:
                        from PIL import Image as _PIL
                        _PIL.fromarray(arr).save(filename)
                    except ImportError:
                        self._write_png_raw(filename, arr)
                else:
                    raw = fbo_out.read(components=4, alignment=1, dtype='f4')
                    arr = __import__('numpy').frombuffer(raw, dtype='float32').reshape(
                        self.height, self.width, 4)
                    arr = __import__('numpy').flipud(arr)
                    try:
                        import OpenEXR, Imath
                        header = OpenEXR.Header(self.width, self.height)
                        header['channels'] = {
                            'R': Imath.Channel(Imath.PixelType(Imath.PixelType.FLOAT)),
                            'G': Imath.Channel(Imath.PixelType(Imath.PixelType.FLOAT)),
                            'B': Imath.Channel(Imath.PixelType(Imath.PixelType.FLOAT)),
                        }
                        exr = OpenEXR.OutputFile(filename, header)
                        exr.writePixels({
                            'R': arr[:, :, 0].tobytes(),
                            'G': arr[:, :, 1].tobytes(),
                            'B': arr[:, :, 2].tobytes(),
                        })
                        exr.close()
                    except ImportError:
                        __import__('numpy').save(filename.replace('.exr', '.npy'), arr)
                        if frame_idx == 0:
                            self._log("⚠ OpenEXR non installé — sauvegarde en .npy")

                self.on_progress(frame_idx + 1, total_frames)

        except Exception as e:
            self._log(f"✖ Erreur séquence frame {frame_idx}: {e}")
            import traceback
            self._log(traceback.format_exc())
            return False
        finally:
            ctx.release()

        self._log(f"✔ Séquence terminée : {total_frames} fichiers dans {output_dir}")
        return True

    # ─────────────────────────────────────────────────────────────────────────
    #  Export principal
    # ─────────────────────────────────────────────────────────────────────────

    def run(self, output_path: str) -> bool:
        """Lance l'export.  Bloquant — appeler dans un ``QThread``."""
        import moderngl

        self._log("▶ Initialisation du contexte OpenGL headless…")
        try:
            self.ctx = moderngl.create_standalone_context()
        except Exception as e:
            self._log(f"✖ Impossible de créer le contexte OpenGL : {e}")
            return False

        res = (self.width, self.height)
        self._log(f"▶ Résolution : {self.width}×{self.height} @ {self.fps} fps")

        # Initialise les ressources partagées (BaseRenderer)
        self.init_gl_base(self.ctx)

        # FBO de rendu principal
        self._fbo_out = self.ctx.framebuffer(
            color_attachments=[self.ctx.texture(res, 3, dtype="f1")])

        def _tex4():
            t = self.ctx.texture(res, 4, dtype="f4")
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
            return t

        self._tex_a = [_tex4(), _tex4()]
        self._fbo_a = [self.ctx.framebuffer(color_attachments=[t]) for t in self._tex_a]
        self._tex_b = _tex4(); self._fbo_b = self.ctx.framebuffer(color_attachments=[self._tex_b])
        self._tex_c = _tex4(); self._fbo_c = self.ctx.framebuffer(color_attachments=[self._tex_c])
        self._tex_d = _tex4(); self._fbo_d = self.ctx.framebuffer(color_attachments=[self._tex_d])
        self._fbo_idx = 0

        # Programmes shaders internes
        self._p_black, self._vao_black = self._make_prog(FRAG_BLACK)
        self._p_img,   self._vao_img   = self._make_prog(FRAG_IMAGE)
        self._current_scene        = None
        self._current_overlay_name = None

        # Scroll texture
        self._scroll_tex = self._make_scroll_tex()

        # Audio
        self._load_audio()

        duration     = float(self.cfg.get("MUSIC_DURATION", 240.0))
        total_frames = int(duration * self.fps)

        music_rel  = self.cfg.get("MUSIC_FILE", "")
        music_path = os.path.join(self.project_dir, music_rel) if music_rel else None
        has_audio  = bool(music_path and os.path.exists(music_path))

        # Mode séquence
        if self.codec in ("png_seq", "exr_seq"):
            return self._run_sequence(output_path, total_frames)

        # ── Démarrage ffmpeg ──────────────────────────────────────────────────
        self._log("▶ Démarrage de ffmpeg…")

        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "pipe:0",
        ]

        if has_audio:
            cmd += ["-i", music_path,
                    "-map", "0:v", "-map", "1:a",
                    "-c:a", "aac", "-b:a", "192k", "-shortest"]
        else:
            self._log("⚠ Pas de fichier audio — export vidéo seule.")

        if self.codec == "h265":
            cmd += ["-c:v", "libx265", "-preset", "fast",
                    "-crf", str(self.crf), "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]
        elif self.codec == "prores":
            cmd += ["-c:v", "prores_ks", "-profile:v", "4444",
                    "-pix_fmt", "yuva444p10le"]
        elif self.codec == "vp9":
            cmd += ["-c:v", "libvpx-vp9", "-crf", str(self.crf),
                    "-b:v", "0", "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", "libx264", "-preset", "fast",
                    "-crf", str(self.crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"]

        cmd.append(output_path)
        self._log("  " + " ".join(cmd))

        try:
            ffmpeg_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            self._log("✖ ffmpeg non trouvé dans le PATH !")
            return False

        # ── Boucle de rendu ───────────────────────────────────────────────────
        self._log(f"▶ Rendu de {total_frames} frames…")

        ctx = self.ctx
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        try:
            for frame_idx in range(total_frames):
                if self._cancelled:
                    self._log("⚠ Export annulé.")
                    ffmpeg_proc.stdin.close()
                    ffmpeg_proc.wait()
                    return False

                t  = frame_idx / self.fps
                au = self._get_audio_uniforms(frame_idx)
                self._kick = au.get("iKick", 0.0)

                sc = self._scene_at(t)

                if sc:
                    self._load_scene(sc["base_name"])
                    progress = (t - sc["start"]) / max(sc["duration"], 1e-6)

                    self._pass(self._p_a, self._vao_a,
                               self._fbo_a[self._fbo_idx],
                               [self._tex_a[1 - self._fbo_idx]], t, progress, res, au)
                    self._pass(self._p_b, self._vao_b, self._fbo_b,
                               [self._tex_a[self._fbo_idx]], t, progress, res, au)
                    self._pass(self._p_c, self._vao_c, self._fbo_c,
                               [self._tex_a[self._fbo_idx], self._tex_b], t, progress, res, au)
                    self._pass(self._p_d, self._vao_d, self._fbo_d,
                               [self._tex_c, self._tex_b, self._tex_a[self._fbo_idx]],
                               t, progress, res, au)

                    self._fbo_out.use()
                    ctx.viewport = (0, 0, *res)
                    ctx.disable(moderngl.BLEND)

                    if self._p_main and self._vao_main:
                        tex_main = self._tex_d if self._p_d else self._tex_a[self._fbo_idx]
                        for i, tex in enumerate([tex_main, self._tex_b, self._tex_c, self._tex_d]):
                            tex.use(i)
                            self._safe_set(self._p_main, f"iChannel{i}", i)
                        self._safe_set(self._p_main, "iTime",          t)
                        self._safe_set(self._p_main, "iResolution",    res)
                        self._safe_set(self._p_main, "iKick",          float(self._kick))
                        self._safe_set(self._p_main, "iSceneProgress", float(progress))
                        self._vao_main.render(moderngl.TRIANGLE_STRIP)
                    else:
                        if self._p_black and self._vao_black:
                            self._vao_black.render(moderngl.TRIANGLE_STRIP)

                    ctx.enable(moderngl.BLEND)
                else:
                    self._fbo_out.use()
                    ctx.viewport = (0, 0, *res)
                    ctx.disable(moderngl.BLEND)
                    if self._p_black and self._vao_black:
                        self._vao_black.render(moderngl.TRIANGLE_STRIP)
                    ctx.enable(moderngl.BLEND)

                ov = self._overlay_at(t)
                if ov:
                    self._render_overlay(ov, t, self._fbo_out)

                img = self._image_at(t)
                if img:
                    self._render_image(img, t, self._fbo_out)

                self._fbo_idx = 1 - self._fbo_idx

                self._fbo_out.use()
                raw = self._fbo_out.read(components=3, alignment=1)
                arr = np.frombuffer(raw, dtype=np.uint8).reshape(self.height, self.width, 3)
                arr = np.flipud(arr)
                try:
                    ffmpeg_proc.stdin.write(arr.tobytes())
                except BrokenPipeError:
                    self._log("✖ ffmpeg a fermé le pipe (erreur d'encodage).")
                    break

                self.on_progress(frame_idx + 1, total_frames)

        except Exception as e:
            self._log(f"✖ Erreur durant le rendu : {e}")
            import traceback
            self._log(traceback.format_exc())
            ffmpeg_proc.stdin.close()
            ffmpeg_proc.wait()
            return False
        finally:
            self._log("▶ Nettoyage de la VRAM...")
            for tex in self._tex_a + [self._tex_b, self._tex_c, self._tex_d]:
                if tex:
                    try: tex.release()
                    except Exception: pass
            if self._scroll_tex:
                try: self._scroll_tex.release()
                except Exception: pass
            for fbo in self._fbo_a + [self._fbo_b, self._fbo_c, self._fbo_d, self._fbo_out]:
                if fbo:
                    try: fbo.release()
                    except Exception: pass
            for p in [self._p_a, self._p_b, self._p_c, self._p_d,
                      self._p_main, self._p_img, self._p_black]:
                if p:
                    try: p.release()
                    except Exception: pass
            self.release_base()
            ctx.release()

        self._log("▶ Finalisation ffmpeg…")
        ffmpeg_proc.stdin.close()
        _, stderr = ffmpeg_proc.communicate()
        if ffmpeg_proc.returncode != 0:
            self._log("✖ ffmpeg a retourné une erreur :")
            self._log(stderr.decode("utf-8", errors="replace")[-2000:])
            return False

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        self._log(f"✔ Export terminé : {output_path}  ({size_mb:.1f} MB)")
        return True
