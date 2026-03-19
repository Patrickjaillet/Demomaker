"""
base_renderer.py  —  Phase 8 : Architecture & Performance
==========================================================

``BaseRenderer`` est la classe de base partagée par :
  - ``system.Engine``       (rendu temps-réel, contexte Pygame/OpenGL)
  - ``export_engine.ExportEngine``  (rendu headless + encodage ffmpeg)

Elle centralise toute la logique dupliquée entre ces deux classes :
  - Gestion du contexte moderngl et du quad buffer
  - Chargement / cache de textures (PNG/RGBA)
  - Compilation et cache de programmes GLSL
  - Injection des uniforms audio dans un programme
  - Chargement et gestion des shaders d'overlay
  - Helpers ``_safe_set`` / ``_read_glsl``
  - Lookup de la scène / overlay courant dans la timeline

Architecture
------------

    BaseRenderer
    ├── _ctx              moderngl.Context   (à remplir par la sous-classe)
    ├── _quad_buf         moderngl.Buffer
    ├── _prog_cache       dict[str, (prog, vao)]
    ├── _tex_cache        dict[str, moderngl.Texture]
    │
    ├── init_gl_base()    à appeler après la création de ctx
    ├── _make_prog()
    ├── _load_texture()
    ├── _get_cached_texture()
    ├── _safe_set()       staticmethod
    ├── _read_glsl()      staticmethod
    ├── _scene_at()
    ├── _overlay_at()
    ├── _bind_audio_uniforms()
    └── release_base()    libère toutes les ressources GPU

Les sous-classes appellent ``super().__init__(project_dir, cfg, timeline, overlays)``
puis créent leur propre contexte GL avant d'appeler ``self.init_gl_base(ctx)``.

Dépendances externes
--------------------
    moderngl >= 0.0.8
    numpy
    (Pillow optionnel, fallback sans PIL pour les textures PNG)
"""

from __future__ import annotations

import os
import struct
import zlib
from typing import Callable, Optional

import numpy as np
import moderngl

# ─────────────────────────────────────────────────────────────────────────────
#  GLSL commun
# ─────────────────────────────────────────────────────────────────────────────

VERT_SHADER = (
    "#version 330\n"
    "in vec2 in_vert;\n"
    "void main(){ gl_Position = vec4(in_vert, 0.0, 1.0); }\n"
)

QUAD_VERTS = np.array([-1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0, -1.0], dtype="f4")

# Uniform audio complet « vide » (toutes valeurs à zéro / 120 BPM)
EMPTY_AUDIO_UNIFORMS: dict[str, float] = {
    "iKick": 0.0, "iBass": 0.0, "iMid": 0.0, "iHigh": 0.0,
    "iBassPeak": 0.0, "iMidPeak": 0.0, "iHighPeak": 0.0,
    "iBassRMS": 0.0, "iMidRMS": 0.0, "iHighRMS": 0.0,
    "iBeat": 0.0, "iBPM": 120.0,
    "iBar": 0.0, "iBeat4": 0.0, "iSixteenth": 0.0,
    "iEnergy": 0.0, "iDrop": 0.0,
    "iStereoWidth": 0.0, "iCue": 0.0, "iSection": 0.0,
}


# ─────────────────────────────────────────────────────────────────────────────
#  BaseRenderer
# ─────────────────────────────────────────────────────────────────────────────

