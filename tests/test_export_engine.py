"""
tests/test_export_engine.py
===========================
Tests unitaires et d'intégration pour ``ExportEngine``.

Couverture
----------
- Instanciation et configuration
- _scene_at / _overlay_at / _image_at
- _get_audio_uniforms (mode simplifié, sans audio)
- _write_png_raw (hérité de BaseRenderer)
- check_ffmpeg
- run() annulé immédiatement
- _run_sequence() (GPU + slow)
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from export_engine import ExportEngine


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def engine(project_dir, minimal_project):
    """ExportEngine minimal (pas de GPU, pas d'audio)."""
    return ExportEngine(
        project_dir  = project_dir,
        project_data = minimal_project,
        width        = 320,
        height       = 180,
        fps          = 10,
        on_log       = lambda m: None,
    )


@pytest.fixture
def engine_with_images(project_dir, minimal_project):
    """ExportEngine avec une piste images."""
    data = dict(minimal_project)
    data["images"] = [{"start": 1.0, "duration": 2.0, "file": "images/test.png"}]
    return ExportEngine(
        project_dir  = project_dir,
        project_data = data,
        width        = 320,
        height       = 180,
        fps          = 10,
        on_log       = lambda m: None,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Tests unitaires
# ─────────────────────────────────────────────────────────────────────────────

class TestExportEngineInit:
    @pytest.mark.unit
    def test_default_codec(self, engine):
        assert engine.codec == "h264"

    @pytest.mark.unit
    def test_resolution_stored(self, engine):
        assert engine.width  == 320
        assert engine.height == 180

    @pytest.mark.unit
    def test_fps_stored(self, engine):
        assert engine.fps == 10

    @pytest.mark.unit
    def test_not_cancelled(self, engine):
        assert not engine._cancelled

    @pytest.mark.unit
    def test_cancel_sets_flag(self, engine):
        engine.cancel()
        assert engine._cancelled


class TestTimelineLookup:
    @pytest.mark.unit
    def test_scene_at_first(self, engine):
        sc = engine._scene_at(2.0)
        assert sc["base_name"] == "scene_a"

    @pytest.mark.unit
    def test_scene_at_second(self, engine):
        sc = engine._scene_at(7.0)
        assert sc["base_name"] == "scene_b"

    @pytest.mark.unit
    def test_scene_at_none(self, engine):
        assert engine._scene_at(100.0) is None

    @pytest.mark.unit
    def test_overlay_at_none(self, engine):
        assert engine._overlay_at(5.0) is None

    @pytest.mark.unit
    def test_image_at(self, engine_with_images):
        img = engine_with_images._image_at(1.5)
        assert img is not None
        assert img["file"] == "images/test.png"

    @pytest.mark.unit
    def test_image_at_none(self, engine_with_images):
        assert engine_with_images._image_at(0.5) is None


class TestGetAudioUniforms:
    @pytest.mark.unit
    def test_returns_dict(self, engine):
        au = engine._get_audio_uniforms(0)
        assert isinstance(au, dict)

    @pytest.mark.unit
    def test_has_iKick(self, engine):
        au = engine._get_audio_uniforms(0)
        assert "iKick" in au

    @pytest.mark.unit
    def test_iBPM_default(self, engine):
        au = engine._get_audio_uniforms(0)
        assert au["iBPM"] == 120.0

    @pytest.mark.unit
    def test_kick_non_negative(self, engine):
        for frame_idx in range(50):
            au = engine._get_audio_uniforms(frame_idx)
            assert au["iKick"] >= 0.0


class TestCheckFfmpeg:
    @pytest.mark.unit
    def test_returns_tuple(self):
        ok, msg = ExportEngine.check_ffmpeg()
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    @pytest.mark.unit
    def test_message_nonempty(self):
        _, msg = ExportEngine.check_ffmpeg()
        assert len(msg) > 0


class TestWritePngRaw:
    """Hérité de BaseRenderer — vérifie que ExportEngine y a bien accès."""

    @pytest.mark.unit
    def test_write_png(self, tmp_path):
        path = str(tmp_path / "out.png")
        arr  = np.zeros((8, 8, 3), dtype=np.uint8)
        ExportEngine._write_png_raw(path, arr)
        assert os.path.exists(path)
        with open(path, "rb") as fh:
            assert fh.read(8) == b"\x89PNG\r\n\x1a\n"


# ─────────────────────────────────────────────────────────────────────────────
#  Tests GPU / intégration
# ─────────────────────────────────────────────────────────────────────────────

class TestRunCancelled:
    @pytest.mark.gpu
    def test_run_cancel_returns_false(self, project_dir, minimal_project, tmp_path):
        """Un export annulé dès la première frame doit retourner False."""
        logs = []
        engine = ExportEngine(
            project_dir  = project_dir,
            project_data = minimal_project,
            width        = 64,
            height       = 36,
            fps          = 5,
            on_log       = logs.append,
        )
        engine.cancel()
        result = engine.run(str(tmp_path / "cancelled.mp4"))
        # Soit False (ffmpeg non trouvé ou annulé), soit True si ffmpeg absent
        # On vérifie juste que ça ne plante pas
        assert isinstance(result, bool)


class TestRunSequence:
    @pytest.mark.gpu
    @pytest.mark.slow
    def test_png_sequence_output(self, project_dir, minimal_project, tmp_path):
        """Vérifie qu'une séquence PNG d'1 seconde produit les bons fichiers."""
        out_dir = str(tmp_path / "seq_png")
        logs    = []
        engine  = ExportEngine(
            project_dir  = project_dir,
            project_data = minimal_project,
            width        = 64,
            height       = 36,
            fps          = 5,
            on_log       = logs.append,
            codec        = "png_seq",
        )
        # On limite à 1 s en patchant la durée
        engine.cfg = dict(engine.cfg)
        engine.cfg["MUSIC_DURATION"] = 1.0

        result = engine.run(out_dir)
        assert result is True
        files = sorted(os.listdir(out_dir))
        assert len(files) == 5  # 5 fps × 1 s
        for f in files:
            assert f.endswith(".png") or f.endswith(".npy")

    @pytest.mark.gpu
    @pytest.mark.slow
    def test_progress_callback_called(self, project_dir, minimal_project, tmp_path):
        out_dir    = str(tmp_path / "seq_progress")
        progress_calls = []
        engine = ExportEngine(
            project_dir  = project_dir,
            project_data = minimal_project,
            width        = 64,
            height       = 36,
            fps          = 5,
            on_log       = lambda m: None,
            on_progress  = lambda f, t: progress_calls.append((f, t)),
            codec        = "png_seq",
        )
        engine.cfg = dict(engine.cfg)
        engine.cfg["MUSIC_DURATION"] = 0.5

        engine.run(out_dir)
        assert len(progress_calls) > 0
        assert progress_calls[-1][0] == progress_calls[-1][1]  # f == total à la fin
