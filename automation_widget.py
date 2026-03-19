"""
automation_widget.py  —  Phase 4.2 : Éditeur de courbes d'automation
=====================================================================
Widget PySide6 autonome intégré dans la GUI.
Affiche et édite les keyframes d'une AutomationCurve.
"""
from __future__ import annotations
import math

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSizePolicy, QMenu, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout,
)
from PySide6.QtCore  import Qt, Signal, QRect, QPoint, QPointF
from PySide6.QtGui   import (
    QPainter, QColor, QPen, QBrush, QFont,
    QLinearGradient, QPainterPath, QPolygon,
)

from param_system import AutomationCurve, Keyframe, ParamDef, INTERP_MODES


# ─── Palette (reprend les couleurs Neon Void) ────────────────────────────────
C_BG      = QColor("#060a0f")
C_BG2     = QColor("#0b1018")
C_BG3     = QColor("#101620")
C_GRID    = QColor("#1c2a3a")
C_CYAN    = QColor("#00f5ff")
C_ORANGE  = QColor("#ff4500")
C_GREEN   = QColor("#00ff88")
C_GOLD    = QColor("#ffcb47")
C_PURPLE  = QColor("#bf5fff")
C_TXT     = QColor("#7a9ab5")
C_TXTHI   = QColor("#cce8ff")
C_TXTDIM  = QColor("#2e4560")
C_SEL     = QColor("#1a3a5c")


