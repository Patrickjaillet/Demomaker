"""
camera_widget.py  —  Phase 9.1 : Widget d'édition de trajectoires caméra
=========================================================================

Panels PyQt6 pour éditer les trajectoires CameraSystem depuis la GUI :

    CameraTrajectoryEditor   Tableau de keyframes éditable + prévisualisation
    CameraKeyframeRow        Ligne éditable (time / pos XYZ / target XYZ / fov / roll)
    BlenderImportDialog      Import JSON exporté depuis Blender
    CameraPreviewWidget      Aperçu 2D (vue de dessus) de la trajectoire

Menu d'intégration (dans demomaker_gui.py) :
    m_p9 = mb.addMenu("Phase 9")
    m_p9.addAction("Caméra — Trajectoires…",   self._open_camera_editor)
    m_p9.addAction("Importer depuis Blender…", self._open_blender_import)
"""

from __future__ import annotations

import os
import json
from typing import Optional, Callable

import numpy as np

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QLineEdit, QDoubleSpinBox, QComboBox, QFileDialog,
    QMessageBox, QSplitter, QSizePolicy, QScrollArea,
)
from PySide6.QtCore    import Qt, Signal, QPointF
from PySide6.QtGui     import (
    QPainter, QPen, QColor, QPainterPath, QBrush, QFont,
)

from camera_system import CameraSystem, CameraTrajectory, CameraKeyframe


# ─────────────────────────────────────────────────────────────────────────────
#  Couleurs
# ─────────────────────────────────────────────────────────────────────────────

C_BG      = QColor("#1a1a2e")
C_GRID    = QColor("#2a2a4e")
C_TRAJ    = QColor("#00ffcc")
C_KF      = QColor("#ff6b35")
C_TARGET  = QColor("#88aaff")
C_SEL     = QColor("#ffffff")
C_TEXT    = QColor("#cccccc")


# ─────────────────────────────────────────────────────────────────────────────
#  CameraPreviewWidget — vue de dessus (XZ plane)
# ─────────────────────────────────────────────────────────────────────────────

