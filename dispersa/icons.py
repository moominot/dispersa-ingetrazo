# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The tab's icons, drawn with QPainter the way IngeTrazo draws its own
(views/icons.py): plain pictures, ink from the palette, no files. Where
IngeTrazo already has the picture (eraser, rotate, scale) it is used."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication

_PX = 48


def _ink() -> QColor:
    app = QApplication.instance()
    if app is not None:
        return QColor(app.palette().windowText().color())
    return QColor(40, 44, 52)


def _accent() -> QColor:
    app = QApplication.instance()
    if app is not None:
        return QColor(app.palette().highlight().color())
    return QColor(60, 130, 220)


def _canvas():
    pm = QPixmap(_PX, _PX)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(_ink(), 3.0)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    return pm, p


def _dots(p):
    p.setBrush(_ink())
    for x, y, r in [(13, 14, 3.4), (30, 11, 2.6), (22, 24, 3.8), (37, 25, 3.0),
                    (12, 34, 2.8), (28, 37, 3.4), (40, 39, 2.4)]:
        p.drawEllipse(QPointF(x, y), r, r)


def _brush(p):
    p.save()
    p.translate(24, 24)
    p.rotate(40)
    p.drawRoundedRect(QRectF(-3.5, -20, 7, 18), 3, 3)        # handle
    p.drawLine(QPointF(-5, -1), QPointF(5, -1))                # ferrule
    path = QPainterPath(QPointF(-5, 0))
    path.lineTo(5, 0)
    path.quadTo(6, 10, 0, 16)
    path.quadTo(-6, 10, -5, 0)
    p.setBrush(_accent())
    p.drawPath(path)
    p.restore()


def _tree(p):
    p.drawLine(QPointF(24, 30), QPointF(24, 42))
    p.setBrush(_accent())
    p.drawEllipse(QPointF(24, 19), 12, 12)


def _sprout(p):
    p.drawLine(QPointF(24, 42), QPointF(24, 22))
    left = QPainterPath(QPointF(24, 26))
    left.quadTo(10, 26, 9, 12)
    left.quadTo(22, 12, 24, 26)
    right = QPainterPath(QPointF(24, 22))
    right.quadTo(26, 8, 39, 8)
    right.quadTo(39, 22, 24, 22)
    p.setBrush(_accent())
    p.drawPath(left)
    p.drawPath(right)


def _mountain(p):
    path = QPainterPath(QPointF(5, 40))
    path.lineTo(18, 16)
    path.lineTo(26, 28)
    path.lineTo(32, 20)
    path.lineTo(43, 40)
    path.closeSubpath()
    p.drawPath(path)


def _spacing(p):
    p.setBrush(_ink())
    p.drawEllipse(QPointF(9, 18), 4, 4)
    p.drawEllipse(QPointF(39, 18), 4, 4)
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(9, 33), QPointF(39, 33))
    for x, s in ((9, 1), (39, -1)):
        p.drawLine(QPointF(x, 33), QPointF(x + 5 * s, 29))
        p.drawLine(QPointF(x, 33), QPointF(x + 5 * s, 37))


def _slope(p):
    p.drawLine(QPointF(6, 40), QPointF(42, 40))
    p.drawLine(QPointF(6, 40), QPointF(40, 14))
    p.drawArc(QRectF(-8, 26, 32, 28), 0, 37 * 16)


def _dice(p):
    p.drawRoundedRect(QRectF(8, 8, 32, 32), 6, 6)
    p.setBrush(_ink())
    for x, y in [(17, 17), (31, 17), (24, 24), (17, 31), (31, 31)]:
        p.drawEllipse(QPointF(x, y), 2.4, 2.4)


def _clear(p):
    p.drawEllipse(QPointF(24, 24), 15, 15)
    p.drawLine(QPointF(13.5, 34.5), QPointF(34.5, 13.5))


def _plus(p):
    p.drawLine(QPointF(24, 10), QPointF(24, 38))
    p.drawLine(QPointF(10, 24), QPointF(38, 24))


def _box(p):
    top = [QPointF(24, 8), QPointF(40, 16), QPointF(24, 24), QPointF(8, 16)]
    p.drawPolygon(top)
    p.drawLine(QPointF(8, 16), QPointF(8, 32))
    p.drawLine(QPointF(40, 16), QPointF(40, 32))
    p.drawLine(QPointF(24, 24), QPointF(24, 40))
    p.drawLine(QPointF(8, 32), QPointF(24, 40))
    p.drawLine(QPointF(40, 32), QPointF(24, 40))


def _shuffle(p):
    p.drawLine(QPointF(6, 14), QPointF(16, 14))
    p.drawLine(QPointF(16, 14), QPointF(32, 34))
    p.drawLine(QPointF(32, 34), QPointF(40, 34))
    p.drawLine(QPointF(6, 34), QPointF(16, 34))
    p.drawLine(QPointF(16, 34), QPointF(32, 14))
    p.drawLine(QPointF(32, 14), QPointF(40, 14))
    for y in (14, 34):
        p.drawLine(QPointF(40, y), QPointF(35, y - 5))
        p.drawLine(QPointF(40, y), QPointF(35, y + 5))


def _count(p):
    for i in range(3):
        for j in range(3):
            p.drawPoint(QPointF(12 + i * 12, 12 + j * 12))
    p.setBrush(_ink())
    for i in range(3):
        for j in range(3):
            p.drawEllipse(QPointF(12 + i * 12, 12 + j * 12), 2.6, 2.6)


def _size(p):
    p.drawRect(QRectF(8, 26, 14, 14))
    p.drawLine(QPointF(22, 26), QPointF(40, 8))
    p.drawLine(QPointF(40, 8), QPointF(30, 8))
    p.drawLine(QPointF(40, 8), QPointF(40, 18))


def _turn(p):
    p.drawArc(QRectF(10, 10, 28, 28), 60 * 16, 280 * 16)
    a = math.radians(60)
    x, y = 24 + 14 * math.cos(a), 24 - 14 * math.sin(a)
    p.drawLine(QPointF(x, y), QPointF(x - 7, y - 2))
    p.drawLine(QPointF(x, y), QPointF(x + 1, y + 7))


_DRAW = {
    "scatter": _dots, "brush": _brush, "tree": _tree, "objects": _sprout,
    "terrain": _mountain, "spacing": _spacing, "slope": _slope,
    "seed": _dice, "clear": _clear, "plus": _plus, "model": _box,
    "variation": _shuffle, "count": _count, "size": _size, "turn": _turn,
}
_FROM_CORE = {"erase": "eraser"}


def icon(key: str) -> QIcon:
    core = _FROM_CORE.get(key)
    if core is not None:
        try:
            from views.icons import tool_icon
            ic = tool_icon(core)
            if not ic.isNull():
                return ic
        except Exception:                # noqa: BLE001 (an older IngeTrazo)
            pass
    draw = _DRAW.get(key)
    if draw is None:
        return QIcon()
    pm, p = _canvas()
    draw(p)
    p.end()
    return QIcon(pm)
