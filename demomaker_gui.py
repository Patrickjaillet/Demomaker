"""
╔══════════════════════════════════════════════════════╗
║      MEGADEMO COMPOSER  —  PySide6 + PyRocket        ║
║  Sauvegarde auto dans project.json                   ║
╚══════════════════════════════════════════════════════╝
"""

import sys, os, json, time, argparse, copy, shutil, math, struct
from param_system import (
    ParamSystem, ParamDef, AutomationCurve, LFO,
    AudioModulator, MathNode, ModSlot, parse_shader_params,
    INTERP_MODES, LFO_SHAPES
)
try:
    from automation_widget import AutomationEditor
    AUTOMATION_AVAILABLE = True
except ImportError:
    AUTOMATION_AVAILABLE = False

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QPushButton, QSlider, QLineEdit, QComboBox, QTextEdit,
    QFormLayout, QMessageBox, QFileDialog,
    QSizePolicy, QFrame, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QToolButton, QTabWidget,
    QProgressBar, QCheckBox, QSpinBox, QGraphicsDropShadowEffect, QDoubleSpinBox, QMenu,
    QPlainTextEdit, QGridLayout, QAbstractItemView, QInputDialog, QStackedWidget,
)
from PySide6.QtCore  import (
    Qt, QTimer, QRect, QPoint, QSize, QSettings, Signal,
    QFileSystemWatcher, QThread, QRectF, QPointF, QUrl,
    QMimeData,
)
from PySide6.QtGui   import (
    QPainter, QColor, QPen, QBrush, QFont,
    QKeySequence, QShortcut, QPolygon, QLinearGradient,
    QRadialGradient, QPainterPath, QFontMetrics,
    QPixmap, QPalette, QSyntaxHighlighter, QTextCharFormat,
    QDrag, QDragEnterEvent, QDropEvent,
)

try:
    from rocket import Rocket
    from rocket.controllers.time import TimeController
    ROCKET_AVAILABLE = True
except ImportError:
    ROCKET_AVAILABLE = False

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtCore import QUrl
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

try:
    from viewport import ViewportPanel
    VIEWPORT_AVAILABLE = True
except ImportError:
    VIEWPORT_AVAILABLE = False

# Phase 9 — Fonctionnalités Créatives
try:
    from camera_system   import CameraSystem
    from particle_system import ParticleSystem
    from text_system     import TextSystem
    from camera_widget   import CameraTrajectoryEditor, BlenderImportDialog
    _PHASE9 = True
except ImportError as _e9:
    print(f"[Phase 9] Non disponible : {_e9}")
    _PHASE9 = False

# ════════════════════════════════════════════════════════════
#  PALETTE NEON VOID
# ════════════════════════════════════════════════════════════

PROJECT_FILE  = "project.json"
SETTINGS_FILE = "demomaker_settings.ini"

SCENE_EXTS   = {".frag", ".glsl", ".vert"}
OVERLAY_EXTS = {".frag", ".glsl"}
IMAGE_EXTS   = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
FONT_EXTS    = {".ttf", ".otf", ".woff", ".woff2"}
MUSIC_EXTS   = {".mp3", ".ogg", ".wav", ".flac", ".aac"}

DEFAULT_CONFIG = {
    "RES": [1920, 1080],
    "WINDOW_TITLE": "MEGADEMO",
    "MUSIC_FILE": "",
    "MUSIC_DURATION": 0.0,
    "SCROLL_TEXT": "",
    "KICK_SENS": 1.5,
    "AUDIO_SMOOTHING": 0.85,
    "BASS_GAIN": 1.0,
    "MID_GAIN": 1.0,
    "HIGH_GAIN": 1.0,
    "BEAT_THRESHOLD": 0.4,
    "ROWS_PER_SECOND": 8,
}

# Deep space blacks
C_BG      = QColor("#060a0f")
C_BG2     = QColor("#0b1018")
C_BG3     = QColor("#101620")
C_BG4     = QColor("#172030")
C_BORDER  = QColor("#1c2a3a")
C_BORDER2 = QColor("#243347")

# Neon accents
C_CYAN    = QColor("#00f5ff")
C_ORANGE  = QColor("#ff4500")
C_GREEN   = QColor("#00ff88")
C_PURPLE  = QColor("#bf5fff")
C_TEAL    = QColor("#00e5c8")
C_GOLD    = QColor("#ffcb47")

# Aliases
C_ACC     = C_CYAN
C_ACC2    = C_ORANGE
C_ACC3    = C_GREEN
C_ACC4    = C_PURPLE

# Text
C_TXT    = QColor("#7a9ab5")
C_TXTDIM = QColor("#2e4560")
C_TXTHI  = QColor("#cce8ff")
C_SEL    = QColor("#081828")

# Timeline
TRACK_H_SCENE   = 56
TRACK_H_OVERLAY = 36
TRACK_H_IMAGE   = 36
TRACK_H_AUDIO   = 30
RULER_H         = 32
LABEL_W         = 92

def _glow(col: QColor, alpha=40) -> QColor:
    g = QColor(col); g.setAlpha(alpha); return g

# ════════════════════════════════════════════════════════════
#  SCAN DYNAMIQUE DES RÉPERTOIRES
# ════════════════════════════════════════════════════════════

def _pretty(stem):
    for pfx in ("scene_", "overlay_", "buffer_a_", "buffer_b_",
                "buffer_c_", "buffer_d_"):
        if stem.startswith(pfx):
            stem = stem[len(pfx):]
            break
    return stem.replace("_", " ").upper()


def scan_scenes(project_dir):
    folder = os.path.join(project_dir, "scenes")
    out = []
    if not os.path.isdir(folder):
        return out
    for fn in sorted(os.listdir(folder)):
        if fn.startswith("__"):
            continue
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in SCENE_EXTS:
            continue
        if stem.startswith("scene_"):
            base = stem[len("scene_"):]
            out.append((base, _pretty(fn), fn))
    return out


def scan_overlays(project_dir):
    folder = os.path.join(project_dir, "overlays")
    out = []
    if not os.path.isdir(folder):
        return out
    for fn in sorted(os.listdir(folder)):
        if fn.startswith("__"):
            continue
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in OVERLAY_EXTS:
            continue
        out.append((stem, _pretty(fn), fn))
    return out


def scan_images(project_dir):
    folder = os.path.join(project_dir, "images")
    out = []
    if not os.path.isdir(folder):
        return out
    for fn in sorted(os.listdir(folder)):
        if os.path.splitext(fn)[1].lower() in IMAGE_EXTS:
            out.append((os.path.join("images", fn), fn))
    return out


def scan_fonts(project_dir):
    folder = os.path.join(project_dir, "fonts")
    out = []
    if not os.path.isdir(folder):
        return out
    for fn in sorted(os.listdir(folder)):
        if os.path.splitext(fn)[1].lower() in FONT_EXTS:
            out.append((os.path.join("fonts", fn), fn))
    return out


def scan_music(project_dir):
    folder = os.path.join(project_dir, "music")
    out = []
    if not os.path.isdir(folder):
        return out
    for fn in sorted(os.listdir(folder)):
        if os.path.splitext(fn)[1].lower() in MUSIC_EXTS:
            out.append((os.path.join("music", fn), fn))
    return out


def ensure_dirs(project_dir):
    for d in ("scenes", "overlays", "images", "fonts", "music"):
        os.makedirs(os.path.join(project_dir, d), exist_ok=True)


# ════════════════════════════════════════════════════════════
#  MODÈLE
# ════════════════════════════════════════════════════════════

class Block:
    _counter = 0

    def __init__(self, kind, name, start, duration, **kw):
        Block._counter += 1
        self.uid      = Block._counter
        self.kind     = kind
        self.name     = name
        self.start    = float(start)
        self.duration = float(duration)
        self.base     = kw.get("base", "")
        self.file     = kw.get("file", "")
        self.effect   = kw.get("effect", "overlay_glitch")

    def end(self):
        return self.start + self.duration

    def q_color(self):
        if self.kind == "scene":   return C_CYAN
        if self.kind == "overlay": return C_ORANGE
        if self.kind == "image":   return C_GOLD
        if self.kind == "scroll":  return C_GREEN
        return C_TEAL


def build_project_dict(scenes, overlays, scrolls, images, cfg, markers=None, cameras=None):
    markers = markers or []
    def _scene_dict(b):
        d = {"name": b.name, "base_name": b.base,
             "start": round(b.start, 3), "duration": round(b.duration, 3)}
        if getattr(b, "slip", 0.0) != 0.0:
            d["slip"] = round(b.slip, 4)
        # Phase 9 — conserver les clés particles / text / camera de la scène
        for key in ("particles", "text", "camera"):
            val = getattr(b, key, None)
            if val:
                d[key] = val
        return d
    tl = [_scene_dict(b) for b in sorted(scenes, key=lambda x: x.start)]
    ov = []
    for b in sorted(overlays, key=lambda x: x.start):
        ov.append({"name": b.name, "file": b.file, "effect": b.effect,
                   "start": round(b.start, 3), "duration": round(b.duration, 3)})
    for b in sorted(scrolls, key=lambda x: x.start):
        ov.append({"name": "Main Scrolltext", "file": "SCROLL_INTERNAL",
                   "effect": "overlay_scrolltext",
                   "start": round(b.start, 3), "duration": round(b.duration, 3)})
    imgs = [{"name": b.name, "file": b.file,
             "start": round(b.start, 3), "duration": round(b.duration, 3)}
            for b in sorted(images, key=lambda x: x.start)]
    d = {"_comment": f"project.json — MEGADEMO COMPOSER — {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "config": cfg, "timeline": tl, "overlays": ov, "images": imgs,
            "_markers": [
                {"t": m["t"], "name": m.get("name",""),
                 "color_hex": m["color"].name() if hasattr(m.get("color"), "name") else str(m.get("color",""))}
                for m in (markers or [])
            ]}
    if cameras:
        d["cameras"] = cameras
    return d


def save_to_disk(project_dir, scenes, overlays, scrolls, images, cfg, markers=None, cameras=None):
    try:
        data = build_project_dict(scenes, overlays, scrolls, images, cfg,
                                  markers=markers, cameras=cameras)
        with open(os.path.join(project_dir, PROJECT_FILE), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True, None
    except Exception as e:
        return False, str(e)


# ════════════════════════════════════════════════════════════
#  TIMELINE WIDGET  — Neon Void Edition
# ════════════════════════════════════════════════════════════

class TimelineWidget(QWidget):
    """
    Phase 3 — Timeline professionnelle
    ────────────────────────────────────
    3.1  Multi-sélection, Solo/Mute/Lock par piste, couleur personnalisable
    3.2  Opérations : multi-select, copy/paste, Alt+Drag, snap magnétique,
         trim gauche, slip edit
    3.3  Marqueurs nommés, régions de boucle/rendu, grille BPM
    3.4  Undo/Redo illimité (pattern Command)
    """

    # Signaux
    block_selected   = Signal(object)   # bloc unique (ou None)
    block_changed    = Signal()
    block_released   = Signal()
    markers_changed  = Signal()

    # ── Constantes de piste ────────────────────────────────────────────────
    _TRACK_DEFS = [
        ("SCENES",  "scene",   C_CYAN),
        ("OVERLAY", "overlay", C_ORANGE),
        ("IMAGES",  "image",   C_GOLD),
        ("AUDIO",   "audio",   C_TEAL),
        ("SCROLL",  "scroll",  C_GREEN),
    ]

    def __init__(self, app):
        super().__init__()
        self.app          = app
        self.px_per_sec   = 8
        self.offset_x     = 0
        self.playhead     = 0.0
        self.setMouseTracking(True)

        # ── 3.1 : état des pistes ────────────────────────────────────────
        # {kind: {muted, solo, locked, color}}
        self._track_state = {
            kind: {"muted": False, "solo": False, "locked": False, "color": col}
            for _, kind, col in self._TRACK_DEFS
        }

        # ── 3.2 : état de sélection ──────────────────────────────────────
        self._selection:  set   = set()     # UIDs des blocs sélectionnés
        self._hover_block = None
        self._clipboard:  list  = []        # blocs copiés (deep copies)

        # Drag
        self._drag_blocks: list  = []       # blocs en cours de drag
        self._drag_type:   str   = ""       # "move" | "resize_r" | "resize_l" | "slip"
        self._drag_offsets: dict = {}       # uid → offset initial
        self._drag_x0:     float = 0.0

        # Rubber-band selection
        self._rb_active = False
        self._rb_x0 = self._rb_y0 = 0
        self._rb_x1 = self._rb_y1 = 0

        # Snap
        self._snap_enabled = True
        self._snap_grid    = 0.25           # secondes (défaut : 1/4 s)
        self._bpm          = 120.0          # BPM pour grille musicale
        self.show_bpm_grid = True

        # ── 3.3 : marqueurs ─────────────────────────────────────────────
        self.markers:  list = []            # [{"t": float, "name": str, "color": QColor}]
        self.loop_in:  float | None = None
        self.loop_out: float | None = None
        self.render_in:  float | None = None
        self.render_out: float | None = None

        # ── 3.4 : Undo/Redo ─────────────────────────────────────────────
        self._undo_stack: list = []         # liste de snapshots JSON
        self._redo_stack: list = []
        self._undo_max   = 100

        h = RULER_H + TRACK_H_SCENE + TRACK_H_OVERLAY + TRACK_H_IMAGE + TRACK_H_AUDIO + TRACK_H_OVERLAY + 4
        self.setMinimumHeight(h)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # ── Géométrie ─────────────────────────────────────────────────────────

    def _total_w(self):
        return LABEL_W + int(self.app.cfg.get("MUSIC_DURATION", 240) * self.px_per_sec) + 200

    def t_to_x(self, t):
        return LABEL_W + int(t * self.px_per_sec) - self.offset_x

    def x_to_t(self, x):
        return max(0.0, (x - LABEL_W + self.offset_x) / self.px_per_sec)

    def _track_y(self, kind):
        base = RULER_H
        if kind == "scene":   return base, TRACK_H_SCENE
        base += TRACK_H_SCENE
        if kind == "overlay": return base, TRACK_H_OVERLAY
        base += TRACK_H_OVERLAY
        if kind == "image":   return base, TRACK_H_IMAGE
        base += TRACK_H_IMAGE
        if kind == "audio":   return base, TRACK_H_AUDIO
        base += TRACK_H_AUDIO
        return base, TRACK_H_OVERLAY

    def _all_blocks(self):
        return self.app.scenes + self.app.overlays + self.app.images + self.app.scrolls

    def _block_at(self, x, y):
        for b in reversed(self._all_blocks()):
            ty, th = self._track_y(b.kind)
            if self.t_to_x(b.start) <= x <= self.t_to_x(b.end()) and ty <= y <= ty + th:
                return b
        return None

    def _is_resize_r(self, b, x):
        return self.t_to_x(b.end()) - 10 <= x <= self.t_to_x(b.end()) + 2

    def _is_resize_l(self, b, x):
        return self.t_to_x(b.start) - 2 <= x <= self.t_to_x(b.start) + 10

    def _is_resize(self, b, x):   # rétrocompat
        return self._is_resize_r(b, x)

    # ── Accesseurs publics ────────────────────────────────────────────────

    def set_scroll(self, px):
        self.offset_x = max(0, px); self.update()

    def set_zoom(self, pps):
        self.px_per_sec = pps
        self.setFixedWidth(self._total_w()); self.update()

    def set_playhead(self, t):
        self.playhead = t; self.update()

    def set_bpm(self, bpm: float):
        self._bpm = max(1.0, bpm); self.update()

    # ── 3.4 : Undo / Redo ────────────────────────────────────────────────

    def _snapshot(self) -> dict:
        """Capture l'état complet de la timeline pour undo."""
        import copy
        return {
            "scenes":   [copy.deepcopy(b) for b in self.app.scenes],
            "overlays": [copy.deepcopy(b) for b in self.app.overlays],
            "images":   [copy.deepcopy(b) for b in self.app.images],
            "scrolls":  [copy.deepcopy(b) for b in self.app.scrolls],
            "markers":  list(self.markers),
        }

    def _restore(self, snap: dict):
        self.app.scenes   = snap["scenes"]
        self.app.overlays = snap["overlays"]
        self.app.images   = snap["images"]
        self.app.scrolls  = snap["scrolls"]
        self.markers      = snap.get("markers", [])

    def push_undo(self):
        """Appeler AVANT une opération destructive."""
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > self._undo_max:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())
        self.app.select_block(None)
        self._selection.clear()
        self.app._refresh_timeline()
        self.app.autosave()
        self.app._set_status("Undo")

    def redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())
        self.app.select_block(None)
        self._selection.clear()
        self.app._refresh_timeline()
        self.app.autosave()
        self.app._set_status("Redo")

    # ── 3.2 : Sélection ──────────────────────────────────────────────────

    def _selected_blocks(self) -> list:
        all_b = self._all_blocks()
        return [b for b in all_b if b.uid in self._selection]

    def _select_all(self):
        self._selection = {b.uid for b in self._all_blocks()}
        self.update()

    def _deselect_all(self):
        self._selection.clear()
        self.app.select_block(None)
        self.update()

    # ── 3.2 : Copy / Paste ───────────────────────────────────────────────

    def copy_selection(self):
        import copy
        sel = self._selected_blocks()
        if not sel:
            if self.app.selected:
                sel = [self.app.selected]
        self._clipboard = [copy.deepcopy(b) for b in sel]
        self.app._set_status(f"Copié : {len(self._clipboard)} bloc(s)")

    def paste_clipboard(self):
        if not self._clipboard:
            return
        import copy
        self.push_undo()
        # Décaler après la fin du dernier bloc existant du même type
        self._selection.clear()
        for b in self._clipboard:
            nb = copy.deepcopy(b)
            Block._counter += 1; nb.uid = Block._counter
            # Décalage : après la fin du dernier bloc de ce type
            lst = self._list_for_kind(nb.kind)
            if lst:
                nb.start = max(b.start, max(x.end() for x in lst)) + 0.0
            lst.append(nb)
            self._selection.add(nb.uid)
        self.app._refresh_timeline()
        self.app.autosave()
        self.app._sync_viewport()
        self.app._set_status(f"Collé : {len(self._clipboard)} bloc(s)")

    def _list_for_kind(self, kind: str) -> list:
        if kind == "scene":   return self.app.scenes
        if kind == "overlay": return self.app.overlays
        if kind == "image":   return self.app.images
        return self.app.scrolls

    # ── 3.2 : Snap ───────────────────────────────────────────────────────

    def _snap(self, t: float) -> float:
        if not self._snap_enabled:
            return round(t, 4)
        grid = self._snap_grid
        # Snap sur la grille temporelle
        snapped = round(t / grid) * grid
        # Snap sur les beats (si grille BPM activée)
        if self.show_bpm_grid and self._bpm > 0:
            beat_dur = 60.0 / self._bpm
            beat_snap = round(t / beat_dur) * beat_dur
            if abs(beat_snap - t) < abs(snapped - t):
                snapped = beat_snap
        # Snap sur les bords des autres blocs (magnétique)
        for b in self._all_blocks():
            for edge in (b.start, b.end()):
                if abs(edge - t) < (8.0 / self.px_per_sec):  # 8 pixels de tolérance
                    if abs(edge - t) < abs(snapped - t):
                        snapped = edge
        return max(0.0, snapped)

    # ── 3.3 : Marqueurs ──────────────────────────────────────────────────

    def add_marker(self, t: float, name: str = "", color: QColor = None):
        col = color or QColor(C_GOLD)
        self.markers.append({"t": t, "name": name or f"M{len(self.markers)+1}",
                             "color": col})
        self.markers.sort(key=lambda m: m["t"])
        self.markers_changed.emit()
        self.update()

    def remove_marker_at(self, t: float, tol: float = 0.2):
        self.markers = [m for m in self.markers if abs(m["t"] - t) > tol]
        self.markers_changed.emit()
        self.update()

    def next_marker(self):
        after = [m for m in self.markers if m["t"] > self.playhead + 0.01]
        if after:
            self.app._rocket_seek(after[0]["t"])

    def prev_marker(self):
        before = [m for m in self.markers if m["t"] < self.playhead - 0.01]
        if before:
            self.app._rocket_seek(before[-1]["t"])

    def set_loop(self, in_t: float | None, out_t: float | None):
        self.loop_in  = in_t
        self.loop_out = out_t
        self.update()

    def set_render_region(self, in_t: float | None, out_t: float | None):
        self.render_in  = in_t
        self.render_out = out_t
        self.update()

    def generate_beat_markers(self, bpm: float, duration: float, color: QColor = None):
        """Génère des marqueurs automatiques sur chaque beat."""
        col = color or QColor(C_TEAL)
        beat_dur = 60.0 / max(1.0, bpm)
        t = 0.0; bar = 0
        while t <= duration:
            name = f"|{bar+1}" if bar % 4 == 0 else ""
            self.markers.append({"t": round(t, 3), "name": name, "color": col})
            t += beat_dur; bar += 1
        self.markers.sort(key=lambda m: m["t"])
        self.markers_changed.emit()
        self.update()

    def clear_beat_markers(self):
        self.markers = [m for m in self.markers if m["name"] and not m["name"].startswith("|")]
        self.markers_changed.emit()
        self.update()

    # ── PAINT ────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        dur = self.app.cfg.get("MUSIC_DURATION", 240)

        # Fond
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, C_BG2); bg.setColorAt(1.0, C_BG)
        p.fillRect(0, 0, w, h, QBrush(bg))

        # ── Pistes ────────────────────────────────────────────────────────
        for _, kind, col in self._TRACK_DEFS:
            ty, th = self._track_y(kind)
            tstate = self._track_state.get(kind, {})
            tg = QLinearGradient(0, ty, 0, ty + th)
            base_col = tstate.get("color", col)
            c1 = QColor(base_col); c1.setAlpha(12 if tstate.get("muted") else 8)
            c2 = QColor(base_col); c2.setAlpha(5  if tstate.get("muted") else 3)
            tg.setColorAt(0, c1); tg.setColorAt(1, c2)
            p.fillRect(LABEL_W, ty, w - LABEL_W, th, QBrush(tg))
            sep = QColor(base_col); sep.setAlpha(30)
            p.setPen(QPen(sep, 1))
            p.drawLine(0, ty + th, w, ty + th)
            # Indicateur mute/solo/lock
            if tstate.get("muted"):
                m_c = QColor(C_ORANGE); m_c.setAlpha(60)
                p.fillRect(LABEL_W, ty, w - LABEL_W, th, m_c)

        # ── Régions loop / rendu ──────────────────────────────────────────
        self._paint_regions(p, w, h)

        # ── Grille BPM ────────────────────────────────────────────────────
        if self.show_bpm_grid and self._bpm > 0:
            self._paint_bpm_grid(p, w, h, dur)
        else:
            self._paint_beat_grid(p, w, h, dur)

        # ── Panel étiquettes (gauche) ──────────────────────────────────────
        lp = QLinearGradient(0, 0, LABEL_W, 0)
        lp.setColorAt(0, C_BG2); lp.setColorAt(1, C_BG3)
        p.fillRect(0, RULER_H, LABEL_W, h - RULER_H, QBrush(lp))
        sep_g = QLinearGradient(LABEL_W, RULER_H, LABEL_W, h)
        sep_g.setColorAt(0.0, _glow(C_CYAN, 80))
        sep_g.setColorAt(0.5, _glow(C_PURPLE, 40))
        sep_g.setColorAt(1.0, _glow(C_GREEN, 60))
        p.setPen(QPen(QBrush(sep_g), 1))
        p.drawLine(LABEL_W, RULER_H, LABEL_W, h)

        fnt_lbl = QFont("Courier New", 7, QFont.Bold)
        fnt_lbl.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        p.setFont(fnt_lbl)
        for _, kind, col in self._TRACK_DEFS:
            ty, th = self._track_y(kind)
            tstate = self._track_state.get(kind, {})
            base_col = tstate.get("color", col)
            lg = QLinearGradient(0, ty, LABEL_W, ty)
            lc = QColor(base_col); lc.setAlpha(20)
            lg.setColorAt(0, lc); lg.setColorAt(1, QColor(0,0,0,0))
            p.fillRect(0, ty, LABEL_W, th, QBrush(lg))
            ab = QColor(base_col); ab.setAlpha(200)
            p.fillRect(0, ty + 4, 3, th - 8, ab)
            p.setPen(base_col)
            lbl_parts = kind.upper()
            icons = ""
            if tstate.get("muted"):  icons += " M"
            if tstate.get("solo"):   icons += " S"
            if tstate.get("locked"): icons += " 🔒"
            p.drawText(QRect(6, ty, LABEL_W - 6, th),
                       Qt.AlignVCenter | Qt.AlignLeft, lbl_parts + icons)

        # ── Ruler ─────────────────────────────────────────────────────────
        ruler_g = QLinearGradient(0, 0, 0, RULER_H)
        ruler_g.setColorAt(0, C_BG3); ruler_g.setColorAt(1, C_BG2)
        p.fillRect(0, 0, w, RULER_H, QBrush(ruler_g))
        rl = QColor(C_CYAN); rl.setAlpha(60)
        p.setPen(QPen(rl, 1))
        p.drawLine(0, RULER_H - 1, w, RULER_H - 1)

        p.setFont(QFont("Courier New", 7))
        for s in range(0, int(dur) + 20):
            x = self.t_to_x(s)
            if x < LABEL_W or x > w: continue
            if s % 10 == 0:
                tc = QColor(C_CYAN); tc.setAlpha(180)
                p.setPen(QPen(tc, 1))
                p.drawLine(x, RULER_H - 12, x, RULER_H)
                p.setPen(C_TXTDIM)
                p.drawText(x - 16, 2, 32, RULER_H - 14, Qt.AlignCenter,
                           f"{s//60}:{s%60:02d}")
            elif s % 5 == 0:
                tc = QColor(C_BORDER2); tc.setAlpha(120)
                p.setPen(QPen(tc, 1))
                p.drawLine(x, RULER_H - 6, x, RULER_H)

        # Fond ruler gauche
        rl2 = QLinearGradient(0, 0, LABEL_W, 0)
        rl2.setColorAt(0, C_BG3); rl2.setColorAt(1, C_BG2)
        p.fillRect(0, 0, LABEL_W, RULER_H, QBrush(rl2))
        p.setFont(QFont("Courier New", 6, QFont.Bold))
        p.setPen(C_TXTDIM)
        p.drawText(QRect(0, 0, LABEL_W, RULER_H), Qt.AlignCenter, "TIME")

        # ── Blocs ─────────────────────────────────────────────────────────
        for b in self._all_blocks():
            self._paint_block(p, b)

        # ── Piste audio ───────────────────────────────────────────────────
        self._paint_audio_track(p)

        # ── Marqueurs ─────────────────────────────────────────────────────
        self._paint_markers(p, h)

        # ── Rubber-band ───────────────────────────────────────────────────
        if self._rb_active:
            rc = QColor(C_CYAN); rc.setAlpha(30)
            x0, y0 = min(self._rb_x0, self._rb_x1), min(self._rb_y0, self._rb_y1)
            rw, rh = abs(self._rb_x1 - self._rb_x0), abs(self._rb_y1 - self._rb_y0)
            p.fillRect(int(x0), int(y0), int(rw), int(rh), rc)
            rc2 = QColor(C_CYAN); rc2.setAlpha(120)
            p.setPen(QPen(rc2, 1))
            p.drawRect(int(x0), int(y0), int(rw), int(rh))

        # ── Playhead ──────────────────────────────────────────────────────
        phx = self.t_to_x(self.playhead)
        if LABEL_W <= phx <= w:
            pg = QLinearGradient(phx - 8, 0, phx + 8, 0)
            pg.setColorAt(0, QColor(0,0,0,0))
            pg.setColorAt(0.5, _glow(C_ORANGE, 30))
            pg.setColorAt(1, QColor(0,0,0,0))
            p.fillRect(phx - 8, 0, 16, h, QBrush(pg))
            p.setPen(QPen(C_ORANGE, 1))
            p.drawLine(phx, 0, phx, h)
            pts = [QPoint(phx - 7, 0), QPoint(phx + 7, 0), QPoint(phx, 13)]
            p.setBrush(QBrush(C_ORANGE)); p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygon(pts))
            p.setFont(QFont("Courier New", 8, QFont.Bold))
            p.setPen(C_ORANGE)
            mm = int(self.playhead)//60; ss = int(self.playhead)%60
            ds = int(self.playhead*10)%10
            p.drawText(phx + 10, 14, f"{mm:02d}:{ss:02d}.{ds}")
        p.end()

    def _paint_regions(self, p, w, h):
        """Dessine les régions de boucle et de rendu."""
        for region, color, label in [
            ((self.loop_in, self.loop_out),   C_GREEN,  "LOOP"),
            ((self.render_in, self.render_out), C_PURPLE, "RENDER"),
        ]:
            in_t, out_t = region
            if in_t is None or out_t is None: continue
            x1 = self.t_to_x(min(in_t, out_t))
            x2 = self.t_to_x(max(in_t, out_t))
            if x2 < LABEL_W or x1 > w: continue
            x1c = max(x1, LABEL_W)
            rc = QColor(color); rc.setAlpha(18)
            p.fillRect(int(x1c), RULER_H, int(x2 - x1c), h - RULER_H, rc)
            # Bords
            bc = QColor(color); bc.setAlpha(160)
            p.setPen(QPen(bc, 1))
            p.drawLine(max(x1, LABEL_W), RULER_H, max(x1, LABEL_W), h)
            p.drawLine(min(x2, w),       RULER_H, min(x2, w),       h)
            # Label
            p.setFont(QFont("Courier New", 7, QFont.Bold))
            p.setPen(bc)
            p.drawText(int(x1c) + 4, RULER_H + 14, label)

    def _paint_bpm_grid(self, p, w, h, dur):
        """Grille de mesures/beats calée sur le BPM."""
        if self._bpm <= 0: return
        beat_dur = 60.0 / self._bpm
        bar_dur  = beat_dur * 4
        # Barres (mesures)
        t = 0.0; bar_n = 0
        while t <= dur + bar_dur:
            x = self.t_to_x(t)
            if LABEL_W <= x <= w:
                if bar_n % 4 == 0:
                    gc = QColor("#00f5ff"); gc.setAlpha(16)
                else:
                    gc = QColor("#00f5ff"); gc.setAlpha(7)
                p.setPen(QPen(gc, 1))
                p.drawLine(x, RULER_H, x, h)
                # Numéro de mesure dans le ruler
                if bar_n % 4 == 0:
                    p.setFont(QFont("Courier New", 6))
                    nc = QColor(C_TEAL); nc.setAlpha(120)
                    p.setPen(nc)
                    p.drawText(x + 2, RULER_H - 2, f"{bar_n//4 + 1}")
            t = round(t + bar_dur, 6); bar_n += 1
        # Beats (subdivisions)
        t = 0.0
        while t <= dur + beat_dur:
            x = self.t_to_x(t)
            if LABEL_W <= x <= w:
                gc = QColor(C_BORDER); gc.setAlpha(50)
                p.setPen(QPen(gc, 1))
                p.drawLine(x, RULER_H, x, h)
            t = round(t + beat_dur, 6)

    def _paint_beat_grid(self, p, w, h, dur):
        """Grille temporelle simple (sans BPM)."""
        for s in range(0, int(dur) + 20):
            x = self.t_to_x(s)
            if x < LABEL_W or x > w: continue
            if s % 30 == 0:
                gc = QColor("#00f5ff"); gc.setAlpha(18)
            elif s % 10 == 0:
                gc = QColor("#00f5ff"); gc.setAlpha(10)
            elif s % 5 == 0:
                gc = QColor(C_BORDER); gc.setAlpha(60)
            else:
                continue
            p.setPen(QPen(gc, 1))
            p.drawLine(x, RULER_H, x, h)

    def _paint_markers(self, p, h):
        """Dessine les marqueurs nommés sur le ruler et la timeline."""
        p.setFont(QFont("Courier New", 7, QFont.Bold))
        for m in self.markers:
            x = self.t_to_x(m["t"])
            if x < LABEL_W or x > self.width(): continue
            col = m.get("color", C_GOLD)
            mc = QColor(col); mc.setAlpha(200)
            p.setPen(QPen(mc, 1))
            p.drawLine(x, 0, x, h)
            # Triangle sur le ruler
            pts = [QPoint(x - 5, 0), QPoint(x + 5, 0), QPoint(x, 10)]
            p.setBrush(QBrush(mc)); p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygon(pts))
            # Nom
            if m.get("name"):
                mc2 = QColor(col); mc2.setAlpha(180)
                p.setPen(mc2)
                p.drawText(x + 4, 18, m["name"])

    def _paint_audio_track(self, p):
        music_file = self.app.cfg.get("MUSIC_FILE", "")
        dur = self.app.cfg.get("MUSIC_DURATION", 240)
        ty, th = self._track_y("audio")
        x1 = self.t_to_x(0.0); x2 = self.t_to_x(dur)
        x1c = max(x1, LABEL_W)
        if x2 < LABEL_W or x1c > self.width() or x2 - x1c < 4: return
        ag = QLinearGradient(x1c, ty, x2, ty)
        c1 = QColor(C_TEAL); c1.setAlpha(30)
        c2 = QColor(C_TEAL); c2.setAlpha(12)
        ag.setColorAt(0, c1); ag.setColorAt(0.5, c2); ag.setColorAt(1, c1)
        p.fillRect(x1c + 1, ty + 2, x2 - x1c - 2, th - 4, QBrush(ag))
        bar_step = max(3, (x2 - x1c) // 180)
        mid = ty + th // 2
        for bx in range(x1c + 2, min(x2 - 2, self.width()), bar_step):
            phase = (bx - x1c) / max(1, x2 - x1c)
            amp = int((th - 12) / 2 * (0.35 + 0.65 * abs(
                math.sin(phase * 47.1 + bx * 0.07) *
                math.sin(phase * 23.5 + 1.2) *
                (0.5 + 0.5 * math.sin(phase * 11.3)))))
            amp = max(1, amp)
            bar_c = QColor(C_TEAL); bar_c.setAlpha(int(50 + 40 * abs(math.sin(phase*31+bx*0.05))))
            p.fillRect(bx, mid - amp, max(1, bar_step - 1), amp * 2, bar_c)
        bc = QColor(C_TEAL); bc.setAlpha(100)
        p.setPen(QPen(bc, 1))
        p.drawRoundedRect(x1c+1, ty+2, x2-x1c-2, th-4, 2, 2)
        if x2 - x1c > 80:
            p.setFont(QFont("Courier New", 7, QFont.Bold))
            lc = QColor(C_TEAL); lc.setAlpha(200)
            p.setPen(lc)
            lbl = os.path.basename(music_file) if music_file else "no audio"
            p.drawText(x1c+8, ty+2, x2-x1c-16, th-4,
                       Qt.AlignVCenter|Qt.AlignLeft, f"♪  {lbl}  [{dur:.0f}s]")

    def _paint_block(self, p, b):
        ty, th = self._track_y(b.kind)
        x1, x2 = self.t_to_x(b.start), self.t_to_x(b.end())
        if x2 < LABEL_W or x1 > self.width(): return
        x1c = max(x1, LABEL_W)
        bw  = x2 - x1c - 2
        if bw < 2: return
        tstate = self._track_state.get(b.kind, {})
        col  = tstate.get("color", b.q_color())
        sel  = (b.uid in self._selection) or (self.app.selected == b)
        hov  = (b == self._hover_block and not sel)
        muted = tstate.get("muted", False)

        bg = QLinearGradient(x1c, ty, x1c, ty + th)
        alpha_top = 70 if sel else 40 if hov else 15 if muted else 25
        alpha_bot = 35 if sel else 20 if hov else 8  if muted else 12
        c_top = QColor(col); c_top.setAlpha(alpha_top)
        c_bot = QColor(col); c_bot.setAlpha(alpha_bot)
        bg.setColorAt(0, c_top); bg.setColorAt(1, c_bot)
        path = QPainterPath()
        path.addRoundedRect(QRectF(x1c+1, ty+3, bw, th-6), 3, 3)
        p.fillPath(path, QBrush(bg))

        # Stripe gauche
        stripe = QLinearGradient(x1c+1, ty+3, x1c+1, ty+th-3)
        s1 = QColor(col); s1.setAlpha(255 if not muted else 80)
        s2 = QColor(col); s2.setAlpha(100 if not muted else 40)
        stripe.setColorAt(0, s1); stripe.setColorAt(1, s2)
        p.fillRect(x1c+1, ty+3, 3, th-6, QBrush(stripe))

        # Bordure
        bc = QColor(col); bc.setAlpha(220 if sel else 100 if hov else 55)
        p.setPen(QPen(bc, 1.5 if sel else 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(x1c+1, ty+3, bw, th-6), 3, 3)

        if sel:
            top_c = QColor(col); top_c.setAlpha(80)
            p.fillRect(x1c+4, ty+3, bw-3, 2, top_c)

        # Texte
        if bw > 20:
            fnt = QFont("Courier New", 8, QFont.Bold if sel else QFont.Normal)
            p.setFont(fnt)
            tc = QColor(C_TXTHI if sel else col)
            tc.setAlpha(100 if muted else 230 if sel else 180)
            p.setPen(tc)
            txt = b.name if b.kind != "scroll" else "▶ SCROLL"
            p.drawText(int(x1c+8), int(ty+3), int(bw-14), int(th-6),
                       Qt.AlignVCenter|Qt.AlignLeft, txt)
        if bw > 60:
            p.setFont(QFont("Courier New", 7))
            dc = QColor(col); dc.setAlpha(120)
            p.setPen(dc)
            p.drawText(int(x1c), int(ty+3), int(bw-4), int(th-6),
                       Qt.AlignVCenter|Qt.AlignRight, f"{b.duration:.1f}s")

        # Handles resize (gauche + droite)
        rh_c = QColor(col); rh_c.setAlpha(100)
        p.fillRect(int(x2-6), int(ty+6), 4, int(th-12), rh_c)       # droite
        p.fillRect(int(x1c+1), int(ty+6), 4, int(th-12), rh_c)      # gauche

    # ── Souris ────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        x, y = e.position().x(), e.position().y()
        mods = e.modifiers()

        # Clic sur le ruler → déplacer playhead / ajouter marqueur
        if y < RULER_H and x >= LABEL_W:
            t = self.x_to_t(x)
            if mods & Qt.ShiftModifier:
                self.add_marker(t)
                self.app._set_status(f"Marqueur ajouté à {t:.2f}s")
            else:
                self.playhead = t
                self.app._rocket_seek(self.playhead)
            self.update()
            return

        b = self._block_at(x, y)

        # Clic sur un bloc
        if b:
            ts = self._track_state.get(b.kind, {})
            if ts.get("locked"):
                return  # piste verrouillée

            if mods & Qt.AltModifier:
                # Alt+Drag → dupliquer
                self.push_undo()
                import copy
                nb = copy.deepcopy(b)
                Block._counter += 1; nb.uid = Block._counter
                self._list_for_kind(b.kind).append(nb)
                self._selection = {nb.uid}
                self.app.select_block(nb)
                b = nb
                self.app._refresh_timeline()
            elif mods & Qt.ShiftModifier:
                # Shift+clic → ajouter/retirer de la sélection
                if b.uid in self._selection:
                    self._selection.discard(b.uid)
                else:
                    self._selection.add(b.uid)
                self.update()
                return
            elif mods & Qt.ControlModifier:
                pass  # Ctrl seul → ne pas écraser la sélection
            else:
                if b.uid not in self._selection:
                    self._selection = {b.uid}
                self.app.select_block(b)

            # Déterminer le type de drag
            if self._is_resize_r(b, x):
                self._drag_type = "resize_r"
            elif self._is_resize_l(b, x):
                self._drag_type = "resize_l"
            elif mods & Qt.ControlModifier and mods & Qt.ShiftModifier:
                self._drag_type = "slip"
            else:
                self._drag_type = "move"

            # Calculer les offsets pour tous les blocs sélectionnés
            self._drag_blocks = self._selected_blocks() or [b]
            self._drag_offsets = {db.uid: x - self.t_to_x(db.start)
                                  for db in self._drag_blocks}
            self._drag_x0 = x
        else:
            # Clic dans le vide → rubber-band
            self._rb_active = True
            self._rb_x0 = self._rb_x1 = x
            self._rb_y0 = self._rb_y1 = y
            if not (mods & Qt.ShiftModifier):
                self._selection.clear()
                self.app.select_block(None)
        self.update()

    def mouseMoveEvent(self, e):
        x, y = e.position().x(), e.position().y()
        mods = e.modifiers()

        if self._drag_blocks:
            for b in self._drag_blocks:
                off = self._drag_offsets.get(b.uid, 0)
                if self._drag_type == "move":
                    raw = self.x_to_t(x - off)
                    b.start = self._snap(raw)
                elif self._drag_type == "resize_r":
                    raw = self.x_to_t(x + self._drag_x0 - self.t_to_x(b.end()))
                    b.duration = max(0.1, self._snap(b.start + raw) - b.start)
                elif self._drag_type == "resize_l":
                    raw    = self.x_to_t(x - off)
                    new_s  = self._snap(max(0.0, raw))
                    b.duration = max(0.1, b.end() - new_s)
                    b.start    = min(new_s, b.end() - 0.1)
                elif self._drag_type == "slip":
                    # Slip edit : décale iSceneProgress sans changer start/duration
                    delta = (x - self._drag_x0) / self.px_per_sec
                    b.slip = getattr(b, 'slip', 0.0) + delta
                    self._drag_x0 = x
            self.block_changed.emit(); self.update()

        elif self._rb_active:
            self._rb_x1 = x; self._rb_y1 = y
            # Sélectionner les blocs dans le rubber-band
            rx0 = min(self._rb_x0, x); rx1 = max(self._rb_x0, x)
            ry0 = min(self._rb_y0, y); ry1 = max(self._rb_y0, y)
            for b in self._all_blocks():
                ty, th = self._track_y(b.kind)
                bx0 = self.t_to_x(b.start); bx1 = self.t_to_x(b.end())
                if bx1 >= rx0 and bx0 <= rx1 and ty+th >= ry0 and ty <= ry1:
                    self._selection.add(b.uid)
                else:
                    self._selection.discard(b.uid)
            self.update()

        else:
            b = self._block_at(x, y)
            if b != self._hover_block:
                self._hover_block = b; self.update()
            if b:
                if self._is_resize_r(b, x) or self._is_resize_l(b, x):
                    self.setCursor(Qt.SizeHorCursor)
                else:
                    self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, e):
        if self._drag_blocks:
            self._drag_blocks = []; self._drag_type = ""; self._drag_offsets = {}
            self.block_released.emit()
        if self._rb_active:
            self._rb_active = False
            self.update()

    def mouseDoubleClickEvent(self, e):
        x, y = e.position().x(), e.position().y()
        b = self._block_at(x, y)
        if b:
            # Double-clic → ouvre le panneau de propriétés
            self.app.select_block(b)
            self.app._props.show_block(b)
        elif y < RULER_H and x >= LABEL_W:
            # Double-clic sur ruler → supprimer marqueur le plus proche
            t = self.x_to_t(x)
            self.remove_marker_at(t)

    def contextMenuEvent(self, e):
        x, y = e.position().x(), e.position().y()
        b = self._block_at(x, y)
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{C_BG2.name()};color:{C_TXT.name()};"
            f"border:1px solid {C_BORDER2.name()};font:8pt 'Courier New';padding:4px 0;}}"
            f"QMenu::item{{padding:5px 20px 5px 10px;}}"
            f"QMenu::item:selected{{background:{C_SEL.name()};color:{C_CYAN.name()};}}")
        if b:
            menu.addAction(f"✎  Propriétés",  lambda: self.app._props.show_block(b))
            menu.addAction(f"⧉  Dupliquer",    lambda: self._ctx_duplicate(b))
            menu.addAction(f"✂  Couper",       lambda: self._ctx_cut(b))
            menu.addSeparator()
            menu.addAction(f"🗑  Supprimer",    lambda: self._ctx_delete(b))
        else:
            t = self.x_to_t(x)
            menu.addAction(f"⊕  Marqueur ici ({t:.2f}s)", lambda: self.add_marker(t))
            menu.addAction(f"[  Loop In ici",    lambda: self.set_loop(t, self.loop_out))
            menu.addAction(f"]  Loop Out ici",   lambda: self.set_loop(self.loop_in, t))
            menu.addAction(f"✕  Supprimer Loop", lambda: self.set_loop(None, None))
        menu.exec(e.globalPosition().toPoint())

    def _ctx_duplicate(self, b):
        self.push_undo()
        import copy
        nb = copy.deepcopy(b); Block._counter += 1; nb.uid = Block._counter
        nb.start += nb.duration
        self._list_for_kind(b.kind).append(nb)
        self.app.select_block(nb); self.app._refresh_timeline()
        self.app.autosave(); self.app._sync_viewport()

    def _ctx_cut(self, b):
        self.push_undo()
        import copy
        self._clipboard = [copy.deepcopy(b)]
        self._list_for_kind(b.kind).remove(b)
        self.app.select_block(None); self.app._refresh_timeline()
        self.app.autosave(); self.app._sync_viewport()
        self.app._set_status(f"Coupé : {b.name}")

    def _ctx_delete(self, b):
        self.push_undo()
        self._list_for_kind(b.kind).remove(b)
        self.app.select_block(None); self.app._refresh_timeline()
        self.app.autosave(); self.app._sync_viewport()

    def sizeHint(self):
        h = RULER_H + TRACK_H_SCENE + TRACK_H_OVERLAY + TRACK_H_IMAGE + TRACK_H_AUDIO + TRACK_H_OVERLAY + 4
        return QSize(self._total_w(), h)


