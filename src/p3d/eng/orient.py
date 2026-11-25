"""Pick the best print orientation: try every stable face (convex-hull facets), score, write the winner."""
import pathlib

import numpy as np
import trimesh

from . import geom

# score weights (sum 1); strength drops out and the rest renormalise when no load direction is given
W = {"support": 0.35, "bed": 0.25, "height": 0.15, "strength": 0.25}


def score(m, load_dir=None):
    """m is already dropped to the bed. Returns raw metrics and the 0..1 score."""
    ext = m.extents
    oh = geom.overhang_area(m)
    contact = geom.bed_contact(m)
    s = {"support": 1 / (1 + oh / 50.0),
         "bed": min(1.0, contact / 100.0) * (0.5 if _tips(m) else 1.0),
         "height": 1 / (1 + ext[2] / 50.0)}
    if load_dir is not None:
        d = np.asarray(load_dir, float)
        s["strength"] = 1 - abs(d[2] / np.linalg.norm(d))      # load along Z pulls layers apart
    w = {k: W[k] for k in s}
    tot = sum(w.values())
    total = sum(s[k] * w[k] for k in s) / tot
    return {"score": round(float(total), 3), "support_mm2": round(oh), "contact_mm2": round(contact),
            "height_mm": round(float(ext[2]), 1), "strength": round(s.get("strength", -1), 2)}


def _tips(m):
    ext = m.extents
    return ext[2] / max(min(ext[0], ext[1]), 0.1) > 3.0


def run(path, load_dir=None, top=12, out=None):
    m = geom.load(path)
    hull = m.convex_hull
    facets = sorted(range(len(hull.facets)), key=lambda i: -hull.facets_area[i])[:top]
    cands = [("as modelled", np.eye(4))]
    for i in facets:
        n = hull.facets_normal[i]
        if n[2] < -0.999:
            continue                      # already the current orientation
        cands.append((f"face {np.round(n, 2).tolist()} down", trimesh.geometry.align_vectors(n, [0, 0, -1])))
    ld = None if load_dir is None else np.asarray(load_dir if not isinstance(load_dir, str) else
                                                   [float(t) for t in load_dir.split(",")], float)
    rows = []
    for name, T in cands:
        r = geom.drop_to_bed(m.copy().apply_transform(T))
        sc = score(r, None if ld is None else T[:3, :3] @ ld)
        rows.append({"name": name, **sc, "T": T.tolist()})
    rows.sort(key=lambda r: -r["score"])
    best = rows[0]
    out = pathlib.Path(out) if out else pathlib.Path(path).with_name(pathlib.Path(path).stem + "_oriented.stl")
    geom.drop_to_bed(m.copy().apply_transform(np.array(best["T"]))).export(str(out))
    current = next(r for r in rows if r["name"] == "as modelled")
    for r in rows:
        r.pop("T")
    return {"top": rows[:3], "current": current, "out": str(out), "changed": best["name"] != "as modelled"}
