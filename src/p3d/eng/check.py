"""Pre-slice gate: catches what makes Orca fail or the print fail, in plain words. `run(path)` -> result dict."""
import numpy as np

from . import geom

WALL_WARN, WALL_FAIL = 0.8, 0.4      # two lines / one nozzle width
FRAC_FAIL, FRAC_WARN = 0.02, 0.10   # share of sampled surface thinner than the limits
OVERHANG_DEG = 50
TALL_RATIO = 3.0
SAMPLES = 4000


def thinnest_wall(m, n=SAMPLES):
    """Ray-cast inward from random surface points; the distance to the far side is the local wall thickness."""
    pts, fi = m.sample(n, return_index=True)
    nrm = m.face_normals[fi]
    org = pts - nrm * 1e-3
    try:
        tri, ray, loc = m.ray.intersects_id(org, -nrm, multiple_hits=False, return_locations=True)
    except Exception:
        return None
    opposite = (m.face_normals[tri] * nrm[ray]).sum(axis=1) < -0.7   # far wall faces back at us; edge grazes do not
    d = np.linalg.norm(loc - org[ray], axis=1)[opposite]
    d = d[d > 0.05]
    if len(d) < 20:
        return None
    return {"min": float(np.percentile(d, 1)), "f_fail": float((d < WALL_FAIL).mean()),
            "f_warn": float((d < WALL_WARN).mean()), "median": float(np.median(d))}


def layer_areas(m, layer=geom.LAYER):
    """Area of every slice at mid-layer height, like the slicer. Returns (areas, heights above the bed)."""
    z0, z1 = m.bounds[0][2], m.bounds[1][2]
    zs = np.arange(z0 + layer / 2, z1, layer)
    areas = []
    for z in zs:
        g = geom.section(m, 2, z)
        areas.append(g.area if g is not None else 0.0)
    return np.array(areas), zs - z0


def run(path, multi=False):
    m = geom.load(path)
    out, worst = [], 0
    rank = {"PASS": 0, "WARN": 1, "FAIL": 2}

    def add(level, text):
        nonlocal worst
        worst = max(worst, rank[level])
        out.append((level, text))

    ext = m.extents
    if m.is_watertight and m.is_winding_consistent and m.volume > 0:
        add("PASS", f"watertight, volume {m.volume / 1000:.1f} cm3")
    else:
        add("FAIL", "mesh has holes or flipped faces (not watertight); the slicer will guess or fail")
    nb = len(m.split(only_watertight=False))
    if nb == 1:
        add("PASS", "1 solid body")
    elif multi:
        add("PASS", f"{nb} separate bodies (allowed by --multi)")
    else:
        add("FAIL", f"{nb} separate bodies (touching solids never merged): union them in the scad, or use --multi")
    m = geom.drop_to_bed(m)
    w = thinnest_wall(m)
    # sharp wedges (chamfers, grooves) are always thin at the edge: judge by how much surface is thin, not the one worst point
    if w is None:
        add("WARN", "wall thickness could not be sampled")
    elif w["f_fail"] >= FRAC_FAIL:
        add("FAIL", f"{w['f_fail']:.0%} of the walls are under one nozzle width (0.4 mm, min ~{w['min']:.2f}): they will not print")
    elif w["f_warn"] >= FRAC_WARN:
        add("WARN", f"{w['f_warn']:.0%} of the walls are under two lines (0.8 mm, min ~{w['min']:.2f}): weak single-line walls")
    else:
        add("PASS", f"walls ok (typical {w['median']:.1f} mm, thinnest ~{w['min']:.1f} at sharp edges)")
    areas, zs = layer_areas(m)
    nz = np.nonzero(areas > 0)[0]
    if len(nz) == 0:
        add("FAIL", "model has no cross-section")
    else:
        rng = range(nz[0], nz[-1] + 1)
        empty = [i for i in rng if areas[i] == 0]
        tiny = [i for i in rng if 0 < areas[i] < max(0.5, 0.01 * areas.max())]
        if empty:
            add("FAIL", f"{len(empty)} empty layer(s) between {zs[empty[0]] - 0.1:.1f} and {zs[empty[-1]] + 0.1:.1f} mm: "
                        "the model is split in Z (slicer: \"empty layer\")")
        elif tiny:
            add("WARN", f"{len(tiny)} near-empty layer(s) near z={zs[tiny[0]]:.1f} mm: a feature thinner than a layer or nozzle")
        else:
            add("PASS", f"{len(areas)} layers, none empty")
    oh = geom.overhang_area(m, OVERHANG_DEG)
    if oh < 10:
        add("PASS", f"no real overhang over {OVERHANG_DEG} deg ({oh:.0f} mm2): no supports needed as oriented")
    else:
        add("WARN", f"overhang over {OVERHANG_DEG} deg: {oh:.0f} mm2, supports needed as oriented (try p3d orient)")
    contact = geom.bed_contact(m)
    foot = geom.section(m, 2, 0.1)
    h, small = ext[2], max(min(ext[0], ext[1]), 0.1)
    outside = False
    if foot is not None:
        from shapely.geometry import Point
        outside = not foot.convex_hull.contains(Point(m.center_mass[0], m.center_mass[1]))
    if outside or h / small > TALL_RATIO or contact < 20:
        why = ("centre of mass is outside the footprint" if outside else
               f"{h:.0f} mm tall on {small:.0f} mm" if h / small > TALL_RATIO else "tiny bed contact")
        add("WARN", f"bed contact {contact:.0f} mm2, tip-over risk ({why}): add a brim (--brim)")
    else:
        add("PASS", f"bed contact {contact:.0f} mm2, stable")
    bed = geom.bed()
    over = [f"{n} {e:.0f}>{b:.0f}" for n, e, b in zip("XYZ", ext, bed, strict=False) if e > b]
    if over:
        add("FAIL", f"does not fit the {bed[0]:.0f}x{bed[1]:.0f}x{bed[2]:.0f} bed: " + ", ".join(over))
    else:
        add("PASS", f"fits the bed ({ext[0]:.0f} x {ext[1]:.0f} x {ext[2]:.0f} mm)")
    return {"lines": out, "worst": ["PASS", "WARN", "FAIL"][worst], "bodies": nb}
