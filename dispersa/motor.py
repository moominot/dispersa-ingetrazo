# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Scattering, with no interface: the surface as triangles, the points on
it, and the container group whose copies share their objects' geometry.

A scatter is ONE group (``component = False``) holding one placement per
copy. Every placement of the same object shares that object's mesh and only
carries its own matrix, so two thousand trees weigh one tree. The group
remembers how it was made in ``group.ext[KEY]`` (the surface included), so
it can be scattered again with other numbers.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

from .texts import tr

KEY = "dispersa"
LAYER = "Dispersa"
FORMAT = 1

DEFAULTS = {
    "mode": "count",          # "count": number of copies; "density": per 100 m²
    "count": 50,
    "density": 4.0,
    "min_distance": 1.0,      # metres between copies (0 = no limit)
    "scale": [80.0, 120.0],   # percent, from and to
    "rotation": 360.0,        # degrees, turned at random from 0 to this
    "align": False,           # lean with the surface instead of upright
    "terrain": False,         # drop every point onto scene.terrain
    "max_slope": 40.0,        # degrees; only for the faces of groups
    "seed": 1,
}


# ---- The objects ---------------------------------------------------------------

def bundled_root() -> Path:
    from core.paths import app_root
    return app_root() / "resources" / "components"


def bundled_entries() -> list[dict]:
    """IngeTrazo's own 3D starters (components.json): key, name, tip and
    the thumbnail, the ones whose .igz is there."""
    root = bundled_root()
    try:
        entries = json.loads((root / "components.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for e in entries:
        if (root / f"{e['key']}.igz").is_file():
            out.append({**e, "thumb": str(root / "thumbs" / f"{e['key']}.png")})
    return out


def model_components(scene) -> list:
    """The components placed in the model, one per definition (the first
    copy found stands for it). Scatters are left out."""
    seen, out = set(), []
    for g in scene.groups:
        if not g.is_component() or is_scatter(g):
            continue
        if id(g.mesh) in seen:
            continue
        seen.add(id(g.mesh))
        out.append(g)
    return out


def _clean_prototype(group):
    """A placement of ``group``'s definition at its own pose: shared mesh
    and subgroups, nothing of how that copy was left."""
    from PySide6.QtGui import QMatrix4x4
    from core.group import copy_group
    p = copy_group(group)
    p.xform = QMatrix4x4()
    p.component = True
    p.hidden = p.locked = False
    p.material = p.layer = p.ifc = None
    p.exploded = p.explode_offset = None
    p.axes = None
    p.ext = None
    return p


def bundled_prototype(key: str, name: str | None = None):
    """IngeTrazo's starter ``key`` read from its .igz, as a component."""
    from PySide6.QtGui import QMatrix4x4
    from core.group import Group
    from core.scene import Scene
    from formats import igz
    path = bundled_root() / f"{key}.igz"
    temp = Scene()
    igz.load_into(temp, path)
    if not temp.groups:
        raise ValueError(tr("Could not read {name}.", name=name or key))
    g = Group(temp.groups[0].mesh, name=name or key)
    g.xform = QMatrix4x4()
    g.component = True
    return g


def model_prototype(scene, name: str):
    for g in model_components(scene):
        if g.name == name:
            return _clean_prototype(g)
    return None


def anchor(proto) -> tuple:
    """Where a copy stands: the centre of the bottom of the object's box,
    in its own coordinates. The starters are drawn metres away from their
    origin, so their origin cannot be it."""
    from core.group import placement_points
    pts = placement_points(proto)
    if not len(pts):
        return (0.0, 0.0, 0.0)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    return (float(lo[0] + hi[0]) / 2, float(lo[1] + hi[1]) / 2, float(lo[2]))


# ---- The surface -----------------------------------------------------------------

def is_scatter(group) -> bool:
    return KEY in (getattr(group, "ext", None) or {})


def surface_from_selection(selection, max_slope: float = 40.0) -> list:
    """The selected faces and groups as world triangles ``[ax, ay, az, bx,
    …, cz]``. A selected face is taken whole, turned up if it faces down;
    from a group, only what faces up at most ``max_slope`` from level —
    its roof and its floor, not its walls. Scatters are skipped."""
    from core.group import Group, iter_placements
    from core.mesh import Face
    tris = []
    for ent in selection:
        if isinstance(ent, Face):
            n = ent.normal()
            for a, b, c in ent.triangulate():
                tris.append(_tri(a, b, c, up=n.z() < 0))
        elif isinstance(ent, Group) and not is_scatter(ent):
            cos_max = math.cos(math.radians(max_slope))
            for g, m in iter_placements(ent):
                for f in g.mesh.faces:
                    for a, b, c in f.triangulate():
                        if m is not None:
                            a, b, c = m.map(a), m.map(b), m.map(c)
                        t = _tri(a, b, c)
                        n = _normal(t)
                        if n is not None and n[2] >= cos_max - 1e-9:
                            tris.append(t)
    return [t for t in tris if _area(t) > 1e-6]


def _tri(a, b, c, up=False):
    t = [a.x(), a.y(), a.z(), b.x(), b.y(), b.z(), c.x(), c.y(), c.z()]
    if up:
        t = t[0:3] + t[6:9] + t[3:6]
    return [round(v, 4) for v in t]


def _cross(t):
    ux, uy, uz = t[3] - t[0], t[4] - t[1], t[5] - t[2]
    vx, vy, vz = t[6] - t[0], t[7] - t[1], t[8] - t[2]
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def _area(t) -> float:
    x, y, z = _cross(t)
    return 0.5 * math.sqrt(x * x + y * y + z * z)


def _normal(t):
    x, y, z = _cross(t)
    n = math.sqrt(x * x + y * y + z * z)
    return None if n < 1e-12 else (x / n, y / n, z / n)


def surface_area(tris) -> float:
    return sum(_area(t) for t in tris)


# ---- The points ------------------------------------------------------------------

def _terrain_normal(terrain, x, y, z):
    d = 0.5
    zx = terrain.height_at(x + d, y)
    zy = terrain.height_at(x, y + d)
    if zx is None or zy is None:
        return (0.0, 0.0, 1.0)
    nx, ny = -(zx - z) / d, -(zy - z) / d
    n = math.sqrt(nx * nx + ny * ny + 1.0)
    return (nx / n, ny / n, 1.0 / n)


def scatter_points(tris, params, terrain=None):
    """``[(point, normal)]`` spread at random over ``tris``, reproducible by
    the seed, at least ``min_distance`` apart. With ``terrain`` the points
    keep their place in plan and take the ground's height (points off the
    captured ground are left out). Returns (points, wanted)."""
    p = {**DEFAULTS, **params}
    rnd = random.Random(int(p["seed"]))
    area = surface_area(tris)
    if p["mode"] == "density":
        wanted = int(round(area * float(p["density"]) / 100.0))
    else:
        wanted = int(p["count"])
    wanted = max(0, min(wanted, 20000))
    if not tris or wanted == 0:
        return [], wanted
    # Area-weighted choice of triangle.
    acc, total = [], 0.0
    for t in tris:
        total += _area(t)
        acc.append(total)
    import bisect
    dmin = max(0.0, float(p["min_distance"]))
    cell = dmin if dmin > 0 else None
    grid: dict = {}
    out = []
    attempts = 0
    limit = wanted * 30
    while len(out) < wanted and attempts < limit:
        attempts += 1
        t = tris[min(bisect.bisect_left(acc, rnd.random() * total), len(tris) - 1)]
        r1, r2 = rnd.random(), rnd.random()
        s = math.sqrt(r1)
        u, v, w = 1 - s, s * (1 - r2), s * r2
        x = u * t[0] + v * t[3] + w * t[6]
        y = u * t[1] + v * t[4] + w * t[7]
        z = u * t[2] + v * t[5] + w * t[8]
        n = _normal(t)
        if n is not None and n[2] < 0:
            n = (-n[0], -n[1], -n[2])
        if terrain is not None:
            h = terrain.height_at(x, y)
            if h is None:
                continue
            z = h
            n = _terrain_normal(terrain, x, y, z)
        if cell is not None:
            k = (math.floor(x / cell), math.floor(y / cell), math.floor(z / cell))
            near = False
            for i in (-1, 0, 1):
                for j in (-1, 0, 1):
                    for m in (-1, 0, 1):
                        for q in grid.get((k[0] + i, k[1] + j, k[2] + m), ()):
                            if (q[0] - x) ** 2 + (q[1] - y) ** 2 + (q[2] - z) ** 2 < dmin * dmin:
                                near = True
                                break
                        if near:
                            break
                    if near:
                        break
                if near:
                    break
            if near:
                continue
            grid.setdefault(k, []).append((x, y, z))
        out.append(((x, y, z), n or (0.0, 0.0, 1.0)))
    return out, wanted


# ---- The scatter -------------------------------------------------------------------

def _align_matrix(n):
    """A rotation taking Z up to the normal ``n``."""
    from PySide6.QtGui import QMatrix4x4, QQuaternion, QVector3D
    m = QMatrix4x4()
    q = QQuaternion.rotationTo(QVector3D(0, 0, 1), QVector3D(*n))
    m.rotate(q)
    return m


def _pick(rnd, weights):
    total = sum(weights)
    r = rnd.random() * total
    for i, w in enumerate(weights):
        r -= w
        if r < 0:
            return i
    return len(weights) - 1


def build(params, prototypes, tris, terrain=None, name=None):
    """The container group: one placement per point, each sharing its
    object's definition. ``prototypes`` is one component per source, in
    the order of ``params["sources"]``. Returns (group, placed, wanted)."""
    from PySide6.QtGui import QMatrix4x4, QVector3D
    from core.group import Group, copy_group
    from core.mesh import Mesh
    p = {**DEFAULTS, **params}
    sources = p["sources"]
    if not sources or len(prototypes) != len(sources):
        raise ValueError(tr("Choose at least one object to scatter."))
    weights = [max(0.0, float(s.get("weight", 1))) for s in sources]
    if sum(weights) <= 0:
        weights = [1.0] * len(sources)
    anchors = [anchor(pr) for pr in prototypes]
    points, wanted = scatter_points(tris, p, terrain)
    # The choices of object, size and turn have their own sequence, so
    # moving the distance does not reshuffle which tree is which.
    rnd = random.Random(int(p["seed"]) * 7919 + 17)
    smin, smax = sorted(float(v) for v in p["scale"])
    rot = float(p["rotation"])
    kids = []
    for (pt, n) in points:
        i = _pick(rnd, weights)
        s = rnd.uniform(smin, smax) / 100.0
        angle = rnd.uniform(0.0, rot)
        m = QMatrix4x4()
        m.translate(QVector3D(*pt))
        if p["align"]:
            m = m * _align_matrix(n)
        m.rotate(angle, 0.0, 0.0, 1.0)
        m.scale(s)
        ax, ay, az = anchors[i]
        m.translate(-ax, -ay, -az)
        g = copy_group(prototypes[i])
        g.xform = m
        g.ext = {KEY: {"src": i}}
        kids.append(g)
    box = Group(Mesh(), name=name or container_name(sources))
    box.adopt(kids)
    box.component = False
    box.layer = LAYER
    stored = {k: p[k] for k in DEFAULTS}
    stored.update({"format": FORMAT, "sources": [dict(s) for s in sources],
                   "surface": [list(t) for t in tris], "placed": len(kids),
                   "wanted": wanted})
    box.ext = {KEY: stored}
    return box, len(kids), wanted


def container_name(sources) -> str:
    names = [s.get("name") or s.get("key") or "?" for s in sources]
    text = ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
    return "Dispersa: " + text


def prototypes_for(scene, sources, old=None):
    """One component per source: taken from the copies of a scatter when
    there are some (its object may be gone from the model), otherwise
    read: a starter from its file, a model component by name."""
    # Every definition the scatters in the model already hold, the one
    # being redone first: a second scatter of trees shares the first one's
    # tree instead of reading the file again.
    known = []
    boxes = ([old] if old is not None else []) + [
        g for g in scene.groups if is_scatter(g) and g is not old]
    for box in boxes:
        olds = box.ext[KEY].get("sources", [])
        seen = set()
        for k in box.children or ():
            i = ((k.ext or {}).get(KEY) or {}).get("src")
            if i is None or i >= len(olds) or i in seen:
                continue
            seen.add(i)
            known.append((olds[i], k))
    out = []
    for s in sources:
        proto = next((_clean_prototype(k) for o, k in known
                      if _same_source(o, s)), None)
        if proto is None:
            if s.get("kind") == "bundled":
                proto = bundled_prototype(s["key"], s.get("name"))
            else:
                proto = model_prototype(scene, s.get("name", ""))
        if proto is None:
            raise ValueError(tr("“{name}” is no longer in the model.",
                                name=s.get("name", "?")))
        out.append(proto)
    return out


def _same_source(a, b) -> bool:
    if a.get("kind") != b.get("kind"):
        return False
    if a.get("kind") == "bundled":
        return a.get("key") == b.get("key")
    return a.get("name") == b.get("name")


def prepare(scene, params, tris=None, old=None, terrain=None):
    """Build a scatter beside the scene, touching nothing: everything that
    can go wrong goes wrong here, before the undo step starts. With
    ``old``, its surface is reused when ``tris`` is None and its objects'
    definitions are taken from its copies. Returns (group, placed, wanted)."""
    if tris is None:
        if old is None:
            raise ValueError(tr("Select faces or a group to scatter on."))
        tris = old.ext[KEY]["surface"]
    if not tris:
        raise ValueError(tr("The selection has no surface to scatter on."))
    if params.get("terrain") and terrain is None:
        raise ValueError(tr("There is no 3D terrain yet: build it in the "
                            "Terrain tab, or untick “On the terrain”."))
    protos = prototypes_for(scene, params["sources"], old)
    box, placed, wanted = build(params, protos, tris,
                                terrain if params.get("terrain") else None)
    if old is not None:
        # A name the user gave stays; the automatic one follows the objects.
        if old.name != container_name(old.ext[KEY].get("sources", [])):
            box.name = old.name
        box.layer = old.layer
        box.hidden = old.hidden
    return box, placed, wanted


def place(scene, box, old=None) -> None:
    """Put a prepared scatter in ``scene``, in the place of ``old`` if it
    is there (no undo: callers wrap this in ``SnapshotImport``)."""
    from core.layers import Layer
    if box.layer and not any(ly.name == box.layer for ly in scene.layers):
        scene.layers.append(Layer(box.layer))
    if old is not None and old in scene.groups:
        scene.groups[scene.groups.index(old)] = box
        scene.selection.discard(old)
    else:
        scene.groups.append(box)
    scene.version += 1


def scatter(scene, params, tris=None, old=None, terrain=None):
    """Prepare and place at once (tests, the Python Console)."""
    box, placed, wanted = prepare(scene, params, tris, old, terrain)
    place(scene, box, old)
    return box, placed, wanted