# ════════════════════════════════════════════════════════════
#  STYLE HELPERS
# ════════════════════════════════════════════════════════════

def _ss_edit(accent=None):
    c = (accent or C_CYAN).name()
    return (
        f"QLineEdit,QSpinBox,QComboBox{{"
        f"background:{C_BG3.name()};color:{C_TXTHI.name()};"
        f"border:1px solid {C_BORDER2.name()};"
        f"border-radius:3px;padding:4px 8px;"
        f"font:9pt 'Courier New';}}"
        f"QLineEdit:focus,QSpinBox:focus,QComboBox:focus{{"
        f"border:1px solid {c};background:{C_BG4.name()};}}"
        f"QComboBox QAbstractItemView{{"
        f"background:{C_BG3.name()};color:{C_TXTHI.name()};"
        f"selection-background-color:{C_SEL.name()};"
        f"border:1px solid {C_BORDER2.name()};}}"
        f"QSpinBox::up-button,QSpinBox::down-button{{"
        f"background:{C_BG4.name()};border:none;width:16px;}}"
    )

def _ss_btn(col, bg=None):
    c = col.name() if hasattr(col,'name') else col
    b = (bg or C_BG3).name()
    return (
        f"QPushButton{{background:{b};color:{c};"
        f"border:1px solid {c}30;border-radius:4px;"
        f"padding:6px 14px;font:bold 8pt 'Courier New';}}"
        f"QPushButton:hover{{background:{c}18;"
        f"border:1px solid {c}80;}}"
        f"QPushButton:pressed{{background:{c}30;}}"
        f"QPushButton:disabled{{color:{C_TXTDIM.name()};"
        f"border-color:{C_BORDER.name()};}}"
    )

def _ss_list(accent=None):
    c = (accent or C_CYAN).name()
    return (
        f"QListWidget{{background:{C_BG.name()};"
        f"border:1px solid {C_BORDER.name()};"
        f"border-radius:4px;"
        f"color:{C_TXTHI.name()};font:8pt 'Courier New';}}"
        f"QListWidget::item{{padding:5px 8px;"
        f"border-bottom:1px solid {C_BG3.name()};}}"
        f"QListWidget::item:hover{{background:{C_BG3.name()};}}"
        f"QListWidget::item:selected{{"
        f"background:{C_SEL.name()};color:{c};"
        f"border-left:3px solid {c};}}"
    )

def _ss_scroll():
    return (
        f"QScrollBar:vertical{{background:{C_BG2.name()};"
        f"width:6px;border:none;border-radius:3px;}}"
        f"QScrollBar::handle:vertical{{background:{C_BORDER2.name()};"
        f"border-radius:3px;min-height:20px;}}"
        f"QScrollBar::handle:vertical:hover{{background:{C_CYAN.name()}40;}}"
        f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}"
    )


class GlowLabel(QLabel):
    """Label avec effet glow coloré."""
    def __init__(self, text, color=None, size=9, bold=False, parent=None):
        super().__init__(text, parent)
        c = color or C_CYAN
        w = "bold " if bold else ""
        self.setStyleSheet(
            f"color:{c.name()};font:{w}{size}pt \'Courier New\';"
            f"padding:2px 4px;background:transparent;")


class NeonButton(QPushButton):
    """Bouton avec style neon glow."""
    def __init__(self, text, color=None, parent=None):
        super().__init__(text, parent)
        self._col = color or C_CYAN
        self._update_style()

    def _update_style(self):
        c = self._col.name()
        self.setStyleSheet(
            f"QPushButton{{background:{C_BG3.name()};color:{c};"
            f"border:1px solid {c}50;border-radius:4px;"
            f"padding:5px 12px;font:bold 8pt \'Courier New\';}}"
            f"QPushButton:hover{{background:{c}20;"
            f"border:1px solid {c}cc;}}"
            f"QPushButton:pressed{{background:{c}35;}}")

    def set_color(self, col):
        self._col = col; self._update_style()


class SectionHeader(QWidget):
    """En-tête de section avec ligne décorative."""
    def __init__(self, title, color=None, parent=None):
        super().__init__(parent)
        self._col = color or C_CYAN
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 4)
        lay.setSpacing(8)
        lbl = QLabel(title)
        lbl.setStyleSheet(
            f"color:{self._col.name()};font:bold 7pt \'Courier New\';"
            f"letter-spacing:2px;background:transparent;")
        lay.addWidget(lbl)
        lay.addStretch()
        self.setFixedHeight(26)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        h = self.height()
        # Bottom glow line
        g = QLinearGradient(0, h-1, self.width(), h-1)
        g.setColorAt(0, _glow(self._col, 0))
        g.setColorAt(0.3, _glow(self._col, 100))
        g.setColorAt(1, _glow(self._col, 0))
        p.setPen(QPen(QBrush(g), 1))
        p.drawLine(0, h-1, self.width(), h-1)
        p.end()


# ════════════════════════════════════════════════════════════
#  ASSET LIST  (un répertoire = un onglet)
# ════════════════════════════════════════════════════════════

class AssetList(QWidget):
    item_double_clicked = Signal(str, str)

    def __init__(self, kind, color, label, exts):
        super().__init__()
        self.kind         = kind
        self.color        = color
        self.exts         = exts
        self._project_dir = ""
        self.setStyleSheet(f"background:{C_BG.name()};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # Header
        hdr = QHBoxLayout()
        title = QLabel(f"  {label}")
        title.setStyleSheet(
            f"color:{color.name()};font:bold 7pt \'Courier New\';"
            f"letter-spacing:2px;padding:2px 0;background:transparent;")
        hdr.addWidget(title)
        hdr.addStretch()

        for icon, tip, slot in [
            ("+", f"Importer dans {kind}/", self._add_files),
            ("📁", f"Ouvrir {kind}/",       self._open_folder),
        ]:
            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(tip)
            btn.setFixedSize(22, 22)
            btn.setStyleSheet(
                f"QToolButton{{background:transparent;color:{color.name()};"
                f"border:1px solid {color.name()}40;border-radius:3px;"
                f"font:bold 9pt \'Courier New\';}}"
                f"QToolButton:hover{{background:{color.name()}25;"
                f"border:1px solid {color.name()}aa;}}")
            btn.clicked.connect(slot)
            hdr.addWidget(btn)
        lay.addLayout(hdr)

        # Separator
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        c = QColor(color); c.setAlpha(40)
        sep.setStyleSheet(f"background:{c.name()};max-height:1px;border:none;")
        lay.addWidget(sep)

        self._list = QListWidget()
        self._list.setStyleSheet(_ss_list(color) + _ss_scroll())
        self._list.itemDoubleClicked.connect(self._on_dbl)
        lay.addWidget(self._list)

        self._count = QLabel("0 fichier(s)")
        self._count.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:7pt \'Courier New\';"
            f"padding:2px 6px;background:transparent;")
        lay.addWidget(self._count)

    def refresh(self, items, project_dir):
        self._project_dir = project_dir
        self._list.clear()
        for value, name in items:
            it = QListWidgetItem(f"  {name}")
            it.setData(Qt.UserRole, value)
            it.setToolTip(value)
            self._list.addItem(it)
        n = len(items)
        self._count.setText(f"{n} fichier{'s' if n!=1 else ''}")

    def _on_dbl(self, item):
        self.item_double_clicked.emit(self.kind, item.data(Qt.UserRole))

    def _find_main_window(self):
        w = self
        while w.parent(): w = w.parent()
        return w

    def _add_files(self):
        if not self._project_dir: return
        dest = os.path.join(self._project_dir, self.kind)
        os.makedirs(dest, exist_ok=True)
        exts_str = " ".join(f"*{e}" for e in self.exts)
        paths, _ = QFileDialog.getOpenFileNames(
            self, f"Importer dans {self.kind}/", "",
            f"Fichiers ({exts_str});;Tous (*.*)")
        if not paths: return
        for src in paths:
            dst = os.path.join(dest, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copy2(src, dst)
        mw = self._find_main_window()
        if hasattr(mw, "_refresh_assets"): mw._refresh_assets()

    def _open_folder(self):
        if not self._project_dir: return
        folder = os.path.join(self._project_dir, self.kind)
        os.makedirs(folder, exist_ok=True)
        import subprocess
        if sys.platform == "win32":   os.startfile(folder)
        elif sys.platform == "darwin": subprocess.run(["open", folder])
        else:                          subprocess.run(["xdg-open", folder])


# ════════════════════════════════════════════════════════════
#  ASSETS PANEL
# ════════════════════════════════════════════════════════════

class AssetsPanel(QWidget):
    add_to_timeline = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.setFixedWidth(220)
        self.setStyleSheet(f"background:{C_BG.name()};border-right:1px solid {C_BORDER.name()};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        hdr = QLabel("  ◈  ASSETS")
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:bold 7pt \'Courier New\';"
            f"letter-spacing:3px;"
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {C_BG3.name()},stop:1 {C_BG2.name()});"
            f"border-bottom:1px solid {C_BORDER.name()};"
            f"padding:0 8px;")
        lay.addWidget(hdr)

        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane{{border:none;background:{C_BG.name()};}}"
            f"QTabBar::tab{{background:{C_BG2.name()};color:{C_TXTDIM.name()};"
            f"font:6pt \'Courier New\';padding:5px 7px;"
            f"border:none;border-right:1px solid {C_BORDER.name()};"
            f"min-width:36px;}}"
            f"QTabBar::tab:selected{{background:{C_BG.name()};"
            f"color:{C_CYAN.name()};"
            f"border-top:2px solid {C_CYAN.name()};}}"
            f"QTabBar::tab:hover{{color:{C_TXT.name()};}}"
        )

        self._scenes_w   = AssetList("scenes",   C_CYAN,   "SCÈNES",   SCENE_EXTS)
        self._overlays_w = AssetList("overlays", C_ORANGE, "OVERLAYS", OVERLAY_EXTS)
        self._images_w   = AssetList("images",   C_GOLD,   "IMAGES",   IMAGE_EXTS)
        self._fonts_w    = AssetList("fonts",    C_PURPLE, "FONTS",    FONT_EXTS)
        self._music_w    = AssetList("music",    C_TEAL,   "MUSIC",    MUSIC_EXTS)

        for widget, tab_lbl in [
            (self._scenes_w,   "SHD"),
            (self._overlays_w, "OVL"),
            (self._images_w,   "IMG"),
            (self._fonts_w,    "FNT"),
            (self._music_w,    "MUS"),
        ]:
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            sc.setStyleSheet("QScrollArea{border:none;background:transparent;}" + _ss_scroll())
            sc.setWidget(widget)
            tabs.addTab(sc, tab_lbl)

        lay.addWidget(tabs)

        hint = QLabel("  ⇥ double-clic → timeline")
        hint.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:7pt \'Courier New\';"
            f"background:{C_BG2.name()};padding:6px 8px;"
            f"border-top:1px solid {C_BORDER.name()};")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self._scenes_w.item_double_clicked.connect(
            lambda k, v: self.add_to_timeline.emit("scene", v))
        self._overlays_w.item_double_clicked.connect(
            lambda k, v: self.add_to_timeline.emit("overlay_shader", v))
        self._images_w.item_double_clicked.connect(
            lambda k, v: self.add_to_timeline.emit("image", v))
        self._fonts_w.item_double_clicked.connect(
            lambda k, v: self.add_to_timeline.emit("font", v))
        self._music_w.item_double_clicked.connect(
            lambda k, v: self.add_to_timeline.emit("music", v))

    def refresh(self, project_dir):
        scenes   = [(base, f"{base} — {name}") for base, name, _ in scan_scenes(project_dir)]
        overlays = [(sid,  name)               for sid,  name, _ in scan_overlays(project_dir)]
        images   = list(scan_images(project_dir))
        fonts    = list(scan_fonts(project_dir))
        music    = list(scan_music(project_dir))
        self._scenes_w.refresh(scenes,   project_dir)
        self._overlays_w.refresh(overlays, project_dir)
        self._images_w.refresh(images,   project_dir)
        self._fonts_w.refresh(fonts,     project_dir)
        self._music_w.refresh(music,     project_dir)


# ════════════════════════════════════════════════════════════
#  PANNEAU PROPRIÉTÉS
# ════════════════════════════════════════════════════════════

class PropsPanel(QWidget):
    apply_requested     = Signal(dict)
    delete_requested    = Signal()
    duplicate_requested = Signal()

    def __init__(self, app_ref):
        super().__init__()
        self._app = app_ref
        self.setFixedWidth(270)
        self.setStyleSheet(
            f"QWidget{{background:{C_BG.name()};color:{C_TXT.name()};}}")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        self._block = None
        self._show_empty()

    def _clear(self):
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def _show_empty(self):
        self._clear()
        # Header
        hdr = QLabel("  ◈  PROPERTIES")
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:bold 7pt \'Courier New\';"
            f"letter-spacing:3px;"
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {C_BG3.name()},stop:1 {C_BG2.name()});"
            f"border-bottom:1px solid {C_BORDER.name()};"
            f"padding:0 8px;")
        self._lay.addWidget(hdr)
        empty = QLabel("◈\n\nSÉLECTIONNE\nUN BLOC")
        empty.setAlignment(Qt.AlignCenter)
        empty.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:10pt \'Courier New\';"
            f"background:transparent;")
        self._lay.addWidget(empty)
        self._lay.addStretch()

    def show_block(self, b):
        self._clear()
        self._block   = b
        self._widgets = {}
        col = b.q_color()

        # Header with block type
        hdr = QWidget()
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {C_BG3.name()},stop:1 {C_BG2.name()});"
            f"border-bottom:1px solid {col.name()}40;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 0, 8, 0)
        accent = QLabel("▌")
        accent.setStyleSheet(f"color:{col.name()};font:14pt;background:transparent;")
        hl.addWidget(accent)
        ttl = QLabel(b.kind.upper())
        ttl.setStyleSheet(
            f"color:{col.name()};font:bold 8pt \'Courier New\';"
            f"letter-spacing:3px;background:transparent;")
        hl.addWidget(ttl)
        hl.addStretch()
        self._lay.addWidget(hdr)

        # Form area
        form_w = QWidget()
        form_w.setStyleSheet(f"background:{C_BG.name()};")
        form = QFormLayout(form_w)
        form.setSpacing(6)
        form.setContentsMargins(10, 10, 10, 6)
        form.setLabelAlignment(Qt.AlignRight)

        sl = (f"color:{C_TXTDIM.name()};font:7pt \'Courier New\';"
              f"letter-spacing:1px;background:transparent;")
        se = _ss_edit(col)

        def _lbl(t):
            l = QLabel(t); l.setStyleSheet(sl); return l

        def _edit(val, key):
            e = QLineEdit(str(val)); e.setStyleSheet(se)
            self._widgets[key] = e; return e

        def _combo(items, current, key):
            cb = QComboBox(); cb.setStyleSheet(se)
            for data, label in items:
                cb.addItem(label, data)
            for i in range(cb.count()):
                if cb.itemData(i) == current:
                    cb.setCurrentIndex(i); break
            self._widgets[key] = cb; return cb

        form.addRow(_lbl("NOM"), _edit(b.name, "name"))

        if b.kind == "scene":
            items = [(base, f"{base}") for base, _, _ in scan_scenes(self._app.project_dir)]
            form.addRow(_lbl("SCÈNE"), _combo(items, b.base, "base_cb"))
        elif b.kind == "overlay":
            img_items = [("", "— aucune —")] + [
                (rp, fn) for rp, fn in scan_images(self._app.project_dir)]
            form.addRow(_lbl("IMAGE"),  _combo(img_items, b.file, "img_cb"))
            ov_items = [(sid, sid) for sid, _, _ in scan_overlays(self._app.project_dir)]
            form.addRow(_lbl("SHADER"), _combo(ov_items, b.effect, "eff_cb"))
        elif b.kind == "image":
            img_items = [(rp, fn) for rp, fn in scan_images(self._app.project_dir)]
            form.addRow(_lbl("FICHIER"), _combo(img_items, b.file, "img_cb"))
            ov_items = [("", "— aucun —")] + [(sid, sid) for sid, _, _ in scan_overlays(self._app.project_dir)]
            form.addRow(_lbl("EFFET"), _combo(ov_items, b.effect, "eff_cb"))

        form.addRow(_lbl("DÉBUT"), _edit(f"{b.start:.2f}", "start"))
        form.addRow(_lbl("DURÉE"), _edit(f"{b.duration:.2f}", "duration"))

        fin_lbl = QLabel(f"{b.end():.2f} s")
        fin_lbl.setStyleSheet(f"color:{col.name()};font:9pt \'Courier New\';background:transparent;")
        self._widgets["fin_lbl"] = fin_lbl
        form.addRow(_lbl("FIN"), fin_lbl)
        self._lay.addWidget(form_w)

        # Separator
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sc = QColor(col); sc.setAlpha(30)
        sep.setStyleSheet(f"background:{sc.name()};max-height:1px;border:none;margin:4px 8px;")
        self._lay.addWidget(sep)

        # Buttons
        btn_w = QWidget()
        btn_w.setStyleSheet(f"background:{C_BG.name()};")
        btn_l = QVBoxLayout(btn_w)
        btn_l.setContentsMargins(10, 4, 10, 10)
        btn_l.setSpacing(6)

        row = QHBoxLayout()
        btn_apply = QPushButton("✓  APPLIQUER")
        btn_apply.setStyleSheet(_ss_btn(col))
        btn_apply.clicked.connect(self._apply)
        btn_dup = QPushButton("⊕  DUPLIQUER")
        btn_dup.setStyleSheet(_ss_btn(C_GREEN))
        btn_dup.clicked.connect(lambda: self.duplicate_requested.emit())
        row.addWidget(btn_apply); row.addWidget(btn_dup)
        btn_l.addLayout(row)

        btn_del = QPushButton("✕  SUPPRIMER")
        btn_del.setStyleSheet(_ss_btn(C_ORANGE))
        btn_del.clicked.connect(lambda: self.delete_requested.emit())
        btn_l.addWidget(btn_del)
        self._lay.addWidget(btn_w)
        self._lay.addStretch()

    def update_fin(self, b):
        lbl = self._widgets.get("fin_lbl")
        if lbl: lbl.setText(f"{b.end():.2f} s")

    def _apply(self):
        if not self._block: return
        b = self._block
        b.name = self._widgets["name"].text()
        if "base_cb" in self._widgets:
            b.base = self._widgets["base_cb"].currentData()
            for base, name, _ in scan_scenes(self._app.project_dir):
                if base == b.base: b.name = name; break
            self._widgets["name"].setText(b.name)
        if "img_cb" in self._widgets:
            b.file = self._widgets["img_cb"].currentData() or ""
        if "eff_cb" in self._widgets:
            b.effect = self._widgets["eff_cb"].currentData() or ""
        try:
            b.start    = float(self._widgets["start"].text())
            b.duration = float(self._widgets["duration"].text())
        except ValueError: pass
        self.update_fin(b)
        self.apply_requested.emit({})


# ════════════════════════════════════════════════════════════
#  PANNEAU CONFIG
# ════════════════════════════════════════════════════════════

class ConfigPanel(QWidget):
    changed = Signal()

    def __init__(self, cfg):
        super().__init__()
        self._cfg = cfg
        self._widgets = {}
        self.setStyleSheet(f"QWidget{{background:{C_BG.name()};color:{C_TXT.name()};}}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        hdr = QLabel("  ◈  CONFIG PROJECT")
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:bold 7pt \'Courier New\';"
            f"letter-spacing:3px;"
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {C_BG3.name()},stop:1 {C_BG2.name()});"
            f"border-bottom:1px solid {C_BORDER.name()};"
            f"padding:0 8px;")
        lay.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}" + _ss_scroll())

        inner = QWidget()
        inner.setStyleSheet(f"background:{C_BG.name()};")
        form = QFormLayout(inner)
        form.setSpacing(5)
        form.setContentsMargins(10, 10, 10, 10)
        form.setLabelAlignment(Qt.AlignRight)

        sl = (f"color:{C_TXTDIM.name()};font:7pt \'Courier New\';"
              f"letter-spacing:1px;background:transparent;")
        se = _ss_edit(C_ORANGE)

        fields = [
            ("WINDOW_TITLE",      "TITRE",       str),
            ("MUSIC_FILE",        "MUSIQUE",      str),
            ("MUSIC_DURATION",    "DURÉE (s)",    float),
            ("ROWS_PER_SECOND",   "ROWS/SEC",     int),
            ("KICK_SENS",         "KICK SENS",    float),
            ("AUDIO_SMOOTHING",   "SMOOTHING",    float),
            ("BASS_GAIN",         "BASS GAIN",    float),
            ("MID_GAIN",          "MID GAIN",     float),
            ("HIGH_GAIN",         "HIGH GAIN",    float),
            ("BEAT_THRESHOLD",    "BEAT THRESH",  float),
        ]
        for key, label, typ in fields:
            lbl = QLabel(label); lbl.setStyleSheet(sl)
            e = QLineEdit(str(cfg.get(key, ""))); e.setStyleSheet(se)
            e.editingFinished.connect(lambda k=key, t=typ, w=e: self._apply_field(k, t, w))
            self._widgets[key] = (e, typ)
            form.addRow(lbl, e)

        lbl_r = QLabel("RÉSOLUTION"); lbl_r.setStyleSheet(sl)
        res = cfg.get("RES", [1920, 1080])
        e_r = QLineEdit(f"{res[0]}x{res[1]}"); e_r.setStyleSheet(se)
        e_r.editingFinished.connect(lambda w=e_r: self._apply_res(w.text()))
        self._widgets["RES"] = (e_r, str)
        form.addRow(lbl_r, e_r)

        lbl_s = QLabel("SCROLL TEXT"); lbl_s.setStyleSheet(sl)
        self._scroll_edit = QTextEdit()
        self._scroll_edit.setPlainText(cfg.get("SCROLL_TEXT", ""))
        self._scroll_edit.setMaximumHeight(60)
        self._scroll_edit.setStyleSheet(
            f"QTextEdit{{background:{C_BG3.name()};color:{C_TXTHI.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:3px;"
            f"font:8pt \'Courier New\';padding:4px;}}"
            f"QTextEdit:focus{{border:1px solid {C_ORANGE.name()};}}")
        self._scroll_edit.textChanged.connect(self._apply_scroll)
        form.addRow(lbl_s, self._scroll_edit)

        scroll.setWidget(inner)
        lay.addWidget(scroll)

    def _apply_field(self, key, typ, w):
        try: self._cfg[key] = typ(w.text()); self.changed.emit()
        except ValueError: pass

    def _apply_res(self, val):
        try:
            parts = val.replace("x"," ").replace(","," ").split()
            self._cfg["RES"] = [int(parts[0]), int(parts[1])]
            self.changed.emit()
        except (ValueError, IndexError): pass

    def _apply_scroll(self):
        self._cfg["SCROLL_TEXT"] = self._scroll_edit.toPlainText()
        self.changed.emit()

    def refresh(self, cfg):
        self._cfg = cfg
        for key, (w, typ) in self._widgets.items():
            if key == "RES":
                res = cfg.get("RES", [1920,1080])
                w.setText(f"{res[0]}x{res[1]}")
            else:
                w.setText(str(cfg.get(key, "")))
        self._scroll_edit.blockSignals(True)
        self._scroll_edit.setPlainText(cfg.get("SCROLL_TEXT", ""))
        self._scroll_edit.blockSignals(False)

# ════════════════════════════════════════════════════════════
#  EXPORT — Worker thread
# ════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════
#  PHASE 4 — AUTOMATION PANEL
# ════════════════════════════════════════════════════════════

