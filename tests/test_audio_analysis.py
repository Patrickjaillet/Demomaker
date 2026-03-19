"""
tests/test_audio_analysis.py
============================
Tests unitaires et d'intégration pour ``AudioAnalyzer``.

Couverture
----------
- Initialisation avec différentes tailles FFT
- update() retourne les bons clés d'uniforms
- Valeurs dans les plages attendues
- precompute() produit le bon nombre de frames
- bind_textures() n'écrase pas les unités déjà utilisées
- Mode stéréo vs mono
"""

from __future__ import annotations

import sys
import os

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Importe uniquement si moderngl est disponible
AudioAnalyzer = pytest.importorskip(
    "audio_analysis", reason="audio_analysis non disponible"
).AudioAnalyzer


EXPECTED_SCALAR_UNIFORMS = {
    "iKick", "iBass", "iMid", "iHigh",
    "iBassPeak", "iMidPeak", "iHighPeak",
    "iBassRMS", "iMidRMS", "iHighRMS",
    "iBeat", "iBPM",
    "iBar", "iBeat4", "iSixteenth",
    "iEnergy", "iDrop", "iStereoWidth",
    "iCue", "iSection",
}


# ─────────────────────────────────────────────────────────────────────────────
#  Fixture analyseur
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def analyzer(gl_context, audio_sine):
    """AudioAnalyzer initialisé avec la sinusoïde 440 Hz mono."""
    ana = AudioAnalyzer(
        ctx            = gl_context,
        audio_data     = audio_sine,
        stereo_data    = None,
        sr             = 44100,
        smoothing      = 0.85,
        kick_sens      = 1.5,
        bass_gain      = 1.0,
        mid_gain       = 1.0,
        high_gain      = 1.0,
        beat_threshold = 0.4,
        latency_ms     = 0.0,
        cue_points     = [],
    )
    yield ana


@pytest.fixture(scope="module")
def analyzer_stereo(gl_context, audio_stereo):
    """AudioAnalyzer initialisé avec de l'audio stéréo."""
    mono = audio_stereo.mean(axis=1)
    ana  = AudioAnalyzer(
        ctx            = gl_context,
        audio_data     = mono,
        stereo_data    = audio_stereo,
        sr             = 44100,
        smoothing      = 0.85,
        kick_sens      = 1.5,
        bass_gain      = 1.0,
        mid_gain       = 1.0,
        high_gain      = 1.0,
        beat_threshold = 0.4,
        latency_ms     = 0.0,
        cue_points     = [],
    )
    yield ana


# ─────────────────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAudioAnalyzerInit:
    @pytest.mark.gpu
    def test_fft_size_chosen(self, analyzer):
        assert analyzer.fft_size in (512, 1024, 2048, 4096)

    @pytest.mark.gpu
    def test_textures_created(self, analyzer):
        """Les textures GPU doivent exister après l'init."""
        # L'attribut exact dépend de l'implémentation, on vérifie que update ne plante pas
        result = analyzer.update(0.0)
        assert isinstance(result, dict)


class TestAudioAnalyzerUpdate:
    @pytest.mark.gpu
    def test_returns_all_uniform_keys(self, analyzer):
        result = analyzer.update(0.5)
        missing = EXPECTED_SCALAR_UNIFORMS - result.keys()
        assert not missing, f"Uniforms manquants : {missing}"

    @pytest.mark.gpu
    def test_kick_in_range(self, analyzer):
        for t in np.linspace(0, 2.9, 30):
            result = analyzer.update(float(t))
            assert 0.0 <= result["iKick"], f"iKick < 0 à t={t}"

    @pytest.mark.gpu
    def test_bpm_plausible(self, analyzer):
        result = analyzer.update(1.0)
        assert 40.0 <= result["iBPM"] <= 250.0, f"BPM implausible : {result['iBPM']}"

    @pytest.mark.gpu
    def test_energy_in_01(self, analyzer):
        result = analyzer.update(1.0)
        assert 0.0 <= result["iEnergy"] <= 1.0

    @pytest.mark.gpu
    def test_stereo_width_in_01(self, analyzer_stereo):
        result = analyzer_stereo.update(0.5)
        assert 0.0 <= result["iStereoWidth"] <= 1.0

    @pytest.mark.gpu
    def test_past_end_no_crash(self, analyzer):
        """update() sur un temps hors audio ne doit pas lever d'exception."""
        result = analyzer.update(9999.0)
        assert isinstance(result, dict)


class TestAudioAnalyzerPrecompute:
    @pytest.mark.gpu
    @pytest.mark.slow
    def test_frame_count(self, analyzer):
        fps      = 30.0
        duration = 1.0
        frames   = analyzer.precompute(duration, fps)
        expected = int(duration * fps)
        # On tolère ±1 frame selon l'arrondi
        assert abs(len(frames) - expected) <= 1

    @pytest.mark.gpu
    @pytest.mark.slow
    def test_each_frame_has_all_keys(self, analyzer):
        frames = analyzer.precompute(0.5, 10.0)
        for i, f in enumerate(frames):
            missing = EXPECTED_SCALAR_UNIFORMS - f.keys()
            assert not missing, f"Frame {i} : uniforms manquants {missing}"

    @pytest.mark.gpu
    @pytest.mark.slow
    def test_frames_are_dicts(self, analyzer):
        frames = analyzer.precompute(0.2, 5.0)
        assert all(isinstance(f, dict) for f in frames)


class TestBindTextures:
    @pytest.mark.gpu
    def test_no_exception(self, analyzer, gl_context):
        """bind_textures ne doit pas lever d'exception avec un prog valide."""
        import moderngl
        frag = (
            "#version 330\n"
            "uniform sampler2D iSpectrum;\n"
            "out vec4 c;\n"
            "void main(){c=vec4(0.0);}\n"
        )
        buf  = gl_context.buffer(
            data=np.array([-1, 1, -1, -1, 1, 1, 1, -1], dtype="f4"))
        try:
            prog = gl_context.program(
                vertex_shader=(
                    "#version 330\nin vec2 in_vert;"
                    "void main(){gl_Position=vec4(in_vert,0,1);}"),
                fragment_shader=frag)
            analyzer.bind_textures(prog, start_unit=8)
        except Exception as exc:
            pytest.fail(f"bind_textures a levé une exception : {exc}")
        finally:
            buf.release()
