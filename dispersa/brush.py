# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The brush: drag over faces or the terrain and copies appear under it;
hold Shift and they go away. Each stroke is kept in the scatter (see
``motor.all_points``) and is one undo step."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QApplication

from tools.base import Tool

from . import motor
from .texts import tr


def ray_tris(o, d, tris):
    """Distance along the ray (o, d) to the nearest of ``tris``, or None
    (Möller–Trumbore, both sides)."""
    best = None
    ox, oy, oz = o
    dx, dy, dz = d
    for t in tris:
        ax, ay, az = t[0], t[1], t[2]
        e1 = (t[3] - ax, t[4] - ay, t[5] - az)
        e2 = (t[6] - ax, t[7] - ay, t[8] - az)
        px = dy * e2[2] - dz * e2[1]
        py = dz * e2[0] - dx * e2[2]
        pz = dx * e2[1] - dy * e2[0]
        det = e1[0] * px + e1[1] * py + e1[2] * pz
        if abs(det) < 1e-12:
            continue
        inv = 1.0 / det
        sx, sy, sz = ox - ax, oy - ay, oz - az
        u = (sx * px + sy * py + sz * pz) * inv
        if u < -1e-9 or u > 1 + 1e-9:
            continue
        qx = sy * e1[2] - sz * e1[1]
        qy = sz * e1[0] - sx * e1[2]
        qz = sx * e1[1] - sy * e1[0]
        v = (dx * qx + dy * qy + dz * qz) * inv
        if v < -1e-9 or u + v > 1 + 1e-9:
            continue
        dist = (e2[0] * qx + e2[1] * qy + e2[2] * qz) * inv
        if dist > 1e-6 and (best is None or dist < best):
            best = dist
    return best


def ray_terrain(terrain, o, d, far=20000.0):
    """Where the ray (o, d) first meets the terrain, or None: walked in
    steps that grow with the distance, then bisected."""
    def above(t):
        x, y, z = o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t
        h = terrain.height_at(x, y)
        return None if h is None else z - h

    t, prev = 0.0, None
    while t < far:
        a = above(t)
        if a is not None:
            if prev is not None and prev[1] > 0 >= a:
                lo, hi = prev[0], t
                for _ in range(30):
                    mid = (lo + hi) / 2
                    m = above(mid)
                    if m is None or m > 0:
                        lo = mid
                    else:
                        hi = mid
                return hi
            prev = (t, a)
        t += max(0.25, t * 0.004)
    return None


def face_tris(face, matrix=None):
    out = []
    for a, b, c in face.triangulate():
        if matrix is not None:
            a, b, c = matrix.map(a), matrix.map(b), matrix.map(c)
        out.append([a.x(), a.y(), a.z(), b.x(), b.y(), b.z(), c.x(), c.y(), c.z()])
    return out


