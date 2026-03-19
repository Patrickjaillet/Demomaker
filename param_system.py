"""
param_system.py  —  Phase 4 : Système de Paramètres & Automation
=================================================================

4.1  Parser @param depuis les commentaires GLSL
     Registre de paramètres par scène
     Injection des valeurs comme uniforms à chaque frame

4.2  Courbes d'automation (keyframes + interpolations)
     6 modes : Linear, Smooth, Step, Bounce, Elastic, EaseInOut

4.3  LFOs (sine/square/saw/triangle/random) sync BPM
     Modulateurs audio (iBass, iMid…)
     Math nodes (multiply, add, clamp, remap)

Utilisation
-----------
    ps = ParamSystem()
    params = ps.parse_shader("scenes/scene_plasma.frag")
    # → [ParamDef(name="iSpeed", type="float", min=0.1, max=5.0, default=1.0), …]

    # Chaque frame :
    ps.set_scene("plasma", params)
    values = ps.evaluate(t, audio_uniforms, bpm)
    # → {"iSpeed": 1.73, "iColorA": (1.0, 0.42, 0.21), …}
    # Puis injecter dans le shader via _bind_audio_uniforms style
"""

from __future__ import annotations
import re
import math
import json
import random
import numpy as np
from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
#  4.1 — DÉFINITION D'UN PARAMÈTRE
# ─────────────────────────────────────────────────────────────────────────────

PARAM_TYPES = {"float", "int", "bool", "vec2", "vec3", "vec4", "color"}

@dataclass
class ParamDef:
    """
    Un paramètre déclaré dans un shader via // @param.

    Syntaxes supportées :
        // @param float  iSpeed    0.1   5.0   1.0        → float min max default
        // @param int    iSteps    1     32    8           → int
        // @param bool   iMirror   false                  → bool
        // @param color  iColorA   #ff6b35                → couleur HTML
        // @param vec2   iOffset   0.0 0.0  1.0 1.0  0.5 0.5   → vec2 min max default
        // @param vec3   iHue      0 0 0    1 1 1    0.5 0.5 0.5
    """
    name:    str
    type:    str          # "float"|"int"|"bool"|"vec2"|"vec3"|"vec4"|"color"
    default: Any          # float | int | bool | tuple
    min_val: Any  = None
    max_val: Any  = None
    label:   str  = ""    # nom lisible (auto-généré depuis name)

    def __post_init__(self):
        if not self.label:
            # "iSpeed" → "Speed", "iColorA" → "Color A"
            n = self.name
            if n.startswith("i"): n = n[1:]
            # CamelCase → "Camel Case"
            self.label = re.sub(r'([A-Z])', r' \1', n).strip()

    def clamp(self, val: Any) -> Any:
        """Ramène val dans [min_val, max_val] selon le type."""
        if self.min_val is None or self.max_val is None:
            return val
        if self.type in ("float", "int"):
            return max(self.min_val, min(self.max_val, val))
        if self.type in ("vec2", "vec3", "vec4", "color"):
            mn = self.min_val; mx = self.max_val
            return tuple(max(mn[i], min(mx[i], v)) for i, v in enumerate(val))
        return val

    def lerp(self, a: Any, b: Any, t: float) -> Any:
        """Interpolation linéaire entre deux valeurs de ce type."""
        if self.type in ("float",):
            return a + (b - a) * t
        if self.type == "int":
            return int(round(a + (b - a) * t))
        if self.type == "bool":
            return b if t >= 0.5 else a
        if self.type in ("vec2", "vec3", "vec4", "color"):
            return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))
        return b if t >= 1.0 else a


# ─────────────────────────────────────────────────────────────────────────────
#  PARSER GLSL → @param
# ─────────────────────────────────────────────────────────────────────────────

def _parse_color(s: str) -> tuple:
    s = s.strip().lstrip("#")
    if len(s) == 6:
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
        return (r, g, b)
    return (0.5, 0.5, 0.5)

def _parse_floats(tokens: list[str], n: int) -> tuple:
    vals = []
    for tk in tokens[:n]:
        try: vals.append(float(tk))
        except ValueError: break
    while len(vals) < n:
        vals.append(0.0)
    return tuple(vals)

