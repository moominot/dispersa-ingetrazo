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


def model_surface(scene):
    """Every face of the model a brush can land on, as an (N, 9) array of
    world triangles: the loose geometry and the groups, never a scatter
    (its copies must not catch the brush) nor what is hidden."""
    import numpy as np
    from core.group import iter_placements
    out = []
    for f in scene.mesh.faces:
        out.extend(face_tris(f))
    for g in scene.groups:
        if motor.is_scatter(g) or getattr(g, "hidden", False):
            continue
        for sub, m in iter_placements(g):
            for f in sub.mesh.faces:
                out.extend(face_tris(f, m))
    return np.asarray(out, dtype=float).reshape(-1, 9)


def surface_key(scene):
    """Changes when the model's geometry does (not when a scatter does)."""
    parts = [id(scene.mesh), len(scene.mesh.faces),
             getattr(scene.mesh, "_mut_serial", 0)]
    for g in scene.groups:
        if motor.is_scatter(g):
            continue
        parts += [id(g), id(g.mesh), getattr(g.mesh, "_mut_serial", 0),
                  bool(getattr(g, "hidden", False)),
                  tuple(round(v, 6) for v in g.xform.data())
                  if getattr(g, "xform", None) is not None else None]
    return tuple(parts)


def ray_array(o, d, T):
    """Nearest distance along the ray (o, d) to the triangles ``T`` (an
    (N, 9) array), or None. Möller–Trumbore for all of them at once."""
    import numpy as np
    if T is None or not len(T):
        return None
    o = np.asarray(o, float)
    d = np.asarray(d, float)
    a = T[:, 0:3]
    e1 = T[:, 3:6] - a
    e2 = T[:, 6:9] - a
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = o - a
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, e1)
    v = (q @ d) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    hit = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t > 1e-6)
    if not hit.any():
        return None
    return float(t[hit].min())


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
        self._surface = None        # the model's triangles, (N, 9)
        self._surface_key = None

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
                tris = self.surface(self.panel.app.scene)
                stroke["tris"] = motor.stroke_surface(
                    tris.tolist(), stroke["path"], r, self.panel.max_slope.value())
                if not stroke["tris"]:
                    self.panel.say(tr("Nothing to paint on there: the faces "
                                      "under the brush are too steep."))
                    return
        self.panel.paint(stroke)

    def surface(self, scene):
        key = surface_key(scene)
        if key != self._surface_key or self._surface is None:
            self._surface = model_surface(scene)
            self._surface_key = key
        return self._surface

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
            t = ray_array(o, d, self.surface(self.panel.app.scene))
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