class CameraPreviewWidget(QWidget):
    """Aperçu 2D de la trajectoire caméra (vue de dessus, plan XZ)."""

    keyframe_clicked = Signal(int)   # index du keyframe cliqué

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 250)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._trajectory: Optional[CameraTrajectory] = None
        self._selected: int = -1
        self._t_cursor: float = 0.0
        self._scale = 30.0   # pixels par unité monde
        self._offset = QPointF(0, 0)

    def set_trajectory(self, traj: Optional[CameraTrajectory]) -> None:
        self._trajectory = traj
        self.update()

    def set_cursor(self, t: float) -> None:
        self._t_cursor = t
        self.update()

    def set_selected(self, idx: int) -> None:
        self._selected = idx
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # Fond
        p.fillRect(0, 0, w, h, C_BG)

        # Grille
        p.setPen(QPen(C_GRID, 1))
        step = self._scale * 5
        for gx in range(int(-cx / step) - 1, int(cx / step) + 2):
            x = cx + gx * step
            p.drawLine(int(x), 0, int(x), h)
        for gy in range(int(-cy / step) - 1, int(cy / step) + 2):
            y = cy + gy * step
            p.drawLine(0, int(y), w, int(y))

        if not self._trajectory or not self._trajectory.keyframes:
            p.setPen(QPen(C_TEXT, 1))
            p.drawText(10, 20, "Aucune trajectoire")
            return

        kfs = self._trajectory.keyframes

        # Tracer la trajectoire interpolée (50 points)
        if len(kfs) >= 2:
            points = []
            t0 = kfs[0].time
            t1 = kfs[-1].time
            for i in range(51):
                t = t0 + (t1 - t0) * i / 50
                kf = self._trajectory.evaluate(t)
                px = cx + kf.pos[0] * self._scale
                py = cy - kf.pos[2] * self._scale   # Z inversé
                points.append(QPointF(px, py))
            path = QPainterPath(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            p.setPen(QPen(C_TRAJ, 2))
            p.drawPath(path)

            # Ligne de regard (pos → target)
            for kf in kfs:
                px = cx + kf.pos[0] * self._scale
                py = cy - kf.pos[2] * self._scale
                tx = cx + kf.target[0] * self._scale
                ty = cy - kf.target[2] * self._scale
                p.setPen(QPen(C_TARGET, 1, Qt.DashLine))
                p.drawLine(QPointF(px, py), QPointF(tx, ty))

        # Keyframes
        for i, kf in enumerate(kfs):
            px = cx + kf.pos[0] * self._scale
            py = cy - kf.pos[2] * self._scale
            color = C_SEL if i == self._selected else C_KF
            p.setPen(QPen(color, 2))
            p.setBrush(QBrush(color))
            p.drawEllipse(QPointF(px, py), 5, 5)
            p.setPen(QPen(C_TEXT, 1))
            p.drawText(int(px) + 7, int(py) + 4, f"{kf.time:.1f}s")

        # Curseur de lecture
        if len(kfs) >= 2:
            kf_cur = self._trajectory.evaluate(self._t_cursor)
            px = cx + kf_cur.pos[0] * self._scale
            py = cy - kf_cur.pos[2] * self._scale
            p.setPen(QPen(QColor("#ffff00"), 2))
            p.setBrush(QBrush(QColor("#ffff00")))
            p.drawEllipse(QPointF(px, py), 4, 4)

        p.setPen(QPen(C_TEXT, 1))
        p.setFont(QFont("Courier New", 8))
        p.drawText(4, h - 4, f"Vue de dessus (XZ) — scroll={self._scale:.0f}px/u")

    def mousePressEvent(self, event):
        if not self._trajectory:
            return
        cx, cy = self.width() / 2, self.height() / 2
        mx, my = event.pos().x(), event.pos().y()
        best_i, best_d = -1, 20.0
        for i, kf in enumerate(self._trajectory.keyframes):
            px = cx + kf.pos[0] * self._scale
            py = cy - kf.pos[2] * self._scale
            d = ((px - mx)**2 + (py - my)**2) ** 0.5
            if d < best_d:
                best_d, best_i = d, i
        if best_i >= 0:
            self._selected = best_i
            self.keyframe_clicked.emit(best_i)
            self.update()

    def wheelEvent(self, event):
        self._scale *= 1.1 if event.angleDelta().y() > 0 else 0.9
        self._scale = max(5.0, min(200.0, self._scale))
        self.update()


# ─────────────────────────────────────────────────────────────────────────────
#  CameraTrajectoryEditor — éditeur complet
# ─────────────────────────────────────────────────────────────────────────────

class CameraTrajectoryEditor(QDialog):
    """
    Dialogue d'édition de trajectoire caméra.

    Paramètres
    ----------
    camera_system : CameraSystem
    traj_name     : nom de la trajectoire à éditer (ou "" pour créer)
    on_save       : callback(traj_name, trajectory) appelé à la sauvegarde
    """

    def __init__(
        self,
        camera_system: CameraSystem,
        traj_name:     str = "",
        on_save:       Optional[Callable] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._cs       = camera_system
        self._name     = traj_name
        self._on_save  = on_save
        self._kfs: list[CameraKeyframe] = []

        if traj_name and traj_name in camera_system.trajectory_names:
            self._kfs = list(camera_system._trajectories[traj_name].keyframes)

        self.setWindowTitle(f"Trajectoire caméra — {traj_name or 'Nouvelle'}")
        self.resize(900, 600)
        self._build_ui()
        self._refresh_table()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Barre d'outils
        bar = QHBoxLayout()
        self._name_edit = QLineEdit(self._name)
        self._name_edit.setPlaceholderText("Nom de la trajectoire…")
        bar.addWidget(QLabel("Nom :"))
        bar.addWidget(self._name_edit)
        bar.addStretch()

        btn_add  = QPushButton("⊕ Keyframe")
        btn_del  = QPushButton("⊖ Supprimer")
        btn_save = QPushButton("💾 Sauvegarder")
        btn_add.clicked.connect(self._add_keyframe)
        btn_del.clicked.connect(self._del_keyframe)
        btn_save.clicked.connect(self._save)
        for btn in (btn_add, btn_del, btn_save):
            bar.addWidget(btn)
        layout.addLayout(bar)

        # Splitter : table + prévisualisation
        splitter = QSplitter(Qt.Horizontal)

        # Table
        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels(
            ["Temps", "Pos X", "Pos Y", "Pos Z",
             "Cible X", "Cible Y", "Cible Z", "FOV", "Roll"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.itemChanged.connect(self._on_item_changed)
        splitter.addWidget(self._table)

        # Prévisualisation
        self._preview = CameraPreviewWidget()
        self._preview.keyframe_clicked.connect(self._table.selectRow)
        splitter.addWidget(self._preview)
        splitter.setSizes([500, 360])
        layout.addWidget(splitter)

        # Boutons bas
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _refresh_table(self):
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._kfs))
        for i, kf in enumerate(self._kfs):
            vals = [
                kf.time,
                kf.pos[0], kf.pos[1], kf.pos[2],
                kf.target[0], kf.target[1], kf.target[2],
                kf.fov, kf.roll,
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(f"{v:.4f}")
                item.setTextAlignment(Qt.AlignCenter)
                self._table.setItem(i, j, item)
        self._table.blockSignals(False)
        self._update_preview()

    def _update_preview(self):
        if self._kfs:
            traj = CameraTrajectory(list(self._kfs))
            self._preview.set_trajectory(traj)
        else:
            self._preview.set_trajectory(None)

    def _on_item_changed(self, item):
        row = item.row()
        col = item.column()
        if row >= len(self._kfs):
            return
        try:
            val = float(item.text())
        except ValueError:
            return
        kf = self._kfs[row]
        if col == 0:
            kf.time = val
            self._kfs.sort(key=lambda k: k.time)
            self._refresh_table()
            return
        elif col == 1: kf.pos[0] = val
        elif col == 2: kf.pos[1] = val
        elif col == 3: kf.pos[2] = val
        elif col == 4: kf.target[0] = val
        elif col == 5: kf.target[1] = val
        elif col == 6: kf.target[2] = val
        elif col == 7: kf.fov = val
        elif col == 8: kf.roll = val
        self._update_preview()

    def _add_keyframe(self):
        t_new = self._kfs[-1].time + 1.0 if self._kfs else 0.0
        self._kfs.append(CameraKeyframe(
            time=t_new, pos=[0, 0, -5], target=[0, 0, 0]))
        self._refresh_table()
        self._table.selectRow(len(self._kfs) - 1)

    def _del_keyframe(self):
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self._kfs):
                self._kfs.pop(r)
        self._refresh_table()

    def _save(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Erreur", "Le nom de la trajectoire est requis.")
            return
        if not self._kfs:
            QMessageBox.warning(self, "Erreur", "Au moins un keyframe est requis.")
            return
        traj = CameraTrajectory(list(self._kfs))
        self._cs.add_trajectory(name, traj)
        if self._on_save:
            self._on_save(name, traj)
        QMessageBox.information(self, "Sauvegardé",
            f"Trajectoire '{name}' sauvegardée ({len(self._kfs)} keyframes).")
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
#  BlenderImportDialog
# ─────────────────────────────────────────────────────────────────────────────

class BlenderImportDialog(QDialog):
    """Dialogue d'import de trajectoire depuis un JSON Blender."""

    def __init__(self, camera_system: CameraSystem,
                 on_import: Optional[Callable] = None, parent=None):
        super().__init__(parent)
        self._cs       = camera_system
        self._on_import = on_import
        self.setWindowTitle("Importer depuis Blender")
        self.resize(500, 220)
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)

        self._path_edit = QLineEdit()
        btn_browse = QPushButton("Parcourir…")
        btn_browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self._path_edit)
        path_row.addWidget(btn_browse)
        layout.addRow("Fichier JSON :", path_row)

        self._name_edit = QLineEdit("blender_cam")
        layout.addRow("Nom trajectoire :", self._name_edit)

        self._fps_spin = QDoubleSpinBox()
        self._fps_spin.setRange(1.0, 240.0)
        self._fps_spin.setValue(24.0)
        self._fps_spin.setSuffix(" fps")
        layout.addRow("FPS Blender :", self._fps_spin)

        self._info = QLabel("")
        self._info.setWordWrap(True)
        layout.addRow(self._info)

        btns = QHBoxLayout()
        btn_import = QPushButton("Importer")
        btn_cancel = QPushButton("Annuler")
        btn_import.clicked.connect(self._do_import)
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_import)
        btns.addWidget(btn_cancel)
        layout.addRow(btns)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir le JSON Blender", "", "JSON (*.json)")
        if path:
            self._path_edit.setText(path)

    def _do_import(self):
        path = self._path_edit.text().strip()
        name = self._name_edit.text().strip()
        fps  = self._fps_spin.value()

        if not path or not os.path.exists(path):
            self._info.setText("⚠ Fichier introuvable.")
            return
        if not name:
            self._info.setText("⚠ Nom requis.")
            return

        ok = self._cs.import_blender(name, path, fps)
        if ok:
            kf_count = len(self._cs._trajectories[name].keyframes)
            self._info.setText(f"✔ '{name}' importé — {kf_count} keyframes")
            if self._on_import:
                self._on_import(name, self._cs._trajectories[name])
            self.accept()
        else:
            self._info.setText("✖ Erreur d'import — voir la console.")