def parse_shader_params(glsl_code: str) -> list[ParamDef]:
    """
    Extrait tous les // @param d'un code GLSL et retourne une liste de ParamDef.
    """
    params: list[ParamDef] = []
    pattern = re.compile(
        r'//\s*@param\s+(\w+)\s+(\w+)\s*(.*)', re.IGNORECASE)

    for line in glsl_code.splitlines():
        m = pattern.match(line.strip())
        if not m:
            continue
        ptype  = m.group(1).lower()
        pname  = m.group(2)
        rest   = m.group(3).strip().split()

        if ptype not in PARAM_TYPES:
            continue

        try:
            if ptype == "float":
                mn  = float(rest[0]) if len(rest) > 0 else 0.0
                mx  = float(rest[1]) if len(rest) > 1 else 1.0
                dflt= float(rest[2]) if len(rest) > 2 else (mn + mx) / 2
                params.append(ParamDef(pname, "float", dflt, mn, mx))

            elif ptype == "int":
                mn  = int(rest[0]) if len(rest) > 0 else 0
                mx  = int(rest[1]) if len(rest) > 1 else 10
                dflt= int(rest[2]) if len(rest) > 2 else (mn + mx) // 2
                params.append(ParamDef(pname, "int", dflt, mn, mx))

            elif ptype == "bool":
                dflt = rest[0].lower() not in ("false", "0", "no") if rest else False
                params.append(ParamDef(pname, "bool", dflt))

            elif ptype == "color":
                dflt = _parse_color(rest[0]) if rest else (0.5, 0.5, 0.5)
                params.append(ParamDef(pname, "color", dflt,
                                       (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)))

            elif ptype == "vec2":
                # min_x min_y  max_x max_y  def_x def_y
                mn   = _parse_floats(rest[0:2], 2)
                mx   = _parse_floats(rest[2:4], 2) if len(rest) >= 4 else (1.0,) * 2
                dflt = _parse_floats(rest[4:6], 2) if len(rest) >= 6 else \
                       tuple((mn[i]+mx[i])/2 for i in range(2))
                params.append(ParamDef(pname, "vec2", dflt, mn, mx))

            elif ptype == "vec3":
                mn   = _parse_floats(rest[0:3], 3)
                mx   = _parse_floats(rest[3:6], 3) if len(rest) >= 6 else (1.0,)*3
                dflt = _parse_floats(rest[6:9], 3) if len(rest) >= 9 else \
                       tuple((mn[i]+mx[i])/2 for i in range(3))
                params.append(ParamDef(pname, "vec3", dflt, mn, mx))

            elif ptype == "vec4":
                mn   = _parse_floats(rest[0:4], 4)
                mx   = _parse_floats(rest[4:8], 4) if len(rest) >= 8 else (1.0,)*4
                dflt = _parse_floats(rest[8:12],4) if len(rest) >= 12 else \
                       tuple((mn[i]+mx[i])/2 for i in range(4))
                params.append(ParamDef(pname, "vec4", dflt, mn, mx))

        except (ValueError, IndexError):
            continue

    return params


# ─────────────────────────────────────────────────────────────────────────────
#  4.2 — KEYFRAME & INTERPOLATIONS
# ─────────────────────────────────────────────────────────────────────────────

INTERP_MODES = ("linear", "smooth", "step", "bounce", "elastic", "ease_in_out")

@dataclass
class Keyframe:
    t:      float    # temps absolu en secondes
    value:  Any      # valeur au keyframe
    interp: str = "smooth"   # mode d'interpolation vers le keyframe SUIVANT
    # Handles bézier relatifs (uniquement pour interp="bezier", réservé futur)
    h_in:   float = 0.33
    h_out:  float = 0.33


def _ease_in_out(t: float) -> float:
    return t * t * (3 - 2 * t)

def _bounce(t: float) -> float:
    if t < 1/2.75:
        return 7.5625 * t * t
    elif t < 2/2.75:
        t -= 1.5/2.75
        return 7.5625*t*t + 0.75
    elif t < 2.5/2.75:
        t -= 2.25/2.75
        return 7.5625*t*t + 0.9375
    else:
        t -= 2.625/2.75
        return 7.5625*t*t + 0.984375

def _elastic(t: float) -> float:
    if t <= 0: return 0.0
    if t >= 1: return 1.0
    p = 0.3
    return -(math.pow(2, 10*(t-1)) * math.sin((t-1-p/4)*(2*math.pi)/p))

