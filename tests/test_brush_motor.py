"""Brush strokes and zones kept clear, in the engine (offscreen). Needs an
IngeTrazo checkout and its Python environment:

    INGETRAZO_SRC=~/src/ingetrazo QT_QPA_PLATFORM=offscreen \\
        <ingetrazo venv>/bin/python -m pytest tests
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_SRC = os.environ.get("INGETRAZO_SRC")
if not _SRC or not (Path(_SRC) / "core" / "group.py").is_file():
    pytest.skip("set INGETRAZO_SRC to an IngeTrazo checkout", allow_module_level=True)
sys.path.insert(0, _SRC)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QVector3D  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dispersa import motor  # noqa: E402

_app = QApplication.instance() or QApplication([])

TREE = {"kind": "bundled", "key": "arbol", "name": "Tree", "weight": 1}
BIRCH = {"kind": "bundled", "key": "abedul", "name": "Birch", "weight": 1}


@pytest.fixture
def scene():
    from core.scene import Scene
    return Scene()


def _ground(scene, size=40.0):
    f = scene.mesh.add_face([QVector3D(x, y, 0) for x, y in
                             [(0, 0), (size, 0), (size, size), (0, size)]])
    return motor.surface_from_selection([f])


def _stroke(tris, path, r=3.0, density=30.0, sources=(BIRCH,), **kw):
    st = {"path": path, "r": r, "erase": False, "terrain": False,
          "tris": motor.stroke_surface(tris, path, r), "sources": list(sources),
          "density": density, "scale": [100.0, 100.0], "rotation": 0.0,
          "align": False}
    st.update(kw)
    return st


def _where(box):
    return [(k.xform.map(QVector3D(0, 0, 0)), k.ext["dispersa"]["src"])
            for k in box.children]


def _poses(box):
    return [tuple(round(v, 6) for v in k.xform.data()) for k in box.children]


def test_a_stroke_paints_only_under_its_band(scene):
    tris = _ground(scene)
    path = [[5, 20, 0], [35, 20, 0]]
    box, placed, _w = motor.scatter(scene, {**motor.DEFAULTS, "sources": [TREE],
                                            "min_distance": 0.5},
                                    tris=[], strokes=[_stroke(tris, path)])
    assert placed > 20
    objects = box.ext["dispersa"]["objects"]
    anc = motor.anchor(motor.bundled_prototype("abedul"))
    for k in box.children:
        assert objects[k.ext["dispersa"]["src"]]["key"] == "abedul"
        e = box.ext["dispersa"]["strokes"][0]
        # Its anchor sits on the ground inside the band (plan distance ≤ r).
        bottom = k.xform.map(QVector3D(*anc))
        assert motor.near_path(e["path"], 3.0 + 1e-6, bottom.x(), bottom.y())
        assert abs(bottom.z()) < 1e-6


def test_a_later_stroke_leaves_the_earlier_copies_as_they_were(scene):
    tris = _ground(scene)
    p = {**motor.DEFAULTS, "sources": [TREE], "count": 30, "min_distance": 1.0}
    a, _, _ = motor.scatter(scene, p, tris=tris)
    first = _poses(a)
    st = _stroke(tris, [[2, 2, 0], [38, 38, 0]])
    b, _, _ = motor.scatter(scene, p, old=a, strokes=[st])
    assert _poses(b)[:len(first)] == first
    assert len(b.children) > len(first)


def test_shift_stroke_takes_copies_away_and_keeps_the_rest(scene):
    tris = _ground(scene)
    p = {**motor.DEFAULTS, "sources": [TREE], "count": 120, "min_distance": 1.0}
    a, _, _ = motor.scatter(scene, p, tris=tris)
    path = [[0, 20, 0], [40, 20, 0]]
    rub = {"path": path, "r": 4.0, "erase": True}
    b, _, _ = motor.scatter(scene, p, old=a, strokes=[rub])
    kept = set(_poses(b))
    gone = [k for k in a.children if tuple(round(v, 6) for v in k.xform.data()) not in kept]
    assert gone and len(b.children) == len(a.children) - len(gone)
    anc = motor.anchor(motor.bundled_prototype("arbol"))
    for k in b.children:
        o = k.xform.map(QVector3D(*anc))
        assert not motor.near_path(path, 4.0 - 1e-6, o.x(), o.y())
    assert kept <= set(_poses(a))


def test_painting_over_a_rubbed_out_band_fills_it_again(scene):
    tris = _ground(scene)
    p = {**motor.DEFAULTS, "sources": [TREE], "count": 0, "min_distance": 1.0}
    path = [[5, 20, 0], [35, 20, 0]]
    paint = _stroke(tris, path)
    rub = {"path": path, "r": 3.0, "erase": True}
    box, n1, _ = motor.scatter(scene, p, tris=[], strokes=[paint])
    _b, n2, _ = motor.scatter(scene, p, tris=[], strokes=[paint, rub])
    _c, n3, _ = motor.scatter(scene, p, tris=[], strokes=[paint, rub, paint])
    assert n1 > 0 and n2 == 0 and n3 > 0


def test_zone_kept_clear_stays_empty_and_survives_scattering_again(scene):
    from core.group import Group
    from core.mesh import Mesh
    tris = _ground(scene)
    m = Mesh()                                   # a 10 × 10 house in the middle
    pts = [(15, 15, 0), (25, 15, 0), (25, 25, 0), (15, 25, 0)]
    m.add_face([QVector3D(*q) for q in pts])
    m.add_face([QVector3D(*q) for q in [(15, 15, 0), (15, 15, 3), (25, 15, 3), (25, 15, 0)]])
    house = Group(m)
    zone = motor.footprint([house])
    assert sum(abs((t[2] - t[0]) * (t[5] - t[1]) - (t[3] - t[1]) * (t[4] - t[0])) / 2
               for t in zone) == pytest.approx(100.0)
    p = {**motor.DEFAULTS, "sources": [TREE], "mode": "density", "density": 20.0,
         "min_distance": 0.0}
    box, _, _ = motor.scatter(scene, p, tris=tris, clear=[zone])
    anc = motor.anchor(motor.bundled_prototype("arbol"))

    def inside(b):
        out = 0
        for k in b.children:
            o = k.xform.map(QVector3D(*anc))
            out += 15 < o.x() < 25 and 15 < o.y() < 25
        return out

    assert len(box.children) > 100 and inside(box) == 0
    again, _, _ = motor.scatter(scene, {**p, "seed": 5}, old=box)
    assert again.ext["dispersa"]["clear"] == box.ext["dispersa"]["clear"]
    assert inside(again) == 0 and len(again.children) > 100


def test_a_stroke_on_the_terrain_takes_its_height(scene):
    class Hill:
        def height_at(self, x, y):
            return 0.1 * x if 0 <= x <= 50 and 0 <= y <= 50 else None
    st = {"path": [[10, 10, 1], [30, 10, 3]], "r": 3.0, "erase": False,
          "terrain": True, "sources": [TREE], "density": 30.0,
          "scale": [100.0, 100.0], "rotation": 0.0, "align": False}
    p = {**motor.DEFAULTS, "sources": [TREE]}
    with pytest.raises(ValueError):
        motor.prepare(scene, p, tris=[], strokes=[st])
    box, placed, _ = motor.scatter(scene, p, tris=[], strokes=[st], terrain=Hill())
    assert placed > 5
    anc = motor.anchor(motor.bundled_prototype("arbol"))
    for k in box.children:
        o = k.xform.map(QVector3D(*anc))
        assert o.z() == pytest.approx(0.1 * o.x(), abs=1e-4)


def test_strokes_and_zones_go_through_the_file(scene, tmp_path):
    from core.scene import Scene
    from formats import igz
    tris = _ground(scene)
    st = _stroke(tris, [[5, 5, 0], [20, 30, 0]])
    zone = [[0, 0, 5, 0, 5, 5]]
    box, placed, _ = motor.scatter(scene, {**motor.DEFAULTS, "sources": [TREE]},
                                   tris=tris, strokes=[st], clear=[zone])
    path = tmp_path / "s.igz"
    igz.save_scene(scene, path)
    other = Scene()
    igz.load_into(other, path)
    back = next(g for g in other.groups if motor.is_scatter(g))
    e = back.ext["dispersa"]
    assert e["strokes"][0]["path"] == st["path"] and e["clear"] == [zone]
    again, n, _ = motor.scatter(other, dict(e), old=back)
    assert n == placed