class BaseRenderer:
    """
    Classe de base commune à ``Engine`` et ``ExportEngine``.

    Paramètres
    ----------
    project_dir : str
        Répertoire racine du projet (contient scenes/, overlays/, …)
    cfg : dict
        Section ``config`` du ``project.json``.
    timeline : list[dict]
        Entrées de la timeline (champs ``start``, ``duration``, ``base_name``).
    overlays : list[dict]
        Entrées de la piste overlay.

    Usage typique dans une sous-classe
    ------------------------------------
    ::

        class Engine(BaseRenderer):
            def __init__(self):
                project = load_project()
                super().__init__(
                    project_dir = os.path.dirname(...),
                    cfg         = project["config"],
                    timeline    = project["timeline"],
                    overlays    = project["overlays"],
                )
                # Créer le contexte (Pygame ou standalone)
                self.ctx = moderngl.create_context()
                # Initialiser les ressources partagées
                self.init_gl_base(self.ctx)
    """

    def __init__(
        self,
        project_dir: str,
        cfg: dict,
        timeline: list,
        overlays: list,
    ) -> None:
        self.project_dir: str   = project_dir
        self.cfg:         dict  = cfg
        self.timeline:    list  = timeline
        self.overlays:    list  = overlays

        # Rempli par init_gl_base()
        self.ctx:        Optional[moderngl.Context] = None
        self._quad_buf:  Optional[moderngl.Buffer]  = None

        # Caches
        self._prog_cache: dict[str, tuple] = {}   # path → (prog, vao)
        self._tex_cache:  dict[str, moderngl.Texture] = {}

        # État courant (pour éviter les rechargements inutiles)
        self._current_overlay_name: Optional[str] = None
        self._prog_overlay:  Optional[moderngl.Program] = None
        self._vao_overlay:   Optional[moderngl.VertexArray] = None

        # Logger injectable (défaut : print)
        self._log: Callable[[str], None] = print

    # ─────────────────────────────────────────────────────────────────────────
    #  Initialisation GL
    # ─────────────────────────────────────────────────────────────────────────

    def init_gl_base(self, ctx: moderngl.Context) -> None:
        """
        Initialise les ressources GL partagées à partir d'un contexte existant.

        Doit être appelé **après** la création du contexte dans la sous-classe.

        Paramètres
        ----------
        ctx : moderngl.Context
            Contexte moderngl déjà créé (Pygame ou standalone).
        """
        self.ctx = ctx
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
        self._quad_buf = self.ctx.buffer(data=QUAD_VERTS)
        self._log("BASE: Ressources GL partagées initialisées")

    # ─────────────────────────────────────────────────────────────────────────
    #  Helpers GLSL statiques
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_set(prog: Optional[moderngl.Program], name: str, value) -> None:
        """Assigne ``value`` à l'uniform ``name`` si celui-ci existe dans ``prog``."""
        if prog is not None and name in prog:
            prog[name].value = value

    @staticmethod
    def _read_glsl(path: str) -> Optional[str]:
        """Lit un fichier GLSL et retourne son contenu, ou ``None`` si absent."""
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                return fh.read()
        return None

    # ─────────────────────────────────────────────────────────────────────────
    #  Compilation de shaders
    # ─────────────────────────────────────────────────────────────────────────

    def _make_prog(
        self, frag_code: Optional[str], vert_code: str = VERT_SHADER
    ) -> tuple[Optional[moderngl.Program], Optional[moderngl.VertexArray]]:
        """
        Compile un programme GLSL et crée un VAO quad associé.

        Paramètres
        ----------
        frag_code : str | None
            Code source du fragment shader.  Si ``None`` ou vide, retourne ``(None, None)``.
        vert_code : str
            Code source du vertex shader (défaut : ``VERT_SHADER``).

        Retourne
        --------
        (prog, vao) ou (None, None) en cas d'erreur.
        """
        if not frag_code:
            return None, None
        try:
            prog = self.ctx.program(
                vertex_shader=vert_code,
                fragment_shader=frag_code,
            )
            vao = self.ctx.simple_vertex_array(prog, self._quad_buf, "in_vert")
            return prog, vao
        except Exception as exc:
            self._log(f"SHADER COMPILE ERR: {exc}")
            return None, None

    def _get_prog(
        self, cache_key: str, frag_code: Optional[str]
    ) -> tuple[Optional[moderngl.Program], Optional[moderngl.VertexArray]]:
        """
        Version avec mise en cache par ``cache_key`` (chemin de fichier ou clé unique).

        Si le programme est déjà compilé et en cache, le retourne directement.
        """
        if cache_key in self._prog_cache:
            return self._prog_cache[cache_key]
        result = self._make_prog(frag_code)
        if result[0] is not None:
            self._prog_cache[cache_key] = result
        return result

    # ─────────────────────────────────────────────────────────────────────────
    #  Chargement de textures
    # ─────────────────────────────────────────────────────────────────────────

    def _load_texture(self, path: str) -> Optional[moderngl.Texture]:
        """
        Charge une image PNG/RGBA depuis ``path`` et retourne une texture moderngl.

        Utilise Pillow si disponible, sinon tente pygame.image.
        Retourne ``None`` si le fichier est absent ou en cas d'erreur.
        """
        if not os.path.exists(path):
            return None
        try:
            from PIL import Image as _PIL  # type: ignore
            img = _PIL.open(path).convert("RGBA")
            img = img.transpose(_PIL.FLIP_TOP_BOTTOM)
            tex = self.ctx.texture(img.size, 4, img.tobytes())
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            return tex
        except ImportError:
            pass
        except Exception as exc:
            self._log(f"TEXTURE PIL ERR '{path}': {exc}")
            return None
        # Fallback pygame
        try:
            import pygame  # type: ignore
            img = pygame.image.load(path).convert_alpha()
            img = pygame.transform.flip(img, False, True)
            tex = self.ctx.texture(img.get_size(), 4, pygame.image.tostring(img, "RGBA"))
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            return tex
        except Exception as exc:
            self._log(f"TEXTURE ERR '{path}': {exc}")
            return None

    def _get_cached_texture(self, rel_path: str) -> Optional[moderngl.Texture]:
        """
        Retourne la texture associée à ``rel_path`` (chemin relatif au projet),
        en la chargeant et la mettant en cache au premier accès.
        """
        if not rel_path:
            return None
        if rel_path not in self._tex_cache:
            full = os.path.join(self.project_dir, rel_path)
            tex = self._load_texture(full)
            if tex:
                self._tex_cache[rel_path] = tex
        return self._tex_cache.get(rel_path)

    # ─────────────────────────────────────────────────────────────────────────
    #  Lookup timeline
    # ─────────────────────────────────────────────────────────────────────────

    def _scene_at(self, t: float) -> Optional[dict]:
        """Retourne la scène active au temps ``t``, ou ``None``."""
        for sc in self.timeline:
            s, d = sc["start"], sc["duration"]
            if s <= t < s + d:
                return sc
        return None

    def _overlay_at(self, t: float) -> Optional[dict]:
        """Retourne l'overlay actif au temps ``t``, ou ``None``."""
        for ov in self.overlays:
            s, d = ov["start"], ov["duration"]
            if s <= t < s + d:
                return ov
        return None

    # ─────────────────────────────────────────────────────────────────────────
    #  Injection audio
    # ─────────────────────────────────────────────────────────────────────────

    def _bind_audio_uniforms(
        self,
        prog: Optional[moderngl.Program],
        audio_uniforms: Optional[dict] = None,
        scene_name: Optional[str] = None,
        t: Optional[float] = None,
    ) -> None:
        """
        Injecte tous les uniforms audio dans ``prog``.

        Paramètres
        ----------
        prog : moderngl.Program | None
            Programme cible.  Aucune action si ``None``.
        audio_uniforms : dict | None
            Dictionnaire ``{uniform_name: float}``.
            Si ``None``, utilise ``EMPTY_AUDIO_UNIFORMS``.
        scene_name : str | None
            Nom de la scène (pour le ParamSystem Phase 4, si disponible).
        t : float | None
            Temps courant (idem).
        """
        if prog is None:
            return
        uniforms = audio_uniforms or EMPTY_AUDIO_UNIFORMS
        for name, value in uniforms.items():
            self._safe_set(prog, name, value)
        # Hook pour les sous-classes (ex. : bind textures GPU de l'analyseur)
        self._on_bind_audio_extra(prog, uniforms, scene_name, t)

    def _on_bind_audio_extra(
        self,
        prog: moderngl.Program,
        uniforms: dict,
        scene_name: Optional[str],
        t: Optional[float],
    ) -> None:
        """
        Crochet optionnel pour lier des textures audio (iSpectrum, etc.)
        ou injecter les ``@params`` du ParamSystem.

        Surchargez cette méthode dans la sous-classe si nécessaire.
        Par défaut, ne fait rien.
        """

    # ─────────────────────────────────────────────────────────────────────────
    #  Overlay shader
    # ─────────────────────────────────────────────────────────────────────────

    def _load_overlay_shader(self, effect_name: str) -> None:
        """
        Charge (ou recharge si changement) le shader d'overlay ``effect_name``.

        Cherche dans ``overlays/`` puis ``scenes/`` du répertoire projet.
        Remplit ``self._prog_overlay`` et ``self._vao_overlay``.
        """
        if effect_name == self._current_overlay_name:
            return
        code = None
        for folder in ("overlays", "scenes"):
            path = os.path.join(self.project_dir, folder, f"{effect_name}.frag")
            code = self._read_glsl(path)
            if code:
                break
        self._prog_overlay, self._vao_overlay = self._make_prog(code)
        self._current_overlay_name = effect_name
        if self._prog_overlay is None:
            self._log(f"OVERLAY: shader '{effect_name}' introuvable ou erreur de compilation")

    # ─────────────────────────────────────────────────────────────────────────
    #  PNG sans PIL (fallback export)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _write_png_raw(path: str, arr: np.ndarray) -> None:
        """
        Écrit un fichier PNG RGB(A) **sans** dépendance Pillow.

        Paramètres
        ----------
        path : str
            Chemin de destination.
        arr : np.ndarray
            Tableau ``(H, W, 3)`` ou ``(H, W, 4)`` uint8, déjà orienté top-down.
        """
        h, w = arr.shape[:2]
        c = arr.shape[2] if arr.ndim == 3 else 3
        color_type = 2 if c == 3 else 6  # RGB ou RGBA

        def _chunk(tag: bytes, data: bytes) -> bytes:
            crc = zlib.crc32(tag + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

        raw = b"".join(b"\x00" + arr[y].tobytes() for y in range(h))
        idat = zlib.compress(raw, 9)
        with open(path, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n")
            fh.write(_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)))
            fh.write(_chunk(b"IDAT", idat))
            fh.write(_chunk(b"IEND", b""))

    # ─────────────────────────────────────────────────────────────────────────
    #  Nettoyage GPU
    # ─────────────────────────────────────────────────────────────────────────

    def release_base(self) -> None:
        """
        Libère toutes les ressources GPU gérées par ``BaseRenderer``.

        Appeler depuis la méthode ``release()`` ou ``__del__()`` de la sous-classe.
        """
        for tex in list(self._tex_cache.values()):
            try:
                tex.release()
            except Exception:
                pass
        self._tex_cache.clear()

        for prog, vao in list(self._prog_cache.values()):
            for obj in (vao, prog):
                if obj:
                    try:
                        obj.release()
                    except Exception:
                        pass
        self._prog_cache.clear()

        if self._vao_overlay:
            try:
                self._vao_overlay.release()
            except Exception:
                pass
        if self._prog_overlay:
            try:
                self._prog_overlay.release()
            except Exception:
                pass

        if self._quad_buf:
            try:
                self._quad_buf.release()
            except Exception:
                pass

        self._log("BASE: Ressources GPU libérées")

    # ─────────────────────────────────────────────────────────────────────────
    #  Résolution courante (helper)
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def resolution(self) -> tuple[int, int]:
        """Retourne ``(width, height)`` depuis ``self.cfg["RES"]``."""
        return tuple(self.cfg["RES"])  # type: ignore[return-value]