def interpolate(a_kf: Keyframe, b_kf: Keyframe, t: float, param: ParamDef) -> Any:
    """Interpole entre deux keyframes à la position t."""
    if b_kf.t <= a_kf.t:
        return a_kf.value
    alpha = (t - a_kf.t) / (b_kf.t - a_kf.t)
    alpha = max(0.0, min(1.0, alpha))

    mode = a_kf.interp
    if mode == "linear":
        s = alpha
    elif mode == "smooth":
        s = _ease_in_out(alpha)
    elif mode == "step":
        s = 1.0 if alpha >= 1.0 else 0.0
    elif mode == "bounce":
        s = _bounce(alpha)
    elif mode == "elastic":
        s = _elastic(alpha)
    elif mode == "ease_in_out":
        s = _ease_in_out(alpha)
    else:
        s = alpha

    return param.lerp(a_kf.value, b_kf.value, s)


class AutomationCurve:
    """
    Courbe d'automation pour un paramètre : liste de keyframes triés par t.
    Supporte l'évaluation, l'enregistrement live, la quantification sur beats.
    """

    def __init__(self, param: ParamDef):
        self.param:     ParamDef       = param
        self.keyframes: list[Keyframe] = []

    def add_keyframe(self, t: float, value: Any, interp: str = "smooth"):
        # Remplacer si un kf existe déjà très proche
        for i, kf in enumerate(self.keyframes):
            if abs(kf.t - t) < 0.02:
                self.keyframes[i] = Keyframe(t, value, interp)
                return
        self.keyframes.append(Keyframe(t, value, interp))
        self.keyframes.sort(key=lambda k: k.t)

    def remove_near(self, t: float, tol: float = 0.1):
        self.keyframes = [k for k in self.keyframes if abs(k.t - t) > tol]

    def evaluate(self, t: float) -> Any:
        kfs = self.keyframes
        if not kfs:
            return self.param.default
        if t <= kfs[0].t:
            return kfs[0].value
        if t >= kfs[-1].t:
            return kfs[-1].value
        # Trouver les deux kf encadrants
        for i in range(len(kfs) - 1):
            if kfs[i].t <= t <= kfs[i+1].t:
                return interpolate(kfs[i], kfs[i+1], t, self.param)
        return kfs[-1].value

    def quantize(self, bpm: float):
        """Force tous les keyframes sur la grille des beats."""
        beat = 60.0 / max(1.0, bpm)
        for kf in self.keyframes:
            kf.t = round(kf.t / beat) * beat

    def copy_to(self, other: 'AutomationCurve'):
        """Copie les keyframes vers une autre courbe du même type."""
        import copy
        other.keyframes = copy.deepcopy(self.keyframes)

    def to_dict(self) -> dict:
        return {
            "param": self.param.name,
            "keyframes": [
                {"t": k.t, "value": list(k.value) if isinstance(k.value, tuple) else k.value,
                 "interp": k.interp}
                for k in self.keyframes
            ]
        }

    @classmethod
    def from_dict(cls, d: dict, param: ParamDef) -> 'AutomationCurve':
        curve = cls(param)
        for kd in d.get("keyframes", []):
            val = kd["value"]
            if isinstance(val, list):
                val = tuple(val)
            curve.keyframes.append(Keyframe(
                t=float(kd["t"]),
                value=val,
                interp=kd.get("interp", "smooth")
            ))
        return curve


# ─────────────────────────────────────────────────────────────────────────────
#  4.3 — LFO
# ─────────────────────────────────────────────────────────────────────────────

LFO_SHAPES = ("sine", "square", "saw", "triangle", "random")