class AutomationPanel(QWidget):
    """
    Panneau latéral Phase 4 — édition d'automation.
    Affiche les @params de la scène sélectionnée,
    permet d'assigner courbes, LFO et modulateurs audio.
    """

    def __init__(self, app_ref, parent=None):
        super().__init__(parent)
        self._app   = app_ref
        self._scene = None
        self._ps    = None          # ParamSystem courant
        self._cur_param = None      # ParamDef sélectionné

        self.setMinimumWidth(260)
        self.setStyleSheet(
            f"QWidget{{background:{C_BG2.name()};color:{C_TXT.name()};}}"
            f"QLabel{{font:8pt 'Courier New';background:transparent;}}"
            f"QComboBox,QDoubleSpinBox,QSpinBox{{background:{C_BG3.name()};"
            f"color:{C_TXTHI.name()};border:1px solid {C_BORDER2.name()};"
            f"border-radius:3px;padding:3px 6px;font:8pt 'Courier New';}}"
            f"QPushButton{{background:{C_BG3.name()};color:{C_CYAN.name()};"
            f"border:1px solid {C_CYAN.name()}40;border-radius:3px;"
            f"padding:4px 10px;font:bold 7pt 'Courier New';}}"
            f"QPushButton:hover{{background:{C_CYAN.name()}18;}}"
            f"QListWidget{{background:{C_BG.name()};border:1px solid {C_BORDER.name()};"
            f"border-radius:3px;font:8pt 'Courier New';}}"
            f"QListWidget::item{{padding:4px 8px;border-bottom:1px solid {C_BG3.name()};}}"
            f"QListWidget::item:selected{{background:{C_SEL.name()};color:{C_CYAN.name()};}}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # En-tête
        hdr = QLabel("  ◈  AUTOMATION")
        hdr.setStyleSheet(
            f"color:{C_PURPLE.name()};font:bold 9pt 'Courier New';"
            f"letter-spacing:2px;padding:4px 0;background:transparent;")
        lay.addWidget(hdr)

        self._scene_lbl = QLabel("— aucune scène —")
        self._scene_lbl.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:7pt 'Courier New';padding:2px 4px;"
            f"background:{C_BG3.name()};border-radius:2px;")
        lay.addWidget(self._scene_lbl)

        # Liste des paramètres
        lay.addWidget(self._sep_lbl("PARAMÈTRES @param"))
        self._param_list = QListWidget()
        self._param_list.setFixedHeight(120)
        self._param_list.currentRowChanged.connect(self._on_param_selected)
        lay.addWidget(self._param_list)

        # Éditeur de courbe
        if AUTOMATION_AVAILABLE:
            lay.addWidget(self._sep_lbl("COURBE D'AUTOMATION"))
            self._editor = AutomationEditor()
            self._editor.setFixedHeight(140)
            self._editor.changed.connect(self._on_curve_changed)
            lay.addWidget(self._editor)
        else:
            self._editor = None
            lay.addWidget(QLabel("  ⚠ automation_widget.py requis"))

        # Mode d'interpolation
        interp_row = QHBoxLayout()
        interp_row.addWidget(QLabel("Interp :"))
        self._interp_cb = QComboBox()
        for m in INTERP_MODES:
            self._interp_cb.addItem(m)
        self._interp_cb.currentTextChanged.connect(self._on_interp_changed)
        interp_row.addWidget(self._interp_cb)
        btn_quant = QPushButton("♩ Quant")
        btn_quant.clicked.connect(self._quantize)
        interp_row.addWidget(btn_quant)
        lay.addLayout(interp_row)

        # Section LFO
        lay.addWidget(self._sep_lbl("LFO"))
        lfo_row = QHBoxLayout()
        self._lfo_shape_cb = QComboBox()
        for s in LFO_SHAPES:
            self._lfo_shape_cb.addItem(s)
        lfo_row.addWidget(self._lfo_shape_cb)
        lfo_row.addWidget(QLabel("Freq:"))
        self._lfo_freq = QDoubleSpinBox()
        self._lfo_freq.setRange(0.0625, 16.0); self._lfo_freq.setValue(1.0)
        self._lfo_freq.setSingleStep(0.5); self._lfo_freq.setDecimals(4)
        self._lfo_freq.setFixedWidth(64)
        lfo_row.addWidget(self._lfo_freq)
        lay.addLayout(lfo_row)
        lfo_row2 = QHBoxLayout()
        lfo_row2.addWidget(QLabel("Amp:"))
        self._lfo_amp = QDoubleSpinBox()
        self._lfo_amp.setRange(0.0, 2.0); self._lfo_amp.setValue(0.5)
        self._lfo_amp.setSingleStep(0.1); self._lfo_amp.setFixedWidth(60)
        lfo_row2.addWidget(self._lfo_amp)
        lfo_row2.addWidget(QLabel("Wt:"))
        self._lfo_wt = QDoubleSpinBox()
        self._lfo_wt.setRange(0.0, 1.0); self._lfo_wt.setValue(1.0)
        self._lfo_wt.setSingleStep(0.1); self._lfo_wt.setFixedWidth(52)
        lfo_row2.addWidget(self._lfo_wt)
        btn_lfo = QPushButton("Set LFO")
        btn_lfo.clicked.connect(self._apply_lfo)
        lfo_row2.addWidget(btn_lfo)
        btn_clr_lfo = QPushButton("✕")
        btn_clr_lfo.setFixedWidth(24)
        btn_clr_lfo.clicked.connect(self._clear_lfo)
        lfo_row2.addWidget(btn_clr_lfo)
        lay.addLayout(lfo_row2)

        # Section Modulateur Audio
        lay.addWidget(self._sep_lbl("MODULATEUR AUDIO"))
        aud_row = QHBoxLayout()
        self._aud_src_cb = QComboBox()
        for s in AudioModulator.SOURCES:
            self._aud_src_cb.addItem(s)
        aud_row.addWidget(self._aud_src_cb)
        aud_row.addWidget(QLabel("Wt:"))
        self._aud_wt = QDoubleSpinBox()
        self._aud_wt.setRange(0.0, 1.0); self._aud_wt.setValue(1.0)
        self._aud_wt.setSingleStep(0.1); self._aud_wt.setFixedWidth(52)
        aud_row.addWidget(self._aud_wt)
        btn_aud = QPushButton("Set")
        btn_aud.clicked.connect(self._apply_audio_mod)
        aud_row.addWidget(btn_aud)
        btn_clr_aud = QPushButton("✕")
        btn_clr_aud.setFixedWidth(24)
        btn_clr_aud.clicked.connect(self._clear_audio_mod)
        aud_row.addWidget(btn_clr_aud)
        lay.addLayout(aud_row)

        # Math node
        lay.addWidget(self._sep_lbl("MATH NODE"))
        math_row = QHBoxLayout()
        self._math_op_cb = QComboBox()
        for op in MathNode.OPS:
            self._math_op_cb.addItem(op)
        math_row.addWidget(self._math_op_cb)
        math_row.addWidget(QLabel("A:"))
        self._math_a = QDoubleSpinBox()
        self._math_a.setRange(-100, 100); self._math_a.setValue(1.0)
        self._math_a.setSingleStep(0.1); self._math_a.setFixedWidth(56)
        math_row.addWidget(self._math_a)
        btn_math = QPushButton("Set")
        btn_math.clicked.connect(self._apply_math)
        math_row.addWidget(btn_math)
        btn_clr_math = QPushButton("✕")
        btn_clr_math.setFixedWidth(24)
        btn_clr_math.clicked.connect(self._clear_math)
        math_row.addWidget(btn_clr_math)
        lay.addLayout(math_row)

        # ── Enregistrement live (Phase 4.2) ───────────────────────────────
        lay.addWidget(self._sep_lbl("ENREGISTREMENT LIVE"))
        rec_row = QHBoxLayout()
        self._btn_rec = QPushButton("⏺ REC")
        self._btn_rec.setCheckable(True)
        self._btn_rec.setStyleSheet(
            f"QPushButton{{background:{C_BG3.name()};color:{C_ORANGE.name()};"
            f"border:1px solid {C_ORANGE.name()}60;border-radius:3px;"
            f"padding:4px 10px;font:bold 7pt 'Courier New';}}"
            f"QPushButton:checked{{background:{C_ORANGE.name()}33;"
            f"border:1px solid {C_ORANGE.name()};color:{C_ORANGE.name()};}}"
            f"QPushButton:hover{{background:{C_ORANGE.name()}18;}}")
        self._btn_rec.toggled.connect(self._toggle_record)
        rec_row.addWidget(self._btn_rec)
        self._rec_status = QLabel("—")
        self._rec_status.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:7pt 'Courier New';"
            f"padding:2px 4px;background:transparent;")
        rec_row.addWidget(self._rec_status)
        lay.addLayout(rec_row)

        # ── Copie de courbe (Phase 4.2) ───────────────────────────────────
        lay.addWidget(self._sep_lbl("COPIE DE COURBE"))
        copy_row = QHBoxLayout()
        copy_row.addWidget(QLabel("Vers :"))
        self._copy_target_cb = QComboBox()
        self._copy_target_cb.setStyleSheet(
            f"QComboBox{{background:{C_BG3.name()};color:{C_TXTHI.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:3px;"
            f"padding:3px 6px;font:8pt 'Courier New';}}")
        copy_row.addWidget(self._copy_target_cb)
        btn_copy = QPushButton("Copier")
        btn_copy.clicked.connect(self._copy_curve_to)
        copy_row.addWidget(btn_copy)
        lay.addLayout(copy_row)

        # Timer pour l'enregistrement live : échantillonne la valeur courante
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(50)   # ~20 Hz
        self._rec_timer.timeout.connect(self._record_tick)
        self._is_recording = False

        lay.addStretch()

    def _sep_lbl(self, txt):
        l = QLabel(f"  {txt}")
        l.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:bold 6pt 'Courier New';"
            f"letter-spacing:1.5px;padding:2px 0;background:transparent;"
            f"border-bottom:1px solid {C_BORDER.name()};")
        return l

    # ── API publique ──────────────────────────────────────────────────────────

    def load_scene(self, scene_name, param_system):
        self._scene = scene_name
        self._ps    = param_system
        self._param_list.clear()
        self._cur_param = None
        if self._editor: self._editor.set_curve(None)
        # Arrêter l'enregistrement si on change de scène
        if self._is_recording:
            self._btn_rec.setChecked(False)
        self._copy_target_cb.clear()

        if scene_name and param_system:
            params = param_system.get_params(scene_name)
            self._scene_lbl.setText(f"  {scene_name}  ({len(params)} params)")
            for p in params:
                self._param_list.addItem(f"{p.label}  [{p.type}]")
        else:
            self._scene_lbl.setText("— aucune scène —")

    def refresh(self):
        if self._editor and self._scene and self._cur_param and self._ps:
            slot = self._ps.get_slot(self._scene, self._cur_param.name)
            if slot and slot.curve:
                dur = self._app.cfg.get("MUSIC_DURATION", 240.0)
                sc  = next((b for b in self._app.scenes
                            if b.base == self._scene), None)
                t0  = sc.start if sc else 0.0
                t1  = sc.end()  if sc else dur
                self._editor.set_curve(slot.curve, t0, t1)
        self._editor.update() if self._editor else None

    # ── Sélection d'un paramètre ──────────────────────────────────────────────

    def _on_param_selected(self, row):
        if not self._scene or not self._ps or row < 0: return
        params = self._ps.get_params(self._scene)
        if row >= len(params): return
        self._cur_param = params[row]
        slot = self._ps.get_slot(self._scene, self._cur_param.name)
        if not slot: return

        # Mettre à jour l'éditeur de courbe
        if self._editor and slot.curve:
            sc  = next((b for b in self._app.scenes if b.base == self._scene), None)
            t0  = sc.start if sc else 0.0
            t1  = sc.end()  if sc else self._app.cfg.get("MUSIC_DURATION", 240.0)
            self._editor.set_curve(slot.curve, t0, t1)

        # Remplir les widgets LFO / audio / math depuis le slot
        if slot.lfo:
            idx = list(LFO_SHAPES).index(slot.lfo.shape) if slot.lfo.shape in LFO_SHAPES else 0
            self._lfo_shape_cb.setCurrentIndex(idx)
            self._lfo_freq.setValue(slot.lfo.freq_beats)
            self._lfo_amp.setValue(slot.lfo.amplitude)
            self._lfo_wt.setValue(slot.lfo_weight)
        if slot.audio:
            sources = list(AudioModulator.SOURCES)
            si = sources.index(slot.audio.source) if slot.audio.source in sources else 0
            self._aud_src_cb.setCurrentIndex(si)
            self._aud_wt.setValue(slot.audio_weight)
        if slot.math:
            ops = list(MathNode.OPS)
            oi = ops.index(slot.math.op) if slot.math.op in ops else 0
            self._math_op_cb.setCurrentIndex(oi)
            self._math_a.setValue(slot.math.a)

        # Mettre à jour les cibles de copie de courbe
        self._refresh_copy_targets()

    def _on_curve_changed(self):
        self._app.autosave()

    def _on_interp_changed(self, mode):
        if not self._editor or not self._editor.curve: return
        for i in self._editor._sel:
            if 0 <= i < len(self._editor.curve.keyframes):
                self._editor.curve.keyframes[i].interp = mode
        self._editor.update()
        self._app.autosave()

    # ── LFO ──────────────────────────────────────────────────────────────────

    def _apply_lfo(self):
        if not self._cur_param or not self._scene or not self._ps: return
        lfo = LFO(
            shape       = self._lfo_shape_cb.currentText(),
            freq_beats  = self._lfo_freq.value(),
            amplitude   = self._lfo_amp.value(),
        )
        self._ps.set_lfo(self._scene, self._cur_param.name, lfo, self._lfo_wt.value())
        self._app.autosave()
        self._app._set_status(f"LFO {lfo.shape} assigné à {self._cur_param.name}")

    def _clear_lfo(self):
        if not self._cur_param or not self._scene or not self._ps: return
        self._ps.set_lfo(self._scene, self._cur_param.name, None)
        self._app.autosave()

    # ── Modulateur audio ──────────────────────────────────────────────────────

    def _apply_audio_mod(self):
        if not self._cur_param or not self._scene or not self._ps: return
        mod = AudioModulator(source=self._aud_src_cb.currentText())
        self._ps.set_audio_mod(self._scene, self._cur_param.name,
                               mod, self._aud_wt.value())
        self._app.autosave()
        self._app._set_status(f"Mod audio {mod.source} assigné à {self._cur_param.name}")

    def _clear_audio_mod(self):
        if not self._cur_param or not self._scene or not self._ps: return
        self._ps.set_audio_mod(self._scene, self._cur_param.name, None)
        self._app.autosave()

    # ── Math node ─────────────────────────────────────────────────────────────

    def _apply_math(self):
        if not self._cur_param or not self._scene or not self._ps: return
        node = MathNode(op=self._math_op_cb.currentText(), a=self._math_a.value())
        self._ps.set_math(self._scene, self._cur_param.name, node)
        self._app.autosave()
        self._app._set_status(f"Math {node.op}({node.a}) assigné à {self._cur_param.name}")

    def _clear_math(self):
        if not self._cur_param or not self._scene or not self._ps: return
        self._ps.set_math(self._scene, self._cur_param.name, None)
        self._app.autosave()

    # ── Quantification ───────────────────────────────────────────────────────

    def _quantize(self):
        if not self._cur_param or not self._scene or not self._ps: return
        bpm = float(self._app._tl._bpm)
        self._ps.quantize_all(self._scene, bpm)
        self.refresh()
        self._app.autosave()
        self._app._set_status(f"Quantifié sur {bpm:.0f} BPM")

    # ── Enregistrement live (Phase 4.2) ──────────────────────────────────────

    def _toggle_record(self, checked: bool):
        """Démarre ou arrête l'enregistrement live du paramètre sélectionné."""
        if checked:
            if not self._cur_param or not self._scene or not self._ps:
                self._btn_rec.setChecked(False)
                self._app._set_status("Sélectionner un paramètre avant d'enregistrer.")
                return
            self._is_recording = True
            self._ps.start_record(self._scene, [self._cur_param.name])
            self._rec_status.setText(f"⏺ {self._cur_param.name}")
            self._rec_timer.start()
            self._app._set_status(
                f"Enregistrement live de «{self._cur_param.name}» — déplacer le slider pour créer des keyframes")
        else:
            self._is_recording = False
            self._ps.stop_record()
            self._rec_timer.stop()
            self._rec_status.setText("—")
            self.refresh()
            self._app.autosave()
            self._app._set_status("Enregistrement arrêté.")

    def _record_tick(self):
        """
        Appelé ~20 Hz pendant l'enregistrement.
        Lit la valeur courante depuis les widgets de l'éditeur de courbe
        (position de la souris sur le widget, ou valeur du slot évaluée)
        et l'enregistre comme keyframe au temps courant de la GUI.
        """
        if not self._is_recording or not self._cur_param or not self._scene or not self._ps:
            return
        # Temps courant de la GUI (playhead)
        t = getattr(self._app, '_current_t', 0.0)
        # Valeur courante : évaluer le slot à t (courbe + LFO + audio)
        bpm = float(self._app._tl._bpm)
        au  = getattr(self._app, '_last_audio_uniforms', {})
        val = self._ps.get_slot(self._scene, self._cur_param.name)
        if val:
            current_val = val.evaluate(t, au, bpm)
            self._ps.record_value(self._scene, self._cur_param.name, t, current_val)
        if self._editor and self._editor.curve:
            self._editor.update()

    # ── Copie de courbe (Phase 4.2) ───────────────────────────────────────────

    def _refresh_copy_targets(self):
        """Peuple le combobox avec les autres paramètres de la scène (même type ou compatibles)."""
        self._copy_target_cb.clear()
        if not self._scene or not self._ps or not self._cur_param:
            return
        params = self._ps.get_params(self._scene)
        for p in params:
            if p.name != self._cur_param.name and p.type == self._cur_param.type:
                self._copy_target_cb.addItem(f"{p.label}  [{p.name}]", userData=p.name)

    def _copy_curve_to(self):
        """Copie la courbe d'automation du paramètre sélectionné vers la cible choisie."""
        if not self._cur_param or not self._scene or not self._ps:
            self._app._set_status("Sélectionner un paramètre source d'abord.")
            return
        target_name = self._copy_target_cb.currentData()
        if not target_name:
            self._app._set_status("Aucune cible de copie disponible (même type requis).")
            return
        src_slot = self._ps.get_slot(self._scene, self._cur_param.name)
        dst_slot = self._ps.get_slot(self._scene, target_name)
        if src_slot and dst_slot and src_slot.curve:
            src_slot.curve.copy_to(dst_slot.curve)
            self._app.autosave()
            self._app._set_status(
                f"Courbe «{self._cur_param.name}» → «{target_name}» copiée.")




# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 5.2 — GLSL SYNTAX HIGHLIGHTER
# ══════════════════════════════════════════════════════════════════════════════

class GlslHighlighter(QSyntaxHighlighter):
    """
    Colorisation syntaxique GLSL pour QPlainTextEdit.
    Couvre : types, mots-clés de contrôle, builtins, uniforms moteur, commentaires, nombres.
    """

    def __init__(self, doc):
        super().__init__(doc)
        self._rules: list[tuple] = []

        def _fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:   f.setFontWeight(700)
            if italic: f.setFontItalic(True)
            return f

        import re as _re

        # Types GLSL
        types = (r'\b(?:void|bool|int|uint|float|double|'
                 r'vec[2-4]|dvec[2-4]|ivec[2-4]|uvec[2-4]|bvec[2-4]|'
                 r'mat[2-4]|mat[2-4]x[2-4]|'
                 r'sampler[12]D|sampler2DArray|samplerCube|sampler3D|'
                 r'sampler2DShadow|sampler2DMS)\b')
        self._rules.append((_re.compile(types), _fmt('#4ec9b0', bold=True)))

        # Mots-clés de contrôle
        keywords = (r'\b(?:if|else|for|while|do|return|break|continue|discard|'
                    r'switch|case|default|struct|in|out|inout|uniform|varying|'
                    r'attribute|const|precision|highp|mediump|lowp|layout|'
                    r'location|binding|flat|smooth|centroid)\b')
        self._rules.append((_re.compile(keywords), _fmt('#c586c0', bold=True)))

        # Fonctions builtin GLSL
        builtins = (r'\b(?:abs|acos|acosh|all|any|asin|asinh|atan|atanh|'
                    r'ceil|clamp|cos|cosh|cross|degrees|dFdx|dFdy|'
                    r'distance|dot|equal|exp|exp2|faceforward|'
                    r'floor|fract|fwidth|greaterThan|greaterThanEqual|'
                    r'inversesqrt|isinf|isnan|length|lessThan|lessThanEqual|'
                    r'log|log2|matrixCompMult|max|min|mix|mod|modf|'
                    r'normalize|not|notEqual|outerProduct|pow|radians|'
                    r'reflect|refract|round|roundEven|sign|sin|sinh|'
                    r'smoothstep|sqrt|step|tan|tanh|texture|texture2D|'
                    r'textureLod|textureSize|transpose|trunc|'
                    r'noise[1-4]|emit|EndPrimitive)\b')
        self._rules.append((_re.compile(builtins), _fmt('#dcdcaa')))

        # Uniforms moteur (iTime, iKick, etc.)
        engine_uniforms = (r'\b(?:iTime|iResolution|iSceneProgress|iLocalTime|iDuration|'
                           r'iChannel[0-7]|iKick|iBass|iMid|iHigh|iBeat|iBPM|'
                           r'iBassPeak|iMidPeak|iHighPeak|iBassRMS|iMidRMS|iHighRMS|'
                           r'iBar|iBeat4|iSixteenth|iSection|iEnergy|iDrop|'
                           r'iStereoWidth|iCue|iTransition|iChannelPrev|iChannelNext|'
                           r'iSpectrum|iWaveform|iSpectrumHistory|iBarkSpectrum|'
                           r'iBlueNoise|iWorleyNoise|iWhiteNoise|iPrevScene)\b')
        self._rules.append((_re.compile(engine_uniforms), _fmt('#9cdcfe', bold=True)))

        # Macros @param
        self._rules.append((_re.compile(r'//\s*@param\b.*'), _fmt('#b5cea8', italic=True)))

        # Commentaires ligne
        self._rules.append((_re.compile(r'//[^\n]*'), _fmt('#6a9955', italic=True)))

        # Nombres
        self._rules.append((_re.compile(r'\b\d+\.?\d*(?:[eE][+-]?\d+)?[fFuU]?\b'),
                            _fmt('#b5cea8')))

        # Directives préprocesseur
        self._rules.append((_re.compile(r'^\s*#\w+.*', _re.MULTILINE), _fmt('#9b9b6e')))

        # Commentaires bloc /* */
        self._block_start = _re.compile(r'/\*')
        self._block_end   = _re.compile(r'\*/')
        self._fmt_comment = _fmt('#6a9955', italic=True)

    def highlightBlock(self, text: str):
        import re as _re
        # Règles inline
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

        # Commentaires bloc (multi-lignes)
        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() != 1:
            m = self._block_start.search(text)
            start = m.start() if m else -1

        while start >= 0:
            m_end = self._block_end.search(text, start)
            if m_end:
                length = m_end.end() - start
                self.setCurrentBlockState(0)
            else:
                self.setCurrentBlockState(1)
                length = len(text) - start
            self.setFormat(start, length, self._fmt_comment)
            m_next = self._block_start.search(text, start + length)
            start = m_next.start() if m_next else -1


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 5.2 — ÉDITEUR GLSL INLINE
# ══════════════════════════════════════════════════════════════════════════════

class GlslEditorPanel(QWidget):
    """
    Éditeur de code GLSL intégré dans la GUI.
    - Syntaxe colorée via GlslHighlighter
    - Affichage des erreurs de compilation avec numéro de ligne
    - Rechargement à chaud : sauvegarde → recompile → status instantané
    - Hot-reload : QFileSystemWatcher sur le fichier courant
    """

    shader_saved = Signal(str)   # path du fichier sauvegardé

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path: str = ''
        self._modified: bool    = False
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_changed)

        self.setMinimumWidth(400)
        ss_base = (f"QWidget{{background:{C_BG.name()};color:{C_TXT.name()};}}"
                   f"QLabel{{background:transparent;font:8pt 'Courier New';}}")
        self.setStyleSheet(ss_base)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Barre de titre ────────────────────────────────────────────────
        bar = QWidget()
        bar.setFixedHeight(32)
        bar.setStyleSheet(f"background:{C_BG3.name()};border-bottom:1px solid {C_BORDER2.name()};")
        blay = QHBoxLayout(bar)
        blay.setContentsMargins(8, 0, 6, 0)
        blay.setSpacing(6)

        self._file_lbl = QLabel("— aucun fichier —")
        self._file_lbl.setStyleSheet(f"color:{C_TXTDIM.name()};font:7pt 'Courier New';")
        blay.addWidget(self._file_lbl)
        blay.addStretch()

        for txt, tip, slot, col in [
            ("📂", "Ouvrir fichier shader…",  self._open_file, C_CYAN),
            ("💾", "Sauvegarder  Ctrl+S",     self._save_file, C_GREEN),
            ("⟳",  "Recharger depuis disque", self._reload_file, C_ORANGE),
        ]:
            b = QToolButton()
            b.setText(txt); b.setToolTip(tip)
            b.setFixedSize(26, 26)
            b.setStyleSheet(
                f"QToolButton{{background:transparent;color:{col.name()};"
                f"border:1px solid {col.name()}40;border-radius:3px;font:10pt;}}"
                f"QToolButton:hover{{background:{col.name()}25;}}")
            b.clicked.connect(slot)
            blay.addWidget(b)
        root.addWidget(bar)

        # ── Éditeur ───────────────────────────────────────────────────────
        self._editor = QPlainTextEdit()
        self._editor.setFont(QFont("Courier New", 9))
        self._editor.setStyleSheet(
            f"QPlainTextEdit{{background:{C_BG.name()};color:#d4d4d4;"
            f"border:none;selection-background-color:{C_SEL.name()};"
            f"font:9pt 'Courier New';}}"
            + _ss_scroll())
        self._editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._editor.setTabStopDistance(28)
        self._highlighter = GlslHighlighter(self._editor.document())
        self._editor.textChanged.connect(self._on_text_changed)
        QShortcut(QKeySequence("Ctrl+S"), self._editor, self._save_file)
        root.addWidget(self._editor, stretch=4)

        # ── Panneau d'erreurs ─────────────────────────────────────────────
        err_header = QWidget()
        err_header.setFixedHeight(24)
        err_header.setStyleSheet(
            f"background:{C_BG3.name()};border-top:1px solid {C_BORDER.name()};")
        ehlay = QHBoxLayout(err_header)
        ehlay.setContentsMargins(8, 0, 8, 0)
        self._err_count_lbl = QLabel("✓ OK")
        self._err_count_lbl.setStyleSheet(
            f"color:{C_GREEN.name()};font:bold 7pt 'Courier New';")
        ehlay.addWidget(self._err_count_lbl)
        ehlay.addStretch()
        root.addWidget(err_header)

        self._err_list = QListWidget()
        self._err_list.setFixedHeight(90)
        self._err_list.setStyleSheet(
            f"QListWidget{{background:{C_BG.name()};border:none;"
            f"font:8pt 'Courier New';}}"
            f"QListWidget::item{{padding:2px 8px;border-bottom:1px solid {C_BG3.name()};}}"
            f"QListWidget::item:selected{{background:{C_SEL.name()};color:{C_ORANGE.name()};}}"
            + _ss_scroll())
        self._err_list.itemClicked.connect(self._jump_to_error)
        root.addWidget(self._err_list, stretch=0)

    # ── API publique ──────────────────────────────────────────────────────────

    def load_file(self, path: str):
        """Charge un fichier .frag dans l'éditeur."""
        if not os.path.exists(path):
            return
        if self._current_path and self._current_path in self._watcher.files():
            self._watcher.removePath(self._current_path)
        self._current_path = path
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                code = f.read()
            self._editor.blockSignals(True)
            self._editor.setPlainText(code)
            self._editor.blockSignals(False)
            self._modified = False
            self._file_lbl.setText(f"  {os.path.basename(path)}")
            self._file_lbl.setStyleSheet(
                f"color:{C_TXTHI.name()};font:7pt 'Courier New';")
            self._watcher.addPath(path)
            self._validate()
        except Exception as e:
            self._show_error(f"Lecture impossible : {e}")

    def get_code(self) -> str:
        return self._editor.toPlainText()

    # ── Validation GLSL (sans contexte GPU) ──────────────────────────────────

    def _validate(self):
        """
        Tente de compiler le shader via moderngl standalone pour avoir
        les vrais messages d'erreur du driver avec numéros de ligne.
        Si moderngl n'est pas disponible hors GPU, parse les erreurs syntaxiques
        de base (accolades non fermées, directives manquantes…).
        """
        code = self._editor.toPlainText()
        errors = []

        # Tentative de compilation GPU (fonctionne si un contexte GL est accessible)
        try:
            import moderngl as _mgl
            VERT_MINI = "#version 330\nin vec2 in_vert;void main(){gl_Position=vec4(in_vert,0,1);}"
            ctx = _mgl.create_standalone_context()
            try:
                ctx.program(vertex_shader=VERT_MINI, fragment_shader=code)
            except Exception as e:
                errors = self._parse_gl_errors(str(e))
            finally:
                ctx.release()
        except Exception:
            # Pas de contexte GL dispo : validation syntaxique légère
            errors = self._static_lint(code)

        self._show_errors(errors)

    def _parse_gl_errors(self, msg: str) -> list[tuple[int, str]]:
        """Parse les messages d'erreur du driver OpenGL → liste (line, message)."""
        import re
        results = []
        # Format driver standard : 0(LINE) : error TYPE: message
        for pat in [r'(\d+)\((\d+)\)\s*:\s*(.+)', r'ERROR:\s*\d+:(\d+):\s*(.+)']:
            for m in re.finditer(pat, msg):
                if len(m.groups()) == 3:
                    results.append((int(m.group(2)), m.group(3).strip()))
                else:
                    results.append((int(m.group(1)), m.group(2).strip()))
        if not results and msg.strip():
            results.append((0, msg.split('\n')[0][:120]))
        return results

    def _static_lint(self, code: str) -> list[tuple[int, str]]:
        """Lint statique minimal : version manquante, accolades déséquilibrées."""
        errors = []
        lines  = code.splitlines()
        if not any(l.strip().startswith('#version') for l in lines[:5]):
            errors.append((1, "Directive #version manquante (ex: #version 330)"))
        depth = 0
        for i, line in enumerate(lines, 1):
            stripped = line.split('//')[0]
            depth += stripped.count('{') - stripped.count('}')
        if depth != 0:
            errors.append((len(lines), f"Accolades déséquilibrées (delta={depth:+d})"))
        return errors

    def _show_errors(self, errors: list[tuple[int, str]]):
        self._err_list.clear()
        if not errors:
            self._err_count_lbl.setText("✓ Compilation OK")
            self._err_count_lbl.setStyleSheet(
                f"color:{C_GREEN.name()};font:bold 7pt 'Courier New';")
            return
        self._err_count_lbl.setText(f"✖ {len(errors)} erreur(s)")
        self._err_count_lbl.setStyleSheet(
            f"color:{C_ORANGE.name()};font:bold 7pt 'Courier New';")
        for line_no, msg in errors:
            label = f"  L{line_no:>4}   {msg}"
            item  = QListWidgetItem(label)
            item.setData(Qt.UserRole, line_no)
            item.setForeground(QColor(C_ORANGE.name()))
            self._err_list.addItem(item)

    def _show_error(self, msg: str):
        self._show_errors([(0, msg)])

    def _jump_to_error(self, item):
        """Déplace le curseur à la ligne de l'erreur cliquée."""
        line_no = item.data(Qt.UserRole)
        if line_no and line_no > 0:
            doc    = self._editor.document()
            block  = doc.findBlockByLineNumber(line_no - 1)
            cursor = self._editor.textCursor()
            cursor.setPosition(block.position())
            self._editor.setTextCursor(cursor)
            self._editor.centerCursor()
            self._editor.setFocus()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_text_changed(self):
        self._modified = True
        name = os.path.basename(self._current_path) if self._current_path else '—'
        self._file_lbl.setText(f"  {name}  •")
        self._file_lbl.setStyleSheet(
            f"color:{C_ORANGE.name()};font:7pt 'Courier New';")

    def _save_file(self):
        if not self._current_path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Sauvegarder shader", '',
                "Shaders GLSL (*.frag *.glsl *.vert);;Tous (*.*)")
            if not path:
                return
            self._current_path = path
        try:
            # Suspendre le watcher le temps de la sauvegarde (évite double-reload)
            if self._current_path in self._watcher.files():
                self._watcher.removePath(self._current_path)
            with open(self._current_path, 'w', encoding='utf-8') as f:
                f.write(self._editor.toPlainText())
            self._modified = False
            self._file_lbl.setText(f"  {os.path.basename(self._current_path)}")
            self._file_lbl.setStyleSheet(
                f"color:{C_GREEN.name()};font:7pt 'Courier New';")
            self._watcher.addPath(self._current_path)
            self._validate()
            self.shader_saved.emit(self._current_path)
        except Exception as e:
            self._show_error(f"Sauvegarde échouée : {e}")

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir shader GLSL", '',
            "Shaders GLSL (*.frag *.glsl *.vert);;Tous (*.*)")
        if path:
            self.load_file(path)

    def _reload_file(self):
        if self._current_path:
            self.load_file(self._current_path)

    def _on_file_changed(self, path: str):
        """Hot-reload : fichier modifié externement → recharger."""
        if path == self._current_path and not self._modified:
            QTimer.singleShot(80, self._reload_file)
        # Ré-ajouter le chemin (certains éditeurs suppriment/recréent le fichier)
        if path not in self._watcher.files():
            self._watcher.addPath(path)


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 5.1 — BROWSER VISUEL SHADERS (thumbnails)
# ══════════════════════════════════════════════════════════════════════════════

class ShaderThumbnailWorker(QThread):
    """
    Thread de rendu des thumbnails : rend une frame fixe (t=2.0 s)
    via moderngl standalone pour chaque shader, retourne un QPixmap 160×90.
    """
    thumbnail_ready = Signal(str, QPixmap)   # (base_name, pixmap)
    error_ready     = Signal(str, str)        # (base_name, error_msg)

    THUMB_W = 160
    THUMB_H = 90

    def __init__(self, project_dir: str, scene_name: str, parent=None):
        super().__init__(parent)
        self._dir   = project_dir
        self._scene = scene_name

    def run(self):
        try:
            import moderngl as _mgl
            import numpy as _np

            VERT = "#version 330\nin vec2 in_vert;void main(){gl_Position=vec4(in_vert,0,1);}"

            def _read(path):
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        return f.read()
                return None

            ctx = _mgl.create_standalone_context()
            res = (self.THUMB_W, self.THUMB_H)

            tex_out = ctx.texture(res, 3, dtype='f1')
            fbo_out = ctx.framebuffer(color_attachments=[tex_out])

            quad = ctx.buffer(data=_np.array(
                [-1, 1, -1, -1, 1, 1, 1, -1], dtype='f4'))

            def _make(code):
                if not code: return None, None
                try:
                    p = ctx.program(vertex_shader=VERT, fragment_shader=code)
                    v = ctx.simple_vertex_array(p, quad, 'in_vert')
                    return p, v
                except Exception:
                    return None, None

            sd  = os.path.join(self._dir, 'scenes')
            p_a, vao_a = _make(_read(os.path.join(sd, f'buffer_a_{self._scene}.frag')))
            p_b, vao_b = _make(_read(os.path.join(sd, f'buffer_b_{self._scene}.frag')))
            p_c, vao_c = _make(_read(os.path.join(sd, f'buffer_c_{self._scene}.frag')))
            p_d, vao_d = _make(_read(os.path.join(sd, f'buffer_d_{self._scene}.frag')))
            p_m, vao_m = _make(_read(os.path.join(sd, f'scene_{self._scene}.frag')))

            if not (p_m and vao_m):
                ctx.release()
                self.error_ready.emit(self._scene, "Shader principal absent")
                return

            def _tex():
                t = ctx.texture(res, 4, dtype='f4')
                t.filter = (_mgl.LINEAR, _mgl.LINEAR)
                return t

            tex_a = [_tex(), _tex()]
            fbo_a = [ctx.framebuffer(color_attachments=[t]) for t in tex_a]
            tex_b = _tex(); fbo_b = ctx.framebuffer(color_attachments=[tex_b])
            tex_c = _tex(); fbo_c = ctx.framebuffer(color_attachments=[tex_c])
            tex_d = _tex(); fbo_d = ctx.framebuffer(color_attachments=[tex_d])

            def _pass(p, v, fbo, inputs, t=2.0, prog=0.5):
                if not (p and v): return
                fbo.use()
                for i, tx in enumerate(inputs):
                    tx.use(i)
                    if f'iChannel{i}' in p: p[f'iChannel{i}'].value = i
                if 'iTime'          in p: p['iTime'].value          = t
                if 'iResolution'    in p: p['iResolution'].value     = (float(res[0]), float(res[1]))
                if 'iSceneProgress' in p: p['iSceneProgress'].value  = prog
                if 'iKick'          in p: p['iKick'].value           = 0.0
                if 'iBass'          in p: p['iBass'].value           = 0.3
                if 'iMid'           in p: p['iMid'].value            = 0.2
                if 'iHigh'          in p: p['iHigh'].value           = 0.1
                v.render(_mgl.TRIANGLE_STRIP)

            _pass(p_a, vao_a, fbo_a[0], [tex_a[1]])
            _pass(p_b, vao_b, fbo_b,    [tex_a[0]])
            _pass(p_c, vao_c, fbo_c,    [tex_a[0], tex_b])
            _pass(p_d, vao_d, fbo_d,    [tex_c, tex_b, tex_a[0]])

            fbo_out.use()
            ctx.viewport = (0, 0, *res)
            for i, tx in enumerate([tex_d, tex_b, tex_c, tex_d]):
                tx.use(i)
                if f'iChannel{i}' in p_m: p_m[f'iChannel{i}'].value = i
            if 'iTime'          in p_m: p_m['iTime'].value          = 2.0
            if 'iResolution'    in p_m: p_m['iResolution'].value     = (float(res[0]), float(res[1]))
            if 'iSceneProgress' in p_m: p_m['iSceneProgress'].value  = 0.5
            vao_m.render(_mgl.TRIANGLE_STRIP)

            raw  = fbo_out.read(components=3, alignment=1)
            arr  = _np.frombuffer(raw, dtype=_np.uint8).reshape(res[1], res[0], 3)
            arr  = _np.flipud(arr)
            from PySide6.QtGui import QImage
            img  = QImage(arr.tobytes(), res[0], res[1], res[0]*3,
                          QImage.Format_RGB888)
            pix  = QPixmap.fromImage(img)
            ctx.release()
            self.thumbnail_ready.emit(self._scene, pix)

        except Exception as e:
            import traceback
            self.error_ready.emit(self._scene, str(e))


