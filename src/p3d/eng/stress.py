"""Beam / section strength estimate for hooks, clamps, brackets. Linear-elastic, static, first-order: a screening
number to decide "will it hold", not FEA. Stress is computed on cross-sections cut from the real mesh.

  section mode:  run(model, load_kg, section_at=Z, arm=30)           one section, force F at lever arm `arm` mm
  region mode:   run(model, load_kg, fix_face="-z", load_at=[x,y,z]) sweep sections from the fixed face to the load point
"""
import numpy as np

from . import geom

G = 9.81
# conservative printed strengths, MPa: (across layer lines, along the layers)
STRENGTH = {"petg": (20.0, 45.0), "pla": (25.0, 50.0), "tpu": (8.0, 20.0)}
SF_OK, SF_WARN = 2.0, 1.2       # static prints creep and fatigue: want 2+
AXES = {"x": 0, "y": 1, "z": 2}


def parse_dir(d):
    """'x', '-z', or 'x,y,z' -> unit vector. Default straight down (gravity)."""
    if d is None:
        return np.array([0, 0, -1.0])
    if isinstance(d, str) and d.strip().lstrip("+-").lower() in AXES:
        v = np.zeros(3)
        v[AXES[d.strip().lstrip("+-").lower()]] = -1.0 if d.strip().startswith("-") else 1.0
        return v
    v = np.array([float(t) for t in (d.split(",") if isinstance(d, str) else d)])
    return v / np.linalg.norm(v)


def frame(axis, sign=1):
    """(p, q) in-plane axis indices so that p x q = sign * axis (right-handed with the beam axis)."""
    p, q = {0: (1, 2), 1: (2, 0), 2: (0, 1)}[axis]
    return (p, q) if sign > 0 else (q, p)


def section_pq(m, axis, value, p, q):
    """Section geometry with coordinates (p, q) in that order, plus its 3D centroid."""
    g = geom.section(m, axis, value)
    if g is None:
        return None
    keep = [i for i in range(3) if i != axis]
    if keep != [p, q]:
        from shapely import affinity
        g = affinity.affine_transform(g, [0, 1, 1, 0, 0, 0])      # swap the two coordinates
    return g


def section_stress(g, N, M_p, M_q, V):
    """Max |stress| on a section with axial force N (+tension), moments about p/q, shear V. -> dict, MPa and mm."""
    A, (cx, cy), Ipp, Iqq, Ipq = geom.moments(g)       # Ipp = integral of p^2 (named as the geom docs: Ixx=y^2)
    # geom.moments returns Ixx = int y^2, Iyy = int x^2; with (x, y) = (p, q) that is Iqq_, Ipp_ -> swap names
    Ipp, Iqq = Iqq, Ipp
    det = Ipp * Iqq - Ipq ** 2
    a = (-M_q * Iqq - M_p * Ipq) / det                 # solves [Ipp Ipq; Ipq Iqq][a b] = [-M_q, M_p]
    b = (M_p * Ipp + M_q * Ipq) / det
    pts = np.vstack([np.array(r.coords) for poly in getattr(g, "geoms", [g]) for r in [poly.exterior]])
    P, Q = pts[:, 0] - cx, pts[:, 1] - cy
    sig = N / A + a * P + b * Q
    bend = np.abs(a * P + b * Q).max()
    return {"sigma": float(np.abs(sig).max()), "bend": float(bend), "axial": float(abs(N) / A),
            "tau": float(1.5 * V / A), "area": float(A), "Ipp": float(Ipp), "Iqq": float(Iqq)}


def verdict(res, material, across_layers):
    weak, strong = STRENGTH[material]
    allow = weak if across_layers else strong
    sf = allow / max(res["sigma"], 1e-9)
    sf_shear = 0.6 * allow / max(res["tau"], 1e-9)
    sf = min(sf, sf_shear)
    lvl = "PASS" if sf >= SF_OK else "WARN" if sf >= SF_WARN else "FAIL"
    return lvl, sf, allow