class LFO:
    """
    Oscillateur Basse Fréquence assignable à un paramètre.
    Peut être synchronisé sur le BPM.
    """

    def __init__(
        self,
        shape:       str   = "sine",
        freq_beats:  float = 1.0,   # 1 = 1 cycle par beat, 4 = 1 par mesure
        amplitude:   float = 1.0,
        phase_offset:float = 0.0,
        center:      float = 0.5,
    ):
        self.shape        = shape
        self.freq_beats   = freq_beats   # cycles par beat
        self.amplitude    = amplitude
        self.phase_offset = phase_offset
        self.center       = center
        self._rng         = random.Random(42)
        self._prev_phase  = 0.0
        self._rand_val    = 0.0

    def evaluate(self, t: float, bpm: float) -> float:
        """Retourne une valeur dans [center-amplitude/2, center+amplitude/2]."""
        beat_dur = 60.0 / max(1.0, bpm)
        phase    = (t / beat_dur * self.freq_beats + self.phase_offset) % 1.0

        if self.shape == "sine":
            raw = math.sin(phase * 2 * math.pi) * 0.5 + 0.5
        elif self.shape == "square":
            raw = 1.0 if phase < 0.5 else 0.0
        elif self.shape == "saw":
            raw = phase
        elif self.shape == "triangle":
            raw = 1.0 - abs(phase * 2 - 1)
        elif self.shape == "random":
            # Nouveau random à chaque cycle
            if phase < self._prev_phase:
                self._rand_val = self._rng.random()
            raw = self._rand_val
        else:
            raw = 0.5

        self._prev_phase = phase
        return self.center + (raw - 0.5) * self.amplitude

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

    @classmethod
    def from_dict(cls, d: dict) -> 'LFO':
        lfo = cls()
        for k, v in d.items():
            if hasattr(lfo, k):
                setattr(lfo, k, v)
        return lfo


# ─────────────────────────────────────────────────────────────────────────────
#  4.3 — MODULATEUR AUDIO
# ─────────────────────────────────────────────────────────────────────────────

class AudioModulator:
    """
    Mappe un uniform audio (iBass, iMid…) sur un paramètre
    avec remapping [in_min, in_max] → [out_min, out_max].
    """
    SOURCES = ("iKick","iBass","iMid","iHigh","iBeat","iBPM",
               "iBar","iEnergy","iDrop","iStereoWidth",
               "iBassPeak","iMidPeak","iHighPeak")

    def __init__(
        self,
        source:  str   = "iBass",
        in_min:  float = 0.0,
        in_max:  float = 1.0,
        out_min: float = 0.0,
        out_max: float = 1.0,
        smooth:  float = 0.0,    # lissage supplémentaire [0..1]
    ):
        self.source  = source
        self.in_min  = in_min
        self.in_max  = in_max
        self.out_min = out_min
        self.out_max = out_max
        self.smooth  = smooth
        self._val    = 0.0

    def evaluate(self, audio: dict) -> float:
        raw = float(audio.get(self.source, 0.0))
        # Remap
        span_in  = self.in_max  - self.in_min  or 1.0
        span_out = self.out_max - self.out_min
        t   = (raw - self.in_min) / span_in
        t   = max(0.0, min(1.0, t))
        val = self.out_min + t * span_out
        # Lissage
        self._val = self._val * self.smooth + val * (1.0 - self.smooth)
        return self._val

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

    @classmethod
    def from_dict(cls, d: dict) -> 'AudioModulator':
        m = cls()
        for k, v in d.items():
            if hasattr(m, k): setattr(m, k, v)
        return m


# ─────────────────────────────────────────────────────────────────────────────
#  4.3 — MATH NODE
# ─────────────────────────────────────────────────────────────────────────────

class MathNode:
    """
    Opération simple sur la valeur d'un modulateur avant injection.
    Opérations : multiply, add, clamp, remap, abs, invert, pow
    """
    OPS = ("multiply","add","clamp","remap","abs","invert","pow")

    def __init__(self, op: str = "multiply", a: float = 1.0, b: float = 0.0):
        self.op = op
        self.a  = a   # paramètre principal (facteur, offset, min_in…)
        self.b  = b   # paramètre secondaire (max_in, max_out…)

    def apply(self, x: float) -> float:
        if self.op == "multiply":  return x * self.a
        if self.op == "add":       return x + self.a
        if self.op == "clamp":     return max(self.a, min(self.b, x))
        if self.op == "remap":     return self.a + (x * (self.b - self.a))
        if self.op == "abs":       return abs(x)
        if self.op == "invert":    return 1.0 - x
        if self.op == "pow":       return math.pow(max(0.0, x), self.a)
        return x

    def to_dict(self) -> dict:
        return {"op": self.op, "a": self.a, "b": self.b}

    @classmethod
    def from_dict(cls, d: dict) -> 'MathNode':
        return cls(d.get("op","multiply"), d.get("a",1.0), d.get("b",0.0))