class ShaderCard(QWidget):
    """Carte miniature d'un shader : thumbnail + nom + boutons."""

    double_clicked   = Signal(str)   # base_name
    edit_requested   = Signal(str)   # path complet du .frag principal
    add_to_timeline  = Signal(str)   # base_name

    CARD_W = 178
    CARD_H = 140

    def __init__(self, base_name: str, project_dir: str, parent=None):
        super().__init__(parent)
        self.base_name   = base_name
        self.project_dir = project_dir
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"Double-clic → ajouter à la timeline\nDrag → déposer sur la timeline")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)

        # Thumbnail
        self._thumb_lbl = QLabel()
        self._thumb_lbl.setFixedSize(ShaderThumbnailWorker.THUMB_W,
                                     ShaderThumbnailWorker.THUMB_H)
        self._thumb_lbl.setAlignment(Qt.AlignCenter)
        self._thumb_lbl.setStyleSheet(
            f"background:{C_BG3.name()};border:1px solid {C_BORDER.name()};"
            f"border-radius:3px;")
        self._set_loading()
        lay.addWidget(self._thumb_lbl)

        # Nom
        lbl = QLabel(f"  {base_name}")
        lbl.setStyleSheet(
            f"color:{C_TXTHI.name()};font:bold 7pt 'Courier New';"
            f"background:transparent;")
        lbl.setWordWrap(False)
        lay.addWidget(lbl)

        # Boutons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(3)
        for txt, tip, sig_val, col in [
            ("＋", "Ajouter à la timeline", base_name, C_GREEN),
            ("✎",  "Éditer le shader",      os.path.join(project_dir, 'scenes',
                                             f'scene_{base_name}.frag'), C_CYAN),
        ]:
            b = QToolButton()
            b.setText(txt); b.setToolTip(tip)
            b.setFixedSize(24, 20)
            b.setStyleSheet(
                f"QToolButton{{background:{C_BG3.name()};color:{col.name()};"
                f"border:1px solid {col.name()}40;border-radius:2px;font:9pt;}}"
                f"QToolButton:hover{{background:{col.name()}25;}}")
            if txt == "＋":
                b.clicked.connect(lambda _, v=sig_val: self.add_to_timeline.emit(v))
            else:
                b.clicked.connect(lambda _, v=sig_val: self.edit_requested.emit(v))
            btn_row.addWidget(b)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self.setStyleSheet(
            f"ShaderCard{{background:{C_BG2.name()};"
            f"border:1px solid {C_BORDER.name()};border-radius:4px;}}"
            f"ShaderCard:hover{{border:1px solid {C_CYAN.name()}60;}}")

    def set_thumbnail(self, pix: QPixmap):
        self._thumb_lbl.setPixmap(
            pix.scaled(ShaderThumbnailWorker.THUMB_W,
                       ShaderThumbnailWorker.THUMB_H,
                       Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._thumb_lbl.setStyleSheet(
            f"background:{C_BG.name()};border:1px solid {C_BORDER.name()};border-radius:3px;")

    def set_error(self, msg: str):
        self._thumb_lbl.setText(f"⚠\n{msg[:40]}")
        self._thumb_lbl.setStyleSheet(
            f"background:{C_BG.name()};color:{C_ORANGE.name()};"
            f"border:1px solid {C_ORANGE.name()}50;border-radius:3px;"
            f"font:7pt 'Courier New';")

    def _set_loading(self):
        self._thumb_lbl.setText("⏳ rendu…")
        self._thumb_lbl.setStyleSheet(
            f"background:{C_BG.name()};color:{C_TXTDIM.name()};"
            f"border:1px solid {C_BORDER.name()};border-radius:3px;"
            f"font:7pt 'Courier New';")

    def mouseDoubleClickEvent(self, _):
        self.double_clicked.emit(self.base_name)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_start = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            delta = (e.position().toPoint() - getattr(self, '_drag_start', e.position().toPoint()))
            if delta.manhattanLength() > 8:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(f"scene:{self.base_name}")
                drag.setMimeData(mime)
                if not self._thumb_lbl.pixmap() is None:
                    drag.setPixmap(self._thumb_lbl.pixmap().scaled(
                        80, 45, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                drag.exec(Qt.CopyAction)


class ShaderBrowserPanel(QWidget):
    """
    5.1 — Panneau de navigation visuelle des shaders.
    Grille de ShaderCard avec thumbnails rendus en arrière-plan.
    """

    add_to_timeline = Signal(str)    # base_name → timeline
    edit_requested  = Signal(str)    # path .frag → éditeur

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_dir = ''
        self._workers: list[ShaderThumbnailWorker] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setFixedHeight(34)
        hdr.setStyleSheet(
            f"background:{C_BG3.name()};border-bottom:1px solid {C_BORDER2.name()};")
        hlay = QHBoxLayout(hdr)
        hlay.setContentsMargins(10, 0, 8, 0)
        lbl = QLabel("  ◈  BROWSER SHADERS")
        lbl.setStyleSheet(
            f"color:{C_CYAN.name()};font:bold 7pt 'Courier New';"
            f"letter-spacing:2px;background:transparent;")
        hlay.addWidget(lbl)
        hlay.addStretch()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filtrer…")
        self._search.setFixedWidth(120)
        self._search.setFixedHeight(22)
        self._search.setStyleSheet(
            f"QLineEdit{{background:{C_BG.name()};color:{C_TXTHI.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:3px;"
            f"padding:2px 6px;font:8pt 'Courier New';}}")
        self._search.textChanged.connect(self._filter_cards)
        hlay.addWidget(self._search)

        btn_refresh = QToolButton()
        btn_refresh.setText("⟳")
        btn_refresh.setToolTip("Regénérer tous les thumbnails")
        btn_refresh.setFixedSize(26, 26)
        btn_refresh.setStyleSheet(
            f"QToolButton{{background:transparent;color:{C_ORANGE.name()};"
            f"border:1px solid {C_ORANGE.name()}40;border-radius:3px;font:10pt;}}"
            f"QToolButton:hover{{background:{C_ORANGE.name()}25;}}")
        btn_refresh.clicked.connect(self.refresh)
        hlay.addWidget(btn_refresh)
        root.addWidget(hdr)

        # Zone scrollable de cartes
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}" + _ss_scroll())

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet(f"background:{C_BG.name()};")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(8, 8, 8, 8)
        self._grid.setSpacing(8)
        self._scroll.setWidget(self._grid_widget)
        root.addWidget(self._scroll)

        self._cards: dict[str, ShaderCard] = {}

    def set_project_dir(self, path: str):
        self._project_dir = path
        self.refresh()

    def refresh(self):
        """Recharge la liste des scènes et relance le rendu des thumbnails."""
        # Annuler les workers en cours
        for w in self._workers:
            w.quit()
        self._workers.clear()

        # Vider la grille
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        if not self._project_dir:
            return

        scenes = scan_scenes(self._project_dir)
        cols   = max(1, self._scroll.width() // (ShaderCard.CARD_W + 8))

        for i, (base_name, pretty_name, _) in enumerate(scenes):
            card = ShaderCard(base_name, self._project_dir)
            card.add_to_timeline.connect(self.add_to_timeline)
            card.edit_requested.connect(self.edit_requested)
            card.double_clicked.connect(self.add_to_timeline)
            self._grid.addWidget(card, i // cols, i % cols)
            self._cards[base_name] = card

            # Lancer le worker de thumbnail
            worker = ShaderThumbnailWorker(self._project_dir, base_name)
            worker.thumbnail_ready.connect(self._on_thumb_ready)
            worker.error_ready.connect(self._on_thumb_error)
            worker.finished.connect(lambda w=worker: self._workers.remove(w)
                                    if w in self._workers else None)
            self._workers.append(worker)
            worker.start()

    def _on_thumb_ready(self, base_name: str, pix: QPixmap):
        if base_name in self._cards:
            self._cards[base_name].set_thumbnail(pix)

    def _on_thumb_error(self, base_name: str, msg: str):
        if base_name in self._cards:
            self._cards[base_name].set_error(msg)

    def _filter_cards(self, text: str):
        for base_name, card in self._cards.items():
            card.setVisible(text.lower() in base_name.lower())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Réorganiser la grille selon la nouvelle largeur
        if self._cards:
            QTimer.singleShot(50, self.refresh)


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 5.3 — DÉTECTION D'ASSETS MANQUANTS + DRAG & DROP + RELINK
# ══════════════════════════════════════════════════════════════════════════════

def validate_project_assets(project_dir: str, project_data: dict) -> list[dict]:
    """
    Scanne le projet et retourne la liste des assets manquants.
    Chaque entrée : {"type": "scene"|"overlay"|"image"|"music",
                     "ref": chemin/nom référencé, "block_idx": int}
    """
    missing = []
    timeline = project_data.get('timeline', [])
    overlays = project_data.get('overlays', [])
    images   = project_data.get('images', [])

    for i, sc in enumerate(timeline):
        base = sc.get('base_name', '')
        path = os.path.join(project_dir, 'scenes', f'scene_{base}.frag')
        if base and not os.path.exists(path):
            missing.append({'type': 'scene', 'ref': base, 'block_idx': i,
                            'expected': path})

    for i, ov in enumerate(overlays):
        effect = ov.get('effect', '')
        if effect:
            found = any(
                os.path.exists(os.path.join(project_dir, d, f'{effect}.frag'))
                for d in ('overlays', 'scenes'))
            if not found:
                missing.append({'type': 'overlay', 'ref': effect, 'block_idx': i,
                                'expected': os.path.join(project_dir, 'overlays',
                                                         f'{effect}.frag')})

    for i, img in enumerate(images):
        rel = img.get('file', '')
        if rel and rel != 'SCROLL_INTERNAL':
            full = os.path.join(project_dir, rel)
            if not os.path.exists(full):
                missing.append({'type': 'image', 'ref': rel, 'block_idx': i,
                                'expected': full})

    music = project_data.get('config', {}).get('MUSIC_FILE', '')
    if music and not os.path.exists(os.path.join(project_dir, music)):
        missing.append({'type': 'music', 'ref': music, 'block_idx': -1,
                        'expected': os.path.join(project_dir, music)})

    return missing


class MissingAssetsDialog(QDialog):
    """
    5.3 — Dialogue affiché au chargement si des assets sont manquants.
    Permet de relinkèr chaque asset manquant via QFileDialog.
    Retourne un dict de remplacements {old_ref: new_ref}.
    """

    def __init__(self, missing: list[dict], project_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assets manquants")
        self.setMinimumWidth(600)
        self.setMinimumHeight(360)
        self._project_dir = project_dir
        self._missing     = missing
        self._relinks: dict[str, str] = {}

        self.setStyleSheet(
            f"QDialog{{background:{C_BG.name()};color:{C_TXT.name()};}}"
            f"QLabel{{font:8pt 'Courier New';color:{C_TXT.name()};"
            f"background:transparent;}}"
            + _ss_btn(C_CYAN) + _ss_scroll())

        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 12, 12, 12)

        hdr = QLabel(f"  ⚠  {len(missing)} asset(s) introuvable(s) dans ce projet")
        hdr.setStyleSheet(
            f"color:{C_ORANGE.name()};font:bold 9pt 'Courier New';"
            f"padding:6px 0;background:transparent;")
        lay.addWidget(hdr)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget{{background:{C_BG2.name()};border:1px solid {C_BORDER.name()};"
            f"font:8pt 'Courier New';}}"
            f"QListWidget::item{{padding:5px 8px;"
            f"border-bottom:1px solid {C_BG3.name()};}}"
            f"QListWidget::item:selected{{background:{C_SEL.name()};"
            f"color:{C_TXTHI.name()};}}" + _ss_scroll())
        for m in missing:
            icon = {'scene': '🎬', 'overlay': '✨', 'image': '🖼',
                    'music': '♪'}.get(m['type'], '?')
            label = f"  {icon}  [{m['type']}]  {m['ref']}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, m)
            item.setForeground(QColor(C_ORANGE.name()))
            self._list.addItem(item)
        self._list.itemDoubleClicked.connect(self._relink_item)
        lay.addWidget(self._list)

        info = QLabel("  Double-clic sur un asset → choisir un fichier de remplacement")
        info.setStyleSheet(f"color:{C_TXTDIM.name()};font:7pt 'Courier New';")
        lay.addWidget(info)

        btns = QHBoxLayout()
        btn_relink = QPushButton("🔗 Relinker sélectionné")
        btn_relink.clicked.connect(lambda: self._relink_item(self._list.currentItem()))
        btns.addWidget(btn_relink)
        btn_all = QPushButton("🔗 Relinker tous…")
        btn_all.clicked.connect(self._relink_all)
        btns.addWidget(btn_all)
        btns.addStretch()
        btn_ok = QPushButton("Continuer quand même")
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_ok)
        lay.addLayout(btns)

    def get_relinks(self) -> dict:
        return self._relinks

    def _relink_item(self, item):
        if not item:
            return
        m = item.data(Qt.UserRole)
        if not m:
            return
        ext_map = {
            'scene':   "Shaders GLSL (*.frag *.glsl)",
            'overlay': "Shaders GLSL (*.frag *.glsl)",
            'image':   "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
            'music':   "Audio (*.mp3 *.ogg *.wav *.flac *.aac)",
        }
        path, _ = QFileDialog.getOpenFileName(
            self, f"Choisir remplacement pour «{m['ref']}»",
            self._project_dir, ext_map.get(m['type'], "Tous (*.*)"))
        if path:
            # Stocker en chemin relatif si dans le project_dir
            rel = os.path.relpath(path, self._project_dir)
            if rel.startswith('..'):
                rel = path   # garder absolu si hors du projet
            self._relinks[m['ref']] = rel
            row = self._list.row(item)
            item.setText(f"  ✓  [{m['type']}]  {m['ref']}  →  {os.path.basename(rel)}")
            item.setForeground(QColor(C_GREEN.name()))

    def _relink_all(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Dossier contenant les assets manquants", self._project_dir)
        if not folder:
            return
        for i in range(self._list.count()):
            item = self._list.item(i)
            m    = item.data(Qt.UserRole)
            if not m or m['ref'] in self._relinks:
                continue
            # Chercher un fichier portant le même nom de base dans ce dossier
            target = os.path.basename(m.get('expected', m['ref']))
            candidate = os.path.join(folder, target)
            if os.path.exists(candidate):
                rel = os.path.relpath(candidate, self._project_dir)
                self._relinks[m['ref']] = rel if not rel.startswith('..') else candidate
                item.setText(f"  ✓  [{m['type']}]  {m['ref']}  →  {target}")
                item.setForeground(QColor(C_GREEN.name()))


# Drag & drop sur AssetList : ajout dans AssetList.mousePressEvent/mouseMoveEvent
# est déjà géré par ShaderCard. On étend AssetList pour supporter le drag natif.

class DraggableAssetList(AssetList):
    """
    AssetList avec support drag-and-drop natif vers la timeline.
    Drag format : "scene:<base_name>" ou "overlay:<name>" etc.
    """

    def __init__(self, kind, color, label, exts, drag_prefix=''):
        super().__init__(kind, color, label, exts)
        self._drag_prefix = drag_prefix or kind
        self._list.setDragEnabled(True)
        self._list.setDefaultDropAction(Qt.CopyAction)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if not (e.buttons() & Qt.LeftButton):
            return
        delta = (e.position().toPoint() -
                 getattr(self, '_drag_pos', e.position().toPoint()))
        if delta.manhattanLength() < 10:
            return
        item = self._list.currentItem()
        if not item:
            return
        val  = item.data(Qt.UserRole)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(f"{self._drag_prefix}:{val}")
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 5.4 — PRESETS DE SCÈNES
# ══════════════════════════════════════════════════════════════════════════════

PRESETS_SUBDIR = 'presets'

class ScenePresetManager:
    """
    5.4 — Sauvegarde et chargement de presets de scène.
    Un preset = {
        "scene_name": str,
        "shader_main": contenu du .frag principal,
        "shader_buffers": {A: code, B: code, ...},
        "params": dict ParamSystem.to_dict() pour cette scène,
        "post": dict post-processing,
        "created": timestamp ISO,
        "description": str
    }
    Stocké dans <project_dir>/presets/<preset_name>.preset.json
    """

    def __init__(self, project_dir: str):
        self._dir = os.path.join(project_dir, PRESETS_SUBDIR)
        os.makedirs(self._dir, exist_ok=True)

    def list_presets(self) -> list[dict]:
        """Retourne la liste des presets disponibles avec métadonnées."""
        presets = []
        if not os.path.isdir(self._dir):
            return presets
        for fn in sorted(os.listdir(self._dir)):
            if fn.endswith('.preset.json'):
                path = os.path.join(self._dir, fn)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        d = json.load(f)
                    presets.append({
                        'name':       fn[:-len('.preset.json')],
                        'scene_name': d.get('scene_name', '?'),
                        'description':d.get('description', ''),
                        'created':    d.get('created', ''),
                        'path':       path,
                    })
                except Exception:
                    pass
        return presets

    def save_preset(self, preset_name: str, scene_name: str,
                    project_dir: str, param_system,
                    post_cfg: dict = None, description: str = '') -> str:
        """Sauvegarde le shader + params + post de la scène en preset."""
        import datetime

        shaders = {}
        sd = os.path.join(project_dir, 'scenes')
        for pfx in ('scene', 'buffer_a', 'buffer_b', 'buffer_c', 'buffer_d'):
            fn   = f'{pfx}_{scene_name}.frag'
            path = os.path.join(sd, fn)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    shaders[pfx] = f.read()

        # Extraire uniquement les données de cette scène du ParamSystem
        all_auto = param_system.to_dict() if param_system else {}
        scene_auto = all_auto.get(scene_name, {})

        preset = {
            'scene_name':    scene_name,
            'description':   description,
            'created':       datetime.datetime.now().isoformat(timespec='seconds'),
            'shaders':       shaders,
            'automation':    scene_auto,
            'post':          post_cfg or {},
        }

        safe_name = preset_name.replace('/', '_').replace('\\', '_')
        out_path  = os.path.join(self._dir, f'{safe_name}.preset.json')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(preset, f, indent=2, ensure_ascii=False)
        return out_path

    def apply_preset(self, preset_path: str, target_scene_name: str,
                     project_dir: str, param_system) -> dict:
        """
        Applique un preset :
        - Copie les shaders dans scenes/ sous le nom target_scene_name
        - Charge l'automation dans param_system
        Retourne le post_cfg du preset.
        """
        with open(preset_path, 'r', encoding='utf-8') as f:
            preset = json.load(f)

        sd = os.path.join(project_dir, 'scenes')
        os.makedirs(sd, exist_ok=True)
        for pfx, code in preset.get('shaders', {}).items():
            fn = f'{pfx}_{target_scene_name}.frag'
            with open(os.path.join(sd, fn), 'w', encoding='utf-8') as f:
                f.write(code)

        # Charger l'automation sous le nouveau nom de scène
        auto_data = preset.get('automation', {})
        if auto_data and param_system:
            param_system.from_dict({target_scene_name: auto_data})

        return preset.get('post', {})

    def delete_preset(self, preset_name: str):
        path = os.path.join(self._dir, f'{preset_name}.preset.json')
        if os.path.exists(path):
            os.remove(path)


class ScenePresetDialog(QDialog):
    """
    5.4 — Dialogue de gestion des presets de scènes.
    Permet de sauvegarder, charger, supprimer des presets.
    """

    preset_applied = Signal(str, str)  # (preset_path, target_scene_name)

    def __init__(self, app_ref, parent=None):
        super().__init__(parent)
        self._app = app_ref
        self.setWindowTitle("Presets de scènes")
        self.setMinimumSize(560, 420)
        self.setStyleSheet(
            f"QDialog{{background:{C_BG.name()};color:{C_TXT.name()};}}"
            f"QLabel{{font:8pt 'Courier New';color:{C_TXT.name()};"
            f"background:transparent;}}"
            + _ss_btn(C_CYAN) + _ss_edit(C_CYAN) + _ss_list(C_CYAN) + _ss_scroll())

        self._mgr = ScenePresetManager(app_ref.project_dir)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 12, 12, 12)

        lay.addWidget(self._sep_lbl("SAUVEGARDER PRESET"))

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("Scène :"))
        self._scene_cb = QComboBox()
        for base, name, _ in scan_scenes(app_ref.project_dir):
            self._scene_cb.addItem(name, userData=base)
        save_row.addWidget(self._scene_cb)
        save_row.addWidget(QLabel("Nom :"))
        self._preset_name = QLineEdit()
        self._preset_name.setPlaceholderText("mon_preset")
        self._preset_name.setFixedWidth(140)
        save_row.addWidget(self._preset_name)
        btn_save = QPushButton("💾 Sauvegarder")
        btn_save.clicked.connect(self._save_preset)
        save_row.addWidget(btn_save)
        lay.addLayout(save_row)

        desc_row = QHBoxLayout()
        desc_row.addWidget(QLabel("Description :"))
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Description optionnelle…")
        desc_row.addWidget(self._desc_edit)
        lay.addLayout(desc_row)

        lay.addWidget(self._sep_lbl("PRESETS DISPONIBLES"))

        self._preset_list = QListWidget()
        self._preset_list.setMinimumHeight(150)
        lay.addWidget(self._preset_list)
        self._refresh_list()

        apply_row = QHBoxLayout()
        apply_row.addWidget(QLabel("Appliquer sur scène :"))
        self._target_cb = QComboBox()
        for base, name, _ in scan_scenes(app_ref.project_dir):
            self._target_cb.addItem(name, userData=base)
        apply_row.addWidget(self._target_cb)
        btn_apply = QPushButton("▶ Appliquer")
        btn_apply.clicked.connect(self._apply_preset)
        apply_row.addWidget(btn_apply)
        btn_del = QPushButton("🗑 Supprimer")
        btn_del.clicked.connect(self._delete_preset)
        apply_row.addWidget(btn_del)
        apply_row.addStretch()
        lay.addLayout(apply_row)

        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close, alignment=Qt.AlignRight)

    def _sep_lbl(self, txt):
        l = QLabel(f"  {txt}")
        l.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:bold 6pt 'Courier New';"
            f"letter-spacing:1.5px;padding:2px 0;background:transparent;"
            f"border-bottom:1px solid {C_BORDER.name()};")
        return l

    def _refresh_list(self):
        self._preset_list.clear()
        for p in self._mgr.list_presets():
            label = (f"  {p['name']}   [{p['scene_name']}]"
                     + (f"  — {p['description']}" if p['description'] else ''))
            item  = QListWidgetItem(label)
            item.setData(Qt.UserRole, p)
            self._preset_list.addItem(item)

    def _save_preset(self):
        name  = self._preset_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Preset", "Entrer un nom de preset.")
            return
        scene = self._scene_cb.currentData()
        if not scene:
            return
        # Trouver le post_cfg de la scène dans la timeline courante
        post_cfg = {}
        for b in self._app.scenes:
            if getattr(b, 'base', '') == scene:
                post_cfg = getattr(b, 'post', {})
                break
        path = self._mgr.save_preset(
            name, scene, self._app.project_dir,
            self._app._param_sys, post_cfg,
            self._desc_edit.text().strip())
        self._refresh_list()
        self._app._set_status(f"Preset «{name}» sauvegardé.")

    def _apply_preset(self):
        item = self._preset_list.currentItem()
        if not item:
            QMessageBox.information(self, "Preset", "Sélectionner un preset dans la liste.")
            return
        p      = item.data(Qt.UserRole)
        target = self._target_cb.currentData()
        if not target:
            return
        post = self._mgr.apply_preset(
            p['path'], target, self._app.project_dir, self._app._param_sys)
        self._app._refresh_assets()
        self._app._set_status(
            f"Preset «{p['name']}» appliqué sur «{target}».")
        self.preset_applied.emit(p['path'], target)

    def _delete_preset(self):
        item = self._preset_list.currentItem()
        if not item:
            return
        p = item.data(Qt.UserRole)
        self._mgr.delete_preset(p['name'])
        self._refresh_list()
        self._app._set_status(f"Preset «{p['name']}» supprimé.")



# ══════════════════════════════════════════════════════════════════════════════
#  FENÊTRES FLOTTANTES — Viewport & Automation
# ══════════════════════════════════════════════════════════════════════════════

class ViewportWindow(QWidget):
    """
    Fenêtre flottante indépendante contenant le ViewportPanel OpenGL.
    Peut être affichée/masquée depuis le menu Fenêtres.
    Sa fermeture la masque seulement (ne la détruit pas).
    """

    window_hidden = Signal()   # émis quand la fenêtre est masquée

    def __init__(self, project_dir: str, main_window, parent=None):
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint)
        self.resize(860, 540)
        self.setStyleSheet(
            f"QWidget{{background:{C_BG2.name()};}}"
            f"QToolButton{{background:transparent;color:{C_CYAN.name()};"
            f"border:1px solid {C_CYAN.name()}40;border-radius:3px;font:9pt;}}"
            f"QToolButton:hover{{background:{C_CYAN.name()}20;}}")

        self._main = main_window

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Barre de titre custom
        titlebar = QWidget()
        titlebar.setFixedHeight(32)
        titlebar.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {C_BG3.name()},stop:1 {C_BG2.name()});"
            f"border-bottom:1px solid {C_BORDER2.name()};")
        tlay = QHBoxLayout(titlebar)
        tlay.setContentsMargins(10, 0, 8, 0)
        ico = QLabel("▣  VIEWPORT")
        ico.setStyleSheet(
            f"color:{C_CYAN.name()};font:bold 8pt 'Courier New';"
            f"letter-spacing:2px;background:transparent;")
        tlay.addWidget(ico)
        tlay.addStretch()

        for txt, tip, slot in [
            ("⟳", "Recharger les shaders", self._reload),
            ("✕", "Fermer (Ctrl+W)",        self.hide),
        ]:
            b = QToolButton()
            b.setText(txt); b.setToolTip(tip)
            b.setFixedSize(26, 26)
            b.clicked.connect(slot)
            tlay.addWidget(b)
        lay.addWidget(titlebar)

        # Le ViewportPanel lui-même
        self.viewport_panel = None
        if VIEWPORT_AVAILABLE:
            try:
                self.viewport_panel = ViewportPanel(project_dir, self)
                lay.addWidget(self.viewport_panel)
            except Exception as e:
                err = QLabel(f"  ⚠ Viewport indisponible : {e}")
                err.setStyleSheet(
                    f"color:{C_ORANGE.name()};font:8pt 'Courier New';"
                    f"padding:20px;background:{C_BG.name()};")
                lay.addWidget(err)

        QShortcut(QKeySequence("Ctrl+W"), self, self.hide)

        # Restaurer la position depuis QSettings si dispo
        self._restore_geometry()

    def _reload(self):
        if self.viewport_panel:
            self.viewport_panel.reload()

    def closeEvent(self, e):
        """Masquer plutôt que fermer."""
        self._save_geometry()
        e.ignore()
        self.hide()

    def hideEvent(self, e):
        self._save_geometry()
        self.window_hidden.emit()
        super().hideEvent(e)

    def _save_geometry(self):
        try:
            s = QSettings()
            s.setValue("viewport_window/geometry", self.saveGeometry())
        except Exception:
            pass

    def _restore_geometry(self):
        try:
            s = QSettings()
            g = s.value("viewport_window/geometry")
            if g:
                self.restoreGeometry(g)
        except Exception:
            pass


class AutomationWindow(QWidget):
    """
    Fenêtre flottante indépendante contenant le panneau Automation (Phase 4).
    Peut être affichée/masquée depuis le menu Fenêtres.
    Sa fermeture la masque seulement.
    """

    window_hidden = Signal()   # émis quand la fenêtre est masquée

    def __init__(self, main_window, parent=None):
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint)
        self.resize(420, 680)
        self.setMinimumWidth(300)
        self.setStyleSheet(
            f"QWidget{{background:{C_BG2.name()};color:{C_TXT.name()};}}"
            f"QLabel{{background:transparent;font:8pt 'Courier New';}}"
            f"QComboBox,QDoubleSpinBox,QSpinBox{{background:{C_BG3.name()};"
            f"color:{C_TXTHI.name()};border:1px solid {C_BORDER2.name()};"
            f"border-radius:3px;padding:3px 6px;font:8pt 'Courier New';}}"
            f"QPushButton{{background:{C_BG3.name()};color:{C_CYAN.name()};"
            f"border:1px solid {C_CYAN.name()}40;border-radius:3px;"
            f"padding:4px 10px;font:bold 7pt 'Courier New';}}"
            f"QPushButton:hover{{background:{C_CYAN.name()}18;}}"
            f"QListWidget{{background:{C_BG.name()};"
            f"border:1px solid {C_BORDER.name()};border-radius:3px;"
            f"font:8pt 'Courier New';}}"
            f"QListWidget::item{{padding:4px 8px;"
            f"border-bottom:1px solid {C_BG3.name()};}}"
            f"QListWidget::item:selected{{background:{C_SEL.name()};"
            f"color:{C_CYAN.name()};}}")

        self._main = main_window

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Barre de titre custom
        titlebar = QWidget()
        titlebar.setFixedHeight(32)
        titlebar.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {C_BG3.name()},stop:1 {C_BG2.name()});"
            f"border-bottom:1px solid {C_BORDER2.name()};")
        tlay = QHBoxLayout(titlebar)
        tlay.setContentsMargins(10, 0, 8, 0)
        ico = QLabel("◈  AUTOMATION")
        ico.setStyleSheet(
            f"color:{C_PURPLE.name()};font:bold 8pt 'Courier New';"
            f"letter-spacing:2px;background:transparent;")
        tlay.addWidget(ico)
        tlay.addStretch()
        btn_close = QToolButton()
        btn_close.setText("✕"); btn_close.setToolTip("Fermer (Ctrl+W)")
        btn_close.setFixedSize(26, 26)
        btn_close.setStyleSheet(
            f"QToolButton{{background:transparent;color:{C_TXTDIM.name()};"
            f"border:1px solid {C_BORDER.name()};border-radius:3px;font:9pt;}}"
            f"QToolButton:hover{{background:{C_ORANGE.name()}20;"
            f"color:{C_ORANGE.name()};}}")
        btn_close.clicked.connect(self.hide)
        tlay.addWidget(btn_close)
        lay.addWidget(titlebar)

        # Le panneau Automation
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}" + _ss_scroll())
        self.auto_panel = AutomationPanel(main_window)
        scroll.setWidget(self.auto_panel)
        lay.addWidget(scroll)

        QShortcut(QKeySequence("Ctrl+W"), self, self.hide)
        self._restore_geometry()

    def closeEvent(self, e):
        self._save_geometry()
        e.ignore()
        self.hide()

    def hideEvent(self, e):
        self._save_geometry()
        self.window_hidden.emit()
        super().hideEvent(e)

    def _save_geometry(self):
        try:
            s = QSettings()
            s.setValue("automation_window/geometry", self.saveGeometry())
        except Exception:
            pass

    def _restore_geometry(self):
        try:
            s = QSettings()
            g = s.value("automation_window/geometry")
            if g:
                self.restoreGeometry(g)
        except Exception:
            pass



# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 6.2 — SYSTÈME DE THÈMES
# ══════════════════════════════════════════════════════════════════════════════

BUILTIN_THEMES = {
    "Neon Void": {
        "bg":      "#060a0f", "bg2": "#0b1018", "bg3": "#101620", "bg4": "#172030",
        "border":  "#1c2a3a", "border2": "#243347",
        "accent":  "#00f5ff", "accent2": "#ff4500", "accent3": "#00ff88",
        "accent4": "#bf5fff", "teal": "#00e5c8", "gold": "#ffcb47",
        "txt":     "#7a9ab5", "txtdim": "#2e4560", "txthi": "#cce8ff",
        "sel":     "#081828",
    },
    "Cyber Amber": {
        "bg":      "#0a0800", "bg2": "#110e00", "bg3": "#1a1500", "bg4": "#221c00",
        "border":  "#2e2200", "border2": "#3d2e00",
        "accent":  "#ffb300", "accent2": "#ff4500", "accent3": "#aaff00",
        "accent4": "#ff69b4", "teal": "#00e5c8", "gold": "#ffcb47",
        "txt":     "#b5953a", "txtdim": "#604800", "txthi": "#ffe082",
        "sel":     "#1a1000",
    },
    "Synthwave Pink": {
        "bg":      "#0d0010", "bg2": "#13001a", "bg3": "#1a0025", "bg4": "#220030",
        "border":  "#3d0060", "border2": "#550080",
        "accent":  "#ff00ff", "accent2": "#00ffff", "accent3": "#ff69b4",
        "accent4": "#9400d3", "teal": "#00e5c8", "gold": "#ffcb47",
        "txt":     "#b07ab5", "txtdim": "#602e60", "txthi": "#ffccff",
        "sel":     "#1a0020",
    },
    "High Contrast": {
        "bg":      "#000000", "bg2": "#0a0a0a", "bg3": "#141414", "bg4": "#1e1e1e",
        "border":  "#333333", "border2": "#555555",
        "accent":  "#ffffff", "accent2": "#ffff00", "accent3": "#00ff00",
        "accent4": "#ff00ff", "teal": "#00ffff", "gold": "#ffff00",
        "txt":     "#cccccc", "txtdim": "#666666", "txthi": "#ffffff",
        "sel":     "#1a1a1a",
    },
    "Light Studio": {
        "bg":      "#f5f5f5", "bg2": "#ebebeb", "bg3": "#e0e0e0", "bg4": "#d5d5d5",
        "border":  "#c0c0c0", "border2": "#a0a0a0",
        "accent":  "#0066cc", "accent2": "#cc3300", "accent3": "#006633",
        "accent4": "#660099", "teal": "#007788", "gold": "#886600",
        "txt":     "#444455", "txtdim": "#888899", "txthi": "#111122",
        "sel":     "#d0e4f8",
    },
}


class ThemeManager:
    """
    6.2 — Gestionnaire de thèmes.
    Charge les thèmes intégrés et les fichiers .theme.json externes.
    Applique dynamiquement les couleurs à toutes les variables globales.
    """

    THEMES_SUBDIR = "themes"

    def __init__(self, project_dir: str = ""):
        self._project_dir = project_dir
        self._current = "Neon Void"

    def list_themes(self) -> list[str]:
        names = list(BUILTIN_THEMES.keys())
        folder = os.path.join(self._project_dir, self.THEMES_SUBDIR)
        if os.path.isdir(folder):
            for fn in sorted(os.listdir(folder)):
                if fn.endswith(".theme.json"):
                    try:
                        with open(os.path.join(folder, fn)) as f:
                            d = json.load(f)
                        name = d.get("name", fn[:-len(".theme.json")])
                        if name not in names:
                            names.append(name)
                    except Exception:
                        pass
        return names

    def get_theme(self, name: str) -> dict:
        if name in BUILTIN_THEMES:
            return dict(BUILTIN_THEMES[name])
        # Chercher dans les fichiers
        folder = os.path.join(self._project_dir, self.THEMES_SUBDIR)
        if os.path.isdir(folder):
            for fn in os.listdir(folder):
                if fn.endswith(".theme.json"):
                    try:
                        with open(os.path.join(folder, fn)) as f:
                            d = json.load(f)
                        if d.get("name") == name:
                            return d
                    except Exception:
                        pass
        return dict(BUILTIN_THEMES["Neon Void"])

    def apply(self, name: str) -> bool:
        """Applique un thème en modifiant les variables globales de couleur."""
        t = self.get_theme(name)
        if not t:
            return False
        self._current = name
        g = globals()
        mapping = {
            "C_BG":      "bg",      "C_BG2":    "bg2",     "C_BG3":    "bg3",
            "C_BG4":     "bg4",     "C_BORDER":  "border",  "C_BORDER2":"border2",
            "C_CYAN":    "accent",  "C_ORANGE":  "accent2", "C_GREEN":  "accent3",
            "C_PURPLE":  "accent4", "C_TEAL":    "teal",    "C_GOLD":   "gold",
            "C_TXT":     "txt",     "C_TXTDIM":  "txtdim",  "C_TXTHI":  "txthi",
            "C_SEL":     "sel",
        }
        for var, key in mapping.items():
            if key in t and var in g:
                g[var].setNamedColor(t[key])
        return True

    def save_theme(self, name: str, project_dir: str):
        """Sauvegarde le thème courant comme fichier .theme.json."""
        folder = os.path.join(project_dir, self.THEMES_SUBDIR)
        os.makedirs(folder, exist_ok=True)
        t = self.get_theme(self._current)
        t["name"] = name
        safe = name.replace("/", "_").replace(" ", "_")
        with open(os.path.join(folder, f"{safe}.theme.json"), "w") as f:
            json.dump(t, f, indent=2)


class ThemeDialog(QDialog):
    """6.2 — Dialogue de sélection et édition de thème."""

    theme_applied = Signal(str)

    def __init__(self, theme_mgr: ThemeManager, parent=None):
        super().__init__(parent)
        self._mgr = theme_mgr
        self.setWindowTitle("Thèmes visuels")
        self.setMinimumSize(480, 360)
        self.setStyleSheet(
            f"QDialog{{background:{C_BG.name()};color:{C_TXT.name()};}}"
            f"QLabel{{font:8pt 'Courier New';background:transparent;}}"
            + _ss_btn(C_CYAN) + _ss_list(C_CYAN) + _ss_scroll())

        lay = QVBoxLayout(self)
        lay.setSpacing(8); lay.setContentsMargins(12, 12, 12, 12)

        hdr = QLabel("  ◈  THÈMES VISUELS")
        hdr.setStyleSheet(
            f"color:{C_PURPLE.name()};font:bold 9pt 'Courier New';"
            f"letter-spacing:2px;padding:4px 0;")
        lay.addWidget(hdr)

        lay.addWidget(self._sep("THÈME ACTIF"))
        self._list = QListWidget()
        for name in theme_mgr.list_themes():
            it = QListWidgetItem(f"  {name}")
            it.setData(Qt.UserRole, name)
            if name == theme_mgr._current:
                it.setForeground(QColor(C_CYAN.name()))
            self._list.addItem(it)
        self._list.setFixedHeight(180)
        lay.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_apply = QPushButton("▶ Appliquer")
        btn_apply.clicked.connect(self._apply)
        btn_row.addWidget(btn_apply)

        btn_save = QPushButton("💾 Sauvegarder comme…")
        btn_save.clicked.connect(self._save_as)
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Section import fichier
        lay.addWidget(self._sep("IMPORTER .theme.json"))
        import_row = QHBoxLayout()
        self._import_edit = QLineEdit()
        self._import_edit.setPlaceholderText("Chemin vers le fichier .theme.json…")
        self._import_edit.setStyleSheet(
            f"QLineEdit{{background:{C_BG3.name()};color:{C_TXTHI.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:3px;"
            f"padding:3px 6px;font:8pt 'Courier New';}}")
        import_row.addWidget(self._import_edit)
        btn_browse = QPushButton("…")
        btn_browse.setFixedWidth(28)
        btn_browse.clicked.connect(self._browse_theme)
        import_row.addWidget(btn_browse)
        btn_import = QPushButton("Importer")
        btn_import.clicked.connect(self._import_theme)
        import_row.addWidget(btn_import)
        lay.addLayout(import_row)

        lay.addStretch()
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close, alignment=Qt.AlignRight)

    def _sep(self, txt):
        l = QLabel(f"  {txt}")
        l.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:bold 6pt 'Courier New';"
            f"letter-spacing:1.5px;padding:2px 0;"
            f"border-bottom:1px solid {C_BORDER.name()};")
        return l

    def _apply(self):
        item = self._list.currentItem()
        if not item: return
        name = item.data(Qt.UserRole)
        self._mgr.apply(name)
        self.theme_applied.emit(name)
        # Mettre en évidence l'item actif
        for i in range(self._list.count()):
            it = self._list.item(i)
            col = C_CYAN if it.data(Qt.UserRole) == name else C_TXT
            it.setForeground(QColor(col.name()))

    def _save_as(self):
        mw = self.parent()
        name, ok = QInputDialog.getText(self, "Sauvegarder thème", "Nom du thème :")
        if ok and name.strip() and mw:
            self._mgr.save_theme(name.strip(),
                                  getattr(mw, 'project_dir', '.'))
            it = QListWidgetItem(f"  {name.strip()}")
            it.setData(Qt.UserRole, name.strip())
            self._list.addItem(it)

    def _browse_theme(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir thème", "", "Thème JSON (*.theme.json);;JSON (*.json)")
        if path:
            self._import_edit.setText(path)

    def _import_theme(self):
        path = self._import_edit.text().strip()
        if not path or not os.path.exists(path):
            return
        mw = self.parent()
        if mw:
            dest_dir = os.path.join(
                getattr(mw, 'project_dir', '.'), ThemeManager.THEMES_SUBDIR)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(path, os.path.join(dest_dir, os.path.basename(path)))
        # Recharger la liste
        for name in self._mgr.list_themes():
            found = False
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.UserRole) == name:
                    found = True; break
            if not found:
                it = QListWidgetItem(f"  {name}")
                it.setData(Qt.UserRole, name)
                self._list.addItem(it)


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 6.3 — PALETTE DE COMMANDES (Ctrl+P)
# ══════════════════════════════════════════════════════════════════════════════

