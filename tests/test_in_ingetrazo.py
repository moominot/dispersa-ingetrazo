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
    names = [p.objects.item(i, 0).data(0x0100)["kind"]
             for i in range(p.objects.rowCount())]
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