# ─────────────────────────────────────────────────────────────────────────────
#  SLOT DE MODULATION : combine courbe + LFO + audio + math
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ModSlot:
    """
    Un slot de modulation pour un paramètre donné.
    Combine (dans l'ordre) : valeur de base de la courbe d'automation,
    puis additions de LFO et modulateurs audio, puis Math node.
    """
    param:    ParamDef
    curve:    AutomationCurve | None       = None
    lfo:      LFO             | None       = None
    audio:    AudioModulator  | None       = None
    math:     MathNode        | None       = None
    # Poids de chaque source [0..1]
    lfo_weight:   float = 1.0
    audio_weight: float = 1.0

    def evaluate(self, t: float, audio_uniforms: dict, bpm: float) -> Any:
        # Valeur de base : courbe ou défaut
        base = self.curve.evaluate(t) if self.curve else self.param.default

        # Additionner LFO (uniquement sur scalaires et vecs)
        if self.lfo and self.lfo_weight > 0:
            lv = self.lfo.evaluate(t, bpm) * self.lfo_weight
            if isinstance(base, tuple):
                base = tuple(v + lv for v in base)
            else:
                base = float(base) + lv

        # Additionner modulateur audio
        if self.audio and self.audio_weight > 0:
            av = self.audio.evaluate(audio_uniforms) * self.audio_weight
            if isinstance(base, tuple):
                base = tuple(v + av for v in base)
            else:
                base = float(base) + av

        # Math node (scalaire seulement pour l'instant)
        if self.math and not isinstance(base, tuple):
            base = self.math.apply(float(base))

        return self.param.clamp(base)


# ─────────────────────────────────────────────────────────────────────────────
#  PARAM SYSTEM — point d'entrée
# ─────────────────────────────────────────────────────────────────────────────

