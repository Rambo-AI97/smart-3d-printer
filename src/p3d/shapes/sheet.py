"""Design sheet: one small JPG with front / side / top / iso views, dimensions, thinnest wall, optional context.

    python -m p3d.shapes.sheet INPUT.stl|INPUT.py [--context mantel|shelf|wall] [--out FILE.jpg]

Runs in the cad venv (trimesh, numpy, matplotlib, PIL). Renderer: matplotlib Agg, painter's algorithm with flat
shading: pure CPU, no GL, same result on any machine. Model frame: Z is up for front/side views; the top view
looks down Z with +Y up. Context presets assume the hook frame used by shapes.j_hook: y = 0 is the mounting
face, the support body lies at y <= 0, and for mantel/shelf its edge is x = 0 (body at x >= 0).
"""
from __future__ import annotations

import argparse
import io
import pathlib
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.spatial import ConvexHull  # noqa: E402
import trimesh  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from PIL import Image  # noqa: E402

OUT_DIR = pathlib.Path.home() / ".local/share/p3d/shots"
BG, FG, ACCENT, WARN = "#14161a", "#e8e8e8", "#7fb4ff", "#ff6b5e"
VIEWS = {  # name: (direction from model to viewer, screen-up vector, x label, y label)
    "FRONT  (X, Z)": ((0, -1, 0), (0, 0, 1), "x", "z"),
    "SIDE  (Y, Z)": ((1, 0, 0), (0, 0, 1), "y", "z"),
    "TOP  (X, Y)": ((0, 0, 1), (0, 1, 0), "x", "y"),
    "ISO": ((1, -1.3, 0.9), (0, 0, 1), None, None),
}


def context_boxes(spec, bb):
    """Resolve a CONTEXT spec to [(label, (x0, x1, y0, y1, z0, z1))]. bb = model bounds (2x3 array)."""
    if not spec:
        return []
    if not isinstance(spec, str):
        return [(c.get("label", "context"), tuple(c["box"])) for c in spec]
    z0, z1 = bb[0][2] - 10, bb[1][2] + 10
    big = 60.0
    return {
        "mantel": [("mantel top and front face (x>=0, y<=0)", (0, big, -big, 0, z0, z1))],
        "shelf": [("shelf 19 mm (x>=0)", (0, big, -19, 0, z0, z1))],
        "wall": [("wall", (-big, big, -10, 0, z0, z1))],
    }[spec]


def thinnest_wall(mesh, n=2500, seed=1):
    """Approximate thinnest wall: ray from sampled surface points inward along -normal; (mm, point) of the min."""
    pts, fi = trimesh.sample.sample_surface(mesh, n, seed=seed)
    nrm = mesh.face_normals[fi]
    org = pts - nrm * 1e-3
    try:
        loc, ray, _ = mesh.ray.intersects_location(org, -nrm, multiple_hits=False)
    except Exception:
        return None, None
    if not len(ray):
        return None, None
    d = np.linalg.norm(loc - org[ray], axis=1)
    hit_n = mesh.face_normals[_]
    keep = (d > 0.15) & ((hit_n * nrm[ray]).sum(1) < -0.85)   # a real opposite wall, not a fillet or groove edge
    if not keep.any():
        return None, None
    i = np.argmin(np.where(keep, d, 1e9))
    return float(d[i]), org[ray][i]


def _basis(v, up):
    v = np.array(v, float)
    v /= np.linalg.norm(v)
    f = -v
    r = np.cross(f, up)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return v, f, r, u


