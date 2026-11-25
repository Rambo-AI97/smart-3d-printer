"""Core helpers: true fillets/chamfers on one solid, rounded paths, swept profiles with taper, export."""
from __future__ import annotations

import math
import pathlib

from build123d import (Circle, Line, Part, Plane, RectangleRounded, ThreePointArc, Vector, Wire, chamfer,
                       fillet, sweep)
from build123d import export_stl as _export_stl


def soften(part, radius: float, edges=None, chamfered: bool = False):
    """Round (true fillet) or chamfer edges of ONE solid. Units mm.

    edges: iterable of Edge, or None for every edge. Retries with a smaller radius (x0.7, up to 6 times)
    if OCC rejects it. Printing: a fillet prints cleaner than stacked chamfer slabs; keep radius < half the
    thinnest wall. A 45 deg chamfer on the bed-side edges offsets elephant foot.
    """
    es = list(edges) if edges is not None else list(part.edges())
    r = radius
    for _ in range(7):
        try:
            res = (chamfer if chamfered else fillet)(es, r)
            if res.is_valid:
                return res
        except Exception:
            pass
        r *= 0.7
    raise ValueError(f"could not soften {len(es)} edges at r={radius}")


def rounded_path(points, radii) -> Wire:
    """Polyline through `points` (x, y in mm, XY plane) with a tangent arc of radius radii[i] at each vertex.

    radii[0] and radii[-1] are ignored (path ends). Neighbouring arcs may consume a whole segment; too big a
    radius raises. The result is G1-smooth, so a swept profile has no kinks.
    """
    P = [Vector(x, y, 0) for x, y in points]
    segs, cur = [], P[0]
    for i in range(1, len(P) - 1):
        a, b, r = P[i - 1], P[i + 1], radii[i]
        if r <= 0:
            if (P[i] - cur).length > 1e-4:
                segs.append(Line(cur, P[i]))
            cur = P[i]
            continue
        ua, ub = (a - P[i]).normalized(), (b - P[i]).normalized()
        theta = math.acos(max(-1.0, min(1.0, ua.dot(ub))))
        d = r / math.tan(theta / 2)
        if d > (a - P[i]).length + 1e-6 or d > (b - P[i]).length + 1e-6:
            raise ValueError(f"bend radius {r} too large at vertex {i}")
        t1, t2 = P[i] + ua * d, P[i] + ub * d
        bis = (ua + ub).normalized()
        centre = P[i] + bis * (r / math.sin(theta / 2))
        if (t1 - cur).length > 1e-4:
            segs.append(Line(cur, t1))
        segs.append(ThreePointArc(t1, centre - bis * r, t2))
        cur = t2
    if (P[-1] - cur).length > 1e-4:
        segs.append(Line(cur, P[-1]))
    return Wire(segs)


def _interp(table, s):
    """Smoothstep interpolation of [(s0, v0), (s1, v1), ...]."""
    if s <= table[0][0]:
        return table[0][1]
    for (s0, v0), (s1, v1) in zip(table, table[1:]):
        if s <= s1:
            u = (s - s0) / (s1 - s0) if s1 > s0 else 1.0
            return v0 + (v1 - v0) * u * u * (3 - 2 * u)
    return table[-1][1]


def sweep_profile(path: Wire, thickness, width=None, corner: float = 0.6, step: float = 1.5,
                  width_dir=(0, 0, 1)) -> Part:
    """Sweep a profile along `path` with a smoothly varying size. Units mm.

    thickness: a number, or [(s, t), ...] with s = 0..1 fraction of path length (smoothstep between knots).
    width: None -> round profile (diameter = thickness); number -> rounded rectangle width x thickness with
      the width along `width_dir` (default +Z) and corner radius `corner`. Sections every ~`step` mm.
    Printing: path in the XY plane + width along Z prints on its side with no supports.
    """
    if isinstance(thickness, (list, tuple)):
        table = [(float(s), float(t)) for s, t in thickness]
    else:
        table = [(0.0, float(thickness)), (1.0, float(thickness))]
    n = max(8, int(path.length / step))
    secs = []
    for k in range(n + 1):
        s = k / n
        t = _interp(table, s)
        pl = Plane(origin=path @ s, x_dir=width_dir, z_dir=path % s)
        if width is None:
            secs.append(pl * Circle(t / 2))
        else:
            secs.append(pl * RectangleRounded(width, t, min(corner, t / 2 - 0.01, width / 2 - 0.01)))
    return sweep(secs, path=path, multisection=True)


def export_stl(part, path, fine: bool = True) -> pathlib.Path:
    """Export STL (0.01 mm / 0.1 rad tessellation when fine: smooth curves). Returns the path.

    OCC can leave a pinhole where tiny fillet patches meet after booleans; when trimesh is available a
    non-watertight result gets its holes filled (only small gaps close) and is rewritten.
    """
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    _export_stl(part, str(p), tolerance=0.01 if fine else 0.05, angular_tolerance=0.1 if fine else 0.3)
    try:
        import trimesh
        m = trimesh.load(p, force="mesh")
        if not m.is_watertight:
            trimesh.repair.fill_holes(m)
            if m.is_watertight:
                m.export(p)
    except ImportError:
        pass
    return p


def check_solid(part) -> dict:
    """Solid count, validity, watertightness (of the exported mesh), volume and size. Needs trimesh."""
    import tempfile

    import trimesh
    with tempfile.TemporaryDirectory() as d:
        f = export_stl(part, pathlib.Path(d) / "x.stl")
        m = trimesh.load(f)
    bb = m.extents                      # mesh extents: OCC's own bounding box can be loose after booleans
    return {"solids": len(part.solids()), "valid": bool(part.is_valid), "watertight": bool(m.is_watertight),
            "volume_mm3": round(float(m.volume), 1), "size_mm": tuple(round(float(v), 2) for v in bb)}
