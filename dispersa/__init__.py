# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""IngeTrazo Dispersa: trees, plants, stones or people scattered over faces,
a group or the terrain.

An extension for IngeTrazo (setup(app), docs/plugins.md): a «Dispersa» tab
in the side tray. Choose components (from the model or IngeTrazo's own),
select faces or a group, and it spreads copies over them with their size
and turn at random, a least distance between them and a seed to repeat
the result. Every copy shares its object's geometry, so thousands weigh
one; the scatter is one group, one undo step, and keeps its numbers to be
changed and scattered again.

Install: copy the ``dispersa`` folder into IngeTrazo's plugins folder
(Extensions ▸ Open plugins folder) and restart IngeTrazo.
"""
from __future__ import annotations

__version__ = "0.1.0"


def _language() -> str:
    from core.i18n import current_language
    return current_language()


def setup(app) -> None:
    from PySide6.QtCore import QTimer
    from . import motor, texts
    from .panel import ScatterPanel
    texts.LANGUAGE = _language
    tr = texts.tr
    panel = ScatterPanel(app)
    dock = app.add_panel("Dispersa", panel)

    def show(group=None):
        app.show_panel(dock)
        if group is not None:
            panel.edit(group)

    app.add_menu_action("Dispersa…", show,
                        tip=tr("Show the Dispersa tab: trees, plants, stones or "
                               "people spread over faces or the terrain."))

    def outliner(group):
        e = (getattr(group, "ext", None) or {}).get(motor.KEY)
        if not e:
            return None
        names = ", ".join(s.get("name", "?") for s in e.get("sources", []))
        return {"type": "Dispersa",
                "props": [(tr("Objects"), names),
                          (tr("Copies"), str(e.get("placed", 0))),
                          (tr("Seed"), str(e.get("seed", 0)))]}

    app.add_outliner_kind(outliner)

    def context_menu(menu, selection):
        scatters = [g for g in selection if motor.is_scatter(g)]
        if len(scatters) == 1:
            g = scatters[0]
            menu.addAction(tr("Edit in Dispersa…"),
                           lambda: QTimer.singleShot(0, lambda: show(g)))

    app.add_context_menu(context_menu)