class BrushTool(Tool):
    name = "Dispersa brush"
    description = ("Drag over faces or the terrain to add copies; hold Shift "
                   "to take them away.")
    uses_snap = False

    def __init__(self, panel) -> None:
        self.panel = panel
        self.cursor = None          # (x, y, z) under the pointer
        self.path = None            # the stroke being drawn
        self.erase = False
        self._faces = {}            # id(face) → its world triangles
        self._known = []            # surfaces met before (behind copies)

    # ---- the tool --------------------------------------------------------------

    def on_activate(self, viewport) -> None:
        self.cursor = None
        self.path = None
        self.panel.brush_on(True)
        flash = getattr(viewport, "flash_status", None)
        if callable(flash):
            flash(tr("Drag to paint copies, Shift+drag to take them away. "
                     "[ and ] change the size; Esc stops."), 6000)

    def on_deactivate(self, viewport) -> None:
        self.path = None
        self.cursor = None
        self.panel.brush_on(False)
        viewport.update()

    def on_click(self, ctx) -> None:
        vp = ctx.viewport
        self.erase = bool(ctx.modifiers & Qt.ShiftModifier)
        self._faces = {}
        self._known = self.panel.brush_surfaces()
        hit = self.hit(vp, ctx.screen.x(), ctx.screen.y())
        self.cursor = hit
        self.path = [hit] if hit is not None else None
        vp.update()

    def on_hover(self, ctx) -> None:
        vp = ctx.viewport
        hit = self.hit(vp, ctx.screen.x(), ctx.screen.y())
        self.cursor = hit
        if self.path is not None and hit is not None:
            last = self.path[-1]
            step = max(0.05, self.radius() / 4)
            if (last[0] - hit[0]) ** 2 + (last[1] - hit[1]) ** 2 >= step * step:
                self.path.append(hit)
        vp.update()

    def on_release(self, viewport) -> None:
        path, self.path = self.path, None
        viewport.update()
        if not path:
            return
        r = self.radius()
        stroke = {"path": [[round(v, 3) for v in q] for q in path],
                  "r": round(r, 3), "erase": self.erase}
        if not self.erase:
            terrain = self.panel.terrain.isChecked()
            stroke["terrain"] = terrain
            if not terrain:
                tris = [t for ts in self._faces.values() for t in ts]
                stroke["tris"] = motor.stroke_surface(
                    tris, stroke["path"], r, self.panel.max_slope.value())
                if not stroke["tris"]:
                    return
        self._faces = {}
        self.panel.paint(stroke)

    def on_cancel(self, viewport) -> None:
        if self.path is not None:
            self.path = None
            viewport.update()
        else:
            self.panel.stop_brush()

    def on_key(self, viewport, key, modifiers) -> bool:
        if key in (Qt.Key_BracketLeft, Qt.Key_BracketRight):
            spin = self.panel.brush
            f = 1 / 1.25 if key == Qt.Key_BracketLeft else 1.25
            spin.setValue(spin.value() * f)
            viewport.update()
            return True
        return False

    def radius(self) -> float:
        return float(self.panel.brush.value())

    # ---- what is under the pointer --------------------------------------------

    def hit(self, vp, sx, sy):
        try:
            o, d = vp._pixel_to_ray(sx, sy)
        except Exception:                # noqa: BLE001
            return None
        if o is None or d is None:
            return None
        o, d = (o.x(), o.y(), o.z()), (d.x(), d.y(), d.z())
        if self.panel.terrain.isChecked():
            terrain = getattr(self.panel.app.scene, "terrain", None)
            if terrain is None:
                return None
            t = ray_terrain(terrain, o, d)
        else:
            t = None
            face, owner = vp.pick_face_any(sx, sy)
            if face is not None and not motor.is_scatter(owner):
                _f, place = vp.pick_face_placement(sx, sy)
                tris = face_tris(face, getattr(place, "xform", None))
                t = ray_tris(o, d, tris)
                if t is not None and self.path is not None:
                    self._faces[id(face), id(place)] = tris
            if t is None:
                # Behind a copy: the surfaces this scatter was made on.
                known = self._known + [x for ts in self._faces.values() for x in ts]
                t = ray_tris(o, d, known)
        if t is None:
            return None
        return (o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t)

    # ---- drawing ---------------------------------------------------------------

    def draw(self, app, painter) -> None:
        if self.cursor is None and not self.path:
            return
        import numpy as np
        erase = self.erase if self.path is not None else bool(
            QApplication.keyboardModifiers() & Qt.ShiftModifier)
        colour = QColor(220, 60, 50) if erase else QColor(40, 160, 70)
        r = self.radius()
        if self.path and len(self.path) > 1:
            fill = QColor(colour)
            fill.setAlpha(70)
            pen = QPen(fill, 1)
            pts = np.array(self.path, dtype=float)
            px, py, ok = app.world_to_pixels(pts)
            # The band's width in pixels, measured at the stroke's start.
            ring = np.array([self.path[0], [self.path[0][0] + r, self.path[0][1],
                                            self.path[0][2]]], dtype=float)
            rx, ry, _ok = app.world_to_pixels(ring)
            width = max(2.0, 2 * math.hypot(rx[1] - rx[0], ry[1] - ry[0]))
            pen.setWidthF(width)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            for i in range(len(px) - 1):
                if ok[i] and ok[i + 1]:
                    painter.drawLine(QPointF(px[i], py[i]), QPointF(px[i + 1], py[i + 1]))
        if self.cursor is not None:
            cx, cy, cz = self.cursor
            ring = np.array([[cx + r * math.cos(a), cy + r * math.sin(a), cz]
                             for a in np.linspace(0, 2 * math.pi, 49)])
            px, py, ok = app.world_to_pixels(ring)
            painter.setPen(QPen(colour, 2))
            for i in range(len(px) - 1):
                if ok[i] and ok[i + 1]:
                    painter.drawLine(QPointF(px[i], py[i]), QPointF(px[i + 1], py[i + 1]))
