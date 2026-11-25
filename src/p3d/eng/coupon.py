"""Cut the critical slice out of a model (a snap, a thread, a clip) so a fit test prints in minutes."""
import pathlib

import numpy as np
import trimesh

from . import geom


def parse_box(box):
    v = [float(t) for t in (box.split(",") if isinstance(box, str) else box)]
    if len(v) != 6:
        raise ValueError("--box needs x0,y0,z0,x1,y1,z1")
    return v


def cut(path, z=None, box=None, out=None):
    """Intersect the model with a Z slab (z='A..B') or a box. Writes OUT (default NAME_coupon.stl, dropped to the bed)."""
    import manifold3d as mf
    m = geom.load(path)
    if box:
        x0, y0, z0, x1, y1, z1 = parse_box(box)
    elif z:
        a, b = [float(t) for t in str(z).split("..")]
        (x0, y0), (x1, y1) = m.bounds[0][:2] - 1, m.bounds[1][:2] + 1
        z0, z1 = min(a, b), max(a, b)
    else:
        raise ValueError("give --z A..B or --box x0,y0,z0,x1,y1,z1")
    man = mf.Manifold(mf.Mesh(vert_properties=np.array(m.vertices, np.float32), tri_verts=np.array(m.faces, np.uint32)))
    if man.status() != mf.Error.NoError:
        raise ValueError(f"model is not a clean manifold ({man.status().name}); run p3d check first")
    cube = mf.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])
    res = (man ^ cube).to_mesh()
    if len(res.tri_verts) == 0:
        raise ValueError("the cut region is empty (outside the model)")
    c = trimesh.Trimesh(res.vert_properties[:, :3], res.tri_verts)
    c.apply_translation([0, 0, -c.bounds[0][2]])
    out = pathlib.Path(out) if out else pathlib.Path(path).with_name(pathlib.Path(path).stem + "_coupon.stl")
    c.export(str(out))
    return {"out": str(out), "size": [round(float(e), 1) for e in c.extents], "volume_cm3": round(float(c.volume) / 1000, 2),
            "full_volume_cm3": round(float(m.volume) / 1000, 2)}