class CommandPalette(QDialog):
    """
    6.3 — Palette de commandes style VS Code.
    Fuzzy-search sur toutes les actions de la GUI.
    Ctrl+P pour ouvrir, Entrée pour exécuter, Échap pour fermer.
    """

    def __init__(self, commands: list[tuple[str, callable]], parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Popup)
        self._commands = commands   # [(label, callback), ...]
        self._filtered = list(commands)

        self.setFixedWidth(520)
        self.setStyleSheet(
            f"QDialog{{background:{C_BG2.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:6px;}}"
            f"QLabel{{background:transparent;font:8pt 'Courier New';}}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Champ de recherche
        self._search = QLineEdit()
        self._search.setPlaceholderText("  ⌕  Rechercher une commande…")
        self._search.setStyleSheet(
            f"QLineEdit{{background:{C_BG3.name()};color:{C_TXTHI.name()};"
            f"border:1px solid {C_CYAN.name()}60;border-radius:4px;"
            f"padding:6px 10px;font:10pt 'Courier New';}}"
            f"QLineEdit:focus{{border:1px solid {C_CYAN.name()};}}")
        self._search.textChanged.connect(self._filter)
        lay.addWidget(self._search)

        # Liste de résultats
        self._list = QListWidget()
        self._list.setFixedHeight(320)
        self._list.setStyleSheet(
            f"QListWidget{{background:{C_BG.name()};border:none;"
            f"font:9pt 'Courier New';}}"
            f"QListWidget::item{{padding:6px 12px;"
            f"border-bottom:1px solid {C_BG3.name()};}}"
            f"QListWidget::item:selected{{background:{C_SEL.name()};"
            f"color:{C_CYAN.name()};}}"
            + _ss_scroll())
        self._list.itemActivated.connect(self._execute)
        self._list.itemDoubleClicked.connect(self._execute)
        lay.addWidget(self._list)

        hint = QLabel("  ↑↓ naviguer  ·  Entrée exécuter  ·  Échap fermer")
        hint.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:6pt 'Courier New';padding:2px 4px;")
        lay.addWidget(hint)

        self._populate(commands)

        # Raccourcis
        QShortcut(QKeySequence("Return"), self, self._execute_current)
        QShortcut(QKeySequence("Escape"), self, self.reject)
        QShortcut(QKeySequence("Down"),   self, self._next)
        QShortcut(QKeySequence("Up"),     self, self._prev)

        self._search.setFocus()

    def _populate(self, cmds):
        self._list.clear()
        for label, _ in cmds:
            it = QListWidgetItem(f"  {label}")
            self._list.addItem(it)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _filter(self, text: str):
        t = text.lower().strip()
        self._filtered = [(l, c) for l, c in self._commands
                          if not t or t in l.lower()]
        self._populate(self._filtered)

    def _execute(self, item):
        row = self._list.row(item)
        if 0 <= row < len(self._filtered):
            self.accept()
            try:
                self._filtered[row][1]()
            except Exception as e:
                print(f"[CommandPalette] Erreur : {e}")

    def _execute_current(self):
        item = self._list.currentItem()
        if item:
            self._execute(item)

    def _next(self):
        r = self._list.currentRow()
        if r < self._list.count() - 1:
            self._list.setCurrentRow(r + 1)

    def _prev(self):
        r = self._list.currentRow()
        if r > 0:
            self._list.setCurrentRow(r - 1)


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 6.3 — ÉDITEUR DE RACCOURCIS
# ══════════════════════════════════════════════════════════════════════════════

KEYMAP_FILE = "keymap.json"

DEFAULT_KEYMAP = {
    "play_pause":         "Space",
    "delete":             "Delete",
    "save":               "Ctrl+S",
    "duplicate":          "Ctrl+D",
    "home":               "Home",
    "undo":               "Ctrl+Z",
    "redo":               "Ctrl+Y",
    "copy":               "Ctrl+C",
    "paste":              "Ctrl+V",
    "select_all":         "Ctrl+A",
    "deselect":           "Escape",
    "add_marker":         "M",
    "loop_in":            "I",
    "loop_out":           "O",
    "viewport":           "Ctrl+Shift+V",
    "automation":         "Ctrl+Shift+A",
    "command_palette":    "Ctrl+P",
}

KEYMAP_LABELS = {
    "play_pause":      "Lecture / Pause",
    "delete":          "Supprimer la sélection",
    "save":            "Sauvegarder",
    "duplicate":       "Dupliquer",
    "home":            "Retour au début",
    "undo":            "Annuler",
    "redo":            "Rétablir",
    "copy":            "Copier",
    "paste":           "Coller",
    "select_all":      "Tout sélectionner",
    "deselect":        "Désélectionner",
    "add_marker":      "Ajouter un marqueur",
    "loop_in":         "Loop In",
    "loop_out":        "Loop Out",
    "viewport":        "Afficher/masquer le Viewport",
    "automation":      "Afficher/masquer l'Automation",
    "command_palette": "Ouvrir la palette de commandes",
}


class KeymapEditor(QDialog):
    """6.3 — Éditeur de raccourcis clavier personnalisables."""

    keymap_changed = Signal(dict)

    def __init__(self, keymap: dict, project_dir: str, parent=None):
        super().__init__(parent)
        self._keymap = dict(keymap)
        self._project_dir = project_dir
        self.setWindowTitle("Raccourcis clavier")
        self.setMinimumSize(500, 480)
        self.setStyleSheet(
            f"QDialog{{background:{C_BG.name()};color:{C_TXT.name()};}}"
            f"QLabel{{font:8pt 'Courier New';background:transparent;}}"
            + _ss_btn(C_CYAN) + _ss_scroll())

        lay = QVBoxLayout(self)
        lay.setSpacing(8); lay.setContentsMargins(12, 12, 12, 12)

        hdr = QLabel("  ◈  RACCOURCIS CLAVIER")
        hdr.setStyleSheet(
            f"color:{C_CYAN.name()};font:bold 9pt 'Courier New';"
            f"letter-spacing:2px;padding:4px 0;")
        lay.addWidget(hdr)

        # Table d'édition
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}" + _ss_scroll())
        container = QWidget()
        container.setStyleSheet(f"background:{C_BG.name()};")
        grid = QGridLayout(container)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(4)

        # Entêtes
        for col, txt in enumerate(["Action", "Raccourci"]):
            lbl = QLabel(f"  {txt}")
            lbl.setStyleSheet(
                f"color:{C_TXTDIM.name()};font:bold 7pt 'Courier New';"
                f"letter-spacing:1px;border-bottom:1px solid {C_BORDER.name()};"
                f"padding:4px 0;")
            grid.addWidget(lbl, 0, col)

        self._editors: dict[str, QLineEdit] = {}
        for row, (key, label) in enumerate(KEYMAP_LABELS.items(), 1):
            lbl = QLabel(f"  {label}")
            lbl.setStyleSheet(f"color:{C_TXT.name()};font:8pt 'Courier New';")
            grid.addWidget(lbl, row, 0)

            ed = QLineEdit(self._keymap.get(key, DEFAULT_KEYMAP.get(key, "")))
            ed.setStyleSheet(
                f"QLineEdit{{background:{C_BG3.name()};color:{C_CYAN.name()};"
                f"border:1px solid {C_BORDER2.name()};border-radius:3px;"
                f"padding:3px 8px;font:8pt 'Courier New';}}"
                f"QLineEdit:focus{{border:1px solid {C_CYAN.name()};}}")
            ed.setPlaceholderText("Ex: Ctrl+Shift+X")
            self._editors[key] = ed
            grid.addWidget(ed, row, 1)

        scroll.setWidget(container)
        lay.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_reset = QPushButton("↺ Réinitialiser par défaut")
        btn_reset.clicked.connect(self._reset_defaults)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        btn_save = QPushButton("💾 Sauvegarder")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

    def _reset_defaults(self):
        for key, ed in self._editors.items():
            ed.setText(DEFAULT_KEYMAP.get(key, ""))

    def _save(self):
        for key, ed in self._editors.items():
            self._keymap[key] = ed.text().strip()
        path = os.path.join(self._project_dir, KEYMAP_FILE)
        try:
            with open(path, "w") as f:
                json.dump(self._keymap, f, indent=2)
        except Exception as e:
            print(f"[KeymapEditor] Erreur sauvegarde : {e}")
        self.keymap_changed.emit(self._keymap)
        self.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 6.4 — PANNEAU DE LOGS STRUCTURÉS
# ══════════════════════════════════════════════════════════════════════════════

class LogPanel(QDialog):
    """
    6.4 — Panneau de logs structuré avec filtres par niveau et source.
    Exportable en .log.
    """

    _instance = None   # singleton léger

    LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")
    COLORS = {"DEBUG": "#5a7a9a", "INFO": "#7a9ab5",
              "WARN":  "#ffcb47", "ERROR": "#ff4500"}

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        LogPanel._instance = self
        self.setWindowTitle("MEGADEMO — Logs")
        self.resize(700, 440)
        self._entries: list[tuple] = []   # (timestamp, level, source, msg)

        self.setStyleSheet(
            f"QDialog{{background:{C_BG.name()};color:{C_TXT.name()};}}"
            f"QLabel{{background:transparent;font:8pt 'Courier New';}}"
            + _ss_btn(C_CYAN) + _ss_scroll())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Barre de filtres
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Filtrer :"))
        self._level_cb = QComboBox()
        self._level_cb.addItem("Tous", None)
        for lv in self.LEVELS:
            self._level_cb.addItem(lv, lv)
        self._level_cb.currentIndexChanged.connect(self._refresh)
        self._level_cb.setStyleSheet(
            f"QComboBox{{background:{C_BG3.name()};color:{C_TXTHI.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:3px;"
            f"padding:3px 6px;font:8pt 'Courier New';}}")
        bar.addWidget(self._level_cb)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Rechercher dans les logs…")
        self._search_edit.setStyleSheet(
            f"QLineEdit{{background:{C_BG3.name()};color:{C_TXTHI.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:3px;"
            f"padding:3px 8px;font:8pt 'Courier New';}}")
        self._search_edit.textChanged.connect(self._refresh)
        bar.addWidget(self._search_edit)

        btn_clear = QPushButton("🗑 Effacer")
        btn_clear.clicked.connect(self._clear)
        bar.addWidget(btn_clear)

        btn_export = QPushButton("💾 Export .log")
        btn_export.clicked.connect(self._export)
        bar.addWidget(btn_export)
        lay.addLayout(bar)

        self._log_widget = QPlainTextEdit()
        self._log_widget.setReadOnly(True)
        self._log_widget.setFont(QFont("Courier New", 8))
        self._log_widget.setStyleSheet(
            f"QPlainTextEdit{{background:{C_BG.name()};color:{C_TXT.name()};"
            f"border:1px solid {C_BORDER.name()};border-radius:3px;}}"
            + _ss_scroll())
        lay.addWidget(self._log_widget)

        QShortcut(QKeySequence("Ctrl+W"), self, self.hide)

    def log(self, msg: str, level: str = "INFO", source: str = "GUI"):
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        self._entries.append((ts, level.upper(), source, msg))
        self._refresh()

    def _refresh(self):
        lv_filter = self._level_cb.currentData()
        txt_filter = self._search_edit.text().lower()
        lines = []
        for ts, lv, src, msg in self._entries:
            if lv_filter and lv != lv_filter:
                continue
            if txt_filter and txt_filter not in msg.lower() and txt_filter not in src.lower():
                continue
            col = self.COLORS.get(lv, "#7a9ab5")
            lines.append(f"[{ts}] [{lv:<5}] [{src:<12}] {msg}")
        self._log_widget.setPlainText("\n".join(lines))
        sb = self._log_widget.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear(self):
        self._entries.clear()
        self._log_widget.clear()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter les logs", "megademo.log",
            "Fichiers log (*.log);;Texte (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                for ts, lv, src, msg in self._entries:
                    f.write(f"[{ts}] [{lv:<5}] [{src:<12}] {msg}\n")

    def closeEvent(self, e):
        e.ignore(); self.hide()


def log_global(msg: str, level: str = "INFO", source: str = "GUI"):
    """Fonction utilitaire pour logger depuis n'importe où."""
    if LogPanel._instance:
        LogPanel._instance.log(msg, level, source)


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 6.3 — MACROS
# ══════════════════════════════════════════════════════════════════════════════

class MacroManager:
    """
    6.3 — Enregistreur et exécuteur de macros.
    Une macro = liste d'actions nommées exécutables en séquence.
    """

    MACROS_FILE = "macros.json"

    def __init__(self, project_dir: str):
        self._dir   = project_dir
        self._macros: dict[str, list[str]] = {}
        self._recording: list[str] = []
        self._is_recording = False
        self._load()

    def _load(self):
        path = os.path.join(self._dir, self.MACROS_FILE)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    self._macros = json.load(f)
            except Exception:
                pass

    def _save(self):
        path = os.path.join(self._dir, self.MACROS_FILE)
        try:
            with open(path, "w") as f:
                json.dump(self._macros, f, indent=2)
        except Exception:
            pass

    def list_macros(self) -> list[str]:
        return list(self._macros.keys())

    def start_record(self):
        self._recording = []
        self._is_recording = True

    def record_action(self, action_name: str):
        if self._is_recording:
            self._recording.append(action_name)

    def stop_record(self, macro_name: str):
        self._is_recording = False
        if macro_name.strip():
            self._macros[macro_name.strip()] = list(self._recording)
            self._save()
        self._recording = []

    def delete(self, name: str):
        self._macros.pop(name, None)
        self._save()

    def get_actions(self, name: str) -> list[str]:
        return self._macros.get(name, [])


class MacroDialog(QDialog):
    """6.3 — Dialogue de gestion des macros."""

    run_macro = Signal(str)   # action_name à exécuter

    def __init__(self, macro_mgr: MacroManager, parent=None):
        super().__init__(parent)
        self._mgr = macro_mgr
        self.setWindowTitle("Macros")
        self.setMinimumSize(420, 380)
        self.setStyleSheet(
            f"QDialog{{background:{C_BG.name()};color:{C_TXT.name()};}}"
            f"QLabel{{font:8pt 'Courier New';background:transparent;}}"
            + _ss_btn(C_CYAN) + _ss_list(C_CYAN) + _ss_scroll())

        lay = QVBoxLayout(self)
        lay.setSpacing(8); lay.setContentsMargins(12, 12, 12, 12)

        hdr = QLabel("  ◈  MACROS")
        hdr.setStyleSheet(
            f"color:{C_GOLD.name()};font:bold 9pt 'Courier New';"
            f"letter-spacing:2px;padding:4px 0;")
        lay.addWidget(hdr)

        info = QLabel(
            "  Une macro enregistre une séquence d'actions et la rejoue en un clic.\n"
            "  Utilisez le menu Édition → Macros pour enregistrer.")
        info.setStyleSheet(f"color:{C_TXTDIM.name()};font:7pt 'Courier New';")
        info.setWordWrap(True)
        lay.addWidget(info)

        self._list = QListWidget()
        self._list.setMinimumHeight(160)
        self._refresh()
        lay.addWidget(self._list)

        # Détail
        self._detail = QLabel("")
        self._detail.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:7pt 'Courier New';"
            f"background:{C_BG2.name()};padding:4px 8px;border-radius:3px;")
        self._detail.setWordWrap(True)
        lay.addWidget(self._detail)
        self._list.currentRowChanged.connect(self._on_select)

        btn_row = QHBoxLayout()
        btn_run = QPushButton("▶ Exécuter")
        btn_run.clicked.connect(self._run)
        btn_row.addWidget(btn_run)
        btn_del = QPushButton("🗑 Supprimer")
        btn_del.clicked.connect(self._delete)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

    def _refresh(self):
        self._list.clear()
        for name in self._mgr.list_macros():
            n = len(self._mgr.get_actions(name))
            it = QListWidgetItem(f"  {name}  ({n} action(s))")
            it.setData(Qt.UserRole, name)
            self._list.addItem(it)

    def _on_select(self, row):
        if row < 0: return
        item = self._list.item(row)
        if not item: return
        name = item.data(Qt.UserRole)
        actions = self._mgr.get_actions(name)
        self._detail.setText("  Actions : " + " → ".join(actions[:10])
                             + ("…" if len(actions) > 10 else ""))

    def _run(self):
        item = self._list.currentItem()
        if not item: return
        name = item.data(Qt.UserRole)
        for action in self._mgr.get_actions(name):
            self.run_macro.emit(action)

    def _delete(self):
        item = self._list.currentItem()
        if not item: return
        self._mgr.delete(item.data(Qt.UserRole))
        self._refresh()


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 7.4 — QUEUE D'EXPORT + RAPPORT HTML + WEBHOOK
# ══════════════════════════════════════════════════════════════════════════════

class ExportQueueItem:
    """Un job dans la queue d'export."""
    def __init__(self, label: str, output_path: str, width: int, height: int,
                 fps: int, project_dir: str, project_data: dict,
                 codec: str = "h264", crf: int = 18,
                 render_in: float = None, render_out: float = None,
                 webhook_url: str = ""):
        self.label        = label
        self.output_path  = output_path
        self.width        = width
        self.height       = height
        self.fps          = fps
        self.project_dir  = project_dir
        self.project_data = project_data
        self.codec        = codec
        self.crf          = crf
        self.render_in    = render_in
        self.render_out   = render_out
        self.webhook_url  = webhook_url
        self.status       = "En attente"   # "En attente" | "Rendu" | "Erreur" | "OK"
        self.progress     = 0