def _draw_view(ax, mesh, name, spec, ctx, thin_pt, dims):
    vdir, up, xl, yl = spec
    v, f, r, u = _basis(vdir, up)
    V, F = mesh.vertices, mesh.faces
    tri = V[F]
    n = mesh.face_normals
    vis = n @ v > 0
    t, nn = tri[vis], n[vis]
    xy = np.stack([t @ r, t @ u], axis=-1)
    depth = (t @ f).mean(axis=1)
    order = np.argsort(-depth)            # far first
    light = v + 0.7 * u - 0.5 * r
    light /= np.linalg.norm(light)
    shade = 0.28 + 0.72 * np.clip(nn @ light, 0, 1)
    cols = np.stack([0.42 * shade + 0.1, 0.62 * shade + 0.1, 0.95 * shade + 0.03], axis=1).clip(0, 1)
    ax.add_collection(PolyCollection(xy[order], facecolors=cols[order], edgecolors=cols[order], linewidths=0.3))
    lo, hi = xy.reshape(-1, 2).min(0), xy.reshape(-1, 2).max(0)
    for _label, (x0, x1, y0, y1, z0, z1) in ctx:
        c = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)
        p = np.stack([c @ r, c @ u], axis=1)
        pad = max(hi - lo) * 0.6
        p = np.clip(p, lo - pad, hi + pad)
        try:
            h = p[ConvexHull(p).vertices]
        except Exception:
            continue
        ax.fill(h[:, 0], h[:, 1], color="#9aa4b2", alpha=0.18, lw=0, zorder=3)
        ax.plot(*np.vstack([h, h[:1]]).T, color="#b8c2d0", lw=0.8, ls="--", zorder=3)
    if thin_pt is not None:
        ax.plot(thin_pt @ r, thin_pt @ u, "o", mfc="none", mec=WARN, ms=7, mew=1.2, zorder=5)
    if xl:                                # dimension lines on the three orthographic views
        wmm, hmm = hi[0] - lo[0], hi[1] - lo[1]
        off = 0.12 * max(wmm, hmm)
        ax.annotate("", (lo[0], lo[1] - off), (hi[0], lo[1] - off), arrowprops=dict(arrowstyle="<->", color=ACCENT, lw=0.9))
        ax.text((lo[0] + hi[0]) / 2, lo[1] - off * 1.25, f"{wmm:.1f} mm", color=ACCENT, fontsize=8, ha="center", va="top")
        ax.annotate("", (hi[0] + off, lo[1]), (hi[0] + off, hi[1]), arrowprops=dict(arrowstyle="<->", color=ACCENT, lw=0.9))
        ax.text(hi[0] + off * 1.3, (lo[1] + hi[1]) / 2, f"{hmm:.1f}", color=ACCENT, fontsize=8, rotation=90, va="center")
        ax.set_xlim(lo[0] - off * 1.2, hi[0] + off * 3)
        ax.set_ylim(lo[1] - off * 2.6, hi[1] + off * 1.2)
    else:
        pad = 0.08 * max(hi - lo)
        ax.set_xlim(lo[0] - pad, hi[0] + pad)
        ax.set_ylim(lo[1] - pad, hi[1] + pad)
    ax.set_aspect("equal")
    ax.set_facecolor(BG)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#30343c")
    ax.set_title(name, color=FG, fontsize=8.5, loc="left", pad=3)


def make_sheet(mesh, title, ctx_spec=None, out=None):
    bb = mesh.bounds
    size = bb[1] - bb[0]
    wall, wpt = thinnest_wall(mesh)
    ctx = context_boxes(ctx_spec, bb)
    fig = plt.figure(figsize=(12, 8), dpi=100, facecolor=BG)
    gs = fig.add_gridspec(2, 2, left=0.02, right=0.98, top=0.88, bottom=0.04, wspace=0.04, hspace=0.12)
    for i, (name, spec) in enumerate(VIEWS.items()):
        _draw_view(fig.add_subplot(gs[i // 2, i % 2]), mesh, name, spec, ctx, wpt, None)
    wtxt = (f"thinnest wall ~{wall:.2f} mm (red ring)" + ("  LOW: < 1.2 mm" if wall < 1.2 else "")) if wall else "wall: n/a"
    fig.text(0.02, 0.955, title, color=FG, fontsize=15, weight="bold", va="center")
    fig.text(0.02, 0.915,
             f"{size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm   |   {mesh.volume / 1000:.2f} cm3 "
             f"(~{mesh.volume * 1.27 / 1000 * 0.35:.1f} g at 35 % solid PETG)   |   {wtxt}"
             + (f"   |   context: {ctx_spec if isinstance(ctx_spec, str) else 'custom'}" if ctx else "")
             + ("" if mesh.is_watertight else "   |   NOT WATERTIGHT"),
             color=WARN if (wall and wall < 1.2) or not mesh.is_watertight else "#9fb3c8", fontsize=9.5, va="center")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    buf.seek(0)
    im = Image.open(buf).convert("RGB")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = pathlib.Path(out) if out else OUT_DIR / f"sheet-{title}-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
    q = 82
    while True:
        im.save(out, "JPEG", quality=q, optimize=True)
        if out.stat().st_size < 290_000 or q <= 40:
            return out, wall
        q -= 8


def main(argv=None):
    ap = argparse.ArgumentParser(prog="p3d.shapes.sheet")
    ap.add_argument("input")
    ap.add_argument("--context", choices=["mantel", "wall", "shelf"])
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    src = pathlib.Path(a.input)
    ctx = a.context
    if src.suffix == ".py":
        from .build import load_design
        from .core import export_stl
        part, c, name = load_design(src)
        ctx = ctx or c
        stl = export_stl(part, src.with_suffix(".stl"))
    else:
        stl, name = src, src.stem
    mesh = trimesh.load(stl, force="mesh")
    out, wall = make_sheet(mesh, name, ctx, a.out)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