def section_mode(m, load_kg, section_at, arm, axis="z", direction=None, material="petg"):
    ax = AXES[axis]
    F = load_kg * G
    p, q = frame(ax)
    g = section_pq(m, ax, section_at, p, q)
    if g is None:
        raise ValueError(f"no cross-section at {axis}={section_at} (model spans {m.bounds[0][ax]:.1f}..{m.bounds[1][ax]:.1f})")
    d = parse_dir(direction) if direction else None
    dirs = [d] if d is not None else [np.eye(3)[p], np.eye(3)[q]]
    best = None
    for dv in dirs:
        a_axial = dv[ax]
        lat = dv.copy()
        lat[ax] = 0
        nl = np.linalg.norm(lat)
        N = F * a_axial
        # lateral force acts at lever `arm` along the beam axis from this section
        Fl = F * nl
        u = lat / nl if nl > 1e-9 else np.zeros(3)
        # moment about p and q from the lateral force at distance arm (beam load point is +arm along the axis)
        r = np.zeros(3)
        r[ax] = arm
        M = np.cross(r, F * u)
        res = section_stress(g, N, M[p], M[q], Fl)
        if best is None or res["sigma"] > best[0]["sigma"]:
            best = (res, dv)
    res, dv = best
    across = ax == 2                  # stress runs along the beam axis; Z beams are loaded across the layer lines
    lvl, sf, allow = verdict(res, material, across)
    lines = [(lvl, f"{axis}={section_at:g}: stress {res['sigma']:.1f} MPa (bending {res['bend']:.1f}, axial {res['axial']:.1f}), "
                   f"shear {res['tau']:.1f}; allowed {allow:.0f} ({material}) -> safety factor {sf:.1f}")]
    lines.append(layer_note(ax, across, dv))
    return {"lines": lines, "sf": sf, "sigma": res["sigma"], "worst": lvl}


def layer_note(ax, across, dv):
    if across:
        return ("WARN", "beam axis is Z: bending/tension crosses the layer lines (weak, ~20 MPa PETG); "
                        "reorient so layers run along the beam (p3d orient --load-dir)")
    return ("PASS", "layer lines run along the beam (strong direction); keep the bending plane across the layer stack")


def region_mode(m, load_kg, fix_face, load_at, direction=None, material="petg", n=14):
    F = load_kg * G * parse_dir(direction)
    fx = fix_face.strip().lower()
    sign_fix = -1 if fx.startswith("-") else 1                 # "-z" = the face on the low-z side
    ax = AXES[fx.lstrip("+-")]
    a_sign = 1 if sign_fix < 0 else -1                         # beam axis points from the fixed face to the load
    lo, hi = m.bounds[0][ax], m.bounds[1][ax]
    start = lo if sign_fix < 0 else hi
    L = np.asarray(load_at, float)
    end = L[ax]
    p, q = frame(ax, a_sign)
    avec = np.zeros(3)
    avec[ax] = a_sign
    N = float(F @ avec)
    worst = None
    for s in np.linspace(start + a_sign * 0.3, end, n, endpoint=False):
        g = section_pq(m, ax, s, p, q)
        if g is None:
            continue
        A, (cp, cq), *_ = geom.moments(g)
        c3 = np.zeros(3)
        c3[ax], c3[p], c3[q] = s, cp, cq
        M = np.cross(L - c3, F)
        V = float(np.linalg.norm(F - N * avec))
        res = section_stress(g, N, M[p], M[q], V)
        res["at"] = float(s)
        if worst is None or res["sigma"] > worst["sigma"]:
            worst = res
    if worst is None:
        raise ValueError("no sections between the fixed face and the load point")
    across = ax == 2
    lvl, sf, allow = verdict(worst, material, across)
    name = "xyz"[ax]
    lines = [(lvl, f"worst section {name}={worst['at']:.1f}: stress {worst['sigma']:.1f} MPa (bending {worst['bend']:.1f}, axial {worst['axial']:.1f}), "
                   f"shear {worst['tau']:.1f}; allowed {allow:.0f} ({material}) -> safety factor {sf:.1f}"),
             layer_note(ax, across, None)]
    return {"lines": lines, "sf": sf, "sigma": worst["sigma"], "worst": lvl}


def run(path, load_kg, material="petg", section_at=None, arm=None, axis="z", direction=None, fix_face=None, load_at=None):
    m = geom.load(path)
    if section_at is not None:
        if arm is None:
            raise ValueError("--section-at needs --arm (lever arm in mm)")
        return section_mode(m, load_kg, section_at, arm, axis, direction, material)
    if fix_face and load_at is not None:
        return region_mode(m, load_kg, fix_face, load_at, direction, material)
    raise ValueError("give --section-at Z --arm MM, or --fix-face -z --load-at x,y,z")
