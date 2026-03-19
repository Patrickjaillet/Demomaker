"""
audio_analysis.py  —  Phase 1 : Moteur Audio Avancé
====================================================

Uniforms scalaires exposés aux shaders
---------------------------------------
  iKick          énergie kick/sub (20–150 Hz), lissée          [0..3]
  iBass          basses 20–250 Hz, lissée                      [0..3]
  iMid           médiums 250–4000 Hz, lissée                   [0..3]
  iHigh          aigus 4000–20000 Hz, lissée                   [0..3]
  iBassPeak      pic instantané basses                         [0..3]
  iMidPeak       pic instantané médiums                        [0..3]
  iHighPeak      pic instantané aigus                          [0..3]
  iBassRMS       RMS basses (fenêtre 100ms)                    [0..1]
  iMidRMS        RMS médiums                                   [0..1]
  iHighRMS       RMS aigus                                     [0..1]
  iBeat          impulsion percussive (onset), décroît vite    [0..3]
  iBPM           BPM estimé par autocorrélation                [60..200]
  iBar           position dans la mesure                       [0..1]
  iBeat4         numéro du beat courant                        [0,1,2,3]
  iSixteenth     position en double-croche                     [0..15]
  iEnergy        RMS long terme normalisé (8 s)                [0..1]
  iDrop          impulsion à un drop détecté                   [0..1]
  iStereoWidth   largeur stéréo L/R                            [0..1]
  iCue           valeur du cue point actif (0 si aucun)        [0..1]
  iSection       index de section musicale détectée            [0..7]

Textures GPU
------------
  iSpectrum        sampler2D  256×1 f32   spectre log [0,1]
  iWaveform        sampler2D  512×1 f32   forme d'onde [0,1]
  iSpectrumHistory sampler2D  256×64 f32  waterfall (axe Y = temps)
  iBarkSpectrum    sampler2D   24×1 f32   bandes Bark perceptives
"""

from __future__ import annotations
import numpy as np
import moderngl
from collections import deque

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

SPEC_BINS      = 256    # largeur texture spectre log
WAVE_BINS      = 512    # largeur texture waveform
HISTORY_ROWS   = 64     # hauteur texture historique waterfall
BARK_BANDS     = 24     # bandes critiques Bark
RMS_WIN_MS     = 100    # fenêtre RMS peak en ms
ENERGY_WIN_S   = 8.0    # fenêtre RMS long terme en secondes
DROP_DECAY     = 0.92   # décroissance iDrop
BEAT_DECAY     = 0.75   # décroissance iBeat
FFT_SIZES      = (512, 1024, 2048, 4096)

# Fréquences de coupure des bandes Bark (ISO 532 B simplifié)
BARK_FREQS = [
    20, 100, 200, 300, 400, 510, 630, 770, 920, 1080,
    1270, 1480, 1720, 2000, 2320, 2700, 3150, 3700, 4400,
    5300, 6400, 7700, 9500, 12000, 15500
]  # 25 bords → 24 bandes

# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _freq_to_bin(freq_hz: float, sr: int, fft_size: int) -> int:
    return int(freq_hz / (sr / 2.0) * (fft_size // 2 + 1))

def _hann(n: int) -> np.ndarray:
    return (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / (n - 1))).astype(np.float32)

def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0

def _band_energy(mag: np.ndarray, lo: int, hi: int) -> float:
    seg = mag[lo:max(lo+1, hi)]
    return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0

def _band_peak(mag: np.ndarray, lo: int, hi: int) -> float:
    seg = mag[lo:max(lo+1, hi)]
    return float(np.max(seg)) if len(seg) else 0.0

# ─────────────────────────────────────────────────────────────────────────────
#  1.2 — BEAT TRACKER PAR AUTOCORRÉLATION
# ─────────────────────────────────────────────────────────────────────────────

class BeatTracker:
    """
    Estime le BPM par autocorrélation de l'énergie sur bandes Bark.
    Plus robuste qu'un simple onset detector.
    Émet aussi iBar, iBeat4, iSixteenth.
    """

    AC_WIN      = 512   # frames d'énergie pour l'autocorrélation
    UPDATE_SECS = 2.0   # recalcule le BPM toutes les N secondes
    BPM_MIN     = 60.0
    BPM_MAX     = 200.0

    def __init__(self, sr: int, hop: int):
        self._sr          = sr
        self._hop         = hop          # samples entre frames d'énergie
        self._fps         = sr / hop     # frames par seconde d'énergie
        self.bpm          = 120.0
        self._energy_buf  = deque(maxlen=self.AC_WIN)
        self._last_update = -self.UPDATE_SECS
        self._beat_phase  = 0.0          # phase continue [0..1) dans le beat
        self._last_t      = 0.0

    def push(self, energy: float, t: float) -> None:
        self._energy_buf.append(energy)
        # Mise à jour BPM périodique
        if t - self._last_update >= self.UPDATE_SECS and len(self._energy_buf) >= 64:
            self._estimate_bpm()
            self._last_update = t

    def tick(self, t: float) -> tuple[float, int, float]:
        """Retourne (iBar [0..1], iBeat4 [0..3], iSixteenth [0..15])."""
        dt = t - self._last_t
        self._last_t = t
        beat_dur = 60.0 / max(self.bpm, 1.0)
        self._beat_phase = (self._beat_phase + dt / beat_dur) % 4.0
        beat4      = int(self._beat_phase)               # 0,1,2,3
        bar        = self._beat_phase / 4.0              # [0..1) sur la mesure
        sixteenth  = self._beat_phase * 4.0 % 16.0      # [0..16)
        return bar, beat4, sixteenth

    def _estimate_bpm(self) -> None:
        e = np.array(self._energy_buf, dtype=np.float32)
        e -= e.mean()
        n = len(e)
        # Autocorrélation via FFT
        fft_e = np.fft.rfft(e, n=n * 2)
        ac    = np.fft.irfft(fft_e * np.conj(fft_e))[:n]
        ac    /= (ac[0] + 1e-9)
        # Chercher le pic dans la plage BPM [BPM_MIN..BPM_MAX]
        lag_min = int(self._fps * 60.0 / self.BPM_MAX)
        lag_max = int(self._fps * 60.0 / self.BPM_MIN)
        lag_min = max(1, min(lag_min, n - 1))
        lag_max = max(lag_min + 1, min(lag_max, n - 1))
        if lag_max <= lag_min:
            return
        peak_lag = lag_min + int(np.argmax(ac[lag_min:lag_max]))
        if peak_lag > 0:
            candidate = 60.0 * self._fps / peak_lag
            # Lissage exponentiel du BPM
            self.bpm = self.bpm * 0.7 + candidate * 0.3

# ─────────────────────────────────────────────────────────────────────────────
#  1.2 — ONSET DETECTOR (flux spectral demi-onde rectifié)
# ─────────────────────────────────────────────────────────────────────────────

class OnsetDetector:
    def __init__(self, threshold: float = 0.4, decay: float = 0.75):
        self._prev  = None
        self.thr    = threshold
        self.decay  = decay
        self._val   = 0.0

    def process(self, mag: np.ndarray) -> float:
        beat = 0.0
        if self._prev is not None:
            flux = float(np.sum(np.maximum(mag - self._prev, 0.0)))
            if flux > self.thr:
                beat = min(flux / self.thr, 3.0)
        self._prev = mag.copy()
        self._val  = max(beat, self._val * self.decay)
        return self._val

# ─────────────────────────────────────────────────────────────────────────────
#  1.2 — DÉTECTION DE SECTIONS (énergie long terme)
# ─────────────────────────────────────────────────────────────────────────────

class SectionDetector:
    """
    Divise la piste en 8 sections (0..7) basées sur l'énergie cumulée.
    Précalculé une seule fois à l'init.
    """
    N_SECTIONS = 8

    def __init__(self, audio_data: np.ndarray, sr: int):
        self._dur    = len(audio_data) / sr
        self._bounds = np.linspace(0.0, self._dur, self.N_SECTIONS + 1)

    def section_at(self, t: float) -> int:
        idx = int(t / self._dur * self.N_SECTIONS)
        return max(0, min(idx, self.N_SECTIONS - 1))

# ─────────────────────────────────────────────────────────────────────────────
#  ANALYSEUR PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class AudioAnalyzer:
    """
    Analyse audio temps-réel complète — Phase 1.

    Paramètres
    ----------
    ctx            : contexte moderngl
    audio_data     : PCM mono float32, shape (N,)
    stereo_data    : PCM stéréo float32, shape (N,2) ou None
    sr             : fréquence d'échantillonnage
    smoothing      : lissage des bandes [0..1]
    kick_sens      : sensibilité kick
    bass_gain / mid_gain / high_gain : gains par bande
    beat_threshold : seuil onset
    latency_ms     : compensation de latence en ms (avance la lecture)
    cue_points     : liste de (temps_s, valeur) pour iCue
    fft_size       : taille FFT (512/1024/2048/4096), ou None = auto
    """

    def __init__(
        self,
        ctx:            moderngl.Context,
        audio_data:     np.ndarray,
        sr:             int,
        stereo_data:    np.ndarray | None = None,
        smoothing:      float = 0.85,
        kick_sens:      float = 1.5,
        bass_gain:      float = 1.0,
        mid_gain:       float = 1.0,
        high_gain:      float = 1.0,
        beat_threshold: float = 0.4,
        latency_ms:     float = 0.0,
        cue_points:     list  = None,
        fft_size:       int   = None,
    ):
        self.ctx         = ctx
        self.data        = audio_data.astype(np.float32)
        self.stereo      = stereo_data.astype(np.float32) if stereo_data is not None else None
        self.sr          = sr
        self.smoothing   = smoothing
        self.kick_sens   = kick_sens
        self.bass_gain   = bass_gain
        self.mid_gain    = mid_gain
        self.high_gain   = high_gain
        self.latency_ms  = latency_ms
        self.cue_points  = sorted(cue_points or [], key=lambda x: x[0])

        # ── FFT adaptative ────────────────────────────────────────────────
        if fft_size is not None and fft_size in FFT_SIZES:
            self._fft_size = fft_size
            self._adaptive = False
        else:
            self._fft_size = 2048
            self._adaptive = True   # sera ajusté selon la scène active

        self._window  = _hann(self._fft_size)

        # ── Indices bandes simples ────────────────────────────────────────
        self._kick_lo = _freq_to_bin(20,   sr, self._fft_size)
        self._kick_hi = _freq_to_bin(150,  sr, self._fft_size)
        self._bass_lo = _freq_to_bin(20,   sr, self._fft_size)
        self._bass_hi = _freq_to_bin(250,  sr, self._fft_size)
        self._mid_lo  = _freq_to_bin(250,  sr, self._fft_size)
        self._mid_hi  = _freq_to_bin(4000, sr, self._fft_size)
        self._high_lo = _freq_to_bin(4000, sr, self._fft_size)
        self._high_hi = _freq_to_bin(20000,sr, self._fft_size)

        # ── Bandes Bark (24 bandes critiques) ────────────────────────────
        self._bark_bins = [
            (_freq_to_bin(BARK_FREQS[i],   sr, self._fft_size),
             _freq_to_bin(BARK_FREQS[i+1], sr, self._fft_size))
            for i in range(BARK_BANDS)
        ]

        # ── État lissage ──────────────────────────────────────────────────
        self._smooth = {k: 0.0 for k in ("kick","bass","mid","high")}

        # ── Fenêtre RMS peak (100 ms) ─────────────────────────────────────
        self._rms_win = max(1, int(sr * RMS_WIN_MS / 1000))

        # ── Énergie long terme (8 s) ──────────────────────────────────────
        energy_buf_size = max(64, int(sr / self._fft_size * ENERGY_WIN_S * 2))
        self._energy_buf = deque(maxlen=energy_buf_size)
        self._energy_max = 1e-6   # normalisateur adaptatif

        # ── Historique spectre (waterfall 256×64) ─────────────────────────
        self._history = np.zeros((HISTORY_ROWS, SPEC_BINS), dtype=np.float32)
        self._hist_row = 0
        self._hist_frame_count = 0
        self._hist_skip = max(1, int(sr / self._fft_size / 8))  # ≈8 Hz waterfall

        # ── Drop detector ─────────────────────────────────────────────────
        self._drop_val      = 0.0
        self._pre_drop_nrg  = deque(maxlen=max(4, int(2.0 * sr / self._fft_size)))

        # ── Sous-systèmes ─────────────────────────────────────────────────
        hop = self._fft_size // 4
        self._onset   = OnsetDetector(threshold=beat_threshold, decay=BEAT_DECAY)
        self._beat_tr = BeatTracker(sr=sr, hop=hop)
        self._section = SectionDetector(audio_data, sr)

        # ── Textures GPU ──────────────────────────────────────────────────
        def _tex1d(w):
            t = ctx.texture((w, 1), 1, dtype='f4')
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
            return t

        self._tex_spectrum = _tex1d(SPEC_BINS)
        self._tex_waveform = _tex1d(WAVE_BINS)
        self._tex_bark     = _tex1d(BARK_BANDS)

        self._tex_history  = ctx.texture((SPEC_BINS, HISTORY_ROWS), 1, dtype='f4')
        self._tex_history.filter = (moderngl.LINEAR, moderngl.LINEAR)

        # Buffer history plat pour upload GPU
        self._history_flat = np.zeros(SPEC_BINS * HISTORY_ROWS, dtype=np.float32)

    # ── API : set_fft_size (FFT adaptative selon scène) ──────────────────────

    def set_fft_size(self, size: int) -> None:
        """Change la taille FFT à chaud (entre les scènes). Phase 1.1."""
        if size not in FFT_SIZES or size == self._fft_size:
            return
        self._fft_size = size
        self._window   = _hann(size)
        # Recalculer tous les indices
        sr = self.sr
        self._kick_lo = _freq_to_bin(20,   sr, size)
        self._kick_hi = _freq_to_bin(150,  sr, size)
        self._bass_lo = _freq_to_bin(20,   sr, size)
        self._bass_hi = _freq_to_bin(250,  sr, size)
        self._mid_lo  = _freq_to_bin(250,  sr, size)
        self._mid_hi  = _freq_to_bin(4000, sr, size)
        self._high_lo = _freq_to_bin(4000, sr, size)
        self._high_hi = _freq_to_bin(20000,sr, size)
        self._bark_bins = [
            (_freq_to_bin(BARK_FREQS[i],   sr, size),
             _freq_to_bin(BARK_FREQS[i+1], sr, size))
            for i in range(BARK_BANDS)
        ]

    # ── UPDATE principal ──────────────────────────────────────────────────────

    def update(self, t: float) -> dict:
        """Calcule tous les uniforms audio pour le temps t (secondes)."""

        # Compensation de latence : avancer dans les données PCM
        t_audio = t + self.latency_ms / 1000.0
        idx = int(t_audio * self.sr)
        idx = max(0, min(idx, len(self.data) - self._fft_size))

        # ── Waveform (512 samples centré sur t) ──────────────────────────
        w0  = max(0, idx - WAVE_BINS // 2)
        wav = self.data[w0: w0 + WAVE_BINS]
        if len(wav) < WAVE_BINS:
            wav = np.pad(wav, (0, WAVE_BINS - len(wav)))
        self._tex_waveform.write(((wav * 0.5 + 0.5).astype(np.float32)).tobytes())

        # ── FFT ───────────────────────────────────────────────────────────
        seg = self.data[idx: idx + self._fft_size]
        if len(seg) < self._fft_size:
            seg = np.pad(seg, (0, self._fft_size - len(seg)))
        if len(self._window) != len(seg):
            self._window = _hann(len(seg))
        mag = np.abs(np.fft.rfft(seg * self._window)) / self._fft_size

        # ── Bandes simples (RMS + Peak) ───────────────────────────────────
        s   = self.smoothing
        is_ = 1.0 - s

        raw_kick = _band_energy(mag, self._kick_lo, self._kick_hi) * self.kick_sens * 15.0
        raw_bass = _band_energy(mag, self._bass_lo, self._bass_hi) * 6.0 * self.bass_gain
        raw_mid  = _band_energy(mag, self._mid_lo,  self._mid_hi)  * 4.0 * self.mid_gain
        raw_high = _band_energy(mag, self._high_lo, self._high_hi) * 5.0 * self.high_gain

        for k, v in (("kick", raw_kick),("bass", raw_bass),("mid", raw_mid),("high", raw_high)):
            self._smooth[k] = self._smooth[k] * s + v * is_

        # Peak instantané (non lissé, pour iBassPeak etc.)
        peak_bass = _band_peak(mag, self._bass_lo, self._bass_hi) * 6.0 * self.bass_gain
        peak_mid  = _band_peak(mag, self._mid_lo,  self._mid_hi)  * 4.0 * self.mid_gain
        peak_high = _band_peak(mag, self._high_lo, self._high_hi) * 5.0 * self.high_gain

        # RMS fenêtre 100 ms
        rms_lo = max(0, idx - self._rms_win)
        rms_seg = self.data[rms_lo: idx + self._rms_win]
        rms_bass = _rms(rms_seg) * 3.0 * self.bass_gain
        rms_mid  = _rms(rms_seg) * 2.0 * self.mid_gain
        rms_high = _rms(rms_seg) * 1.5 * self.high_gain

        # ── Énergie long terme + drop ─────────────────────────────────────
        frame_nrg = float(np.mean(mag ** 2))
        self._energy_buf.append(frame_nrg)
        self._energy_max = max(self._energy_max, frame_nrg * 1.1)

        energy_lt = 0.0
        if len(self._energy_buf) > 0:
            energy_lt = float(np.mean(self._energy_buf)) / self._energy_max

        # Drop : chute soudaine d'énergie après une accumulation élevée
        self._pre_drop_nrg.append(frame_nrg)
        pre_mean = float(np.mean(self._pre_drop_nrg)) if self._pre_drop_nrg else 0.0
        drop_trig = 1.0 if (pre_mean > self._energy_max * 0.5
                            and frame_nrg < pre_mean * 0.3) else 0.0
        self._drop_val = max(drop_trig, self._drop_val * DROP_DECAY)

        # ── Onset → beat → BPM par autocorrélation ───────────────────────
        beat = self._onset.process(mag)
        self._beat_tr.push(frame_nrg, t)
        bar, beat4, sixteenth = self._beat_tr.tick(t)
        bpm = self._beat_tr.bpm

        # ── Section musicale ──────────────────────────────────────────────
        section = self._section.section_at(t)

        # ── Stéréo width ──────────────────────────────────────────────────
        stereo_width = self._stereo_width(idx)

        # ── Cue point ─────────────────────────────────────────────────────
        cue_val = self._cue_at(t)

        # ── Spectre log → texture spectrum + historique waterfall ─────────
        log_mag = self._compute_log_spectrum(mag)
        self._tex_spectrum.write(log_mag.tobytes())
        self._update_history(log_mag)

        # ── Bandes Bark → texture ─────────────────────────────────────────
        bark = self._compute_bark(mag)
        self._tex_bark.write(bark.tobytes())

        return {
            # Bandes lissées
            "iKick":      float(min(self._smooth["kick"], 3.0)),
            "iBass":      float(min(self._smooth["bass"], 3.0)),
            "iMid":       float(min(self._smooth["mid"],  3.0)),
            "iHigh":      float(min(self._smooth["high"], 3.0)),
            # Peaks instantanés
            "iBassPeak":  float(min(peak_bass, 3.0)),
            "iMidPeak":   float(min(peak_mid,  3.0)),
            "iHighPeak":  float(min(peak_high, 3.0)),
            # RMS fenêtre
            "iBassRMS":   float(min(rms_bass, 1.0)),
            "iMidRMS":    float(min(rms_mid,  1.0)),
            "iHighRMS":   float(min(rms_high, 1.0)),
            # Beat / BPM
            "iBeat":      float(min(beat, 3.0)),
            "iBPM":       float(bpm),
            "iBar":       float(bar),
            "iBeat4":     float(beat4),
            "iSixteenth": float(sixteenth),
            # Macro
            "iEnergy":    float(min(energy_lt, 1.0)),
            "iDrop":      float(min(self._drop_val, 1.0)),
            "iStereoWidth": float(stereo_width),
            "iCue":       float(cue_val),
            "iSection":   float(section),
        }

    # ── Helpers internes ──────────────────────────────────────────────────────

    def _compute_log_spectrum(self, mag: np.ndarray) -> np.ndarray:
        """Spectre log normalisé sur SPEC_BINS bandes."""
        n   = len(mag)
        out = np.zeros(SPEC_BINS, dtype=np.float32)
        for i in range(SPEC_BINS):
            lo_hz = 20.0 * ((self.sr / 2.0 / 20.0) ** (i / SPEC_BINS))
            hi_hz = 20.0 * ((self.sr / 2.0 / 20.0) ** ((i + 1) / SPEC_BINS))
            lo_b  = max(0, _freq_to_bin(lo_hz, self.sr, self._fft_size))
            hi_b  = min(n - 1, _freq_to_bin(hi_hz, self.sr, self._fft_size) + 1)
            seg   = mag[lo_b:hi_b]
            out[i] = float(np.mean(seg)) if len(seg) > 0 else 0.0
        out = np.log1p(out * 80.0) / np.log1p(80.0)
        return out

    def _compute_bark(self, mag: np.ndarray) -> np.ndarray:
        """24 bandes Bark perceptives, normalisées [0,1]."""
        out = np.zeros(BARK_BANDS, dtype=np.float32)
        for i, (lo, hi) in enumerate(self._bark_bins):
            out[i] = _band_energy(mag, lo, max(lo+1, hi)) * 8.0
        out = np.log1p(out * 20.0) / np.log1p(20.0)
        return np.clip(out, 0.0, 1.0)

    def _update_history(self, log_mag: np.ndarray) -> None:
        """Met à jour le waterfall toutes les _hist_skip frames."""
        self._hist_frame_count += 1
        if self._hist_frame_count < self._hist_skip:
            return
        self._hist_frame_count = 0
        # Décaler les lignes vers le bas (ligne 0 = plus récent)
        self._history = np.roll(self._history, 1, axis=0)
        self._history[0] = log_mag
        # Upload GPU : la texture est organisée ligne par ligne
        self._history_flat[:] = self._history.ravel()
        self._tex_history.write(self._history_flat.tobytes())

    def _stereo_width(self, idx: int) -> float:
        """Calcule la largeur stéréo L-R sur une fenêtre de FFT_SIZE samples."""
        if self.stereo is None:
            return 0.0
        n    = self._fft_size
        lo   = max(0, idx)
        hi   = min(lo + n, len(self.stereo))
        if hi - lo < 64:
            return 0.0
        L = self.stereo[lo:hi, 0].astype(np.float32)
        R = self.stereo[lo:hi, 1].astype(np.float32)
        if len(L) < n:
            L = np.pad(L, (0, n - len(L)))
            R = np.pad(R, (0, n - len(R)))
        mid  = (L + R) * 0.5
        side = (L - R) * 0.5
        mid_rms  = _rms(mid)
        side_rms = _rms(side)
        denom = mid_rms + side_rms
        return float(side_rms / denom) if denom > 1e-9 else 0.0

    def _cue_at(self, t: float) -> float:
        """Retourne la valeur du cue point actif (fenêtre ±0.2 s), 0 sinon."""
        for cue_t, cue_v in self.cue_points:
            if abs(t - cue_t) < 0.2:
                # Impulsion triangulaire centrée sur le cue
                return float(cue_v) * (1.0 - abs(t - cue_t) / 0.2)
        return 0.0

    # ── API GPU ───────────────────────────────────────────────────────────────

    def bind_uniforms(self, prog, uniforms: dict) -> None:
        if prog is None:
            return
        for name, value in uniforms.items():
            if name in prog:
                prog[name].value = value

    def bind_textures(self, prog, start_unit: int = 8) -> None:
        """
        Lie les textures audio sur les units start_unit … start_unit+3 :
          +0 : iSpectrum        (256×1)
          +1 : iWaveform        (512×1)
          +2 : iSpectrumHistory (256×64)
          +3 : iBarkSpectrum    (24×1)
        """
        if prog is None:
            return
        pairs = [
            ("iSpectrum",        self._tex_spectrum, start_unit),
            ("iWaveform",        self._tex_waveform, start_unit + 1),
            ("iSpectrumHistory", self._tex_history,  start_unit + 2),
            ("iBarkSpectrum",    self._tex_bark,     start_unit + 3),
        ]
        for uniform_name, tex, unit in pairs:
            tex.use(unit)
            if uniform_name in prog:
                prog[uniform_name].value = unit

    # ── Mode offline : précalcul complet ─────────────────────────────────────

    def precompute(self, duration: float, fps: float = 60.0) -> list[dict]:
        """
        Précalcule tous les uniforms pour [0..duration] à fps frames/s.
        Utilisé par export_engine pour garantir la précision audio à l'export.
        Retourne une liste de dicts indexés par frame.
        """
        frames = []
        t = 0.0
        dt = 1.0 / fps
        while t <= duration:
            frames.append(self.update(t))
            t += dt
        return frames

    # ── Propriétés ───────────────────────────────────────────────────────────

    @property
    def tex_spectrum(self):        return self._tex_spectrum
    @property
    def tex_waveform(self):        return self._tex_waveform
    @property
    def tex_history(self):         return self._tex_history
    @property
    def tex_bark(self):            return self._tex_bark
    @property
    def fft_size(self):            return self._fft_size
    @property
    def bpm(self):                 return self._beat_tr.bpm
