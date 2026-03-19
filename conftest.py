"""
conftest.py  —  Fixtures partagées pour la suite de tests MEGADEMO
==================================================================

Fixtures disponibles
--------------------
project_dir      : chemin temporaire avec la structure minimale du projet
minimal_project  : dict ``project_data`` minimal (config + timeline + overlays)
gl_context       : contexte moderngl standalone (skip si GPU indisponible)
base_renderer    : instance de BaseRenderer connectée au contexte GL de test
simple_timeline  : timeline avec 2 scènes consécutives
audio_sine       : tableau numpy float32 d'une sinusoïde 440 Hz @ 44100 Hz
"""

from __future__ import annotations

import json
import os
import tempfile

import numpy as np
import pytest


# ─────────────────────────────────────────────────────────────────────────────
#  Projet minimal
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def minimal_config() -> dict:
    """Configuration ``config`` minimale compatible avec les classes du moteur."""
    return {
        "RES":             [640, 360],
        "MUSIC_FILE":      "",
        "MUSIC_DURATION":  10.0,
        "WINDOW_TITLE":    "MEGADEMO-TEST",
        "INTRO_TIME":      0.0,
        "LOGO_DURATION":   0.0,
        "PRESENTS_DURATION": 0.0,
        "AUDIO_SMOOTHING": 0.85,
        "KICK_SENS":       1.5,
        "BASS_GAIN":       1.0,
        "MID_GAIN":        1.0,
        "HIGH_GAIN":       1.0,
        "BEAT_THRESHOLD":  0.4,
        "LATENCY_MS":      0.0,
        "CUE_POINTS":      [],
    }


@pytest.fixture(scope="session")
def simple_timeline() -> list:
    """Timeline avec deux scènes consécutives (pas de gap)."""
    return [
        {"base_name": "scene_a", "start": 0.0,  "duration": 5.0},
        {"base_name": "scene_b", "start": 5.0,  "duration": 5.0},
    ]


@pytest.fixture(scope="session")
def minimal_project(minimal_config, simple_timeline) -> dict:
    """Dict ``project_data`` complet minimal."""
    return {
        "config":   minimal_config,
        "timeline": simple_timeline,
        "overlays": [],
        "images":   [],
    }


@pytest.fixture(scope="session")
def project_dir(minimal_project, tmp_path_factory) -> str:
    """
    Répertoire temporaire avec une arborescence minimale du projet :
    project.json, scenes/, overlays/, fonts/, images/, luts/.

    Un shader trivial ``scene_scene_a.frag`` est créé pour que
    les tests de chargement puissent fonctionner.
    """
    d = tmp_path_factory.mktemp("project")
    # Sous-dossiers requis
    for sub in ("scenes", "overlays", "fonts", "images", "luts", "shaders"):
        (d / sub).mkdir(exist_ok=True)

    # project.json
    (d / "project.json").write_text(
        json.dumps(minimal_project, indent=2), encoding="utf-8")

    # Shader trivial pour scene_a
    frag_trivial = (
        "#version 330\n"
        "out vec4 fragColor;\n"
        "uniform float iTime;\n"
        "void main(){ fragColor = vec4(mod(iTime, 1.0), 0.0, 0.0, 1.0); }\n"
    )
    (d / "scenes" / "scene_scene_a.frag").write_text(frag_trivial, encoding="utf-8")

    # Shader overlay trivial
    (d / "overlays" / "test_overlay.frag").write_text(
        "#version 330\nout vec4 f;\nvoid main(){f=vec4(1.0);}\n",
        encoding="utf-8")

    return str(d)


# ─────────────────────────────────────────────────────────────────────────────
#  Contexte OpenGL
# ─────────────────────────────────────────────────────────────────────────────

def _try_create_gl():
    """Tente de créer un contexte moderngl standalone. Retourne None si impossible."""
    try:
        import moderngl
        return moderngl.create_standalone_context()
    except Exception:
        return None


@pytest.fixture(scope="session")
def gl_context():
    """
    Contexte moderngl standalone partagé pour toute la session de tests.

    Si aucun contexte GL n'est disponible (CI sans GPU), tous les tests
    marqués ``gpu`` sont automatiquement sautés via ce fixture.
    """
    ctx = _try_create_gl()
    if ctx is None:
        pytest.skip("Contexte OpenGL indisponible (pas de GPU ou pas de EGL/OSMesa)")
    yield ctx
    ctx.release()


@pytest.fixture
def gl_context_per_test():
    """
    Contexte GL **par test** (isolation totale).
    Utiliser uniquement pour les tests qui modifient l'état GL de façon
    destructive.
    """
    ctx = _try_create_gl()
    if ctx is None:
        pytest.skip("Contexte OpenGL indisponible")
    yield ctx
    ctx.release()


# ─────────────────────────────────────────────────────────────────────────────
#  BaseRenderer de test
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def base_renderer(gl_context, project_dir, minimal_project):
    """
    Instance de ``BaseRenderer`` initialisée avec le contexte GL de session
    et le projet minimal.
    """
    import sys
    # Ajoute le dossier racine du projet au path pour les imports relatifs
    root = os.path.dirname(os.path.dirname(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from base_renderer import BaseRenderer

    br = BaseRenderer(
        project_dir = project_dir,
        cfg         = minimal_project["config"],
        timeline    = minimal_project["timeline"],
        overlays    = minimal_project["overlays"],
    )
    br.init_gl_base(gl_context)
    yield br
    br.release_base()


# ─────────────────────────────────────────────────────────────────────────────
#  Audio de test
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def audio_sine() -> np.ndarray:
    """
    Sinusoïde 440 Hz, 3 secondes, mono, float32 @ 44100 Hz.
    Utilisée pour tester AudioAnalyzer sans dépendance à un fichier audio.
    """
    sr  = 44100
    dur = 3.0
    t   = np.linspace(0, dur, int(sr * dur), endpoint=False)
    return (np.sin(2 * np.pi * 440 * t)).astype(np.float32)


@pytest.fixture(scope="session")
def audio_stereo(audio_sine) -> np.ndarray:
    """Version stéréo de ``audio_sine`` (shape ``(N, 2)``)."""
    return np.column_stack([audio_sine, audio_sine * 0.8])


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_wav(audio_sine, tmp_path) -> str:
    """
    Fichier WAV temporaire contenant la sinusoïde 440 Hz.
    Nécessite ``soundfile``.
    """
    pytest.importorskip("soundfile")
    import soundfile as sf
    path = str(tmp_path / "test_audio.wav")
    sf.write(path, audio_sine, 44100)
    return path


@pytest.fixture
def small_png(tmp_path) -> str:
    """Image PNG 16×16 RGBA de test (rouge uni)."""
    path = str(tmp_path / "test.png")
    try:
        from PIL import Image
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        img.save(path)
    except ImportError:
        # Fallback : écriture PNG brute via BaseRenderer._write_png_raw
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from base_renderer import BaseRenderer
        arr = np.full((16, 16, 3), [255, 0, 0], dtype=np.uint8)
        BaseRenderer._write_png_raw(path, arr)
    return path