class AutomationEditor(QWidget):
    """
    Éditeur de courbe bézier/interpolée pour un seul AutomationCurve.

    Interactions :
        Clic gauche vide    → ajouter un keyframe
        Clic gauche KF      → sélectionner / déplacer (drag)
        Double-clic KF      → éditer la valeur précisément
        Clic droit KF       → menu (supprimer, changer interpolation)
        Ctrl+A              → sélectionner tous les KF
        Delete              → supprimer les KF sélectionnés
    """

    changed    = Signal()   # émis après toute modification
    kf_selected = Signal(object)  # keyframe sélectionné (ou None)

    KF_RADIUS  = 6
    MARGIN_L   = 42
    MARGIN_R   = 12
    MARGIN_T   = 10
    MARGIN_B   = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.curve:    AutomationCurve | None = None
        self.t_start:  float = 0.0
        self.t_end:    float = 30.0
        self._sel:     set   = set()      # indices KF sélectionnés
        self._drag_i:  int   = -1
        self._drag_ox: float = 0.0
        self._drag_oy: float = 0.0
        self._hover_i: int   = -1
        self._playhead:float = 0.0
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    # ── API publique ─────────────────────────────────────────────────────────

    def set_curve(self, curve: AutomationCurve,
                  t_start: float = 0.0, t_end: float = 30.0) -> None:
        self.curve   = curve
        self.t_start = t_start
        self.t_end   = max(t_end, t_start + 0.1)
        self._sel.clear()
        self.update()

    def set_playhead(self, t: float) -> None:
        self._playhead = t
        self.update()

    # ── Coordonnées ──────────────────────────────────────────────────────────

    def _plot_rect(self) -> QRect:
        return QRect(
            self.MARGIN_L, self.MARGIN_T,
            self.width()  - self.MARGIN_L - self.MARGIN_R,
            self.height() - self.MARGIN_T - self.MARGIN_B,
        )

    def _t_to_x(self, t: float) -> float:
        r = self._plot_rect()
        return r.left() + (t - self.t_start) / (self.t_end - self.t_start) * r.width()

    def _v_to_y(self, v: float) -> float:
        r = self._plot_rect()
        if self.curve and self.curve.param.min_val is not None:
            mn = self.curve.param.min_val
            mx = self.curve.param.max_val
            if isinstance(mn, tuple): mn = mn[0]; mx = mx[0]
        else:
            mn, mx = 0.0, 1.0
        span = mx - mn or 1.0
        return r.bottom() - (v - mn) / span * r.height()

    def _x_to_t(self, x: float) -> float:
        r = self._plot_rect()
        return self.t_start + (x - r.left()) / max(r.width(), 1) * (self.t_end - self.t_start)

    def _y_to_v(self, y: float) -> float:
        r = self._plot_rect()
        if self.curve and self.curve.param.min_val is not None:
            mn = self.curve.param.min_val
            mx = self.curve.param.max_val
            if isinstance(mn, tuple): mn = mn[0]; mx = mx[0]
        else:
            mn, mx = 0.0, 1.0
        span = mx - mn or 1.0
        return mn + (r.bottom() - y) / max(r.height(), 1) * span

    def _kf_at(self, x: float, y: float) -> int:
        if not self.curve: return -1
        for i, kf in enumerate(self.curve.keyframes):
            kx = self._t_to_x(kf.t)
            v  = kf.value if not isinstance(kf.value, tuple) else kf.value[0]
            ky = self._v_to_y(v)
            if math.hypot(x - kx, y - ky) <= self.KF_RADIUS + 3:
                return i
        return -1

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r    = self._plot_rect()

        # Fond
        p.fillRect(0, 0, w, h, C_BG2)
        p.fillRect(r, C_BG)

        if not self.curve:
            p.setPen(C_TXT)
            p.setFont(QFont("Courier New", 9))
            p.drawText(r, Qt.AlignCenter, "Aucun paramètre sélectionné")
            p.end(); return

        param = self.curve.param
        mn = param.min_val if param.min_val is not None else 0.0
        mx = param.max_val if param.max_val is not None else 1.0
        if isinstance(mn, tuple): mn = mn[0]
        if isinstance(mx, tuple): mx = mx[0]

        # ── Grille ────────────────────────────────────────────────────────────
        p.setPen(QPen(C_GRID, 1))
        for i in range(5):
            gy = r.top() + i * r.height() // 4
            p.drawLine(r.left(), gy, r.right(), gy)
        # Lignes verticales (temps)
        dur = self.t_end - self.t_start
        step = max(1, int(dur / 10))
        t = self.t_start
        while t <= self.t_end + step:
            x = int(self._t_to_x(t))
            p.drawLine(x, r.top(), x, r.bottom())
            t += step

        # ── Labels axe Y ─────────────────────────────────────────────────────
        p.setFont(QFont("Courier New", 7))
        p.setPen(C_TXTDIM)
        span = mx - mn or 1.0
        for i in range(5):
            v  = mn + (4 - i) / 4 * span
            gy = r.top() + i * r.height() // 4
            p.drawText(2, gy - 5, self.MARGIN_L - 4, 14,
                       Qt.AlignRight | Qt.AlignVCenter, f"{v:.2f}")

        # ── Labels axe X ─────────────────────────────────────────────────────
        t = self.t_start
        while t <= self.t_end + step:
            x = int(self._t_to_x(t))
            p.drawText(x - 12, r.bottom() + 4, 24, 16,
                       Qt.AlignCenter, f"{t:.0f}s")
            t += step

        # ── Courbe interpolée ─────────────────────────────────────────────────
        kfs = self.curve.keyframes
        if kfs:
            path = QPainterPath()
            steps = max(200, r.width())
            first = True
            for i in range(steps + 1):
                t_i = self.t_start + i / steps * dur
                v   = self.curve.evaluate(t_i)
                if isinstance(v, tuple): v = v[0]
                x = self._t_to_x(t_i)
                y = self._v_to_y(v)
                if first:
                    path.moveTo(x, y); first = False
                else:
                    path.lineTo(x, y)

            cc = QColor(C_CYAN); cc.setAlpha(180)
            p.setPen(QPen(cc, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

            # Zone sous la courbe
            if kfs:
                fill = QPainterPath(path)
                fill.lineTo(self._t_to_x(min(kfs[-1].t, self.t_end)), r.bottom())
                fill.lineTo(self._t_to_x(max(kfs[0].t,  self.t_start)), r.bottom())
                fill.closeSubpath()
                fc = QColor(C_CYAN); fc.setAlpha(18)
                p.fillPath(fill, fc)

        # ── Keyframes ─────────────────────────────────────────────────────────
        for i, kf in enumerate(kfs):
            v  = kf.value if not isinstance(kf.value, tuple) else kf.value[0]
            kx = int(self._t_to_x(kf.t))
            ky = int(self._v_to_y(v))
            sel = i in self._sel
            hov = i == self._hover_i

            # Glow
            if sel or hov:
                gc = QColor(C_ORANGE if sel else C_CYAN)
                gc.setAlpha(40)
                p.setBrush(gc); p.setPen(Qt.NoPen)
                p.drawEllipse(QPoint(kx, ky), self.KF_RADIUS + 4, self.KF_RADIUS + 4)

            # Point
            col = C_ORANGE if sel else C_CYAN
            p.setBrush(QBrush(col))
            p.setPen(QPen(C_TXTHI, 1))
            p.drawEllipse(QPoint(kx, ky), self.KF_RADIUS, self.KF_RADIUS)

            # Icône interpolation
            ic = {"linear":"─","smooth":"~","step":"⌐",
                  "bounce":"↗","elastic":"≋","ease_in_out":"⌒"}.get(kf.interp,"")
            if ic:
                p.setFont(QFont("Courier New", 7))
                p.setPen(C_TXTDIM)
                p.drawText(kx + self.KF_RADIUS + 2, ky - 4, ic)

        # ── Playhead ──────────────────────────────────────────────────────────
        if hasattr(self, '_playhead'):
            phx = int(self._t_to_x(self._playhead))
            if r.left() <= phx <= r.right():
                p.setPen(QPen(C_ORANGE, 1))
                p.drawLine(phx, r.top(), phx, r.bottom())

        # Bordure
        bc = QColor(C_GRID); bc.setAlpha(200)
        p.setPen(QPen(bc, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        p.end()

    # ── Souris ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if not self.curve: return
        x, y = e.position().x(), e.position().y()
        i    = self._kf_at(x, y)

        if e.button() == Qt.LeftButton:
            if i >= 0:
                if not (e.modifiers() & Qt.ShiftModifier):
                    self._sel.clear()
                self._sel.add(i)
                self._drag_i  = i
                kf = self.curve.keyframes[i]
                v = kf.value if not isinstance(kf.value, tuple) else kf.value[0]
                self._drag_ox = x - self._t_to_x(kf.t)
                self._drag_oy = y - self._v_to_y(v)
                self.kf_selected.emit(kf)
            else:
                # Ajouter un keyframe
                self._sel.clear()
                t = max(self.t_start, min(self.t_end, self._x_to_t(x)))
                v = self.curve.param.clamp(self._y_to_v(y))
                if isinstance(self.curve.param.default, tuple):
                    v = tuple(v for _ in self.curve.param.default)
                self.curve.add_keyframe(t, v)
                self._sel.add(len(self.curve.keyframes) - 1)
                self.changed.emit()
            self.update()

        elif e.button() == Qt.RightButton and i >= 0:
            self._show_kf_menu(i, e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if not self.curve: return
        x, y = e.position().x(), e.position().y()
        if self._drag_i >= 0 and e.buttons() & Qt.LeftButton:
            kf  = self.curve.keyframes[self._drag_i]
            new_t = max(self.t_start,
                        min(self.t_end, self._x_to_t(x - self._drag_ox)))
            new_v = self.curve.param.clamp(self._y_to_v(y - self._drag_oy))
            if isinstance(kf.value, tuple):
                new_v = tuple(new_v for _ in kf.value)
            kf.t     = round(new_t, 3)
            kf.value = new_v
            self.curve.keyframes.sort(key=lambda k: k.t)
            self._drag_i = next(
                (j for j, k in enumerate(self.curve.keyframes) if k is kf), -1)
            self.changed.emit()
            self.update()
        else:
            new_h = self._kf_at(x, y)
            if new_h != self._hover_i:
                self._hover_i = new_h
                self.update()
            self.setCursor(Qt.SizeAllCursor if new_h >= 0 else Qt.CrossCursor)

    def mouseReleaseEvent(self, e):
        self._drag_i = -1

    def mouseDoubleClickEvent(self, e):
        if not self.curve: return
        x, y = e.position().x(), e.position().y()
        i = self._kf_at(x, y)
        if i >= 0:
            self._edit_kf_value(i)

    def keyPressEvent(self, e):
        if not self.curve: return
        if e.key() == Qt.Key_Delete and self._sel:
            for i in sorted(self._sel, reverse=True):
                if 0 <= i < len(self.curve.keyframes):
                    self.curve.keyframes.pop(i)
            self._sel.clear()
            self.changed.emit(); self.update()
        elif e.key() == Qt.Key_A and e.modifiers() & Qt.ControlModifier:
            self._sel = set(range(len(self.curve.keyframes)))
            self.update()

    # ── Menu contextuel ───────────────────────────────────────────────────────

    def _show_kf_menu(self, i: int, pos: QPoint):
        kf   = self.curve.keyframes[i]
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:#0b1018;color:#7a9ab5;"
            f"border:1px solid #1c2a3a;font:8pt 'Courier New';padding:4px 0;}}"
            f"QMenu::item{{padding:4px 18px 4px 10px;}}"
            f"QMenu::item:selected{{background:#1a3a5c;color:#00f5ff;}}")
        menu.addAction("✎ Éditer valeur", lambda: self._edit_kf_value(i))
        menu.addSeparator()
        interp_menu = menu.addMenu("Interpolation →")
        for mode in INTERP_MODES:
            act = interp_menu.addAction(
                f"{'✓ ' if kf.interp == mode else '  '}{mode}",
                lambda m=mode: self._set_interp(i, m))
        menu.addSeparator()
        menu.addAction("🗑 Supprimer", lambda: self._delete_kf(i))
        menu.exec(pos)

    def _set_interp(self, i: int, mode: str):
        if self.curve and 0 <= i < len(self.curve.keyframes):
            self.curve.keyframes[i].interp = mode
            self.changed.emit(); self.update()

    def _delete_kf(self, i: int):
        if self.curve and 0 <= i < len(self.curve.keyframes):
            self.curve.keyframes.pop(i)
            self._sel.discard(i)
            self.changed.emit(); self.update()

    def _edit_kf_value(self, i: int):
        if not self.curve or i >= len(self.curve.keyframes):
            return
        kf    = self.curve.keyframes[i]
        param = self.curve.param
        dlg   = QDialog(self)
        dlg.setWindowTitle(f"Éditer  {param.name}  @ t={kf.t:.3f}s")
        dlg.setStyleSheet(
            "QDialog{background:#0b1018;} QLabel{color:#7a9ab5;font:8pt 'Courier New';}"
            "QDoubleSpinBox{background:#101620;color:#cce8ff;border:1px solid #243347;"
            "padding:3px;font:9pt 'Courier New';}")
        lay  = QFormLayout(dlg)
        spins = []
        val  = kf.value if isinstance(kf.value, tuple) else (kf.value,)
        for ci, v in enumerate(val):
            sb = QDoubleSpinBox()
            mn = param.min_val; mx = param.max_val
            if isinstance(mn, tuple): mn = mn[ci]; mx = mx[ci]
            sb.setRange(mn or -1e6, mx or 1e6)
            sb.setDecimals(4); sb.setSingleStep(0.01)
            sb.setValue(float(v))
            lay.addRow(f"  {['X','Y','Z','W'][ci] if len(val)>1 else 'Value'}", sb)
            spins.append(sb)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay.addRow(bb)
        if dlg.exec():
            new_val = tuple(s.value() for s in spins)
            kf.value = new_val[0] if len(new_val) == 1 else new_val
            self.changed.emit(); self.update()
