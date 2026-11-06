"""Blender (headless): any game/art model -> one solid, printable STL + preview PNG.
Thickens thin parts (sails, ropes, one-sided hulls), voxel-remeshes to a watertight solid,
optionally cuts a flat base, scales the longest side to --length mm, sits it on z=0.
All sizes are relative to the model, so it works for any model in any units.
Run: blender -b -P to_stl.py -- IN OUT.stl [--length 85] [--thicken 0.012] [--voxel 0.004]
     [--flat 0.04] [--png OUT.png]          (p3d model does this)
"""
import argparse, sys
import bpy
from mathutils import Vector

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("out")
ap.add_argument("--length", type=float, default=85, help="longest side, mm")
ap.add_argument("--thicken", type=float, default=0.012, help="shell thickness, fraction of length")
ap.add_argument("--voxel", type=float, default=0.004, help="remesh voxel, fraction of length")
ap.add_argument("--flat", type=float, default=0.0, help="cut this fraction of the height off the bottom")
ap.add_argument("--png", default="")
a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])

bpy.ops.wm.read_factory_settings(use_empty=True)
ext = a.src.lower().rsplit(".", 1)[-1]
if ext in ("glb", "gltf"): bpy.ops.import_scene.gltf(filepath=a.src)
elif ext == "obj": bpy.ops.wm.obj_import(filepath=a.src)
elif ext == "fbx": bpy.ops.import_scene.fbx(filepath=a.src)
elif ext == "stl": bpy.ops.wm.stl_import(filepath=a.src)
else: sys.exit(f"unsupported: {ext}")

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
for o in bpy.data.objects: o.select_set(o.type == "MESH")
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
if len(meshes) > 1: bpy.ops.object.join()
ob = bpy.context.active_object
for o in [o for o in bpy.data.objects if o.type != "MESH"]: bpy.data.objects.remove(o)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
L = max(ob.dimensions)

def apply(mod):
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=mod.name)

m = ob.modifiers.new("s", "SOLIDIFY"); m.thickness = a.thicken * L; m.offset = 0; apply(m)
r = ob.modifiers.new("r", "REMESH"); r.mode = "VOXEL"; r.voxel_size = a.voxel * L; apply(r)

if a.flat > 0:
    zs = [v.co.z for v in ob.data.vertices]
    cut = min(zs) + a.flat * (max(zs) - min(zs))
    bpy.ops.mesh.primitive_cube_add(size=L * 4, location=(0, 0, cut - L * 2))
    cube = bpy.context.active_object
    b = ob.modifiers.new("b", "BOOLEAN"); b.operation = "DIFFERENCE"; b.object = cube; b.solver = "EXACT"
    apply(b); bpy.data.objects.remove(cube)

s = a.length / max(ob.dimensions)
ob.scale = (s, s, s); bpy.ops.object.transform_apply(scale=True)
bb = [Vector(c) for c in ob.bound_box]
ob.location -= Vector(((min(v.x for v in bb) + max(v.x for v in bb)) / 2,
                       (min(v.y for v in bb) + max(v.y for v in bb)) / 2, min(v.z for v in bb)))
bpy.ops.object.transform_apply(location=True)
d = ob.dimensions
print(f"SIZE_MM {d.x:.1f} x {d.y:.1f} x {d.z:.1f}  tris {len(ob.data.polygons)}")
bpy.ops.wm.stl_export(filepath=a.out)

if a.png:
    sc = bpy.context.scene; sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x, sc.render.resolution_y = 900, 700
    sc.display.shading.light = "STUDIO"; sc.display.shading.color_type = "SINGLE"
    sc.display.shading.single_color = (0.9, 0.9, 0.88)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    ctr = Vector((0, 0, d.z / 2)); k = max(d) * 1.5
    cam.location = ctr + Vector((k, -k, k * 0.55))
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = a.png; bpy.ops.render.render(write_still=True)
    print("PREVIEW", a.png)
