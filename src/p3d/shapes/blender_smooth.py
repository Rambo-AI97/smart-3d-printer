"""Organic smoothing in headless Blender: STL in, watertight smoother STL out.

    blender -b --python src/p3d/shapes/blender_smooth.py -- IN.stl OUT.stl [options]

Pipeline (each step optional): voxel remesh (welds + makes it watertight) -> corrective smooth (relaxes
faceting without shrinking much) -> subdivision surface -> bevel (edges sharper than --bevel-angle) ->
solidify (turn a surface into a shell of --solidify mm). Then exports binary STL and prints one JSON line
with triangle count, the non-manifold edge count (0 = watertight) and the bounding box.

Options (mm; defaults suit a 30-80 mm part on a 0.4 nozzle):
  --voxel 0.25        voxel size of the remesh; 0 skips it. Smaller = finer detail, more triangles.
  --smooth 10         corrective-smooth iterations (0 skips). factor 0.6
  --subsurf 0         subdivision levels, Catmull-Clark on the remeshed mesh (0 skips; 1 is plenty)
  --bevel 0           bevel width mm on sharp edges (0 skips); --bevel-angle 40 (deg)
  --solidify 0        shell thickness mm (0 skips); offset -1 keeps the outside surface in place
  --scale 1.0         uniform scale applied last
Printing: voxel < 0.2 mm is wasted on a 0.4 mm nozzle; smoothing shaves ~voxel/2 off thin features, so
keep walls >= 4 x voxel. Check the result with `p3d sheet OUT.stl` before slicing.
"""
import json
import math
import sys

import bpy
import bmesh


def parse(argv):
    a = {"voxel": 0.25, "smooth": 10, "subsurf": 0, "bevel": 0.0, "bevel_angle": 40.0, "solidify": 0.0, "scale": 1.0}
    pos, i = [], 0
    while i < len(argv):
        if argv[i].startswith("--"):
            k = argv[i][2:].replace("-", "_")
            a[k] = type(a[k])(float(argv[i + 1]))
            i += 2
        else:
            pos.append(argv[i])
            i += 1
    return pos, a


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    pos, o = parse(argv)
    src, dst = pos
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.stl_import(filepath=src)
    ob = bpy.context.selected_objects[0]
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_smooth()

    def add(kind, **kw):
        m = ob.modifiers.new(kind.title(), kind)
        for k, v in kw.items():
            setattr(m, k, v)
        bpy.ops.object.modifier_apply(modifier=m.name)

    if o["voxel"] > 0:
        add("REMESH", mode="VOXEL", voxel_size=o["voxel"], adaptivity=0.0)
    if o["smooth"] > 0:
        add("CORRECTIVE_SMOOTH", factor=0.6, iterations=int(o["smooth"]), smooth_type="SIMPLE", rest_source="BIND")
    if o["subsurf"] > 0:
        add("SUBSURF", levels=int(o["subsurf"]), render_levels=int(o["subsurf"]), subdivision_type="CATMULL_CLARK")
    if o["bevel"] > 0:
        add("BEVEL", width=o["bevel"], segments=2, limit_method="ANGLE", angle_limit=math.radians(o["bevel_angle"]))
    if o["solidify"] > 0:
        add("SOLIDIFY", thickness=o["solidify"], offset=-1, use_even_offset=True)
    if o["scale"] != 1.0:
        ob.scale = (o["scale"],) * 3
        bpy.ops.object.transform_apply(scale=True)

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bad = sum(1 for e in bm.edges if not e.is_manifold)
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    bm.free()
    bpy.ops.wm.stl_export(filepath=dst, export_selected_objects=True, ascii_format=False)
    bb = [list(map(lambda v: round(v, 2), c)) for c in (ob.dimensions,)]
    print("RESULT " + json.dumps({"out": dst, "triangles": tris, "nonmanifold_edges": bad, "size_mm": bb[0]}))


main()
