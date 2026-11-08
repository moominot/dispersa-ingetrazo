"""The extension inside a real IngeTrazo window (offscreen): its tab, the
objects, the selection, the button and the undo. Needs an IngeTrazo
checkout and its Python environment:

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

import dispersa  # noqa: E402
from dispersa import motor  # noqa: E402
from dispersa import panel as ds_panel  # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def window(monkeypatch):
    from core import extensions
    from core.paths import app_root
    from views.extension_api import ExtensionApp
    from views.main_window import MainWindow
    monkeypatch.setattr(extensions, "plugin_dirs", lambda: [app_root() / "plugins"])
    win = MainWindow()
    win.resize(1000, 700)
    win.show()
    _app.processEvents()
    app = ExtensionApp(win, "dispersa")
    dispersa.setup(app)
    yield win, app
    win._saved_version = win.viewport.scene.version
    win.close()


def _panel(win):
    return next(w for w in win.findChildren(ds_panel.ScatterPanel))


def _face(scene, size=25.0):
    return scene.mesh.add_face([QVector3D(x, y, 0) for x, y in
                                [(0, 0), (size, 0), (size, size), (0, size)]])


def test_the_tab_lists_ingetrazo_objects_and_waits_for_a_selection(window):
    win, _ = window
    p = _panel(win)
    names = [t.src["kind"] for t in p.tiles]
    assert names.count("bundled") >= 5
    p._refresh_selection(True)
    assert not p.go.isEnabled()


def test_scatter_from_the_panel_is_one_undo_step(window):
    win, _ = window
    scene = win.viewport.scene
    f = _face(scene)
    scene.selection.clear()
    scene.selection.add(f)
    p = _panel(win)
    p._refresh_selection(True)
    assert p.go.isEnabled() and "625" in p.where.text()
    p.check("bundled", "arbol")
    p.check("bundled", "chica", 2)
    p.amount.setValue(30)
    groups_before = list(scene.groups)
    p.run()
    box = next(g for g in scene.groups if motor.is_scatter(g))
    assert len(box.children) == 30
    assert scene.selection == {box}
    assert p._editing is box and "Editing" in p.editing.text()
    # The Browser knows what it is.
    win.viewport.history.undo()
    assert scene.groups == groups_before
    win.viewport.history.redo()
    assert box in scene.groups


def test_selecting_a_scatter_brings_its_numbers_and_scatters_again(window):
    win, _ = window
    scene = win.viewport.scene
    scene.selection.add(_face(scene))
    p = _panel(win)
    p._refresh_selection(True)
    p.check("bundled", "abedul")
    p.amount.setValue(12)
    p.seed.setValue(321)
    p.run()
    box = next(g for g in scene.groups if motor.is_scatter(g))
    # Another face selected: the panel leaves the scatter...
    other = scene.mesh.add_face([QVector3D(x, y, 0) for x, y in
                                 [(100, 0), (110, 0), (110, 10), (100, 10)]])
    scene.selection.clear()
    scene.selection.add(other)
    p._refresh_selection(True)
    assert p._editing is None
    p.seed.setValue(5)
    # ...and selecting the scatter brings back how it was made.
    scene.selection.clear()
    scene.selection.add(box)
    p._refresh_selection(True)
    assert p._editing is box and p.seed.value() == 321
    assert [s["key"] for s in p.sources()] == ["abedul"]
    p.amount.setValue(20)
    p.run()
    new = next(g for g in scene.groups if motor.is_scatter(g))
    assert new is not box and len(new.children) == 20
    assert sum(1 for g in scene.groups if motor.is_scatter(g)) == 1
    win.viewport.history.undo()
    assert box in scene.groups and new not in scene.groups


def test_no_object_chosen_says_so(window):
    win, _ = window
    scene = win.viewport.scene
    scene.selection.add(_face(scene))
    p = _panel(win)
    p._refresh_selection(True)
    n = len(scene.groups)
    p.run()
    assert len(scene.groups) == n and p.status.text()


def test_terrain_ticked_without_terrain_changes_nothing(window):
    win, _ = window
    scene = win.viewport.scene
    scene.selection.add(_face(scene))
    p = _panel(win)
    p._refresh_selection(True)
    p.check("bundled", "arbol")
    p.terrain.setChecked(True)
    n = len(scene.groups)
    p.run()
    assert len(scene.groups) == n and "Terrain" in p.status.text()


def test_the_counting_modes_keep_their_own_number(window):
    win, _ = window
    p = _panel(win)
    p.amount.setValue(80)
    p.mode.setCurrentIndex(p.mode.findData("density"))
    p.amount.setValue(2.5)
    p.mode.setCurrentIndex(p.mode.findData("count"))
    assert p.amount.value() == 80
    prm = p.params()
    assert prm["count"] == 80 and prm["density"] == 2.5


def test_it_waits_visibly_and_gives_the_cursor_back(window):
    import time
    win, _ = window
    scene = win.viewport.scene
    scene.selection.add(_face(scene))
    p = _panel(win)
    p._refresh_selection(True)
    p.check("bundled", "arbol")
    p.amount.setValue(5)
    p.run()
    assert QApplication.overrideCursor() is not None and not p.go.isEnabled()
    end = time.time() + 2
    while QApplication.overrideCursor() is not None and time.time() < end:
        _app.processEvents()
        time.sleep(0.02)
    assert QApplication.overrideCursor() is None and p.go.isEnabled()
    # An error gives it back too.
    p.terrain.setChecked(True)
    p.run()
    end = time.time() + 2
    while QApplication.overrideCursor() is not None and time.time() < end:
        _app.processEvents()
        time.sleep(0.02)
    assert QApplication.overrideCursor() is None and "Terrain" in p.status.text()


# ---- 0.2: the brush and the zones kept clear -----------------------------------

def _ctx(vp, px, py, shift=False):
    from types import SimpleNamespace
    from PySide6.QtCore import QPointF, Qt
    return SimpleNamespace(viewport=vp, screen=QPointF(px, py), world=None,
                           snap=None,
                           modifiers=Qt.ShiftModifier if shift else Qt.NoModifier)


def _pixel(app, x, y, z=0.0):
    import numpy as np
    px, py, ok = app.world_to_pixels(np.array([[x, y, z]], dtype=float))
    assert ok[0]
    return float(px[0]), float(py[0])


def _drag(tool, vp, app, pts, shift=False):
    tool.on_click(_ctx(vp, *_pixel(app, *pts[0]), shift=shift))
    for q in pts[1:]:
        tool.on_hover(_ctx(vp, *_pixel(app, *q), shift=shift))
    tool.on_release(vp)
    _app.processEvents()


def _brush_window(window):
    win, app = window
    scene = win.viewport.scene
    _face(scene, size=40.0)
    notify = getattr(win.viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()
    vp = win.viewport
    vp.camera.target = QVector3D(20, 20, 0)
    _app.processEvents()
    p = _panel(win)
    p.check("bundled", "abedul")
    p.brush.setValue(3.0)
    p.brush_density.setValue(40.0)
    p.paint_btn.setChecked(True)
    _app.processEvents()
    assert vp.active_tool is p._tool
    return win, app, scene, vp, p


def test_the_brush_hits_the_face_under_the_pointer(window):
    win, app, scene, vp, p = _brush_window(window)
    hit = p._tool.hit(vp, *_pixel(app, 12.0, 30.0))
    assert hit is not None
    assert hit[0] == pytest.approx(12.0, abs=0.05)
    assert hit[1] == pytest.approx(30.0, abs=0.05)
    assert hit[2] == pytest.approx(0.0, abs=1e-4)


def test_a_brush_stroke_makes_a_scatter_and_the_next_adds_to_it(window):
    win, app, scene, vp, p = _brush_window(window)
    before = len(scene.groups)
    _drag(p._tool, vp, app, [(8, 10, 0), (14, 10, 0), (20, 10, 0), (26, 10, 0)])
    boxes = [g for g in scene.groups if motor.is_scatter(g)]
    assert len(boxes) == 1 and len(scene.groups) == before + 1
    first = boxes[0]
    n1 = len(first.children)
    assert n1 > 3
    assert first.ext[motor.KEY]["surface"] == []
    assert p._editing is first and first not in scene.selection
    _drag(p._tool, vp, app, [(8, 30, 0), (20, 30, 0), (30, 30, 0)])
    boxes = [g for g in scene.groups if motor.is_scatter(g)]
    assert len(boxes) == 1
    second = boxes[0]
    assert len(second.ext[motor.KEY]["strokes"]) == 2
    assert len(second.children) > n1
    win.viewport.history.undo()            # one stroke, one undo step
    _app.processEvents()
    boxes = [g for g in scene.groups if motor.is_scatter(g)]
    assert len(boxes) == 1 and len(boxes[0].children) == n1


def test_shift_drag_takes_copies_away(window):
    win, app, scene, vp, p = _brush_window(window)
    _drag(p._tool, vp, app, [(8, 20, 0), (32, 20, 0)])
    n1 = len(next(g for g in scene.groups if motor.is_scatter(g)).children)
    _drag(p._tool, vp, app, [(20, 14, 0), (20, 26, 0)], shift=True)
    box = next(g for g in scene.groups if motor.is_scatter(g))
    assert 0 < len(box.children) < n1
    assert box.ext[motor.KEY]["strokes"][-1]["erase"] is True


def test_brush_size_keys_and_another_tool_unticks_paint(window):
    from PySide6.QtCore import Qt
    win, app, scene, vp, p = _brush_window(window)
    assert p._tool.on_key(vp, Qt.Key_BracketRight, Qt.NoModifier)
    assert p.brush.value() == pytest.approx(3.75)
    win._activate_tool("select")
    _app.processEvents()
    assert not p.paint_btn.isChecked()
    p.paint_btn.setChecked(True)
    p.paint_btn.setChecked(False)
    assert vp.active_tool is not p._tool


def test_the_overlay_draws_the_brush_without_errors(window):
    from PySide6.QtGui import QImage, QPainter
    win, app, scene, vp, p = _brush_window(window)
    p._tool.on_hover(_ctx(vp, *_pixel(app, 20, 20)))
    p._tool.on_click(_ctx(vp, *_pixel(app, 10, 20)))
    p._tool.on_hover(_ctx(vp, *_pixel(app, 25, 20)))
    img = QImage(vp.width(), vp.height(), QImage.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    p.draw_brush(vp, painter)
    painter.end()
    p._tool.on_cancel(vp)                 # first Esc drops the stroke
    assert p._tool.path is None and vp.active_tool is p._tool
    assert any(img.pixel(x, y) for x in range(0, img.width(), 4)
               for y in range(0, img.height(), 4))


def test_keep_the_selection_clear_empties_it_in_the_last_scatter(window):
    win, _app_ext = window
    scene = win.viewport.scene
    p = _panel(win)
    ground = _face(scene, size=40.0)
    scene.selection.clear()
    scene.selection.add(ground)
    p._refresh_selection(True)
    p.check("bundled", "arbol")
    p.mode.setCurrentIndex(p.mode.findData("density"))
    p.amount.setValue(20.0)
    p.distance.setValue(0.0)
    p.run()
    box = next(g for g in scene.groups if motor.is_scatter(g))
    assert len(box.children) > 100
    pond = scene.mesh.add_face([QVector3D(x, y, 0.5) for x, y in
                                [(10, 10), (20, 10), (20, 20), (10, 20)]])
    scene.selection.clear()
    scene.selection.add(pond)
    from PySide6.QtTest import QTest
    QTest.qWait(300)                       # the button waits after scattering
    p._refresh_selection(True)
    assert p._editing is None and p.clear_btn.isEnabled()
    assert p.keep_clear()
    box2 = next(g for g in scene.groups if motor.is_scatter(g))
    anc = motor.anchor(motor.bundled_prototype("arbol"))
    for k in box2.children:
        o = k.xform.map(QVector3D(*anc))
        assert not (10.01 < o.x() < 19.99 and 10.01 < o.y() < 19.99)
    assert len(box2.ext[motor.KEY]["clear"]) == 1
    assert p.free_zones()
    box3 = next(g for g in scene.groups if motor.is_scatter(g))
    assert box3.ext[motor.KEY]["clear"] == []
    assert len(box3.children) == len(box.children)


def test_a_stroke_on_a_big_scatter_stays_quick(window):
    import time
    win, app, scene, vp, p = _brush_window(window)
    p.brush_density.setValue(100.0)
    p.distance.setValue(0.5)
    for y in (6, 12, 18, 24, 30):
        _drag(p._tool, vp, app, [(4, y, 0), (36, y, 0)])
    box = next(g for g in scene.groups if motor.is_scatter(g))
    assert len(box.children) > 300
    t = time.time()
    _drag(p._tool, vp, app, [(4, 36, 0), (36, 36, 0)])
    assert time.time() - t < 3.0


def test_real_mouse_strokes_keep_painting_behind_earlier_copies(window):
    """Victor, 08-11: the first stroke painted, the next ones mostly did not
    (the trees already painted hid the ground from the pick). Real mouse
    events, bands one behind the other."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    win, app, scene, vp, p = _brush_window(window)
    p.brush_density.setValue(25.0)

    def at(x, y):
        a, b = _pixel(app, x, y)
        return QPoint(int(a), int(b))

    counts = []
    for y in (8, 16, 24, 32):
        QTest.mouseMove(vp, at(5, y))
        QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, at(5, y))
        for x in range(6, 36, 2):
            QTest.mouseMove(vp, at(x, y))
        QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, at(35, y))
        QTest.qWait(250)
        box = next((g for g in scene.groups if motor.is_scatter(g)), None)
        counts.append(len(box.children) if box else 0)
    assert all(b > a for a, b in zip([0] + counts, counts)), counts