class ExportQueueDialog(QDialog):
    """
    7.4 — File d'attente d'exports multi-résolutions.
    Permet d'empiler plusieurs exports (résolutions, régions) et de les lancer en séquence.
    """

    def __init__(self, parent, project_dir: str, project_data: dict):
        super().__init__(parent)
        self._dir   = project_dir
        self._data  = project_data
        self._jobs: list[ExportQueueItem] = []
        self._worker = None
        self._current_engine = None

        self.setWindowTitle("Queue d'export")
        self.setMinimumSize(700, 520)
        self.setStyleSheet(
            f"QDialog{{background:{C_BG.name()};color:{C_TXT.name()};}}"
            f"QLabel{{font:8pt 'Courier New';background:transparent;}}"
            + _ss_btn(C_CYAN) + _ss_edit(C_CYAN) + _ss_scroll()
            + f"QTextEdit{{background:{C_BG2.name()};color:{C_TXTDIM.name()};"
            f"border:1px solid {C_BORDER2.name()};font:8pt 'Courier New';}}")

        lay = QVBoxLayout(self)
        lay.setSpacing(8); lay.setContentsMargins(12, 12, 12, 12)

        hdr = QLabel("  ◈  QUEUE D'EXPORT")
        hdr.setStyleSheet(
            f"color:{C_CYAN.name()};font:bold 9pt 'Courier New';"
            f"letter-spacing:2px;padding:4px 0;")
        lay.addWidget(hdr)

        # Formulaire d'ajout
        add_grp = QWidget()
        add_grp.setStyleSheet(
            f"background:{C_BG2.name()};border-radius:4px;"
            f"border:1px solid {C_BORDER.name()};")
        ag = QGridLayout(add_grp)
        ag.setContentsMargins(10, 8, 10, 8); ag.setSpacing(6)

        sl = f"color:{C_TXTDIM.name()};font:7pt 'Courier New';"
        def _lbl(t): l = QLabel(t); l.setStyleSheet(sl); return l

        cfg = project_data.get("config", {})
        res = cfg.get("RES", [1920, 1080])

        ag.addWidget(_lbl("Fichier de sortie"), 0, 0)
        out_row = QHBoxLayout()
        default_name = cfg.get("WINDOW_TITLE", "megademo").lower().replace(" ", "_")
        self._add_out = QLineEdit(os.path.join(project_dir, "export", f"{default_name}.mp4"))
        out_row.addWidget(self._add_out)
        btn_br = QPushButton("…"); btn_br.setFixedWidth(28)
        btn_br.clicked.connect(self._browse_add)
        out_row.addWidget(btn_br)
        ag.addLayout(out_row, 0, 1, 1, 3)

        ag.addWidget(_lbl("Résolution"), 1, 0)
        self._add_w = QSpinBox(); self._add_w.setRange(320, 7680); self._add_w.setValue(res[0])
        self._add_h = QSpinBox(); self._add_h.setRange(240, 4320); self._add_h.setValue(res[1])
        rres = QHBoxLayout(); rres.addWidget(self._add_w)
        rres.addWidget(QLabel("×")); rres.addWidget(self._add_h)
        ag.addLayout(rres, 1, 1)

        ag.addWidget(_lbl("FPS"), 1, 2)
        self._add_fps = QComboBox()
        for f in ("24", "25", "30", "60"):
            self._add_fps.addItem(f"{f} fps", int(f))
        self._add_fps.setCurrentIndex(3)
        ag.addWidget(self._add_fps, 1, 3)

        ag.addWidget(_lbl("Codec"), 2, 0)
        self._add_codec = QComboBox()
        for c, lbl in [("h264","H.264"), ("h265","H.265/HEVC"),
                       ("prores","ProRes 4444"), ("vp9","VP9"),
                       ("png_seq","Séquence PNG"), ("exr_seq","Séquence EXR")]:
            self._add_codec.addItem(lbl, c)
        ag.addWidget(self._add_codec, 2, 1)

        ag.addWidget(_lbl("CRF (qualité)"), 2, 2)
        self._add_crf = QSpinBox(); self._add_crf.setRange(0, 51); self._add_crf.setValue(18)
        ag.addWidget(self._add_crf, 2, 3)

        ag.addWidget(_lbl("Webhook URL"), 3, 0)
        self._add_webhook = QLineEdit()
        self._add_webhook.setPlaceholderText("https://hooks.slack.com/… (optionnel)")
        ag.addWidget(self._add_webhook, 3, 1, 1, 3)

        btn_add = QPushButton("＋ Ajouter à la queue")
        btn_add.clicked.connect(self._add_job)
        ag.addWidget(btn_add, 4, 0, 1, 4)

        lay.addWidget(add_grp)

        # Liste des jobs
        self._job_list = QListWidget()
        self._job_list.setFixedHeight(130)
        self._job_list.setStyleSheet(
            f"QListWidget{{background:{C_BG2.name()};border:1px solid {C_BORDER.name()};"
            f"font:8pt 'Courier New';}}"
            f"QListWidget::item{{padding:4px 8px;"
            f"border-bottom:1px solid {C_BG3.name()};}}" + _ss_scroll())
        lay.addWidget(self._job_list)

        btn_row2 = QHBoxLayout()
        btn_del_job = QPushButton("🗑 Retirer sélectionné")
        btn_del_job.clicked.connect(self._remove_job)
        btn_row2.addWidget(btn_del_job)
        btn_row2.addStretch()
        lay.addLayout(btn_row2)

        # Progression globale
        self._global_prog = QProgressBar()
        self._global_prog.setRange(0, 100); self._global_prog.setValue(0)
        self._global_prog.setStyleSheet(
            f"QProgressBar{{background:{C_BG3.name()};border:1px solid {C_BORDER.name()};"
            f"border-radius:3px;height:16px;text-align:center;font:7pt 'Courier New';}}"
            f"QProgressBar::chunk{{background:{C_CYAN.name()};border-radius:2px;}}")
        self._global_prog.setFormat("En attente")
        lay.addWidget(self._global_prog)

        # Log
        self._log = QTextEdit(); self._log.setReadOnly(True); self._log.setFixedHeight(80)
        lay.addWidget(self._log)

        btn_run_row = QHBoxLayout()
        self._btn_run_all = QPushButton("▶  LANCER TOUS LES EXPORTS")
        self._btn_run_all.clicked.connect(self._run_all)
        btn_run_row.addWidget(self._btn_run_all)
        self._btn_stop = QPushButton("✖  STOPPER")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop)
        btn_run_row.addWidget(self._btn_stop)
        btn_run_row.addStretch()
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        btn_run_row.addWidget(btn_close)
        lay.addLayout(btn_run_row)

        self._current_job_idx = 0

    def _browse_add(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Fichier de sortie", self._add_out.text(), "Vidéo (*.mp4 *.mov);;Tous (*.*)")
        if path: self._add_out.setText(path)

    def _add_job(self):
        out = self._add_out.text().strip()
        if not out: return
        label = f"{self._add_w.value()}×{self._add_h.value()} @ {self._add_fps.currentData()} fps  —  {os.path.basename(out)}"
        job = ExportQueueItem(
            label=label, output_path=out,
            width=self._add_w.value(), height=self._add_h.value(),
            fps=self._add_fps.currentData(),
            project_dir=self._dir, project_data=self._data,
            codec=self._add_codec.currentData(), crf=self._add_crf.value(),
            webhook_url=self._add_webhook.text().strip())
        self._jobs.append(job)
        it = QListWidgetItem(f"  ⏳  {label}")
        it.setData(Qt.UserRole, len(self._jobs) - 1)
        self._job_list.addItem(it)

    def _remove_job(self):
        row = self._job_list.currentRow()
        if row >= 0:
            self._job_list.takeItem(row)
            # Ne pas supprimer de self._jobs pour garder les index cohérents

    def _log_msg(self, msg):
        self._log.append(msg)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())

    def _run_all(self):
        pending = [j for j in self._jobs if j.status == "En attente"]
        if not pending:
            QMessageBox.information(self, "Queue", "Aucun job en attente.")
            return
        self._btn_run_all.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._current_job_idx = 0
        self._run_next()

    def _run_next(self):
        pending = [j for j in self._jobs if j.status == "En attente"]
        if not pending:
            self._btn_run_all.setEnabled(True)
            self._btn_stop.setEnabled(False)
            self._global_prog.setFormat("✔ Tous les exports terminés !")
            self._log_msg("\n✔ Queue d'export complète.")
            return

        job = pending[0]
        job.status = "Rendu"
        total = len(self._jobs)
        done  = sum(1 for j in self._jobs if j.status in ("OK", "Erreur"))
        self._global_prog.setValue(int(done * 100 / max(total, 1)))
        self._global_prog.setFormat(f"Job {done+1}/{total} : {job.label}")
        self._log_msg(f"\n▶ Export : {job.label}")

        from export_engine import ExportEngine
        engine = ExportEngine(job.project_dir, job.project_data,
                              width=job.width, height=job.height, fps=job.fps)
        engine.on_log      = lambda m: self._log_msg(m)
        engine.on_progress = lambda c, t: None
        self._current_engine = engine

        out = job.output_path

        def _run_job():
            ok = engine.run(out)
            return ok, out if ok else "Échec"

        worker = ExportWorker(_run_job)
        worker.log_signal.connect(self._log_msg)
        worker.done_signal.connect(lambda ok, msg, j=job: self._on_job_done(ok, msg, j))
        self._worker = worker
        worker.start()

    def _on_job_done(self, ok: bool, msg: str, job: ExportQueueItem):
        job.status = "OK" if ok else "Erreur"
        if ok:
            self._log_msg(f"✔ Terminé : {msg}")
            # Rapport HTML
            self._generate_report(job)
            # Webhook
            if job.webhook_url:
                self._send_webhook(job)
        else:
            self._log_msg(f"✖ Erreur : {msg}")
        # Mettre à jour l'affichage de la liste
        for i in range(self._job_list.count()):
            it = self._job_list.item(i)
            idx = it.data(Qt.UserRole)
            if idx is not None and 0 <= idx < len(self._jobs):
                j = self._jobs[idx]
                icon = {"OK": "✔", "Erreur": "✖", "En attente": "⏳", "Rendu": "⏳"}.get(j.status, "?")
                it.setText(f"  {icon}  {j.label}")
        self._run_next()

    def _stop(self):
        if self._current_engine:
            self._current_engine.cancel()
        for j in self._jobs:
            if j.status == "En attente":
                pass  # laisser en attente

    def _generate_report(self, job: ExportQueueItem):
        """7.4 — Génère un rapport HTML après un export réussi."""
        try:
            import datetime
            size_mb = os.path.getsize(job.output_path) / (1024 * 1024) if os.path.exists(job.output_path) else 0
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'>
<title>Export Report — {job.label}</title>
<style>
  body{{font-family:'Courier New',monospace;background:#060a0f;color:#7a9ab5;padding:40px;}}
  h1{{color:#00f5ff;letter-spacing:3px;}} h2{{color:#bf5fff;}}
  table{{border-collapse:collapse;width:100%;}}
  td,th{{border:1px solid #1c2a3a;padding:8px 12px;}}
  th{{background:#0b1018;color:#cce8ff;}}
  .ok{{color:#00ff88;}} .label{{color:#ffcb47;font-weight:bold;}}
</style></head><body>
<h1>◈ MEGADEMO — RAPPORT D'EXPORT</h1>
<p class='label'>Généré le {ts}</p>
<h2>Détails</h2>
<table>
<tr><th>Champ</th><th>Valeur</th></tr>
<tr><td>Fichier</td><td>{job.output_path}</td></tr>
<tr><td>Résolution</td><td>{job.width}×{job.height}</td></tr>
<tr><td>FPS</td><td>{job.fps}</td></tr>
<tr><td>Codec</td><td>{job.codec}</td></tr>
<tr><td>Taille</td><td>{size_mb:.1f} MB</td></tr>
<tr><td>Statut</td><td class='ok'>✔ Terminé</td></tr>
</table>
</body></html>"""
            report_path = job.output_path.rsplit(".", 1)[0] + "_report.html"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html)
            self._log_msg(f"  📄 Rapport : {report_path}")
        except Exception as e:
            self._log_msg(f"  ⚠ Rapport impossible : {e}")

    def _send_webhook(self, job: ExportQueueItem):
        """7.4 — Envoie une notification webhook POST-export."""
        try:
            import urllib.request, urllib.parse
            payload = json.dumps({
                "text": f"✔ Export terminé : {job.label}",
                "file": job.output_path,
                "resolution": f"{job.width}×{job.height}",
                "fps": job.fps,
            }).encode("utf-8")
            req = urllib.request.Request(
                job.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST")
            urllib.request.urlopen(req, timeout=5)
            self._log_msg(f"  📡 Webhook envoyé → {job.webhook_url}")
        except Exception as e:
            self._log_msg(f"  ⚠ Webhook échoué : {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 7.3 — RÉCEPTEUR OSC / MIDI
# ══════════════════════════════════════════════════════════════════════════════

class OscMidiDialog(QDialog):
    """
    7.3 — Dialogue de configuration OSC et MIDI.
    OSC : réception de messages UDP pour contrôler les paramètres.
    MIDI : mapping de CC/notes vers les uniforms et paramètres.
    """

    param_received = Signal(str, float)   # (param_name, value)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("OSC / MIDI Input")
        self.resize(520, 560)
        self._osc_thread  = None
        self._midi_thread = None
        self._osc_running  = False
        self._midi_running = False
        self._osc_mappings:  list[tuple] = []   # [(osc_addr, param_name), ...]
        self._midi_mappings: list[tuple] = []   # [(cc_num, param_name), ...]

        self.setStyleSheet(
            f"QDialog{{background:{C_BG.name()};color:{C_TXT.name()};}}"
            f"QLabel{{font:8pt 'Courier New';background:transparent;}}"
            + _ss_btn(C_CYAN) + _ss_edit(C_CYAN) + _ss_scroll())

        lay = QVBoxLayout(self)
        lay.setSpacing(8); lay.setContentsMargins(12, 12, 12, 12)

        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane{{border:none;background:{C_BG.name()};}}"
            f"QTabBar::tab{{background:{C_BG2.name()};color:{C_TXTDIM.name()};"
            f"font:8pt 'Courier New';padding:6px 14px;border:none;}}"
            f"QTabBar::tab:selected{{background:{C_BG.name()};"
            f"color:{C_CYAN.name()};border-top:2px solid {C_CYAN.name()};}}")

        # ── Onglet OSC ────────────────────────────────────────────────────
        osc_w = QWidget()
        olay = QVBoxLayout(osc_w)
        olay.setSpacing(6)

        osc_hdr = QLabel("  Open Sound Control (OSC) — Réception UDP")
        osc_hdr.setStyleSheet(
            f"color:{C_CYAN.name()};font:bold 8pt 'Courier New';padding:4px 0;")
        olay.addWidget(osc_hdr)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Port UDP :"))
        self._osc_port = QSpinBox()
        self._osc_port.setRange(1024, 65535); self._osc_port.setValue(9000)
        self._osc_port.setStyleSheet(
            f"QSpinBox{{background:{C_BG3.name()};color:{C_TXTHI.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:3px;padding:3px;font:8pt 'Courier New';}}")
        port_row.addWidget(self._osc_port)
        self._btn_osc = QPushButton("▶ Démarrer OSC")
        self._btn_osc.clicked.connect(self._toggle_osc)
        port_row.addWidget(self._btn_osc)
        port_row.addStretch()
        olay.addLayout(port_row)

        olay.addWidget(QLabel("  Mappings  (adresse OSC → nom du paramètre) :"))
        self._osc_map_list = QListWidget()
        self._osc_map_list.setFixedHeight(100)
        self._osc_map_list.setStyleSheet(
            f"QListWidget{{background:{C_BG2.name()};border:1px solid {C_BORDER.name()};"
            f"font:8pt 'Courier New';}}"
            f"QListWidget::item{{padding:3px 8px;}}" + _ss_scroll())
        olay.addWidget(self._osc_map_list)

        osc_add = QHBoxLayout()
        self._osc_addr  = QLineEdit(); self._osc_addr.setPlaceholderText("/megademo/iSpeed")
        self._osc_param = QLineEdit(); self._osc_param.setPlaceholderText("iSpeed")
        osc_add.addWidget(self._osc_addr); osc_add.addWidget(QLabel("→")); osc_add.addWidget(self._osc_param)
        btn_osc_add = QPushButton("＋"); btn_osc_add.setFixedWidth(28)
        btn_osc_add.clicked.connect(self._add_osc_mapping)
        btn_osc_del = QPushButton("−"); btn_osc_del.setFixedWidth(28)
        btn_osc_del.clicked.connect(lambda: self._del_mapping(self._osc_map_list, self._osc_mappings))
        osc_add.addWidget(btn_osc_add); osc_add.addWidget(btn_osc_del)
        olay.addLayout(osc_add)

        self._osc_log = QPlainTextEdit()
        self._osc_log.setReadOnly(True); self._osc_log.setFixedHeight(80)
        self._osc_log.setStyleSheet(
            f"QPlainTextEdit{{background:{C_BG.name()};color:{C_TXTDIM.name()};"
            f"border:1px solid {C_BORDER.name()};font:7pt 'Courier New';}}" + _ss_scroll())
        olay.addWidget(self._osc_log)
        olay.addStretch()
        tabs.addTab(osc_w, "OSC")

        # ── Onglet MIDI ───────────────────────────────────────────────────
        midi_w = QWidget()
        mlay = QVBoxLayout(midi_w)
        mlay.setSpacing(6)

        midi_hdr = QLabel("  MIDI Input — Mapping CC → Paramètres")
        midi_hdr.setStyleSheet(
            f"color:{C_PURPLE.name()};font:bold 8pt 'Courier New';padding:4px 0;")
        mlay.addWidget(midi_hdr)

        # Sélection du port MIDI
        port_row2 = QHBoxLayout()
        port_row2.addWidget(QLabel("Port MIDI :"))
        self._midi_port_cb = QComboBox()
        self._midi_port_cb.setStyleSheet(
            f"QComboBox{{background:{C_BG3.name()};color:{C_TXTHI.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:3px;"
            f"padding:3px 6px;font:8pt 'Courier New';}}")
        self._refresh_midi_ports()
        port_row2.addWidget(self._midi_port_cb)
        btn_refresh_midi = QPushButton("⟳")
        btn_refresh_midi.setFixedWidth(28)
        btn_refresh_midi.clicked.connect(self._refresh_midi_ports)
        port_row2.addWidget(btn_refresh_midi)
        self._btn_midi = QPushButton("▶ Démarrer MIDI")
        self._btn_midi.clicked.connect(self._toggle_midi)
        port_row2.addWidget(self._btn_midi)
        port_row2.addStretch()
        mlay.addLayout(port_row2)

        mlay.addWidget(QLabel("  Mappings  (CC# → nom du paramètre) :"))
        self._midi_map_list = QListWidget()
        self._midi_map_list.setFixedHeight(100)
        self._midi_map_list.setStyleSheet(
            f"QListWidget{{background:{C_BG2.name()};border:1px solid {C_BORDER.name()};"
            f"font:8pt 'Courier New';}}"
            f"QListWidget::item{{padding:3px 8px;}}" + _ss_scroll())
        mlay.addWidget(self._midi_map_list)

        midi_add = QHBoxLayout()
        self._midi_cc    = QSpinBox(); self._midi_cc.setRange(0, 127)
        self._midi_cc.setStyleSheet(
            f"QSpinBox{{background:{C_BG3.name()};color:{C_TXTHI.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:3px;"
            f"padding:3px;font:8pt 'Courier New';}}")
        self._midi_param = QLineEdit(); self._midi_param.setPlaceholderText("iSpeed")
        midi_add.addWidget(QLabel("CC#")); midi_add.addWidget(self._midi_cc)
        midi_add.addWidget(QLabel("→")); midi_add.addWidget(self._midi_param)
        btn_midi_add = QPushButton("＋"); btn_midi_add.setFixedWidth(28)
        btn_midi_add.clicked.connect(self._add_midi_mapping)
        btn_midi_del = QPushButton("−"); btn_midi_del.setFixedWidth(28)
        btn_midi_del.clicked.connect(lambda: self._del_mapping(self._midi_map_list, self._midi_mappings))
        midi_add.addWidget(btn_midi_add); midi_add.addWidget(btn_midi_del)
        mlay.addLayout(midi_add)

        self._midi_log = QPlainTextEdit()
        self._midi_log.setReadOnly(True); self._midi_log.setFixedHeight(80)
        self._midi_log.setStyleSheet(
            f"QPlainTextEdit{{background:{C_BG.name()};color:{C_TXTDIM.name()};"
            f"border:1px solid {C_BORDER.name()};font:7pt 'Courier New';}}" + _ss_scroll())
        mlay.addWidget(self._midi_log)
        mlay.addStretch()
        tabs.addTab(midi_w, "MIDI")

        lay.addWidget(tabs)
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.hide)
        lay.addWidget(btn_close, alignment=Qt.AlignRight)
        QShortcut(QKeySequence("Ctrl+W"), self, self.hide)

    def _refresh_midi_ports(self):
        self._midi_port_cb.clear()
        try:
            import mido
            ports = mido.get_input_names()
            for p in ports:
                self._midi_port_cb.addItem(p)
            if not ports:
                self._midi_port_cb.addItem("(aucun port MIDI détecté)")
        except ImportError:
            self._midi_port_cb.addItem("mido non installé — pip install mido python-rtmidi")

    def _toggle_osc(self):
        if self._osc_running:
            self._osc_running = False
            self._btn_osc.setText("▶ Démarrer OSC")
            self._osc_log.appendPlainText("⬛ OSC arrêté.")
        else:
            port = self._osc_port.value()
            self._osc_running = True
            self._btn_osc.setText("⬛ Arrêter OSC")
            self._osc_log.appendPlainText(f"▶ OSC en écoute sur UDP :{port}")
            import threading
            t = threading.Thread(target=self._osc_listen, args=(port,), daemon=True)
            t.start()

    def _osc_listen(self, port: int):
        """Thread OSC — écoute les messages UDP et les dispatche."""
        import socket, struct
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        try:
            sock.bind(("", port))
        except Exception as e:
            self._osc_log.appendPlainText(f"✖ OSC bind error: {e}")
            return
        while self._osc_running:
            try:
                data, addr = sock.recvfrom(4096)
                self._parse_osc(data)
            except socket.timeout:
                continue
            except Exception:
                break
        sock.close()

    def _parse_osc(self, data: bytes):
        """Parse minimale d'un paquet OSC pour extraire l'adresse et la valeur float."""
        try:
            # Adresse OSC (string null-terminée, padded à 4 bytes)
            null = data.index(b'\x00')
            addr = data[:null].decode('ascii', errors='ignore')
            # Chercher le type tag string après le padding
            offset = (null + 4) & ~3
            if offset < len(data) and data[offset:offset+1] == b',':
                tag_end = data.index(b'\x00', offset + 1)
                tags = data[offset+1:tag_end].decode('ascii', errors='ignore')
                val_offset = (tag_end + 4) & ~3
                if 'f' in tags:
                    val = struct.unpack_from('>f', data, val_offset)[0]
                    for osc_addr, param_name in self._osc_mappings:
                        if addr == osc_addr:
                            self.param_received.emit(param_name, float(val))
                    self._osc_log.appendPlainText(f"  {addr} → {val:.3f}")
        except Exception:
            pass

    def _toggle_midi(self):
        if self._midi_running:
            self._midi_running = False
            self._btn_midi.setText("▶ Démarrer MIDI")
            self._midi_log.appendPlainText("⬛ MIDI arrêté.")
        else:
            port_name = self._midi_port_cb.currentText()
            if "non installé" in port_name or "aucun port" in port_name:
                self._midi_log.appendPlainText("✖ Pas de port MIDI disponible.")
                return
            self._midi_running = True
            self._btn_midi.setText("⬛ Arrêter MIDI")
            self._midi_log.appendPlainText(f"▶ MIDI en écoute sur : {port_name}")
            import threading
            t = threading.Thread(
                target=self._midi_listen, args=(port_name,), daemon=True)
            t.start()

    def _midi_listen(self, port_name: str):
        try:
            import mido
            with mido.open_input(port_name) as port:
                for msg in port:
                    if not self._midi_running:
                        break
                    if msg.type == 'control_change':
                        val = msg.value / 127.0
                        for cc_num, param_name in self._midi_mappings:
                            if msg.control == cc_num:
                                self.param_received.emit(param_name, val)
                        self._midi_log.appendPlainText(
                            f"  CC#{msg.control} = {msg.value}  ch={msg.channel}")
        except Exception as e:
            self._midi_log.appendPlainText(f"✖ MIDI error: {e}")

    def _add_osc_mapping(self):
        addr  = self._osc_addr.text().strip()
        param = self._osc_param.text().strip()
        if addr and param:
            self._osc_mappings.append((addr, param))
            self._osc_map_list.addItem(f"  {addr}  →  {param}")
            self._osc_addr.clear(); self._osc_param.clear()

    def _add_midi_mapping(self):
        cc    = self._midi_cc.value()
        param = self._midi_param.text().strip()
        if param:
            self._midi_mappings.append((cc, param))
            self._midi_map_list.addItem(f"  CC#{cc}  →  {param}")
            self._midi_param.clear()

    def _del_mapping(self, list_widget: QListWidget, mappings: list):
        row = list_widget.currentRow()
        if row >= 0:
            list_widget.takeItem(row)
            if row < len(mappings):
                mappings.pop(row)

    def closeEvent(self, e):
        self._osc_running  = False
        self._midi_running = False
        e.ignore(); self.hide()


class ExportWorker(QThread):
    """Thread générique pour les exports longs (MP4, EXE)."""
    log_signal      = Signal(str)
    progress_signal = Signal(int, int)   # (current, total)
    done_signal     = Signal(bool, str)  # (success, message)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self._func   = func
        self._args   = args
        self._kwargs = kwargs

    def run(self):
        try:
            ok, msg = self._func(*self._args, **self._kwargs)
            self.done_signal.emit(ok, msg)
        except Exception as e:
            import traceback
            self.log_signal.emit(traceback.format_exc())
            self.done_signal.emit(False, str(e))


# ════════════════════════════════════════════════════════════
#  EXPORT MP4  — Dialog
# ════════════════════════════════════════════════════════════

class Mp4ExportDialog(QDialog):
    def __init__(self, parent, project_dir, project_data):
        super().__init__(parent)
        self.project_dir  = project_dir
        self.project_data = project_data
        self._worker      = None
        self._engine      = None   # initialisé dans _start()

        self.setWindowTitle("Export MP4")
        self.setMinimumWidth(560)
        self.setStyleSheet(
            f"QDialog{{background:{C_BG.name()};color:{C_TXT.name()};}}"
            f"QLabel{{color:{C_TXT.name()};font:9pt 'Courier New';background:transparent;}}"
            + _ss_edit(C_CYAN)
            + _ss_btn(C_CYAN)
            + f"QCheckBox{{color:{C_TXT.name()};font:9pt 'Courier New';}}"
            f"QTextEdit{{background:{C_BG2.name()};color:{C_TXTDIM.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:3px;font:8pt 'Courier New';}}")

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        # Titre
        ttl = QLabel("  ◈  EXPORT  MP4")
        ttl.setStyleSheet(f"color:{C_CYAN.name()};font:bold 11pt 'Courier New';letter-spacing:3px;padding:6px 8px;background:transparent;")
        lay.addWidget(ttl)

        # Vérif ffmpeg
        from export_engine import ExportEngine
        ok_ff, ver_ff = ExportEngine.check_ffmpeg()
        ff_lbl = QLabel(f"  {'✔' if ok_ff else '✖'}  ffmpeg : {ver_ff[:60]}")
        ff_lbl.setStyleSheet(
            f"color:{C_GREEN.name() if ok_ff else C_ACC2.name()};"
            f"font:8pt 'Courier New';padding:2px 4px;")
        lay.addWidget(ff_lbl)

        form = QFormLayout(); form.setSpacing(6)
        sl = f"color:{C_TXTDIM.name()};font:8pt 'Courier New';"

        def _lbl(t): l = QLabel(t); l.setStyleSheet(sl); return l

        # Fichier de sortie
        out_row = QHBoxLayout()
        cfg = project_data.get("config", {})
        default_name = cfg.get("WINDOW_TITLE", "megademo").lower().replace(" ", "_") + ".mp4"
        default_out  = os.path.join(project_dir, "export", default_name)
        self._out_edit = QLineEdit(default_out)
        btn_browse = QPushButton("…")
        btn_browse.setFixedWidth(32)
        btn_browse.setStyleSheet(
            f"QPushButton{{background:{C_BG3.name()};color:{C_TXTDIM.name()};"
            f"border:1px solid {C_BORDER.name()};padding:3px;}}")
        btn_browse.clicked.connect(self._browse_out)
        out_row.addWidget(self._out_edit); out_row.addWidget(btn_browse)
        form.addRow(_lbl("FICHIER"), out_row)

        # Résolution
        res = cfg.get("RES", [1920, 1080])
        res_row = QHBoxLayout()
        self._w_spin = QSpinBox(); self._w_spin.setRange(320, 7680); self._w_spin.setValue(res[0])
        self._h_spin = QSpinBox(); self._h_spin.setRange(240, 4320); self._h_spin.setValue(res[1])
        self._w_spin.setSingleStep(16); self._h_spin.setSingleStep(16)
        res_row.addWidget(self._w_spin); res_row.addWidget(QLabel("×")); res_row.addWidget(self._h_spin)
        form.addRow(_lbl("RÉSOLUTION"), res_row)

        # FPS
        self._fps_cb = QComboBox()
        for f in ("24", "25", "30", "50", "60"):
            self._fps_cb.addItem(f"{f} fps", int(f))
        self._fps_cb.setCurrentIndex(4)   # 60
        form.addRow(_lbl("FPS"), self._fps_cb)

        # Codec / Format — Phase 7.1
        self._codec_cb = QComboBox()
        for code, label in [
            ("h264",    "H.264  (libx264 — universel)"),
            ("h265",    "H.265/HEVC  (libx265 — plus compact)"),
            ("prores",  "ProRes 4444  (qualité max, gros fichier)"),
            ("vp9",     "VP9  (web, open source)"),
            ("png_seq", "Séquence PNG  (images/frame_XXXXX.png)"),
            ("exr_seq", "Séquence EXR  (32 bits float, compositing)"),
        ]:
            self._codec_cb.addItem(label, code)
        self._codec_cb.currentIndexChanged.connect(self._on_codec_changed)
        form.addRow(_lbl("FORMAT"), self._codec_cb)

        # CRF (qualité vidéo)
        crf_row = QHBoxLayout()
        self._crf_spin = QSpinBox()
        self._crf_spin.setRange(0, 51); self._crf_spin.setValue(18)
        self._crf_spin.setToolTip("0 = sans perte, 18 = visuellement sans perte, 23 = défaut, 51 = pire qualité")
        crf_row.addWidget(self._crf_spin)
        self._crf_lbl = QLabel("(0=lossless  18=excellent  23=défaut  51=pire)")
        self._crf_lbl.setStyleSheet(sl)
        crf_row.addWidget(self._crf_lbl)
        form.addRow(_lbl("CRF"), crf_row)

        lay.addLayout(form)

        # Validation pre-export — Phase 7.1
        self._validation_widget = QWidget()
        self._validation_widget.setStyleSheet(
            f"background:{C_BG2.name()};border:1px solid {C_BORDER.name()};"
            f"border-radius:3px;")
        vl = QVBoxLayout(self._validation_widget)
        vl.setContentsMargins(8, 6, 8, 6); vl.setSpacing(3)
        val_hdr = QHBoxLayout()
        val_title = QLabel("  ⓘ  Validation pre-export")
        val_title.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:bold 7pt 'Courier New';")
        val_hdr.addWidget(val_title)
        btn_validate = QPushButton("Vérifier maintenant")
        btn_validate.setFixedHeight(22)
        btn_validate.setStyleSheet(
            f"QPushButton{{background:{C_BG3.name()};color:{C_CYAN.name()};"
            f"border:1px solid {C_CYAN.name()}40;border-radius:3px;"
            f"padding:2px 8px;font:7pt 'Courier New';}}"
            f"QPushButton:hover{{background:{C_CYAN.name()}18;}}")
        btn_validate.clicked.connect(self._run_validation)
        val_hdr.addWidget(btn_validate); val_hdr.addStretch()
        vl.addLayout(val_hdr)
        self._val_result = QLabel("  Cliquer pour vérifier les assets et la configuration.")
        self._val_result.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:7pt 'Courier New';")
        self._val_result.setWordWrap(True)
        vl.addWidget(self._val_result)
        lay.addWidget(self._validation_widget)

        # Barre de progression
        self._progress = QProgressBar()
        self._progress.setRange(0, 100); self._progress.setValue(0)
        self._progress.setStyleSheet(
            f"QProgressBar{{background:{C_BG3.name()};border:1px solid {C_BORDER.name()};"
            f"border-radius:3px;height:18px;text-align:center;font:8pt 'Courier New';}}"
            f"QProgressBar::chunk{{background:{C_ACC.name()};border-radius:2px;}}")
        self._progress.setFormat("En attente…")
        lay.addWidget(self._progress)

        # Log
        self._log = QTextEdit(); self._log.setReadOnly(True); self._log.setFixedHeight(160)
        lay.addWidget(self._log)

        # Boutons
        btn_row = QHBoxLayout()
        self._btn_start  = QPushButton("▶  LANCER L'EXPORT")
        self._btn_cancel = QPushButton("✖  ANNULER")
        self._btn_cancel.setStyleSheet(
            f"QPushButton{{background:{C_BG3.name()};color:{C_ACC2.name()};"
            f"border:1px solid {C_ACC2.name()};padding:5px 12px;"
            f"font:bold 9pt 'Courier New';}}"
            f"QPushButton:hover{{background:{C_BG2.name()};}}")
        self._btn_cancel.setEnabled(False)
        self._btn_start.clicked.connect(self._start)
        self._btn_cancel.clicked.connect(self._cancel)
        btn_row.addWidget(self._btn_start); btn_row.addWidget(self._btn_cancel)
        lay.addLayout(btn_row)

        if not ok_ff:
            self._btn_start.setEnabled(False)
            self._log.append("✖ ffmpeg est requis pour l'export MP4.\n"
                             "Installez-le depuis https://ffmpeg.org et ajoutez-le au PATH.")

    def _browse_out(self):
        codec = self._codec_cb.currentData() if hasattr(self, '_codec_cb') else 'h264'
        if codec in ("png_seq", "exr_seq"):
            path = QFileDialog.getExistingDirectory(
                self, "Dossier pour la séquence d'images",
                os.path.dirname(self._out_edit.text()))
            if path:
                self._out_edit.setText(path)
        else:
            ext_map = {"h264": "MP4 (*.mp4)", "h265": "MP4 (*.mp4)",
                       "prores": "MOV (*.mov)", "vp9": "WebM (*.webm)"}
            filt = ext_map.get(codec, "Vidéo (*.mp4)")
            path, _ = QFileDialog.getSaveFileName(
                self, "Enregistrer la vidéo", self._out_edit.text(), filt)
            if path:
                self._out_edit.setText(path)

    def _log_msg(self, msg):
        self._log.append(msg)
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum())

    def _on_progress(self, cur, total):
        pct = int(cur * 100 / max(total, 1))
        self._progress.setValue(pct)
        self._progress.setFormat(f"Frame {cur}/{total}  ({pct}%)")

    def _on_codec_changed(self, idx):
        codec = self._codec_cb.currentData()
        out   = self._out_edit.text()
        base  = out.rsplit(".", 1)[0] if "." in os.path.basename(out) else out
        ext_map = {
            "h264": ".mp4", "h265": ".mp4", "prores": ".mov",
            "vp9": ".webm", "png_seq": "_frames", "exr_seq": "_exr",
        }
        self._out_edit.setText(base + ext_map.get(codec, ".mp4"))
        self._crf_spin.setEnabled(codec not in ("png_seq", "exr_seq", "prores"))

    def _run_validation(self):
        """Phase 7.1 — Vérifie les assets et la config avant l'export."""
        issues = []
        cfg = self.project_data.get("config", {})
        if cfg.get("MUSIC_DURATION", 0) <= 0:
            issues.append("⚠ MUSIC_DURATION = 0")
        music = cfg.get("MUSIC_FILE", "")
        if not music:
            issues.append("⚠ Aucun fichier audio")
        elif not os.path.exists(os.path.join(self.project_dir, music)):
            issues.append(f"✖ Audio introuvable : {music}")
        missing = validate_project_assets(self.project_dir, self.project_data)
        for m in missing[:4]:
            issues.append(f"✖ [{m['type']}] {m['ref']}")
        if len(missing) > 4:
            issues.append(f"… et {len(missing)-4} autre(s)")
        if not issues:
            self._val_result.setText("  ✔ Tous les assets présents. Prêt !")
            self._val_result.setStyleSheet(
                f"color:{C_GREEN.name()};font:7pt 'Courier New';")
        else:
            self._val_result.setText("  " + "\n  ".join(issues))
            self._val_result.setStyleSheet(
                f"color:{C_ORANGE.name()};font:7pt 'Courier New';")

    def _start(self):
        out_path = self._out_edit.text().strip()
        if not out_path:
            return
        codec = self._codec_cb.currentData() if hasattr(self, '_codec_cb') else 'h264'
        crf   = self._crf_spin.value() if hasattr(self, '_crf_spin') else 18
        self._run_validation()
        dest_dir = out_path if codec in ("png_seq","exr_seq") else os.path.dirname(os.path.abspath(out_path))
        os.makedirs(dest_dir, exist_ok=True)
        w   = self._w_spin.value()
        h   = self._h_spin.value()
        fps = self._fps_cb.currentData()
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._progress.setValue(0)
        self._progress.setFormat("Initialisation…")
        self._log.clear()
        from export_engine import ExportEngine
        engine = ExportEngine(
            self.project_dir, self.project_data,
            width=w, height=h, fps=fps,
            codec=codec, crf=crf)
        def _run():
            ok = engine.run(out_path)
            return ok, out_path if ok else "Échec de l'export"
        self._engine = engine
        self._worker = ExportWorker(_run)
        self._worker.log_signal.connect(self._log_msg)
        engine.on_log      = lambda m: self._worker.log_signal.emit(m)
        engine.on_progress = lambda c, t: self._worker.progress_signal.emit(c, t)
        self._worker.progress_signal.connect(self._on_progress)
        self._worker.done_signal.connect(self._on_done)
        self._worker.start()

    def _cancel(self):
        if self._engine:
            self._engine.cancel()
        self._btn_cancel.setEnabled(False)
        self._progress.setFormat("Annulation…")

    def _on_done(self, ok, msg):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        if ok:
            self._progress.setValue(100)
            self._progress.setFormat("✔ Terminé !")
            self._log_msg(f"\n✔ Fichier : {msg}")
            QMessageBox.information(self, "Export MP4", f"Export terminé !\n{msg}")
        else:
            self._progress.setFormat("✖ Erreur")
            self._log_msg(f"\n✖ {msg}")

    def closeEvent(self, e):
        if self._worker and self._worker.isRunning():
            self._cancel()
            self._worker.wait(3000)
        e.accept()


# ════════════════════════════════════════════════════════════
#  EXPORT EXE  — Dialog
# ════════════════════════════════════════════════════════════

class ExeExportDialog(QDialog):
    def __init__(self, parent, project_dir):
        super().__init__(parent)
        self.project_dir = project_dir
        self._worker     = None

        self.setWindowTitle("Export EXE / Binaire standalone")
        self.setMinimumWidth(560)
        self.setStyleSheet(
            f"QDialog{{background:{C_BG.name()};color:{C_TXT.name()};}}"
            f"QLabel{{color:{C_TXT.name()};font:9pt 'Courier New';background:transparent;}}"
            + _ss_edit(C_PURPLE)
            + _ss_btn(C_PURPLE)
            + f"QCheckBox{{color:{C_TXT.name()};font:9pt 'Courier New';}}"
            f"QTextEdit{{background:{C_BG2.name()};color:{C_TXTDIM.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:3px;font:8pt 'Courier New';}}")

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        ttl = QLabel("  ◈  EXPORT  EXE / BINAIRE")
        ttl.setStyleSheet(f"color:{C_PURPLE.name()};font:bold 11pt 'Courier New';letter-spacing:3px;padding:6px 8px;background:transparent;")
        lay.addWidget(ttl)

        # Vérif PyInstaller
        from build_exe import check_pyinstaller
        ok_pi, ver_pi = check_pyinstaller()
        pi_lbl = QLabel(f"  {'✔' if ok_pi else '✖'}  PyInstaller : {ver_pi[:60]}")
        pi_lbl.setStyleSheet(
            f"color:{C_GREEN.name() if ok_pi else C_ACC2.name()};"
            f"font:8pt 'Courier New';padding:2px 4px;")
        lay.addWidget(pi_lbl)

        form = QFormLayout(); form.setSpacing(6)
        sl = f"color:{C_TXTDIM.name()};font:8pt 'Courier New';"
        def _lbl(t): l = QLabel(t); l.setStyleSheet(sl); return l

        # Dossier de sortie
        out_row = QHBoxLayout()
        default_dist = os.path.join(project_dir, "export", "dist")
        self._out_edit = QLineEdit(default_dist)
        btn_browse = QPushButton("…")
        btn_browse.setFixedWidth(32)
        btn_browse.setStyleSheet(
            f"QPushButton{{background:{C_BG3.name()};color:{C_TXTDIM.name()};"
            f"border:1px solid {C_BORDER.name()};padding:3px;}}")
        btn_browse.clicked.connect(self._browse_out)
        out_row.addWidget(self._out_edit); out_row.addWidget(btn_browse)
        form.addRow(_lbl("DOSSIER DIST"), out_row)

        # Options
        self._onefile_cb = QCheckBox("--onefile  (un seul exécutable, plus lent au démarrage)")
        self._onefile_cb.setChecked(True)
        self._console_cb = QCheckBox("--console  (garder la fenêtre console/terminal)")
        self._console_cb.setChecked(False)
        form.addRow(_lbl("OPTIONS"), self._onefile_cb)
        form.addRow(_lbl(""), self._console_cb)

        lay.addLayout(form)

        # Info plateforme
        plat = f"Plateforme : {sys.platform}  —  Python {sys.version.split()[0]}"
        plat_lbl = QLabel(f"  ⓘ  {plat}")
        plat_lbl.setStyleSheet(f"color:{C_TXTDIM.name()};font:7pt 'Courier New';")
        lay.addWidget(plat_lbl)

        # Barre de progression (texte)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)    # mode indéterminé
        self._progress.setVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar{{background:{C_BG3.name()};border:1px solid {C_BORDER.name()};"
            f"border-radius:3px;height:18px;text-align:center;font:8pt 'Courier New';}}"
            f"QProgressBar::chunk{{background:{C_ACC4.name()};border-radius:2px;}}")
        lay.addWidget(self._progress)

        # Log
        self._log = QTextEdit(); self._log.setReadOnly(True); self._log.setFixedHeight(200)
        lay.addWidget(self._log)

        # Boutons
        btn_row = QHBoxLayout()
        self._btn_start  = QPushButton("▶  COMPILER L'EXÉCUTABLE")
        self._btn_cancel = QPushButton("✖  ANNULER")
        self._btn_cancel.setStyleSheet(
            f"QPushButton{{background:{C_BG3.name()};color:{C_ACC2.name()};"
            f"border:1px solid {C_ACC2.name()};padding:5px 12px;"
            f"font:bold 9pt 'Courier New';}}"
            f"QPushButton:hover{{background:{C_BG2.name()};}}")
        self._btn_cancel.setEnabled(False)
        self._btn_start.clicked.connect(self._start)
        self._btn_cancel.clicked.connect(self._cancel)
        btn_row.addWidget(self._btn_start); btn_row.addWidget(self._btn_cancel)
        lay.addLayout(btn_row)

        if not ok_pi:
            self._btn_start.setEnabled(False)
            self._log.append(
                "✖ PyInstaller est requis pour l'export EXE.\n"
                "Installez-le : pip install pyinstaller\n"
                "Puis relancez le Demomaker.")

    def _browse_out(self):
        path = QFileDialog.getExistingDirectory(
            self, "Dossier de destination", self._out_edit.text())
        if path:
            self._out_edit.setText(path)

    def _log_msg(self, msg):
        self._log.append(msg)
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum())

    def _start(self):
        out_dir  = self._out_edit.text().strip()
        one_file = self._onefile_cb.isChecked()
        console  = self._console_cb.isChecked()

        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._progress.setVisible(True)
        self._log.clear()
        self._log_msg("▶ Démarrage de la compilation…\n")

        from build_exe import build_exe

        def _run():
            return build_exe(
                project_dir=self.project_dir,
                output_dir=out_dir,
                on_log=lambda m: self._worker.log_signal.emit(m),
                one_file=one_file,
                console=console,
            )

        self._worker = ExportWorker(_run)
        self._worker.log_signal.connect(self._log_msg)
        self._worker.done_signal.connect(self._on_done)
        self._worker.start()

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self._btn_cancel.setEnabled(False)
        self._progress.setVisible(False)

    def _on_done(self, ok, msg):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._progress.setVisible(False)
        if ok:
            self._log_msg(f"\n✔ Exécutable : {msg}")
            QMessageBox.information(
                self, "Export EXE",
                f"Compilation réussie !\n\n{msg}")
        else:
            self._log_msg(f"\n✖ {msg}")

    def closeEvent(self, e):
        if self._worker and self._worker.isRunning():
            self._cancel()
            self._worker.wait(2000)
        e.accept()


# ════════════════════════════════════════════════════════════
#  FENÊTRE PRINCIPALE
# ════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self, rocket_host=None, rocket_port=1338):
        super().__init__()
        self.setWindowTitle("MEGADEMO COMPOSER  ──  PySide6")

        self.scenes      = []
        self.overlays    = []
        # Phase 4 — Param System
        self._param_sys  = ParamSystem()
        self._current_scene_for_params = ''
        self.images      = []
        self.scrolls     = []
        self.cfg         = dict(DEFAULT_CONFIG)
        self.selected    = None
        self.project_dir = os.path.dirname(os.path.abspath(__file__))

        self.rocket         = None
        self.rocket_playing = False
        self._rocket_host   = rocket_host
        self._rocket_port   = rocket_port
        self._local_playing = False
        self._local_start   = 0.0
        self._viewport      = None   # initialisé dans _build_ui
        self._current_t     = 0.0
        self._last_audio_uniforms: dict = {}

        # Phase 6 — Thèmes, palette, keymap, logs, macros
        self._theme_mgr    = ThemeManager(self.project_dir)
        self._keymap       = dict(DEFAULT_KEYMAP)
        self._log_panel    = None   # créé à la demande
        self._macro_mgr    = MacroManager(self.project_dir)

        # Phase 7 — OSC/MIDI
        self._osc_midi_dlg = None   # créé à la demande

        # Phase 9 — Caméra 3D, Particules, Texte SDF
        if _PHASE9:
            res    = tuple(self.cfg.get("RES", [1920, 1080]))
            aspect = res[0] / max(res[1], 1)
            self.camera_system = CameraSystem(aspect_ratio=aspect)
        else:
            self.camera_system = None

        # ── Lecteur audio ──────────────────────────────────────
        self._audio_player  = None
        self._audio_output  = None
        self._audio_volume  = 1.0
        self._audio_muted   = False
        if AUDIO_AVAILABLE:
            self._audio_output = QAudioOutput()
            self._audio_output.setVolume(1.0)
            self._audio_player = QMediaPlayer()
            self._audio_player.setAudioOutput(self._audio_output)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_save)

        self._settings = QSettings(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILE),
            QSettings.IniFormat)

        # Watcher filesystem
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._refresh_assets)

        self._build_ui()
        self._apply_stylesheet()
        self._load_default_timeline()
        self._restore_window()
        self._init_rocket()
        self._setup_watcher()
        self._refresh_assets()
        # Phase 5.1 — Initialiser le browser shaders
        QTimer.singleShot(500, lambda: self._shader_browser.set_project_dir(self.project_dir))
        self._sync_audio_controls()

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(50)

        QShortcut(QKeySequence("Space"),      self, self._toggle_play)
        QShortcut(QKeySequence("Delete"),      self, self._delete_selected)
        QShortcut(QKeySequence("Ctrl+S"),      self, lambda: self.autosave(force=True))
        QShortcut(QKeySequence("Ctrl+D"),      self, self._duplicate_selected)
        QShortcut(QKeySequence("Home"),        self, self._reset_playhead)
        # Phase 3 — nouveaux raccourcis
        QShortcut(QKeySequence("Ctrl+Z"),      self, lambda: self._tl.undo())
        QShortcut(QKeySequence("Ctrl+Y"),      self, lambda: self._tl.redo())
        QShortcut(QKeySequence("Ctrl+Shift+Z"),self, lambda: self._tl.redo())
        QShortcut(QKeySequence("Ctrl+C"),      self, lambda: self._tl.copy_selection())
        QShortcut(QKeySequence("Ctrl+V"),      self, lambda: self._tl.paste_clipboard())
        QShortcut(QKeySequence("Ctrl+A"),      self, lambda: self._tl._select_all())
        QShortcut(QKeySequence("Escape"),      self, lambda: self._tl._deselect_all())
        QShortcut(QKeySequence("M"),           self, self._add_marker_at_playhead)
        QShortcut(QKeySequence("Left"),        self, lambda: self._tl.prev_marker())
        QShortcut(QKeySequence("Right"),       self, lambda: self._tl.next_marker())
        QShortcut(QKeySequence("I"),           self, self._set_loop_in)
        QShortcut(QKeySequence("O"),           self, self._set_loop_out)
        # Fenêtres flottantes
        QShortcut(QKeySequence("Ctrl+Shift+V"),self, self._toggle_viewport_window)
        QShortcut(QKeySequence("Ctrl+Shift+A"),self, self._toggle_automation_window)
        # Phase 6 — Palette de commandes
        QShortcut(QKeySequence("Ctrl+P"),      self, self._open_command_palette)

    # ── Watcher ──────────────────────────────────────────────

    def _setup_watcher(self):
        if self._watcher.directories():
            self._watcher.removePaths(self._watcher.directories())
        for d in ("scenes", "overlays", "images", "fonts", "music"):
            path = os.path.join(self.project_dir, d)
            os.makedirs(path, exist_ok=True)
            self._watcher.addPath(path)
        # Phase 5.2 — Le watcher de fichiers individuels est géré par GlslEditorPanel lui-même

    def _on_dir_changed(self, _):
        self._debounce.start()

    def _reload_viewport(self):
        if self._viewport:
            self._viewport.reload()
            self._sync_viewport()
            self._set_status("Shaders rechargés.")

    def _refresh_assets(self):
        ensure_dirs(self.project_dir)
        self._assets.refresh(self.project_dir)

    # ── Restauration ─────────────────────────────────────────

    def _restore_window(self):
        geom  = self._settings.value("window/geometry")
        state = self._settings.value("window/state")
        maxi  = self._settings.value("window/maximized", "true")
        if geom: self.restoreGeometry(geom)
        else:    self.showMaximized(); return
        if state: self.restoreState(state)
        self.showMaximized() if maxi == "true" else self.show()

    def closeEvent(self, event):
        self._settings.setValue("window/geometry",  self.saveGeometry())
        self._settings.setValue("window/state",     self.saveState())
        self._settings.setValue("window/maximized", "true" if self.isMaximized() else "false")
        # Fermer les fenêtres flottantes proprement
        if hasattr(self, '_viewport_window') and self._viewport_window:
            self._viewport_window.blockSignals(True)
            self._viewport_window.close()
        if hasattr(self, '_auto_window') and self._auto_window:
            self._auto_window.blockSignals(True)
            self._auto_window.close()
        self.autosave(force=True)
        event.accept()

    # ── Build UI ─────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        ml = QVBoxLayout(central)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        ml.addWidget(self._build_toolbar())

        sp = QSplitter(Qt.Horizontal)
        sp.setHandleWidth(2)
        sp.setStyleSheet(
            f"QSplitter::handle{{background:{C_BORDER2.name()};}}"
            f"QSplitter::handle:hover{{background:{C_CYAN.name()}60;}}")

        # ── Gauche : assets + browser shaders (Phase 5.1) ────────────────
        left_tabs = QTabWidget()
        left_tabs.setFixedWidth(240)
        left_tabs.setStyleSheet(
            f"QTabWidget::pane{{border:none;background:{C_BG.name()};}}"
            f"QTabBar::tab{{background:{C_BG2.name()};color:{C_TXTDIM.name()};"
            f"font:6pt 'Courier New';padding:5px 7px;"
            f"border:none;border-right:1px solid {C_BORDER.name()};min-width:40px;}}"
            f"QTabBar::tab:selected{{background:{C_BG.name()};color:{C_CYAN.name()};"
            f"border-top:2px solid {C_CYAN.name()};}}"
            f"QTabBar::tab:hover{{color:{C_TXT.name()};}}")

        self._assets = AssetsPanel()
        self._assets.add_to_timeline.connect(self._add_from_asset)
        left_tabs.addTab(self._assets, "ASSETS")

        # Phase 5.1 — Browser visuel shaders
        self._shader_browser = ShaderBrowserPanel()
        self._shader_browser.add_to_timeline.connect(
            lambda base: self._add_from_asset("scene", base))
        self._shader_browser.edit_requested.connect(self._open_shader_in_editor)
        left_tabs.addTab(self._shader_browser, "BROWSER")

        sp.addWidget(left_tabs)

        # ── Centre : timeline + config ──────────────────────────────────
        tl_cfg = QSplitter(Qt.Vertical)
        tl_cfg.setHandleWidth(2)
        tl_cfg.setStyleSheet(
            f"QSplitter::handle{{background:{C_BORDER.name()};}}"
            f"QSplitter::handle:hover{{background:{C_ORANGE.name()}40;}}")
        tl_cfg.addWidget(self._build_timeline_area())
        self._config_panel = ConfigPanel(self.cfg)
        self._config_panel.changed.connect(self.autosave)
        tl_cfg.addWidget(self._config_panel)
        tl_cfg.setSizes([520, 200])
        sp.addWidget(tl_cfg)

        # ── Droite : propriétés + éditeur GLSL + viewport ─────────────────
        right_split = QSplitter(Qt.Vertical)
        right_split.setHandleWidth(2)
        right_split.setStyleSheet(
            f"QSplitter::handle{{background:{C_BORDER.name()};}}"
            f"QSplitter::handle:hover{{background:{C_PURPLE.name()}40;}}")

        self._props = PropsPanel(self)
        self._props.apply_requested.connect(lambda _: self._on_props_applied())
        self._props.delete_requested.connect(self._delete_selected)
        self._props.duplicate_requested.connect(self._duplicate_selected)
        right_split.addWidget(self._props)

        # Phase 5.2 — Éditeur GLSL inline (initialement caché)
        self._glsl_editor = GlslEditorPanel()
        self._glsl_editor.shader_saved.connect(self._on_shader_saved)
        self._glsl_editor.setVisible(False)
        right_split.addWidget(self._glsl_editor)

        right_split.setSizes([300, 1])
        glsl_idx = right_split.indexOf(self._glsl_editor)
        right_split.setCollapsible(glsl_idx, True)

        sp.addWidget(right_split)

        # ── Fenêtres flottantes (Viewport + Automation) ───────────────────
        # Viewport
        self._viewport        = None
        self._viewport_window = None
        if VIEWPORT_AVAILABLE:
            try:
                self._viewport_window = ViewportWindow(self.project_dir, self)
                self._viewport = self._viewport_window.viewport_panel
                self._viewport_window.window_hidden.connect(
                    lambda: self._btn_viewport.setChecked(False)
                    if hasattr(self, '_btn_viewport') else None)
            except Exception as e:
                print(f"[GUI] Viewport non disponible : {e}")

        # Automation (Phase 4)
        self._auto_panel   = None
        self._auto_window  = None
        if AUTOMATION_AVAILABLE:
            self._auto_window = AutomationWindow(self)
            self._auto_panel  = self._auto_window.auto_panel
            self._auto_window.window_hidden.connect(
                lambda: self._btn_automation.setChecked(False)
                if hasattr(self, '_btn_automation') else None)

        sp.setSizes([240, 950, 290])
        ml.addWidget(sp)
        ml.addWidget(self._build_statusbar())
        self._build_menu()


    def _build_toolbar(self):
        tb = QWidget()
        tb.setFixedHeight(52)
        tb.setObjectName("toolbar")
        lay = QHBoxLayout(tb)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(6)

        def _btn(txt, slot, col, wide=False):
            b = QPushButton(txt)
            c = col.name() if hasattr(col, "name") else col
            b.setFixedHeight(32)
            if wide: b.setMinimumWidth(90)
            b.setStyleSheet(
                f"QPushButton{{background:{C_BG3.name()};color:{c};"
                f"border:1px solid {c}40;border-radius:4px;"
                f"padding:0 12px;font:bold 8pt \'Courier New\';letter-spacing:1px;}}"
                f"QPushButton:hover{{background:{c}20;"
                f"border:1px solid {c}cc;}}"
                f"QPushButton:pressed{{background:{c}40;}}")
            b.clicked.connect(slot)
            return b

        # Logo
        logo = QLabel("◈ MDC")
        logo.setStyleSheet(
            f"color:{C_CYAN.name()};font:bold 11pt \'Courier New\';"
            f"letter-spacing:3px;padding:0 8px;background:transparent;")
        lay.addWidget(logo)

        lay.addWidget(self._vsep2())

        # Transport
        self._play_btn = _btn("▶  PLAY", self._toggle_play, C_GREEN, wide=True)
        lay.addWidget(self._play_btn)
        lay.addWidget(_btn("⏮", self._reset_playhead, C_ORANGE))
        lay.addWidget(self._vsep2())

        # Edit
        lay.addWidget(_btn("AUTO",  self._auto_arrange,   C_CYAN))
        lay.addWidget(_btn("CLEAR", self._clear_timeline, C_ORANGE))
        lay.addWidget(self._vsep2())

        # Reload
        lay.addWidget(_btn("⟳ SHD", self._reload_viewport, C_GREEN))
        lay.addWidget(self._vsep2())

        # Fenêtres flottantes — boutons de la toolbar
        def _win_btn(txt, tip, slot, col):
            b = QPushButton(txt)
            b.setToolTip(tip)
            b.setFixedHeight(32)
            b.setCheckable(True)
            b.setStyleSheet(
                f"QPushButton{{background:{C_BG3.name()};color:{col.name()};"
                f"border:1px solid {col.name()}40;border-radius:4px;"
                f"padding:0 10px;font:bold 8pt 'Courier New';letter-spacing:1px;}}"
                f"QPushButton:hover{{background:{col.name()}18;}}"
                f"QPushButton:checked{{background:{col.name()}25;"
                f"border:1px solid {col.name()}aa;}}")
            b.clicked.connect(slot)
            return b

        self._btn_viewport = _win_btn(
            "▣ VIEWPORT", "Afficher/masquer le viewport  Ctrl+Shift+V",
            self._toggle_viewport_window, C_CYAN)
        lay.addWidget(self._btn_viewport)

        self._btn_automation = _win_btn(
            "◈ AUTOMATION", "Afficher/masquer l'automation  Ctrl+Shift+A",
            self._toggle_automation_window, C_PURPLE)
        lay.addWidget(self._btn_automation)
        lay.addWidget(self._vsep2())

        # Export
        lay.addWidget(_btn("▼ MP4", self._export_mp4,  C_CYAN))
        lay.addWidget(_btn("▼ EXE", self._export_exe,  C_PURPLE))
        lay.addWidget(self._vsep2())

        # Zoom
        zoom_lbl = QLabel("ZOOM")
        zoom_lbl.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:7pt \'Courier New\';padding:0 2px;background:transparent;")
        lay.addWidget(zoom_lbl)

        self._zoom_sl = QSlider(Qt.Horizontal)
        self._zoom_sl.setRange(2, 40); self._zoom_sl.setValue(8)
        self._zoom_sl.setFixedWidth(90); self._zoom_sl.setFixedHeight(20)
        self._zoom_sl.setStyleSheet(
            f"QSlider::groove:horizontal{{background:{C_BG3.name()};height:4px;border-radius:2px;}}"
            f"QSlider::handle:horizontal{{background:{C_CYAN.name()};width:12px;height:12px;"
            f"margin:-4px 0;border-radius:6px;}}"
            f"QSlider::sub-page:horizontal{{background:{C_CYAN.name()}60;border-radius:2px;}}")
        self._zoom_sl.valueChanged.connect(self._on_zoom)
        lay.addWidget(self._zoom_sl)

        self._zoom_lbl = QLabel("8px/s")
        self._zoom_lbl.setStyleSheet(
            f"color:{C_CYAN.name()};font:8pt \'Courier New\';min-width:42px;background:transparent;")
        lay.addWidget(self._zoom_lbl)
        lay.addStretch()

        # Rocket status
        self._rocket_lbl = QLabel("◌ ROCKET")
        self._rocket_lbl.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:7pt \'Courier New\';background:transparent;")
        lay.addWidget(self._rocket_lbl)
        lay.addWidget(self._vsep2())

        # Save indicator
        self._save_lbl = QLabel("● SAVED")
        self._save_lbl.setStyleSheet(
            f"color:{C_GREEN.name()};font:bold 7pt \'Courier New\';background:transparent;")
        lay.addWidget(self._save_lbl)
        lay.addWidget(self._vsep2())

        # Time display
        self._time_lbl = QLabel("00:00.0")
        self._time_lbl.setStyleSheet(
            f"color:{C_CYAN.name()};font:bold 20pt \'Courier New\';background:transparent;")
        lay.addWidget(self._time_lbl)
        return tb

    def _vsep(self):
        f = QFrame(); f.setFrameShape(QFrame.VLine)
        c = QColor(C_BORDER); c.setAlpha(80)
        f.setStyleSheet(f"color:{c.name()};max-width:1px;margin:8px 2px;"); return f

    def _vsep2(self):
        return self._vsep()

    def _build_timeline_area(self):
        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        scroll = QScrollArea()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(False)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        self._tl = TimelineWidget(self)
        self._tl.block_selected.connect(self.select_block)
        self._tl.block_changed.connect(self._on_block_changed)
        self._tl.block_released.connect(self.autosave)
        scroll.setWidget(self._tl)
        scroll.horizontalScrollBar().valueChanged.connect(self._tl.set_scroll)
        lay.addWidget(scroll)
        lay.addWidget(self._build_audio_controls())
        return container

    def _build_audio_controls(self):
        """Barre de contrôles audio sous la timeline — Neon Void style."""
        bar = QWidget()
        bar.setFixedHeight(38)
        bar.setObjectName("audiobar")
        bar.setStyleSheet(
            f"#audiobar{{"
            f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {C_BG3.name()},stop:1 {C_BG2.name()});"
            f"border-top:1px solid {C_TEAL.name()}30;"
            f"border-bottom:1px solid {C_BORDER.name()};}}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 0, 12, 0)
        lay.setSpacing(8)

        # ♪ icon
        ico = QLabel("♪")
        ico.setStyleSheet(
            f"color:{C_TEAL.name()};font:bold 11pt 'Courier New';"
            f"background:transparent;")
        lay.addWidget(ico)

        # Filename label (double-clic pour changer)
        self._audio_file_lbl = QLabel("—")
        self._audio_file_lbl.setStyleSheet(
            f"color:{C_TXT.name()};font:8pt 'Courier New';"
            f"min-width:120px;max-width:200px;background:transparent;")
        self._audio_file_lbl.setToolTip("Double-clic pour changer le fichier audio")
        self._audio_file_lbl.mouseDoubleClickEvent = lambda e: self._pick_audio_file()
        lay.addWidget(self._audio_file_lbl)

        lay.addWidget(self._vsep())

        # Mute button
        self._mute_btn = QToolButton()
        self._mute_btn.setText("🔊")
        self._mute_btn.setFixedSize(26, 26)
        self._mute_btn.setToolTip("Mute / Unmute")
        self._mute_btn.setStyleSheet(
            f"QToolButton{{background:{C_BG4.name()};border:1px solid {C_BORDER2.name()};"
            f"border-radius:4px;font:11pt;color:{C_TEAL.name()};}}"
            f"QToolButton:hover{{background:{C_TEAL.name()}25;"
            f"border:1px solid {C_TEAL.name()}80;}}"
            f"QToolButton:pressed{{background:{C_TEAL.name()}40;}}")
        self._mute_btn.clicked.connect(self._audio_toggle_mute)
        lay.addWidget(self._mute_btn)

        # Volume label
        vol_lbl = QLabel("VOL")
        vol_lbl.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:6pt 'Courier New';"
            f"letter-spacing:1px;background:transparent;")
        lay.addWidget(vol_lbl)

        # Volume slider
        self._vol_slider = QSlider(Qt.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(100)
        self._vol_slider.setFixedWidth(80)
        self._vol_slider.setFixedHeight(18)
        self._vol_slider.setToolTip("Volume (0–100%)")
        self._vol_slider.setStyleSheet(
            f"QSlider::groove:horizontal{{background:{C_BG4.name()};"
            f"height:4px;border-radius:2px;border:1px solid {C_BORDER2.name()};}}"
            f"QSlider::handle:horizontal{{background:{C_TEAL.name()};"
            f"width:11px;height:11px;margin:-4px 0;border-radius:6px;}}"
            f"QSlider::sub-page:horizontal{{background:{C_TEAL.name()}70;"
            f"border-radius:2px;}}")
        self._vol_slider.valueChanged.connect(lambda v: self._audio_set_volume(v / 100.0))
        lay.addWidget(self._vol_slider)

        self._vol_pct_lbl = QLabel("100%")
        self._vol_pct_lbl.setStyleSheet(
            f"color:{C_TEAL.name()};font:7pt 'Courier New';"
            f"min-width:32px;background:transparent;")
        self._vol_slider.valueChanged.connect(lambda v: self._vol_pct_lbl.setText(f"{v}%"))
        lay.addWidget(self._vol_pct_lbl)

        lay.addWidget(self._vsep())

        # Duration label + edit
        dur_lbl = QLabel("DUR")
        dur_lbl.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:6pt 'Courier New';"
            f"letter-spacing:1px;background:transparent;")
        lay.addWidget(dur_lbl)

        self._dur_edit = QLineEdit()
        self._dur_edit.setFixedWidth(52)
        self._dur_edit.setFixedHeight(22)
        self._dur_edit.setPlaceholderText("240.0")
        self._dur_edit.setStyleSheet(
            f"QLineEdit{{background:{C_BG4.name()};color:{C_TXTHI.name()};"
            f"border:1px solid {C_BORDER2.name()};border-radius:3px;"
            f"padding:1px 5px;font:8pt 'Courier New';}}"
            f"QLineEdit:focus{{border:1px solid {C_TEAL.name()};}}")
        self._dur_edit.editingFinished.connect(self._apply_audio_duration)
        lay.addWidget(self._dur_edit)

        dur_s = QLabel("s")
        dur_s.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:7pt 'Courier New';background:transparent;")
        lay.addWidget(dur_s)

        # Auto detect button
        btn_detect = QPushButton("⟳ AUTO")
        btn_detect.setFixedHeight(22)
        btn_detect.setToolTip("Détecter la durée depuis le fichier MP3")
        btn_detect.setStyleSheet(
            f"QPushButton{{background:{C_BG4.name()};color:{C_TEAL.name()};"
            f"border:1px solid {C_TEAL.name()}40;border-radius:3px;"
            f"padding:0 8px;font:7pt 'Courier New';}}"
            f"QPushButton:hover{{background:{C_TEAL.name()}20;"
            f"border:1px solid {C_TEAL.name()}90;}}")
        btn_detect.clicked.connect(self._detect_audio_duration)
        lay.addWidget(btn_detect)

        if not AUDIO_AVAILABLE:
            warn = QLabel("  ⚠ PySide6-Multimedia manquant")
            warn.setStyleSheet(
                f"color:{C_ORANGE.name()};font:7pt 'Courier New';background:transparent;")
            lay.addWidget(warn)

        lay.addStretch()
        return bar

    def _build_statusbar(self):
        sb = QWidget()
        sb.setFixedHeight(24)
        sb.setObjectName("statusbar")
        sb.setStyleSheet(
            f"#statusbar{{background:{C_BG2.name()};"
            f"border-top:1px solid {C_BORDER.name()};}}")
        lay = QHBoxLayout(sb)
        lay.setContentsMargins(10, 0, 10, 0); lay.setSpacing(12)
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(
            f"color:{C_GREEN.name()};font:8pt;background:transparent;")
        lay.addWidget(self._status_dot)
        self._status_lbl = QLabel("Prêt.")
        self._status_lbl.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:7pt 'Courier New';background:transparent;")
        lay.addWidget(self._status_lbl)
        lay.addStretch()
        self._dir_lbl = QLabel(self.project_dir)
        self._dir_lbl.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:7pt 'Courier New';"
            f"background:transparent;max-width:400px;")
        lay.addWidget(self._dir_lbl)
        return sb

    def _build_menu(self):
        mb = self.menuBar()
        mss = (
            f"QMenuBar{{background:{C_BG2.name()};color:{C_TXT.name()};"
            f"font:8pt 'Courier New';border-bottom:1px solid {C_BORDER.name()};"
            f"padding:2px 4px;}}"
            f"QMenuBar::item{{padding:3px 10px;border-radius:3px;}}"
            f"QMenuBar::item:selected{{background:{C_BG4.name()};color:{C_CYAN.name()};}}"
            f"QMenu{{background:{C_BG2.name()};color:{C_TXT.name()};"
            f"border:1px solid {C_BORDER2.name()};font:8pt 'Courier New';padding:4px 0;}}"
            f"QMenu::item{{padding:5px 24px 5px 12px;}}"
            f"QMenu::item:selected{{background:{C_SEL.name()};color:{C_CYAN.name()};}}"
            f"QMenu::separator{{background:{C_BORDER.name()};height:1px;margin:4px 8px;}}")
        mb.setStyleSheet(mss)
        m_f = mb.addMenu("Fichier")
        m_f.addAction("Ouvrir project.json…", self._open_project)
        m_f.addAction("Changer dossier…",     self._change_dir)
        m_f.addSeparator()
        m_f.addAction("Sauvegarder  Ctrl+S",  lambda: self.autosave(force=True))
        m_f.addSeparator()
        m_f.addAction("Quitter",              self.close)
        m_e = mb.addMenu("Édition")
        m_e.addAction("Undo  Ctrl+Z",            lambda: self._tl.undo())
        m_e.addAction("Redo  Ctrl+Y",            lambda: self._tl.redo())
        m_e.addSeparator()
        m_e.addAction("Tout sélectionner  Ctrl+A",self._tl._select_all)
        m_e.addAction("Copier  Ctrl+C",           self._tl.copy_selection)
        m_e.addAction("Coller  Ctrl+V",           self._tl.paste_clipboard)
        m_e.addSeparator()
        m_e.addAction("Auto-arranger scènes",     self._auto_arrange)
        m_e.addAction("Effacer la timeline",      self._clear_timeline)
        m_e.addSeparator()
        m_e.addAction("Ajouter marqueur  M",      self._add_marker_at_playhead)
        m_e.addAction("Effacer marqueurs beat",   self._tl.clear_beat_markers)
        m_e.addAction("Générer marqueurs BPM…",   self._generate_beat_markers)
        m_e.addSeparator()
        m_e.addAction("Loop In  I",               self._set_loop_in)
        m_e.addAction("Loop Out  O",              self._set_loop_out)
        m_e.addAction("Effacer Loop",             lambda: self._tl.set_loop(None,None))
        m_e.addSeparator()
        m_e.addAction("Exporter clip sélectionné…", self._export_clip)
        m_e.addAction("Importer clip (.democlip)…",  self._import_clip)
        m_a = mb.addMenu("Assets")
        m_a.addAction("Rafraîchir  ⟳",           self._refresh_assets)
        m_a.addSeparator()
        m_a.addAction("Ajouter shader scène…",    lambda: self._import("scenes",   SCENE_EXTS))
        m_a.addAction("Ajouter overlay…",         lambda: self._import("overlays", OVERLAY_EXTS))
        m_a.addAction("Ajouter image…",           lambda: self._import("images",   IMAGE_EXTS))
        m_a.addAction("Ajouter font…",            lambda: self._import("fonts",    FONT_EXTS))
        m_a.addAction("Ajouter musique…",         lambda: self._import("music",    MUSIC_EXTS))
        m_a.addSeparator()
        m_a.addAction("Browser shaders  (vue grille)",  self._show_shader_browser)
        m_a.addAction("Vérifier les assets manquants…", self._check_missing_assets)
        # Phase 5.4 — Presets
        m_s = mb.addMenu("Shaders")
        m_s.addAction("Éditeur GLSL inline",             self._toggle_glsl_editor)
        m_s.addAction("Ouvrir shader dans l'éditeur…",   self._pick_shader_for_editor)
        m_s.addSeparator()
        m_s.addAction("Presets de scènes…",              self._open_preset_manager)
        m_r = mb.addMenu("Rocket")
        m_r.addAction("Connecter à GNU Rocket…", self._connect_rocket_dlg)
        m_r.addAction("Déconnecter",             self._disconnect_rocket)
        m_p = mb.addMenu("Automation")
        m_p.addAction("Afficher l'éditeur de courbes",  self._show_automation)
        m_p.addAction("Tout quantifier sur les beats",   self._quantize_all)
        m_p.addAction("Effacer l'automation de la scène", self._clear_automation)
        m_p.addSeparator()
        m_p.addAction("Import Rocket .xml…",  self._import_rocket)
        m_p.addAction("Export Rocket .xml…",  self._export_rocket)
        # ── Menu Fenêtres ─────────────────────────────────────────────────
        m_w = mb.addMenu("Fenêtres")
        m_w.setStyleSheet(mss)
        act_vp = m_w.addAction("▣  Viewport OpenGL",    self._toggle_viewport_window)
        act_vp.setShortcut(QKeySequence("Ctrl+Shift+V"))
        act_au = m_w.addAction("◈  Automation",         self._toggle_automation_window)
        act_au.setShortcut(QKeySequence("Ctrl+Shift+A"))
        m_w.addSeparator()
        m_w.addAction("Tout afficher",  self._show_all_windows)
        m_w.addAction("Tout masquer",   self._hide_all_windows)
        m_x = mb.addMenu("Export")
        m_x.addAction("Exporter en MP4…",        self._export_mp4)
        m_x.addAction("Compiler EXE / Binaire…", self._export_exe)
        m_x.addSeparator()
        m_x.addAction("Queue d'export…",          self._open_export_queue)
        # Phase 6 — Interface
        m_u = mb.addMenu("Interface")
        m_u.addAction("Thèmes…",                  self._open_theme_dialog)
        m_u.addSeparator()
        m_u.addAction("Palette de commandes  Ctrl+P", self._open_command_palette)
        m_u.addAction("Raccourcis clavier…",      self._open_keymap_editor)
        m_u.addSeparator()
        m_u.addAction("Macros…",                  self._open_macros)
        m_u.addAction("Enregistrer macro…",       self._record_macro)
        m_u.addSeparator()
        m_u.addAction("Logs structurés…",         self._open_log_panel)
        # Phase 7 — Entrées live
        m_live = mb.addMenu("Live")
        m_live.addAction("OSC / MIDI Input…",     self._open_osc_midi)

        # Phase 9 — Fonctionnalités Créatives
        if _PHASE9:
            m_p9 = mb.addMenu("Phase 9 ✨")
            m_p9.setStyleSheet(mss)
            m_p9.addAction("🎥  Caméra — Trajectoires…",     self._open_camera_editor)
            m_p9.addAction("📦  Importer depuis Blender…",   self._open_blender_import)
            m_p9.addSeparator()
            m_p9.addAction("✨  Particules — Paramètres…",   self._open_particle_editor)
            m_p9.addSeparator()
            m_p9.addAction("🔤  Texte SDF — Configuration…", self._open_text_editor)

    def _apply_stylesheet(self):
        self.setStyleSheet(
            f"QMainWindow,QWidget{{background:{C_BG.name()};color:{C_TXT.name()};}}"
            f"QSplitter::handle{{background:{C_BORDER.name()};width:1px;height:1px;}}"
            f"QScrollBar:horizontal{{background:{C_BG2.name()};height:8px;border:none;border-radius:4px;margin:0 2px;}}"
            f"QScrollBar::handle:horizontal{{background:{C_BORDER2.name()};min-width:30px;border-radius:4px;}}"
            f"QScrollBar::handle:horizontal:hover{{background:{C_CYAN.name()}50;}}"
            f"QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{{width:0;}}"
            f"#toolbar{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {C_BG3.name()},stop:1 {C_BG2.name()});"
            f"border-bottom:1px solid {C_BORDER2.name()};}}"
            f"QToolTip{{background:{C_BG3.name()};color:{C_TXTHI.name()};"
            f"border:1px solid {C_BORDER2.name()};font:8pt 'Courier New';"
            f"padding:4px 8px;border-radius:3px;}}")

    # ── Import ────────────────────────────────────────────────

    def _import(self, subdir, exts):
        dest = os.path.join(self.project_dir, subdir)
        os.makedirs(dest, exist_ok=True)
        exts_str = " ".join(f"*{e}" for e in exts)
        paths, _ = QFileDialog.getOpenFileNames(
            self, f"Importer dans {subdir}/", "",
            f"Fichiers ({exts_str});;Tous (*.*)")
        if not paths: return
        n = 0
        for src in paths:
            dst = os.path.join(dest, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copy2(src, dst); n += 1
        if n:
            self._refresh_assets()
            self._set_status(f"{n} fichier(s) importé(s) dans {subdir}/")

    # ── Timeline par défaut / chargement ─────────────────────

    def _load_default_timeline(self):
        pj = os.path.join(self.project_dir, PROJECT_FILE)
        if os.path.exists(pj):
            try: self._load_project_file(pj); return
            except Exception: pass
        self.scenes = []; self.overlays = []; self.images = []; self.scrolls = []
        self._refresh_timeline()

    def _sync_viewport(self):
        """Pousse les données timeline courantes vers le viewport."""
        if not self._viewport:
            return
        self._viewport.set_project(
            self.cfg,
            [{"name": b.name, "base_name": b.base,
              "start": b.start, "duration": b.duration}
             for b in self.scenes],
            [{"name": b.name, "file": b.file, "effect": b.effect,
              "start": b.start, "duration": b.duration}
             for b in self.overlays + self.scrolls],
            [{"name": b.name, "file": b.file, "effect": b.effect,
              "start": b.start, "duration": b.duration}
             for b in self.images]
        )

    # ── Actions ───────────────────────────────────────────────

    def _add_from_asset(self, kind, value):
        self._tl.push_undo()
        if kind == "scene":
            start = max((b.end() for b in self.scenes), default=0.0)
            display = value
            for base, name, _ in scan_scenes(self.project_dir):
                if base == value: display = name; break
            b = Block("scene", display, start, 10.0, base=value)
            self.scenes.append(b)

        elif kind == "overlay_shader":
            start = max((b.end() for b in self.overlays), default=0.0)
            b = Block("overlay", value, start, 5.0, file="", effect=value)
            self.overlays.append(b)

        elif kind == "image":
            start = max((b.end() for b in self.images), default=0.0)
            b = Block("image", os.path.basename(value), start, 5.0,
                      file=value, effect="")
            self.images.append(b)

        elif kind == "font":
            self._set_status(f"Font : {value}  (utilisez dans Config Project)")
            return

        elif kind == "music":
            self.cfg["MUSIC_FILE"] = value
            if hasattr(self, "_config_panel"):
                self._config_panel.refresh(self.cfg)
            self._sync_audio_controls()
            self._tl.update()
            self.autosave()
            self._set_status(f"♪ Musique définie : {os.path.basename(value)}")
            return

        else:
            return

        self.select_block(b)
        self._refresh_timeline()
        self.autosave()
        self._sync_viewport()
        self._set_status(f"+ {b.name} ajouté à {b.start:.1f}s")

    def select_block(self, b):
        self.selected = b
        self._tl.update()
        if b: self._props.show_block(b)
        else: self._props._show_empty()
        # Phase 4 — mettre à jour le panneau automation
        if hasattr(self, '_on_block_selected_for_params'):
            self._on_block_selected_for_params(b)

    def _on_block_changed(self):
        if self.selected: self._props.update_fin(self.selected)
        self._sync_viewport()

    def _on_props_applied(self):
        self._tl.update(); self.autosave()
        self._sync_viewport()

    def _delete_selected(self):
        if not self.selected and not self._tl._selection: return
        self._tl.push_undo()
        to_delete = self._tl._selected_blocks()
        if not to_delete and self.selected:
            to_delete = [self.selected]
        for b in to_delete:
            for lst in [self.scenes, self.overlays, self.images, self.scrolls]:
                if b in lst: lst.remove(b); break
        self._tl._selection.clear()
        self.select_block(None)
        self._refresh_timeline(); self.autosave()
        self._sync_viewport()

    def _duplicate_selected(self):
        if not self.selected: return
        self._tl.push_undo()
        b = copy.deepcopy(self.selected)
        Block._counter += 1; b.uid = Block._counter
        b.start += b.duration
        lst = (self.scenes if b.kind == "scene"
               else self.overlays if b.kind == "overlay"
               else self.images   if b.kind == "image"
               else self.scrolls)
        lst.append(b)
        self.select_block(b)
        self._refresh_timeline(); self.autosave()
        self._sync_viewport()

    def _auto_arrange(self):
        self._tl.push_undo()
        self.scenes.sort(key=lambda b: b.start)
        cur = 0.0
        for b in self.scenes:
            b.start = round(cur * 4) / 4; cur += b.duration
        self._tl.update(); self.autosave()
        self._set_status("Scènes auto-arrangées.")
        self._sync_viewport()

    # ── Phase 3 : Marqueurs ──────────────────────────────────────────────────

    def _add_marker_at_playhead(self):
        t = self._tl.playhead
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Marqueur", "Nom du marqueur :", text=f"M{t:.1f}")
        if ok:
            self._tl.add_marker(t, name or f"M{t:.1f}")
            self._set_status(f"Marqueur '{name}' ajouté à {t:.2f}s")

    def _generate_beat_markers(self):
        from PySide6.QtWidgets import QInputDialog
        bpm, ok = QInputDialog.getDouble(self, "Marqueurs BPM",
                                          "BPM :", self._tl._bpm, 40, 300, 1)
        if ok:
            dur = self.cfg.get("MUSIC_DURATION", 240.0)
            self._tl.generate_beat_markers(bpm, dur)
            self._set_status(f"Marqueurs BPM générés ({bpm:.0f} BPM)")

    def _set_loop_in(self):
        self._tl.set_loop(self._tl.playhead, self._tl.loop_out)
        self._set_status(f"Loop In : {self._tl.playhead:.2f}s")

    def _set_loop_out(self):
        self._tl.set_loop(self._tl.loop_in, self._tl.playhead)
        self._set_status(f"Loop Out : {self._tl.playhead:.2f}s")

    # ── Phase 3 : Versioning et sauvegarde ───────────────────────────────────

    def _do_save(self):
        # Phase 4 : sauvegarder l'automation dans cfg
        if hasattr(self, '_param_sys'):
            self.cfg['automation'] = self._param_sys.to_dict()
        # Phase 9 : sauvegarder les trajectoires caméra
        cameras = None
        if _PHASE9 and self.camera_system:
            cameras = self.camera_system.to_dict()
        ok, err = save_to_disk(
            self.project_dir, self.scenes, self.overlays, self.scrolls, self.images, self.cfg,
            markers=getattr(self._tl, "markers", []), cameras=cameras)
        if ok:
            self._save_lbl.setText("● SAVED")
            self._save_lbl.setStyleSheet(
                f"color:{C_GREEN.name()};font:bold 7pt 'Courier New';background:transparent;")
            if hasattr(self, '_status_dot'):
                self._status_dot.setStyleSheet(
                    f"color:{C_GREEN.name()};font:8pt;background:transparent;")
            ts = time.strftime("%H:%M:%S")
            self._set_status(
                f"Sauvegardé → {os.path.join(self.project_dir, PROJECT_FILE)}  [{ts}]")
            # Versioning léger : copier avec timestamp toutes les 5 minutes
            self._maybe_version()
        else:
            self._save_lbl.setText("● ERREUR")
            self._save_lbl.setStyleSheet(
                f"color:{C_ORANGE.name()};font:bold 7pt 'Courier New';background:transparent;")
            self._set_status(f"ERREUR : {err}")

    def _maybe_version(self):
        """Crée une version horodatée toutes les 5 minutes."""
        now = time.time()
        if not hasattr(self, '_last_version_t'):
            self._last_version_t = 0.0
        if now - self._last_version_t < 300:  # 5 minutes
            return
        self._last_version_t = now
        src = os.path.join(self.project_dir, PROJECT_FILE)
        if not os.path.exists(src):
            return
        ver_dir = os.path.join(self.project_dir, ".versions")
        os.makedirs(ver_dir, exist_ok=True)
        ts  = time.strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(ver_dir, f"project_{ts}.json")
        try:
            import shutil
            shutil.copy2(src, dst)
            # Garder seulement les 20 dernières versions
            versions = sorted(os.listdir(ver_dir))
            for old in versions[:-20]:
                os.remove(os.path.join(ver_dir, old))
        except Exception:
            pass

    # ── Phase 3 : Import / Export de clips ───────────────────────────────────

    def _export_clip(self):
        """Exporte les blocs sélectionnés en fichier .democlip."""
        sel = self._tl._selected_blocks()
        if not sel and self.selected:
            sel = [self.selected]
        if not sel:
            self._set_status("Aucun bloc sélectionné pour l'export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter clip", self.project_dir,
            "DemoClip (*.democlip);;JSON (*.json)")
        if not path:
            return
        if not path.endswith((".democlip", ".json")):
            path += ".democlip"
        clip = {
            "_type": "democlip",
            "_version": "1.0",
            "_created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "blocks": [
                {
                    "kind":     b.kind,
                    "name":     b.name,
                    "start":    round(b.start, 3),
                    "duration": round(b.duration, 3),
                    "base":     getattr(b, "base", ""),
                    "file":     getattr(b, "file", ""),
                    "effect":   getattr(b, "effect", ""),
                }
                for b in sorted(sel, key=lambda x: x.start)
            ]
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(clip, f, indent=2, ensure_ascii=False)
            self._set_status(f"Clip exporté : {os.path.basename(path)} ({len(sel)} bloc(s))")
        except Exception as e:
            self._set_status(f"Erreur export clip : {e}")

    def _import_clip(self):
        """Importe un fichier .democlip dans la timeline."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer clip", self.project_dir,
            "DemoClip (*.democlip);;JSON (*.json);;Tous (*.*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                clip = json.load(f)
            if clip.get("_type") != "democlip":
                self._set_status("Fichier non reconnu comme DemoClip.")
                return
            self._tl.push_undo()
            # Décaler tous les blocs après la fin de la timeline courante
            all_b = self.scenes + self.overlays + self.images + self.scrolls
            offset = max((b.end() for b in all_b), default=0.0) if all_b else 0.0
            clip_start = min((b["start"] for b in clip["blocks"]), default=0.0)
            delta = offset - clip_start
            imported = 0
            for bd in clip["blocks"]:
                b = Block(
                    kind     = bd["kind"],
                    name     = bd["name"],
                    start    = bd["start"] + delta,
                    duration = bd["duration"],
                    base     = bd.get("base", ""),
                    file     = bd.get("file", ""),
                    effect   = bd.get("effect", "overlay_glitch"),
                )
                lst = self._tl._list_for_kind(b.kind)
                lst.append(b); imported += 1
            self._refresh_timeline(); self.autosave(); self._sync_viewport()
            self._set_status(f"Clip importé : {imported} bloc(s) depuis {os.path.basename(path)}")
        except Exception as e:
            self._set_status(f"Erreur import clip : {e}")

    # ══════════════════════════════════════════════════════════
    #  PHASE 4 — AUTOMATION & ROCKET
    # ══════════════════════════════════════════════════════════

    # ── Fenêtres flottantes ───────────────────────────────────────────────────

    def _toggle_viewport_window(self):
        """Affiche ou masque la fenêtre Viewport flottante."""
        if self._viewport_window is None:
            self._set_status("Viewport non disponible (viewport.py requis).")
            if hasattr(self, '_btn_viewport'): self._btn_viewport.setChecked(False)
            return
        if self._viewport_window.isVisible():
            self._viewport_window.hide()
            if hasattr(self, '_btn_viewport'): self._btn_viewport.setChecked(False)
        else:
            self._viewport_window.show()
            self._viewport_window.raise_()
            self._viewport_window.activateWindow()
            if hasattr(self, '_btn_viewport'): self._btn_viewport.setChecked(True)
            self._sync_viewport()

    def _toggle_automation_window(self):
        """Affiche ou masque la fenêtre Automation flottante."""
        if self._auto_window is None:
            self._set_status("Automation non disponible (automation_widget.py requis).")
            if hasattr(self, '_btn_automation'): self._btn_automation.setChecked(False)
            return
        if self._auto_window.isVisible():
            self._auto_window.hide()
            if hasattr(self, '_btn_automation'): self._btn_automation.setChecked(False)
        else:
            self._auto_window.show()
            self._auto_window.raise_()
            self._auto_window.activateWindow()
            if hasattr(self, '_btn_automation'): self._btn_automation.setChecked(True)
            if self.selected and self.selected.kind == "scene":
                self._auto_panel.load_scene(self.selected.base, self._param_sys)

    def _show_all_windows(self):
        if self._viewport_window:
            self._viewport_window.show(); self._viewport_window.raise_()
        if self._auto_window:
            self._auto_window.show(); self._auto_window.raise_()

    def _hide_all_windows(self):
        if self._viewport_window: self._viewport_window.hide()
        if self._auto_window:     self._auto_window.hide()

    def _show_automation(self):
        """Affiche la fenêtre Automation et charge la scène courante."""
        if self._auto_window is None:
            self._set_status("automation_widget.py requis."); return
        self._auto_window.show()
        self._auto_window.raise_()
        self._auto_window.activateWindow()
        if self.selected and self.selected.kind == "scene":
            self._auto_panel.load_scene(self.selected.base, self._param_sys)

    def _quantize_all(self):
        if not self.selected or self.selected.kind != "scene": return
        self._param_sys.quantize_all(self.selected.base, float(self._tl._bpm))
        if self._auto_panel: self._auto_panel.refresh()
        self._set_status(f"Quantifié sur {self._tl._bpm:.0f} BPM")

    def _clear_automation(self):
        if not self.selected or self.selected.kind != "scene": return
        name = self.selected.base
        for slot in self._param_sys._slots.get(name, {}).values():
            if slot.curve: slot.curve.keyframes.clear()
        if self._auto_panel: self._auto_panel.refresh()
        self.autosave()
        self._set_status(f"Automation effacée pour '{name}'")

    def _on_block_selected_for_params(self, block):
        if not self._auto_panel or not AUTOMATION_AVAILABLE: return
        if block and block.kind == "scene":
            sp = os.path.join(self.project_dir, "scenes", f"scene_{block.base}.frag")
            if os.path.exists(sp):
                params = self._param_sys.parse_shader(sp)
                if params: self._param_sys.register_scene(block.base, params)
            self._auto_panel.load_scene(block.base, self._param_sys)
        else:
            self._auto_panel.load_scene(None, self._param_sys)

    def _import_rocket(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importer Rocket XML",
            self.project_dir, "Rocket XML (*.xml *.rocket);;Tous (*.*)")
        if not path: return
        try:
            import xml.etree.ElementTree as ET
            tr2 = ET.parse(path); root2 = tr2.getroot()
            rps = self.cfg.get("ROWS_PER_SECOND", 8); imported = 0
            for track in root2.findall(".//track"):
                parts = track.get("name","").split(".")
                if len(parts) != 2: continue
                sn, pn = parts
                params = self._param_sys.get_params(sn)
                param  = next((p for p in params if p.name == pn), None)
                if param is None:
                    param = ParamDef(pn, "float", 0.0, 0.0, 1.0)
                    self._param_sys.register_scene(sn, [param])
                from param_system import AutomationCurve
                curve = AutomationCurve(param)
                for key in track.findall("key"):
                    itp = ["step","linear","smooth"][min(int(key.get("interpolation",1)),2)]
                    curve.add_keyframe(int(key.get("row",0))/rps,
                                       float(key.get("value",0.0)), itp)
                slot = self._param_sys.get_slot(sn, pn)
                if slot: slot.curve = curve
                imported += 1
            self.autosave()
            self._set_status(f"Rocket importé : {imported} track(s)")
        except Exception as e:
            self._set_status(f"Erreur import Rocket : {e}")

    def _export_rocket(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exporter Rocket XML",
            self.project_dir, "Rocket XML (*.xml);;Tous (*.*)")
        if not path: return
        if not path.endswith(".xml"): path += ".xml"
        try:
            import xml.etree.ElementTree as ET
            rps = self.cfg.get("ROWS_PER_SECOND", 8)
            root2 = ET.Element("tracks")
            for sn, slots in self._param_sys._slots.items():
                for pn, slot in slots.items():
                    if not slot.curve or not slot.curve.keyframes: continue
                    tr = ET.SubElement(root2, "track", name=f"{sn}.{pn}")
                    for kf in slot.curve.keyframes:
                        val  = kf.value if not isinstance(kf.value,tuple) else kf.value[0]
                        mode = {"step":0,"linear":1,"smooth":2}.get(kf.interp,1)
                        ET.SubElement(tr,"key",row=str(int(kf.t*rps)),
                                      value=f"{float(val):.6f}",interpolation=str(mode))
            ET.indent(root2)
            ET.ElementTree(root2).write(path, encoding="unicode", xml_declaration=True)
            self._set_status(f"Rocket exporté : {os.path.basename(path)}")
        except Exception as e:
            self._set_status(f"Erreur export Rocket : {e}")

    def _clear_timeline(self):
        if QMessageBox.question(self, "CLEAR", "Effacer toute la timeline ?",
            QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self._tl.push_undo()
            self.scenes.clear(); self.overlays.clear(); self.images.clear(); self.scrolls.clear()
            self.select_block(None)
            self._refresh_timeline(); self.autosave()
            self._sync_viewport()

    def _refresh_timeline(self):
        self._tl.setFixedWidth(self._tl._total_w()); self._tl.update()

    def _on_zoom(self, val):
        self._zoom_lbl.setText(f"{val}px/s"); self._tl.set_zoom(val)

    # ── Playback ──────────────────────────────────────────────

    def _audio_load(self):
        """Charge le fichier audio depuis cfg si besoin."""
        if not self._audio_player:
            return
        music_rel = self.cfg.get("MUSIC_FILE", "")
        if not music_rel:
            return
        path = os.path.join(self.project_dir, music_rel)
        if not os.path.exists(path):
            self._set_status(f"⚠ Fichier audio introuvable : {path}")
            return
        url = QUrl.fromLocalFile(os.path.abspath(path))
        if self._audio_player.source() != url:
            self._audio_player.setSource(url)

    def _audio_play(self, t=None):
        if not self._audio_player:
            return
        self._audio_load()
        if t is not None:
            self._audio_player.setPosition(int(t * 1000))
        self._audio_output.setVolume(0.0 if self._audio_muted else self._audio_volume)
        self._audio_player.play()

    def _audio_pause(self):
        if self._audio_player:
            self._audio_player.pause()

    def _audio_stop(self):
        if self._audio_player:
            self._audio_player.stop()

    def _audio_seek(self, t):
        if self._audio_player:
            self._audio_player.setPosition(int(t * 1000))

    def _audio_set_volume(self, val):
        """val = 0.0 à 1.0"""
        self._audio_volume = val
        if self._audio_output and not self._audio_muted:
            self._audio_output.setVolume(val)
        # Met à jour le label du bouton mute
        if hasattr(self, "_mute_btn"):
            self._mute_btn.setText("🔇" if self._audio_muted else ("🔈" if val < 0.4 else "🔊"))

    def _audio_toggle_mute(self):
        self._audio_muted = not self._audio_muted
        if self._audio_output:
            self._audio_output.setVolume(0.0 if self._audio_muted else self._audio_volume)
        if hasattr(self, "_mute_btn"):
            self._mute_btn.setText("🔇" if self._audio_muted else "🔊")

    def _toggle_play(self):
        if self.rocket and ROCKET_AVAILABLE:
            self.rocket_playing = not self.rocket_playing
        else:
            self._local_playing = not self._local_playing
            if self._local_playing:
                self._local_start = time.time() - self._tl.playhead
                self._audio_play(self._tl.playhead)
            else:
                self._audio_pause()
        playing = self._local_playing or self.rocket_playing
        self._play_btn.setText("⏸  PAUSE" if playing else "▶  PLAY")

    def _reset_playhead(self):
        self._local_playing = False; self.rocket_playing = False
        self._play_btn.setText("▶  PLAY")
        self._audio_stop()
        self._tl.set_playhead(0.0); self._update_time(0.0)
        if self._viewport:
            self._viewport.set_time(0.0)

    def _rocket_seek(self, t):
        self._audio_seek(t)
        if self._viewport:
            self._viewport.set_time(t)
        if self.rocket and ROCKET_AVAILABLE:
            row = int(t * self.cfg.get("ROWS_PER_SECOND", 8))
            try: self.rocket.connector.controller_row_changed(row)
            except Exception: pass

    def _update_time(self, t):
        self._current_t = t   # exposé pour l'enregistrement live (Phase 4.2)
        m = int(t) // 60; s = int(t) % 60; ds = int((t * 10) % 10)
        self._time_lbl.setText(f"{m:02d}:{s:02d}.{ds}")

    def _tick(self):
        if self.rocket and ROCKET_AVAILABLE:
            try:
                self.rocket.update()
                t = self.rocket.time
                self._tl.set_playhead(t); self._update_time(t)
                if self._viewport:
                    self._viewport.set_time(t)
            except Exception:
                self._disconnect_rocket()
        elif self._local_playing:
            t = time.time() - self._local_start
            max_t = self.cfg.get("MUSIC_DURATION", 240.0)
            if t >= max_t:
                t = max_t; self._local_playing = False
                self._audio_stop()
                self._play_btn.setText("▶  PLAY")
            # Gestion de la région de loop (Phase 3.3)
            lo, hi = self._tl.loop_in, self._tl.loop_out
            if lo is not None and hi is not None and lo < hi:
                if t >= hi:
                    t = lo
                    self._local_start = time.time() - t
                    self._audio_seek(t)
            self._tl.set_playhead(t); self._update_time(t)
            if self._viewport:
                self._viewport.set_time(t)
            # Mettre à jour les uniforms audio courants pour l'enregistrement live
            if hasattr(self, '_viewport') and self._viewport:
                au = getattr(self._viewport, 'last_audio_uniforms', None)
                if au:
                    self._last_audio_uniforms = au

    def _pick_audio_file(self):
        exts_str = " ".join(f"*{e}" for e in MUSIC_EXTS)
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir fichier audio", self.project_dir,
            f"Audio ({exts_str});;Tous (*.*)")
        if not path:
            return
        # Copie dans music/ si besoin
        dest_dir = os.path.join(self.project_dir, "music")
        os.makedirs(dest_dir, exist_ok=True)
        dst = os.path.join(dest_dir, os.path.basename(path))
        if os.path.abspath(path) != os.path.abspath(dst):
            shutil.copy2(path, dst)
        rel = os.path.join("music", os.path.basename(dst))
        self.cfg["MUSIC_FILE"] = rel
        self._sync_audio_controls()
        if hasattr(self, "_config_panel"):
            self._config_panel.refresh(self.cfg)
        self._tl.update()
        self.autosave()
        self._set_status(f"♪ Musique : {rel}")

    def _apply_audio_duration(self):
        try:
            v = float(self._dur_edit.text())
            if v > 0:
                self.cfg["MUSIC_DURATION"] = v
                self._tl.set_zoom(self._tl.px_per_sec)  # force recalc width
                self._tl.update()
                if hasattr(self, "_config_panel"):
                    self._config_panel.refresh(self.cfg)
                self.autosave()
        except ValueError:
            pass

    def _detect_audio_duration(self):
        """Tente de lire la durée réelle du fichier MP3 via QMediaPlayer."""
        if not AUDIO_AVAILABLE or not self._audio_player:
            self._set_status("⚠ Lecture audio non disponible.")
            return
        self._audio_load()
        # On attend que le player ait chargé les métadonnées
        def _on_duration(ms):
            if ms > 0:
                secs = ms / 1000.0
                self.cfg["MUSIC_DURATION"] = round(secs, 2)
                self._dur_edit.setText(f"{secs:.1f}")
                self._tl.set_zoom(self._tl.px_per_sec)
                self._tl.update()
                if hasattr(self, "_config_panel"):
                    self._config_panel.refresh(self.cfg)
                self.autosave()
                self._set_status(f"♪ Durée détectée : {secs:.1f}s")
        try:
            # Déconnecter d'abord pour éviter les connexions multiples
            try:
                self._audio_player.durationChanged.disconnect()
            except Exception:
                pass
            self._audio_player.durationChanged.connect(_on_duration)
        except Exception:
            pass
        self._set_status("⟳ Chargement métadonnées audio…")

    def _sync_audio_controls(self):
        """Met à jour les widgets de la barre audio depuis cfg."""
        music_file = self.cfg.get("MUSIC_FILE", "")
        dur = self.cfg.get("MUSIC_DURATION", 240.0)
        if hasattr(self, "_audio_file_lbl"):
            lbl = os.path.basename(music_file) if music_file else "— aucun fichier —"
            self._audio_file_lbl.setText(lbl)
            self._audio_file_lbl.setToolTip(music_file)
        if hasattr(self, "_dur_edit"):
            self._dur_edit.setText(f"{dur:.1f}")

    # ── Rocket ────────────────────────────────────────────────

    def _init_rocket(self):
        if self._rocket_host and ROCKET_AVAILABLE:
            self._connect_rocket(self._rocket_host, self._rocket_port)

    def _connect_rocket_dlg(self):
        if not ROCKET_AVAILABLE:
            QMessageBox.warning(self, "Rocket", "pyrocket non installé."); return
        dlg = QDialog(self)
        dlg.setWindowTitle("Connecter GNU Rocket")
        dlg.setStyleSheet(
            f"QDialog{{background:{C_BG2.name()};}} QLabel{{color:{C_TXT.name()};}}")
        lay = QFormLayout(dlg)
        h_e = QLineEdit("127.0.0.1"); p_e = QLineEdit("1338")
        es = (f"background:{C_BG3.name()};color:{C_TXTHI.name()};"
              f"border:1px solid {C_BORDER.name()};padding:3px;")
        h_e.setStyleSheet(es); p_e.setStyleSheet(es)
        lay.addRow("Host", h_e); lay.addRow("Port", p_e)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.setStyleSheet(
            f"QPushButton{{background:{C_BG3.name()};color:{C_ACC.name()};"
            f"border:1px solid {C_ACC.name()};padding:4px 10px;}}")
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay.addRow(bb)
        if dlg.exec() == QDialog.Accepted:
            self._connect_rocket(h_e.text(), int(p_e.text()))

    def _connect_rocket(self, host, port):
        try:
            ctrl = TimeController(rows_per_second=self.cfg.get("ROWS_PER_SECOND", 8))
            self.rocket = Rocket.from_socket(
                ctrl, host=host, port=port, track_path=self.project_dir)
            self._rocket_lbl.setText(f"◉  ROCKET {host}:{port}")
            self._rocket_lbl.setStyleSheet(
                f"color:{C_GREEN.name()};font:bold 7pt 'Courier New';background:transparent;")
            self._set_status(f"Rocket connecté à {host}:{port}")
        except Exception as e:
            self.rocket = None
            QMessageBox.critical(self, "Rocket", f"Connexion échouée :\n{e}")

    def _disconnect_rocket(self):
        self.rocket = None; self.rocket_playing = False
        self._rocket_lbl.setText("◌ ROCKET")
        self._rocket_lbl.setStyleSheet(
            f"color:{C_TXTDIM.name()};font:7pt 'Courier New';background:transparent;")
        self._play_btn.setText("▶  PLAY")

    # ── Autosave ──────────────────────────────────────────────

    def autosave(self, force=False):
        self._save_lbl.setText("● MODIFIÉ")
        self._save_lbl.setStyleSheet(
            f"color:{C_ORANGE.name()};font:bold 7pt 'Courier New';background:transparent;")
        if hasattr(self, '_status_dot'):
            self._status_dot.setStyleSheet(
                f"color:{C_ORANGE.name()};font:8pt;background:transparent;")
        self._save_timer.stop()
        self._save_timer.start(0 if force else 300)


    def _change_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier projet", self.project_dir)
        if d:
            self.project_dir = d
            self._dir_lbl.setText(d)
            self._setup_watcher()
            self._refresh_assets()
            if self._viewport:
                self._viewport.set_project_dir(d)
            self.autosave(force=True)

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir project.json", self.project_dir,
            "Projet Demomaker (project.json);;JSON (*.json);;Tous (*.*)")
        if not path: return
        try:
            self._load_project_file(path)
            self._set_status(f"Projet chargé : {path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger :\n{e}")

    def _load_project_file(self, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.cfg = data.get("config", dict(DEFAULT_CONFIG))
        if "RES_W" in self.cfg and "RES" not in self.cfg:
            self.cfg["RES"] = [self.cfg.pop("RES_W"), self.cfg.pop("RES_H")]
        self.scenes = []
        for s in data.get("timeline", []):
            b = Block(
                "scene", s.get("name", s.get("base_name", "")),
                s["start"], s["duration"], base=s.get("base_name", ""))
            # Phase 9 — conserver particles / text / camera par scène
            for key in ("particles", "text", "camera"):
                if key in s:
                    setattr(b, key, s[key])
            self.scenes.append(b)
        self.overlays = []; self.scrolls = []; self.images = []
        for o in data.get("overlays", []):
            if o.get("file") == "SCROLL_INTERNAL":
                self.scrolls.append(Block(
                    "scroll", o.get("name", "SCROLL TEXT"),
                    o["start"], o["duration"],
                    file="SCROLL_INTERNAL",
                    effect=o.get("effect", "overlay_scrolltext")))
            else:
                self.overlays.append(Block(
                    "overlay", o.get("name", "OVERLAY"),
                    o["start"], o["duration"],
                    file=o.get("file", ""),
                    effect=o.get("effect", "overlay_glitch")))
        for img in data.get("images", []):
            self.images.append(Block(
                "image", img.get("name", os.path.basename(img.get("file", ""))),
                img["start"], img["duration"],
                file=img.get("file", ""), effect=""))
        self.project_dir = os.path.dirname(os.path.abspath(path))
        self._dir_lbl.setText(self.project_dir)
        self.select_block(None)
        if hasattr(self, "_config_panel"):
            self._config_panel.refresh(self.cfg)
        self._refresh_timeline()
        self._setup_watcher()
        self._refresh_assets()
        if self._viewport:
            self._viewport.set_project_dir(self.project_dir)
        if hasattr(self, '_viewport_window') and self._viewport_window:
            self._viewport_window.setWindowTitle(
                f"MEGADEMO — Viewport  [{os.path.basename(self.project_dir)}]")
        self._sync_viewport()
        self._sync_audio_controls()
        if hasattr(self, '_shader_browser'):
            self._shader_browser.set_project_dir(self.project_dir)
        QTimer.singleShot(300, self._validate_assets_on_load)
        # Phase 9 — Recharger les trajectoires caméra
        if _PHASE9 and self.camera_system:
            self.camera_system.load_from_project(data)
            res    = tuple(self.cfg.get("RES", [1920, 1080]))
            self.camera_system.aspect = res[0] / max(res[1], 1)

    # ── Phase 5 — Shaders & Assets ───────────────────────────────────────────

    def _show_shader_browser(self):
        """Bascule sur l'onglet Browser du panneau gauche et rafraîchit les thumbnails."""
        # Trouver l'onglet Browser (index 1) dans left_tabs
        try:
            left_tabs = self._shader_browser.parent().parent()
            left_tabs.setCurrentIndex(1)
        except Exception:
            pass
        self._shader_browser.set_project_dir(self.project_dir)

    def _open_shader_in_editor(self, path: str):
        """Ouvre un fichier shader dans l'éditeur GLSL inline (Phase 5.2)."""
        if os.path.exists(path):
            self._glsl_editor.setVisible(True)
            self._glsl_editor.load_file(path)
            self._set_status(f"Shader ouvert : {os.path.basename(path)}")
        else:
            self._set_status(f"⚠ Fichier introuvable : {path}")

    def _toggle_glsl_editor(self):
        """Affiche/masque l'éditeur GLSL inline sans perturber le viewport."""
        visible = not self._glsl_editor.isVisible()
        self._glsl_editor.setVisible(visible)
        # Ajuster les tailles du splitter parent
        splitter = self._glsl_editor.parent()
        if isinstance(splitter, QSplitter):
            idx = splitter.indexOf(self._glsl_editor)
            sizes = splitter.sizes()
            if visible:
                # Donner 220px à l'éditeur en prenant sur le viewport (dernier widget)
                if len(sizes) > idx and sizes[idx] < 10:
                    sizes[idx] = 220
                    # Réduire le dernier widget (viewport) d'autant
                    last = len(sizes) - 1
                    if last != idx and sizes[last] > 220:
                        sizes[last] = max(200, sizes[last] - 220)
                    splitter.setSizes(sizes)
                splitter.handle(idx).setEnabled(True)
            else:
                sizes[idx] = 1
                splitter.setSizes(sizes)
                splitter.handle(idx).setEnabled(False)
        self._set_status("Éditeur GLSL " + ("affiché" if visible else "masqué"))

    def _pick_shader_for_editor(self):
        """Ouvre un dialogue pour choisir un fichier shader à éditer."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir shader dans l'éditeur",
            os.path.join(self.project_dir, "scenes"),
            "Shaders GLSL (*.frag *.glsl *.vert);;Tous (*.*)")
        if path:
            self._open_shader_in_editor(path)

    def _on_shader_saved(self, path: str):
        """Appelé quand le shader est sauvegardé depuis l'éditeur GLSL."""
        self._set_status(f"✓ Shader sauvegardé : {os.path.basename(path)}")
        # Hot-reload du viewport si disponible
        if self._viewport:
            self._viewport.reload()
        # Rafraîchir le browser
        self._shader_browser.set_project_dir(self.project_dir)

    def _check_missing_assets(self):
        """Phase 5.3 — Vérifie les assets manquants et propose le relink."""
        project_data = self._current_project_data()
        missing = validate_project_assets(self.project_dir, project_data)
        if not missing:
            QMessageBox.information(self, "Assets",
                "✓ Tous les assets sont présents.")
            return
        dlg = MissingAssetsDialog(missing, self.project_dir, self)
        dlg.exec()
        relinks = dlg.get_relinks()
        if relinks:
            self._apply_relinks(relinks)

    def _apply_relinks(self, relinks: dict):
        """Applique les remplacements d'assets dans la timeline et la config."""
        changed = False
        for b in self.scenes:
            if b.base in relinks:
                b.base = os.path.splitext(
                    os.path.basename(relinks[b.base]))[0].replace('scene_', '')
                changed = True
        for b in self.overlays:
            if b.effect in relinks:
                b.effect = os.path.splitext(
                    os.path.basename(relinks[b.effect]))[0]
                changed = True
        for b in self.images:
            if getattr(b, 'file', '') in relinks:
                b.file = relinks[b.file]
                changed = True
        music = self.cfg.get('MUSIC_FILE', '')
        if music in relinks:
            self.cfg['MUSIC_FILE'] = relinks[music]
            changed = True
        if changed:
            self.autosave(force=True)
            self._refresh_assets()
            self._set_status(f"✓ {len(relinks)} asset(s) relinkés.")

    def _validate_assets_on_load(self):
        """Phase 5.3 — Vérifie les assets manquants après chargement de projet."""
        project_data = self._current_project_data()
        missing = validate_project_assets(self.project_dir, project_data)
        if missing:
            dlg = MissingAssetsDialog(missing, self.project_dir, self)
            dlg.exec()
            relinks = dlg.get_relinks()
            if relinks:
                self._apply_relinks(relinks)

    def _open_preset_manager(self):
        """Phase 5.4 — Ouvre le gestionnaire de presets de scènes."""
        dlg = ScenePresetDialog(self, self)
        dlg.exec()

    # ── Phase 6 — Interface ────────────────────────────────────────────────────

    def _load_keymap(self):
        """Charge le keymap depuis keymap.json si présent."""
        path = os.path.join(self.project_dir, KEYMAP_FILE)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    loaded = json.load(f)
                self._keymap.update(loaded)
            except Exception:
                pass

    def _open_theme_dialog(self):
        """6.2 — Ouvre le dialogue de thèmes."""
        self._theme_mgr._project_dir = self.project_dir
        dlg = ThemeDialog(self._theme_mgr, self)
        dlg.theme_applied.connect(self._on_theme_applied)
        dlg.exec()

    def _on_theme_applied(self, name: str):
        """Reapplique les stylesheets après changement de thème."""
        self._apply_stylesheet()
        # Rafraîchir les fenêtres flottantes
        if self._viewport_window:
            self._viewport_window.setStyleSheet(
                f"QWidget{{background:{C_BG2.name()};}}"
                f"QToolButton{{background:transparent;color:{C_CYAN.name()};"
                f"border:1px solid {C_CYAN.name()}40;border-radius:3px;font:9pt;}}"
                f"QToolButton:hover{{background:{C_CYAN.name()}20;}}")
        self._set_status(f"Thème «{name}» appliqué.")

    def _open_command_palette(self):
        """6.3 — Ouvre la palette de commandes Ctrl+P."""
        commands = self._build_command_list()
        dlg = CommandPalette(commands, self)
        # Centrer sur la fenêtre principale
        geo = self.geometry()
        dlg.move(geo.center().x() - dlg.width() // 2,
                 geo.y() + 80)
        dlg.exec()

    def _build_command_list(self) -> list[tuple]:
        """Construit la liste de toutes les commandes disponibles."""
        cmds = [
            # Fichier
            ("Fichier : Ouvrir project.json",      self._open_project),
            ("Fichier : Changer dossier projet",   self._change_dir),
            ("Fichier : Sauvegarder  Ctrl+S",      lambda: self.autosave(force=True)),
            # Édition
            ("Édition : Undo",                     lambda: self._tl.undo()),
            ("Édition : Redo",                     lambda: self._tl.redo()),
            ("Édition : Tout sélectionner",        self._tl._select_all),
            ("Édition : Copier",                   self._tl.copy_selection),
            ("Édition : Coller",                   self._tl.paste_clipboard),
            ("Édition : Dupliquer  Ctrl+D",        self._duplicate_selected),
            ("Édition : Supprimer la sélection",   self._delete_selected),
            ("Édition : Auto-arranger scènes",     self._auto_arrange),
            ("Édition : Effacer la timeline",      self._clear_timeline),
            ("Édition : Ajouter marqueur",         self._add_marker_at_playhead),
            ("Édition : Générer marqueurs BPM",    self._generate_beat_markers),
            ("Édition : Loop In",                  self._set_loop_in),
            ("Édition : Loop Out",                 self._set_loop_out),
            ("Édition : Effacer Loop",             lambda: self._tl.set_loop(None, None)),
            ("Édition : Exporter clip sélectionné",self._export_clip),
            ("Édition : Importer clip",            self._import_clip),
            # Transport
            ("Transport : Lecture / Pause",        self._toggle_play),
            ("Transport : Retour au début",        self._reset_playhead),
            # Fenêtres
            ("Fenêtres : Viewport OpenGL",         self._toggle_viewport_window),
            ("Fenêtres : Automation",              self._toggle_automation_window),
            ("Fenêtres : Tout afficher",           self._show_all_windows),
            ("Fenêtres : Tout masquer",            self._hide_all_windows),
            # Assets
            ("Assets : Rafraîchir",                self._refresh_assets),
            ("Assets : Browser shaders",           self._show_shader_browser),
            ("Assets : Vérifier assets manquants", self._check_missing_assets),
            # Shaders
            ("Shaders : Éditeur GLSL inline",      self._toggle_glsl_editor),
            ("Shaders : Ouvrir shader dans éditeur",self._pick_shader_for_editor),
            ("Shaders : Presets de scènes",        self._open_preset_manager),
            ("Shaders : Recharger shaders",        self._reload_viewport),
            # Automation
            ("Automation : Afficher éditeur",      self._show_automation),
            ("Automation : Quantifier sur beats",  self._quantize_all),
            ("Automation : Effacer automation",    self._clear_automation),
            ("Automation : Import Rocket XML",     self._import_rocket),
            ("Automation : Export Rocket XML",     self._export_rocket),
            # Interface
            ("Interface : Thèmes",                 self._open_theme_dialog),
            ("Interface : Raccourcis clavier",     self._open_keymap_editor),
            ("Interface : Macros",                 self._open_macros),
            ("Interface : Logs structurés",        self._open_log_panel),
            # Export
            ("Export : Exporter en MP4",           self._export_mp4),
            ("Export : Compiler EXE",              self._export_exe),
            ("Export : Queue d'export",            self._open_export_queue),
            # Live
            ("Live : OSC / MIDI Input",            self._open_osc_midi),
        ]
        # Ajouter les macros enregistrées
        for macro_name in self._macro_mgr.list_macros():
            cmds.append((f"Macro : {macro_name}",
                         lambda n=macro_name: self._run_macro(n)))
        return cmds

    def _open_keymap_editor(self):
        """6.3 — Ouvre l'éditeur de raccourcis."""
        dlg = KeymapEditor(self._keymap, self.project_dir, self)
        dlg.keymap_changed.connect(self._apply_keymap)
        dlg.exec()

    def _apply_keymap(self, keymap: dict):
        """Reapplique les raccourcis clavier depuis le keymap chargé."""
        self._keymap = keymap
        # Les QShortcut existants sont recréés au prochain démarrage.
        # Pour un rechargement à chaud minimal, on met à jour le statut.
        self._set_status("Raccourcis mis à jour — redémarrer pour appliquer tous les changements.")

    def _open_log_panel(self):
        """6.4 — Ouvre le panneau de logs structurés."""
        if self._log_panel is None:
            self._log_panel = LogPanel(self)
        self._log_panel.show()
        self._log_panel.raise_()
        self._log_panel.activateWindow()

    def _open_macros(self):
        """6.3 — Ouvre le gestionnaire de macros."""
        dlg = MacroDialog(self._macro_mgr, self)
        dlg.run_macro.connect(self._run_macro)
        dlg.exec()

    def _record_macro(self):
        """6.3 — Démarre/arrête l'enregistrement d'une macro."""
        if self._macro_mgr._is_recording:
            name, ok = QInputDialog.getText(self, "Sauvegarder macro", "Nom de la macro :")
            if ok and name.strip():
                self._macro_mgr.stop_record(name.strip())
                self._set_status(f"Macro «{name.strip()}» enregistrée.")
            else:
                self._macro_mgr.stop_record("")
        else:
            self._macro_mgr.start_record()
            self._set_status("⏺ Enregistrement macro démarré — refaire Édition→Enregistrer macro pour arrêter.")

    def _run_macro(self, action_name: str):
        """Exécute une action nommée (pour les macros)."""
        action_map = {label: cb for label, cb in self._build_command_list()}
        for label, cb in action_map.items():
            if action_name in label:
                try:
                    cb()
                except Exception as e:
                    self._set_status(f"Macro erreur : {e}")
                return

    # ── Phase 7 — Export & Live ────────────────────────────────────────────────

    def _open_export_queue(self):
        """7.4 — Ouvre la queue d'export multi-résolutions."""
        data = self._current_project_data()
        dlg  = ExportQueueDialog(self, self.project_dir, data)
        dlg.exec()

    def _open_osc_midi(self):
        """7.3 — Ouvre le dialogue OSC/MIDI."""
        if self._osc_midi_dlg is None:
            self._osc_midi_dlg = OscMidiDialog(self)
            self._osc_midi_dlg.param_received.connect(self._on_osc_midi_param)
        self._osc_midi_dlg.show()
        self._osc_midi_dlg.raise_()
        self._osc_midi_dlg.activateWindow()

    def _on_osc_midi_param(self, param_name: str, value: float):
        """Reçoit une valeur depuis OSC ou MIDI et l'applique au param system."""
        if self.selected and self.selected.kind == "scene":
            self._param_sys.record_value(self.selected.base, param_name,
                                          self._current_t, value)
        # Log
        if self._log_panel:
            self._log_panel.log(f"{param_name} = {value:.4f}", "INFO", "OSC/MIDI")

    # ── Export ────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────
    #  Phase 9 — Caméra 3D
    # ─────────────────────────────────────────────────────────────────────────

    def _open_camera_editor(self):
        """Ouvre l'éditeur de trajectoires caméra."""
        if not _PHASE9 or not self.camera_system:
            return
        names = self.camera_system.trajectory_names
        choices = ["(Nouvelle trajectoire)"] + names
        name, ok = QInputDialog.getItem(
            self, "Trajectoire caméra",
            "Sélectionner une trajectoire à éditer :", choices, 0, False)
        if not ok:
            return
        traj_name = "" if name == "(Nouvelle trajectoire)" else name
        dlg = CameraTrajectoryEditor(
            camera_system = self.camera_system,
            traj_name     = traj_name,
            on_save       = self._on_camera_saved,
            parent        = self,
        )
        dlg.exec()

    def _on_camera_saved(self, name, trajectory):
        """Callback après sauvegarde d'une trajectoire caméra."""
        self.autosave()
        self.log(f"Trajectoire caméra '{name}' sauvegardée "
                 f"({len(trajectory.keyframes)} keyframes)", "INFO", "CAMÉRA")

    def _open_blender_import(self):
        """Importe une trajectoire depuis un JSON Blender."""
        if not _PHASE9 or not self.camera_system:
            return
        dlg = BlenderImportDialog(
            camera_system = self.camera_system,
            on_import     = self._on_camera_saved,
            parent        = self,
        )
        dlg.exec()

    # ─────────────────────────────────────────────────────────────────────────
    #  Phase 9 — Particules GPU
    # ─────────────────────────────────────────────────────────────────────────

    def _open_particle_editor(self):
        """Éditeur de paramètres particules pour la scène sélectionnée."""
        sc_block = self._get_selected_scene_block()
        if not sc_block:
            QMessageBox.information(self, "Particules",
                "Sélectionnez d'abord une scène dans la timeline.")
            return

        pcfg = getattr(sc_block, "particles", {}) or {}

        dlg  = QDialog(self)
        dlg.setWindowTitle(f"✨ Particules — {sc_block.base}")
        dlg.resize(420, 360)
        form = QFormLayout(dlg)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)

        spin_count = QSpinBox()
        spin_count.setRange(100, 500_000)
        spin_count.setValue(pcfg.get("count", 50_000))
        spin_count.setSingleStep(5000)
        form.addRow("Nombre de particules :", spin_count)

        spin_lifetime = QDoubleSpinBox()
        spin_lifetime.setRange(0.1, 30.0)
        spin_lifetime.setSingleStep(0.1)
        spin_lifetime.setValue(pcfg.get("lifetime", 3.0))
        spin_lifetime.setSuffix(" s")
        form.addRow("Durée de vie :", spin_lifetime)

        spin_spread = QDoubleSpinBox()
        spin_spread.setRange(0.0, 20.0)
        spin_spread.setSingleStep(0.1)
        spin_spread.setValue(pcfg.get("spread", 1.0))
        form.addRow("Dispersion :", spin_spread)

        spin_size_start = QDoubleSpinBox()
        spin_size_start.setRange(0.5, 50.0)
        spin_size_start.setValue(pcfg.get("size_start", 4.0))
        form.addRow("Taille initiale (px) :", spin_size_start)

        spin_size_end = QDoubleSpinBox()
        spin_size_end.setRange(0.0, 50.0)
        spin_size_end.setValue(pcfg.get("size_end", 0.5))
        form.addRow("Taille finale (px) :", spin_size_end)

        chk_audio_grav  = QCheckBox("Gravité audio-réactive (iBass)")
        chk_audio_burst = QCheckBox("Explosion sur kick (iKick)")
        chk_audio_grav.setChecked(pcfg.get("audio_gravity", True))
        chk_audio_burst.setChecked(pcfg.get("audio_burst", True))
        form.addRow(chk_audio_grav)
        form.addRow(chk_audio_burst)

        edit_color_start = QLineEdit(str(pcfg.get("color_start", [1.0, 0.4, 0.1, 1.0])))
        edit_color_end   = QLineEdit(str(pcfg.get("color_end",   [0.2, 0.0, 0.5, 0.0])))
        form.addRow("Couleur début [R,G,B,A] :", edit_color_start)
        form.addRow("Couleur fin [R,G,B,A] :",   edit_color_end)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec():
            def _parse_list(s, default):
                try:
                    import ast
                    v = ast.literal_eval(s.strip())
                    return list(v) if isinstance(v, (list, tuple)) else default
                except Exception:
                    return default

            sc_block.particles = {
                "count":         spin_count.value(),
                "lifetime":      spin_lifetime.value(),
                "spread":        spin_spread.value(),
                "size_start":    spin_size_start.value(),
                "size_end":      spin_size_end.value(),
                "audio_gravity": chk_audio_grav.isChecked(),
                "audio_burst":   chk_audio_burst.isChecked(),
                "color_start":   _parse_list(edit_color_start.text(), [1.0, 0.4, 0.1, 1.0]),
                "color_end":     _parse_list(edit_color_end.text(),   [0.2, 0.0, 0.5, 0.0]),
            }
            self.autosave()
            self.log(f"Particules configurées pour '{sc_block.base}'", "INFO", "PARTICULES")

    # ─────────────────────────────────────────────────────────────────────────
    #  Phase 9 — Texte SDF
    # ─────────────────────────────────────────────────────────────────────────

    def _open_text_editor(self):
        """Éditeur de configuration texte SDF pour la scène sélectionnée."""
        sc_block = self._get_selected_scene_block()
        if not sc_block:
            QMessageBox.information(self, "Texte SDF",
                "Sélectionnez d'abord une scène dans la timeline.")
            return

        tcfg = getattr(sc_block, "text", {}) or {}

        dlg  = QDialog(self)
        dlg.setWindowTitle(f"🔤 Texte SDF — {sc_block.base}")
        dlg.resize(500, 440)
        form = QFormLayout(dlg)

        combo_mode = QComboBox()
        combo_mode.addItems(["sdf", "plain"])
        combo_mode.setCurrentText(tcfg.get("mode", "sdf"))
        form.addRow("Mode rendu :", combo_mode)

        edit_font = QLineEdit(tcfg.get("font", "fonts/Orbitron-Bold.ttf"))
        btn_font  = QPushButton("…")
        btn_font.setFixedWidth(30)
        font_row = QHBoxLayout()
        font_row.addWidget(edit_font)
        font_row.addWidget(btn_font)
        form.addRow("Police (chemin) :", font_row)

        def _browse_font():
            p, _ = QFileDialog.getOpenFileName(
                dlg, "Choisir une police", self.project_dir,
                "Polices (*.ttf *.otf *.woff *.woff2);;Tous (*)")
            if p:
                rel = os.path.relpath(p, self.project_dir)
                edit_font.setText(rel)
        btn_font.clicked.connect(_browse_font)

        spin_size = QSpinBox()
        spin_size.setRange(8, 256)
        spin_size.setValue(tcfg.get("size", 64))
        spin_size.setSuffix(" px")
        form.addRow("Taille atlas :", spin_size)

        # Lignes
        edit_lines = QPlainTextEdit()
        edit_lines.setMaximumHeight(110)
        import json as _json
        lines_default = _json.dumps(tcfg.get("lines", [
            {"text": "MEGADEMO", "y": 0.6, "size": 80, "color": "#00ffcc"}
        ]), indent=2, ensure_ascii=False)
        edit_lines.setPlainText(lines_default)
        edit_lines.setPlaceholderText('[{"text":"...", "y":0.5, "size":64, "color":"#ffffff"}]')
        form.addRow("Lignes statiques (JSON) :", edit_lines)

        # Scroll
        edit_scroll_text  = QLineEdit(tcfg.get("scroll", {}).get("text", ""))
        spin_scroll_speed = QDoubleSpinBox()
        spin_scroll_speed.setRange(0, 2000)
        spin_scroll_speed.setValue(tcfg.get("scroll", {}).get("speed", 200.0))
        spin_scroll_speed.setSuffix(" px/s")
        form.addRow("Scroll text :", edit_scroll_text)
        form.addRow("Vitesse scroll :", spin_scroll_speed)

        # Info karaoke
        lbl_kar = QLabel(
            "<small>💡 Karaoke : éditer <code>project.json → scène → text.karaoke</code><br>"
            "Format : <code>{\"words\":[...], \"timecodes\":[...], \"color_on\":\"#fff\"}</code></small>")
        lbl_kar.setWordWrap(True)
        form.addRow(lbl_kar)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec():
            try:
                lines = _json.loads(edit_lines.toPlainText())
            except Exception:
                lines = []
            text_cfg = {
                "mode": combo_mode.currentText(),
                "font": edit_font.text().strip(),
                "size": spin_size.value(),
                "lines": lines,
            }
            scroll_text = edit_scroll_text.text().strip()
            if scroll_text:
                text_cfg["scroll"] = {
                    "text":  scroll_text,
                    "y":     0.05,
                    "speed": spin_scroll_speed.value(),
                    "size":  40,
                }
            # Conserver le karaoke existant s'il y en a un
            if "karaoke" in tcfg:
                text_cfg["karaoke"] = tcfg["karaoke"]

            sc_block.text = text_cfg
            self.autosave()
            self.log(f"Texte SDF configuré pour '{sc_block.base}'", "INFO", "TEXTE")

    # ─────────────────────────────────────────────────────────────────────────
    #  Phase 9 — Helper : bloc de scène sélectionné
    # ─────────────────────────────────────────────────────────────────────────

    def _get_selected_scene_block(self):
        """
        Retourne le Block de la scène actuellement sélectionnée
        dans la timeline, ou None.
        """
        sel = self._tl._selected_blocks()
        if not sel:
            # Essayer self.selected (sélection par clic simple)
            if self.selected and self.selected.kind == "scene":
                return self.selected
            return None
        b = sel[0]
        return b if b.kind == "scene" else None

    def _current_project_data(self):
        """Retourne le dict projet courant (sans sauvegarder)."""
        cameras = None
        if _PHASE9 and self.camera_system:
            cameras = self.camera_system.to_dict()
        return build_project_dict(
            self.scenes, self.overlays, self.scrolls, self.images, self.cfg,
            markers=getattr(self._tl, "markers", []), cameras=cameras)

    def _export_mp4(self):
        import json as _json
        data = _json.loads(_json.dumps(
            build_project_dict(
                self.scenes, self.overlays, self.scrolls, self.images, self.cfg)))
        dlg = Mp4ExportDialog(self, self.project_dir, data)
        dlg.exec()

    def _export_exe(self):
        # Sauvegarde d'abord pour que project.json soit à jour
        self.autosave(force=True)
        QTimer.singleShot(400, lambda: ExeExportDialog(self, self.project_dir).exec())

    def _set_status(self, msg):
        self._status_lbl.setText(msg)


# ════════════════════════════════════════════════════════════
#  ENTRÉE
# ════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Megademo Composer — PySide6")
    parser.add_argument("--rocket-host", default=None)
    parser.add_argument("--rocket-port", type=int, default=1338)
    parser.add_argument("--project-dir", default=None)
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow(rocket_host=args.rocket_host, rocket_port=args.rocket_port)
    if args.project_dir:
        win.project_dir = os.path.abspath(args.project_dir)
        win._dir_lbl.setText(win.project_dir)
        win._setup_watcher()
        win._refresh_assets()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
