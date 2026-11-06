# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The Dispersa tab: which objects, on what, how many and how varied, and
one button. Selecting a scatter brings its numbers back to change them."""
from __future__ import annotations

import random

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)

from . import motor
from .texts import tr


def _core_tr(text: str) -> str:
    try:
        from core.i18n import tr as core_tr
        return core_tr(text)
    except Exception:                    # noqa: BLE001
        return text


class ScatterPanel(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self._editing = None             # the scatter being edited, if any
        self._busy = False               # scattering: the button waits
        self._sel_key = None
        self._tris = []
        lay = QVBoxLayout(self)

        intro = QLabel(tr("Spread copies of components over faces, a group or "
                          "the terrain, with their size and turn at random."))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        # Objects
        box = QGroupBox(tr("Objects"))
        bl = QVBoxLayout(box)
        self.objects = QTableWidget(0, 2)
        self.objects.setHorizontalHeaderLabels([tr("Object"), tr("Share")])
        self.objects.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.objects.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.objects.verticalHeader().setVisible(False)
        self.objects.setSelectionMode(QTableWidget.NoSelection)
        self.objects.setMinimumHeight(260)
        bl.addWidget(self.objects)
        lay.addWidget(box)

        # Surface
        box = QGroupBox(tr("Surface"))
        form = QFormLayout(box)
        self.where = QLabel()
        self.where.setWordWrap(True)
        form.addRow(self.where)
        self.terrain = QCheckBox(tr("On the terrain"))
        self.terrain.setToolTip(tr("Drop every copy onto the 3D terrain of the "
                                   "Terrain tab, inside the selected area"))
        form.addRow(self.terrain)
        self.max_slope = QDoubleSpinBox()
        self.max_slope.setRange(0.0, 90.0)
        self.max_slope.setDecimals(0)
        self.max_slope.setSuffix(" °")
        self.max_slope.setToolTip(tr("From a group, only the faces this close to "
                                     "level (its floors and roofs, not its walls)"))
        self.max_slope.valueChanged.connect(lambda _v: self._refresh_selection(True))
        form.addRow(tr("Steepest slope"), self.max_slope)
        lay.addWidget(box)

        # Copies
        box = QGroupBox(tr("Copies"))
        form = QFormLayout(box)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItem(tr("Number of copies"), "count")
        self.mode.addItem(tr("Copies per 100 m²"), "density")
        self.amount = QDoubleSpinBox()
        self.mode.currentIndexChanged.connect(self._mode_changed)
        row.addWidget(self.mode, 1)
        row.addWidget(self.amount)
        form.addRow(row)
        self.distance = QDoubleSpinBox()
        self.distance.setRange(0.0, 100.0)
        self.distance.setDecimals(2)
        self.distance.setSingleStep(0.25)
        self.distance.setSuffix(" m")
        self.distance.setToolTip(tr("The least distance from one copy to the next "
                                    "(0 = no limit)"))
        form.addRow(tr("Distance between copies"), self.distance)
        lay.addWidget(box)

        # Variation
        box = QGroupBox(tr("Variation"))
        form = QFormLayout(box)
        row = QHBoxLayout()
        self.smin, self.smax = QSpinBox(), QSpinBox()
        for s in (self.smin, self.smax):
            s.setRange(1, 1000)
            s.setSingleStep(5)
            s.setSuffix(" %")
        row.addWidget(self.smin)
        row.addWidget(QLabel(tr("to")))
        row.addWidget(self.smax)
        form.addRow(tr("Size from"), row)
        self.rotation = QDoubleSpinBox()
        self.rotation.setRange(0.0, 360.0)
        self.rotation.setDecimals(0)
        self.rotation.setSuffix(" °")
        self.rotation.setToolTip(tr("Each copy turns at random, from 0 up to "
                                    "this angle"))
        form.addRow(tr("Turn up to"), self.rotation)
        self.align = QCheckBox(tr("Lean with the surface"))
        self.align.setToolTip(tr("Copies follow the slope (stones, grass) "
                                 "instead of standing upright (trees, people)"))
        form.addRow(self.align)
        row = QHBoxLayout()
        self.seed = QSpinBox()
        self.seed.setRange(0, 999999)
        self.seed.setToolTip(tr("The same seed gives the same scatter"))
        new_seed = QPushButton(tr("New"))
        new_seed.setToolTip(tr("Another random arrangement"))
        new_seed.clicked.connect(self._new_seed)
        row.addWidget(self.seed, 1)
        row.addWidget(new_seed)
        form.addRow(tr("Seed"), row)
        lay.addWidget(box)

        self.editing = QLabel()
        self.editing.setWordWrap(True)
        lay.addWidget(self.editing)
        self.go = QPushButton()
        self.go.setDefault(True)
        self.go.clicked.connect(self.run)
        lay.addWidget(self.go)
        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch(1)

        self.set_params(motor.DEFAULTS)
        self.fill_objects()
        # IngeTrazo says nothing to extensions when the selection changes:
        # look at it while the tab is on screen (a few objects, cheap).
        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        app.on_document_changed(self._document_changed)
        self._refresh_selection(True)

    # ---- objects --------------------------------------------------------------

    def fill_objects(self, chosen=None) -> None:
        """The model's components first, then IngeTrazo's starters. ``chosen``
        (a list of sources) ticks those and sets their share."""
        explicit = chosen is not None
        if chosen is None:
            chosen = self.sources() if self.objects.rowCount() else []
        rows = []
        for g in motor.model_components(self.app.scene):
            rows.append(({"kind": "model", "name": g.name}, None, tr("In the model")))
        for e in motor.bundled_entries():
            rows.append(({"kind": "bundled", "key": e["key"],
                          "name": _core_tr(e["name"])}, e["thumb"],
                         _core_tr(e.get("tip", e["name"]))))
        # A source of the scatter being edited whose object left the model
        # (its copies still carry it) stays on the list.
        for s in chosen:
            if not any(motor._same_source(s, r[0]) for r in rows):
                rows.insert(0, ({k: s[k] for k in s if k != "weight"}, None,
                                tr("In the model")))
        sig = [(r[0].get("kind"), r[0].get("key"), r[0].get("name")) for r in rows]
        if sig == getattr(self, "_rows_sig", None) and not explicit:
            return                       # the same list: keep ticks as they are
        self._rows_sig = sig
        self.objects.clearContents()
        self.objects.setRowCount(0)
        self.objects.setRowCount(len(rows))
        for i, (src, thumb, tip) in enumerate(rows):
            item = QTableWidgetItem(src["name"])
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            pick = next((c for c in chosen if motor._same_source(c, src)), None)
            item.setCheckState(Qt.Checked if pick else Qt.Unchecked)
            item.setData(Qt.UserRole, src)
            item.setToolTip(tip)
            if thumb:
                item.setIcon(QIcon(thumb))
            self.objects.setItem(i, 0, item)
            w = QSpinBox()
            w.setRange(1, 100)
            w.setValue(int(pick.get("weight", 1)) if pick else 1)
            w.setToolTip(tr("How often this object comes out, against the others"))
            self.objects.setCellWidget(i, 1, w)

    def sources(self) -> list:
        out = []
        for i in range(self.objects.rowCount()):
            item = self.objects.item(i, 0)
            if item is not None and item.checkState() == Qt.Checked:
                s = dict(item.data(Qt.UserRole))
                s["weight"] = self.objects.cellWidget(i, 1).value()
                out.append(s)
        return out

    def check(self, kind: str, key_or_name: str, weight: int = 1) -> None:
        """Tick one object (tests and the console)."""
        for i in range(self.objects.rowCount()):
            src = self.objects.item(i, 0).data(Qt.UserRole)
            if src["kind"] == kind and (src.get("key") == key_or_name
                                        or src.get("name") == key_or_name):
                self.objects.item(i, 0).setCheckState(Qt.Checked)
                self.objects.cellWidget(i, 1).setValue(weight)
                return
        raise KeyError(key_or_name)

    # ---- parameters -----------------------------------------------------------

    def _mode_changed(self, _i=None) -> None:
        # Each way of counting keeps its own number.
        new = self.mode.currentData()
        before = getattr(self, "_amount_mode", None)
        store = self.__dict__.setdefault("_other_amount", {})
        if before is not None and before != new:
            store[before] = self.amount.value()
        self._amount_mode = new
        self._apply_range(new)
        if before is not None and before != new and new in store:
            self.amount.setValue(store[new])

    def _apply_range(self, mode) -> None:
        if mode == "density":
            self.amount.setRange(0.01, 1000.0)
            self.amount.setDecimals(2)
            self.amount.setSingleStep(0.5)
        else:
            self.amount.setRange(1, 20000)
            self.amount.setDecimals(0)
            self.amount.setSingleStep(10)

    def set_params(self, p) -> None:
        p = {**motor.DEFAULTS, **p}
        self._other_amount = {"count": p["count"], "density": p["density"]}
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(max(0, self.mode.findData(p["mode"])))
        self.mode.blockSignals(False)
        self._amount_mode = p["mode"]
        self._apply_range(p["mode"])
        self.amount.setValue(p["density"] if p["mode"] == "density" else p["count"])
        self.distance.setValue(p["min_distance"])
        self.smin.setValue(int(p["scale"][0]))
        self.smax.setValue(int(p["scale"][1]))
        self.rotation.setValue(p["rotation"])
        self.align.setChecked(bool(p["align"]))
        self.terrain.setChecked(bool(p["terrain"]))
        self.max_slope.setValue(p["max_slope"])
        self.seed.setValue(int(p["seed"]))

    def params(self) -> dict:
        mode = self.mode.currentData()
        p = {"mode": mode,
             "count": int(self.amount.value()) if mode == "count"
             else int(self._other_amount.get("count", motor.DEFAULTS["count"])),
             "density": float(self.amount.value()) if mode == "density"
             else float(self._other_amount.get("density", motor.DEFAULTS["density"])),
             "min_distance": self.distance.value(),
             "scale": [float(self.smin.value()), float(self.smax.value())],
             "rotation": self.rotation.value(),
             "align": self.align.isChecked(),
             "terrain": self.terrain.isChecked(),
             "max_slope": self.max_slope.value(),
             "seed": self.seed.value(),
             "sources": self.sources()}
        return p

    def _new_seed(self) -> None:
        self.seed.setValue(random.randint(1, 999999))

    # ---- selection ------------------------------------------------------------

    def _tick(self) -> None:
        if self.isVisible():
            self._refresh_selection()

    def _document_changed(self) -> None:
        if self._editing is not None and self._editing not in self.app.scene.groups:
            self._editing = None
        self.fill_objects()
        self._refresh_selection(True)

    def _refresh_selection(self, force=False) -> None:
        sel = list(self.app.scene.selection)
        key = (len(sel), tuple(sorted(id(e) for e in sel[:200])))
        if key == self._sel_key and not force:
            return
        self._sel_key = key
        scatters = [g for g in sel if motor.is_scatter(g)]
        if len(sel) == 1 and scatters:
            self.edit(scatters[0])
            return
        self._tris = motor.surface_from_selection(sel, self.max_slope.value())
        if self._tris:
            self._editing = None
            self.where.setText(tr("Selection: {a} m² ({n} triangles)",
                                  n=len(self._tris),
                                  a=f"{motor.surface_area(self._tris):.1f}"))
        else:
            self.where.setText(tr("Select faces or a group in the model."))
        self._show_mode()

    def edit(self, group) -> None:
        """Bring a scatter's numbers into the panel, to change them."""
        e = group.ext[motor.KEY]
        if self._editing is not group:
            self.set_params(e)
            self.fill_objects(e.get("sources", []))
        self._editing = group
        self._tris = []
        self.where.setText(tr("The scatter's surface: {a} m² ({n} triangles)",
                              n=len(e["surface"]),
                              a=f"{motor.surface_area(e['surface']):.1f}"))
        self._show_mode()

    def _show_mode(self) -> None:
        if self._editing is not None:
            self.editing.setText("<b>" + tr("Editing: {name}", name=self._editing.name)
                                 + "</b><br>" + tr(
                "Change the numbers and scatter again on the same surface; or "
                "select faces to start a new one."))
            self.go.setText(tr("Scatter again"))
            self.go.setEnabled(not self._busy)
        else:
            self.editing.setText("")
            self.go.setText(tr("Scatter on the selection"))
            self.go.setEnabled(bool(self._tris) and not self._busy)

    # ---- the button -----------------------------------------------------------

    def run(self) -> None:
        from core.history import SnapshotImport
        params = self.params()
        if not params["sources"]:
            self.status.setText(tr("Choose at least one object to scatter."))
            return
        vp = self.app.viewport
        old = self._editing
        tris = None if old is not None else list(self._tris)
        scene = self.app.scene
        terrain = getattr(scene, "terrain", None)
        end = getattr(vp, "end_group_edit", None)
        if callable(end):
            end()
        # Reading the objects, building the copies and IngeTrazo's own
        # first drawing of them can take seconds: say so, and wait visibly.
        from PySide6.QtWidgets import QApplication
        self.status.setText(tr("Scattering…"))
        self._busy = True
        self.go.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            try:
                box, placed, wanted = motor.prepare(scene, params, tris=tris,
                                                    old=old, terrain=terrain)
            except ValueError as exc:
                self.status.setText(str(exc))
                return
            vp.history.execute(SnapshotImport(lambda s: motor.place(s, box, old)))
            if box not in scene.groups:  # IngeTrazo logged why; nothing changed
                self.status.setText(getattr(vp.history, "last_error", None) or "")
                return
            self._finish(vp, scene, box, placed, wanted)
        finally:
            # After the next paint: the timer cannot fire while IngeTrazo is
            # still busy drawing the new copies for the first time.
            QTimer.singleShot(200, self._idle)

    def _idle(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.restoreOverrideCursor()
        self._busy = False
        self._show_mode()

    def _finish(self, vp, scene, box, placed, wanted) -> None:
        notify = getattr(vp, "notify_scene_changed", None)
        if callable(notify):
            notify()
        scene.selection.clear()
        scene.selection.add(box)
        self._editing = box
        self._sel_key = None
        msg = (tr("{n} copies placed.", n=placed) if placed >= wanted else
               tr("{n} of {w} copies placed: there is no room for more at "
                  "that distance.", n=placed, w=wanted))
        self.status.setText(msg + " " + tr("Ctrl+Z undoes it at once."))
        self._refresh_selection(True)
