"""Mesh helpers shared by the eng tools. Needs trimesh + shapely (the cad venv)."""
import numpy as np
import trimesh
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union



def bed():
    """Build volume (x, y, z) mm of the configured printer (config printer_model / bed_size)."""
    from p3d import config
    return tuple(float(v) for v in config.get().bed)


def __getattr__(name):  # geom.BED stays readable
    if name == "BED":
        return bed()
    raise AttributeError(name)


NOZZLE, LAYER = 0.4, 0.2


def load(path):
    """Load an STL as ONE trimesh (vertices merged, so touching facets of separate solids stay separate bodies)."""
    m = trimesh.load(str(path), force="mesh")
    m.merge_vertices()
    return m


def drop_to_bed(m):
    m = m.copy()
    m.apply_translation([0, 0, -m.bounds[0][2]])
    return m


def section(m, axis, value):
    """Cross-section at coordinate `value` on axis 0/1/2 -> shapely geometry in the other two axes (in order)."""
    n = np.zeros(3)
    n[axis] = 1
    o = np.zeros(3)
    o[axis] = value
    segs = trimesh.intersections.mesh_plane(m, n, o)
    if segs is None or len(segs) == 0:
        return None
    keep = [i for i in range(3) if i != axis]
    s2 = np.round(segs[:, :, keep], 6)
    lines = [LineString(s) for s in s2 if (s[0] != s[1]).any()]
    if not lines:
        return None
    polys = sorted(polygonize(unary_union(lines)), key=lambda p: -p.area)
    if not polys:
        return None
    g = polys[0]
    for p in polys[1:]:        # even-odd: nested rings are holes
        g = g.symmetric_difference(p)
    return g


def moments(g):
    """Area, centroid, Ixx, Iyy, Ixy about the centroid (Green's theorem on every ring; holes subtract)."""
    A = Sx = Sy = Ixx = Iyy = Ixy = 0.0
    for poly in getattr(g, "geoms", [g]):
        for ring, sg in [(poly.exterior, 1)] + [(r, -1) for r in poly.interiors]:
            c = np.array(ring.coords)
            x, y, x1, y1 = c[:-1, 0], c[:-1, 1], c[1:, 0], c[1:, 1]
            cr = x * y1 - x1 * y
            if cr.sum() < 0:                       # make the ring counter-clockwise
                cr = -cr
            A += sg * cr.sum() / 2
            Sx += sg * ((x + x1) * cr).sum() / 6
            Sy += sg * ((y + y1) * cr).sum() / 6
            Ixx += sg * ((y * y + y * y1 + y1 * y1) * cr).sum() / 12
            Iyy += sg * ((x * x + x * x1 + x1 * x1) * cr).sum() / 12
            Ixy += sg * ((x * y1 + 2 * x * y + 2 * x1 * y1 + x1 * y) * cr).sum() / 24
    cx, cy = Sx / A, Sy / A
    return A, (cx, cy), Ixx - A * cy * cy, Iyy - A * cx * cx, Ixy - A * cx * cy


def overhang_area(m, deg=50.0, tol=0.05):
    """Area (mm2) of faces leaning out more than `deg` from vertical, excluding faces sitting on the bed."""
    nz = m.face_normals[:, 2]
    zmin = m.bounds[0][2]
    on_bed = m.triangles[:, :, 2].max(axis=1) < zmin + tol
    bad = (nz < -np.sin(np.radians(deg))) & ~on_bed
    return float(m.area_faces[bad].sum())


def bed_contact(m, tol=0.05):
    zmin = m.bounds[0][2]
    flat = (m.face_normals[:, 2] < -0.99) & (m.triangles[:, :, 2].max(axis=1) < zmin + tol)
    return float(m.area_faces[flat].sum())