class ParamSystem:
    """
    Gère tous les paramètres de toutes les scènes.
    Évalue les valeurs à chaque frame et injecte dans les shaders.

    Persistance dans project.json → champ "automation"
    """

    def __init__(self):
        # {scene_name: {param_name: ModSlot}}
        self._slots:  dict[str, dict[str, ModSlot]] = {}
        # {scene_name: [ParamDef]}
        self._params: dict[str, list[ParamDef]]     = {}
        # Enregistrement live : dict{param_name: bool}
        self._recording: dict[str, bool]            = {}
        self._record_mode = False

    # ── 4.1 : Parser ─────────────────────────────────────────────────────────

    def parse_shader(self, path: str) -> list[ParamDef]:
        """Lit un fichier GLSL et retourne la liste de ses @params."""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                code = f.read()
            return parse_shader_params(code)
        except Exception:
            return []

    def register_scene(self, scene_name: str, params: list[ParamDef]) -> None:
        """Enregistre les paramètres d'une scène (créé les slots manquants)."""
        self._params[scene_name] = params
        if scene_name not in self._slots:
            self._slots[scene_name] = {}
        existing = self._slots[scene_name]
        for p in params:
            if p.name not in existing:
                existing[p.name] = ModSlot(
                    param = p,
                    curve = AutomationCurve(p),
                )

    def get_params(self, scene_name: str) -> list[ParamDef]:
        return self._params.get(scene_name, [])

    def get_slot(self, scene_name: str, param_name: str) -> ModSlot | None:
        return self._slots.get(scene_name, {}).get(param_name)

    def get_slots(self, scene_name: str) -> dict[str, ModSlot]:
        return self._slots.get(scene_name, {})

    # ── 4.2 : Keyframes ──────────────────────────────────────────────────────

    def add_keyframe(self, scene: str, param: str, t: float,
                     value: Any, interp: str = "smooth") -> None:
        slot = self.get_slot(scene, param)
        if slot and slot.curve:
            slot.curve.add_keyframe(t, value, interp)

    def remove_keyframe(self, scene: str, param: str, t: float) -> None:
        slot = self.get_slot(scene, param)
        if slot and slot.curve:
            slot.curve.remove_near(t)

    def quantize_all(self, scene: str, bpm: float) -> None:
        for slot in self._slots.get(scene, {}).values():
            if slot.curve:
                slot.curve.quantize(bpm)

    # ── 4.3 : LFO / Audio mod ────────────────────────────────────────────────

    def set_lfo(self, scene: str, param: str, lfo: LFO | None,
                weight: float = 1.0) -> None:
        slot = self.get_slot(scene, param)
        if slot:
            slot.lfo        = lfo
            slot.lfo_weight = weight

    def set_audio_mod(self, scene: str, param: str,
                      mod: AudioModulator | None, weight: float = 1.0) -> None:
        slot = self.get_slot(scene, param)
        if slot:
            slot.audio        = mod
            slot.audio_weight = weight

    def set_math(self, scene: str, param: str, node: MathNode | None) -> None:
        slot = self.get_slot(scene, param)
        if slot:
            slot.math = node

    # ── Enregistrement live ───────────────────────────────────────────────────

    def start_record(self, scene: str, params: list[str] = None) -> None:
        self._record_mode = True
        self._recording   = {p: True for p in (params or [])}

    def stop_record(self) -> None:
        self._record_mode = False
        self._recording   = {}

    def record_value(self, scene: str, param: str, t: float, value: Any) -> None:
        if self._record_mode and self._recording.get(param, False):
            self.add_keyframe(scene, param, t, value, "smooth")

    # ── Évaluation principale ─────────────────────────────────────────────────

    def evaluate(self, scene_name: str, t: float,
                 audio_uniforms: dict, bpm: float) -> dict[str, Any]:
        """
        Retourne un dict {param_name: value} pour tous les paramètres
        de la scène, évalués au temps t.
        """
        results = {}
        for pname, slot in self._slots.get(scene_name, {}).items():
            results[pname] = slot.evaluate(t, audio_uniforms, bpm)
        return results

    def inject(self, prog, scene_name: str, t: float,
               audio_uniforms: dict, bpm: float) -> None:
        """
        Évalue et injecte tous les paramètres dans un programme GLSL.
        Compatible avec moderngl (vérifie name in prog).
        """
        if prog is None:
            return
        for pname, val in self.evaluate(scene_name, t, audio_uniforms, bpm).items():
            if pname not in prog:
                continue
            try:
                if isinstance(val, tuple):
                    prog[pname].value = val
                elif isinstance(val, bool):
                    prog[pname].value = int(val)
                else:
                    prog[pname].value = float(val)
            except Exception:
                pass

    # ── Persistance JSON ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        out = {}
        for scene_name, slots in self._slots.items():
            scene_data = {}
            for pname, slot in slots.items():
                sd: dict = {}
                if slot.curve and slot.curve.keyframes:
                    sd["curve"] = slot.curve.to_dict()
                if slot.lfo:
                    sd["lfo"] = slot.lfo.to_dict()
                    sd["lfo_weight"] = slot.lfo_weight
                if slot.audio:
                    sd["audio"] = slot.audio.to_dict()
                    sd["audio_weight"] = slot.audio_weight
                if slot.math:
                    sd["math"] = slot.math.to_dict()
                if sd:
                    scene_data[pname] = sd
            if scene_data:
                out[scene_name] = scene_data
        return out

    def from_dict(self, d: dict) -> None:
        """Charge l'automation depuis un dict (project.json → "automation")."""
        for scene_name, scene_data in d.items():
            if scene_name not in self._slots:
                self._slots[scene_name] = {}
            for pname, sd in scene_data.items():
                # Reconstruire le ParamDef depuis les params enregistrés
                params = self._params.get(scene_name, [])
                param = next((p for p in params if p.name == pname), None)
                if param is None:
                    # Param inconnu : créer un float par défaut
                    param = ParamDef(pname, "float", 0.0, 0.0, 1.0)
                slot = ModSlot(param=param)
                if "curve" in sd:
                    slot.curve = AutomationCurve.from_dict(sd["curve"], param)
                else:
                    slot.curve = AutomationCurve(param)
                if "lfo" in sd:
                    slot.lfo        = LFO.from_dict(sd["lfo"])
                    slot.lfo_weight = sd.get("lfo_weight", 1.0)
                if "audio" in sd:
                    slot.audio        = AudioModulator.from_dict(sd["audio"])
                    slot.audio_weight = sd.get("audio_weight", 1.0)
                if "math" in sd:
                    slot.math = MathNode.from_dict(sd["math"])
                self._slots[scene_name][pname] = slot
